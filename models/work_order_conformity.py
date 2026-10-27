# -*- coding: utf-8 -*-
import base64
import re
import uuid
from io import BytesIO

import qrcode

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MaintenanceStage(models.Model):
    _inherit = "maintenance.stage"

    pmant_code = fields.Selection([
        ("new", "Nueva solicitud"),
        ("in_progress", "En progreso"),
        ("review", "Revisión"),
        ("billing_hes", "Por facturar - HES"),
        ("done", "Finalizado"),
        ("unassigned", "Sin referencia / Sin responsable"),
    ], string="Etapa PMANT", copy=False, index=True)

    @api.model
    def pmant_setup_work_order_stages(self):
        definitions = (
            ("new", "Nueva solicitud", 10, False),
            ("in_progress", "En progreso", 20, False),
            ("review", "Revisión", 30, False),
            ("billing_hes", "Por facturar - HES", 40, False),
            ("done", "Finalizado", 50, True),
            ("unassigned", "Sin referencia / Sin responsable", 60, False),
        )
        aliases = {
            "new": ("nueva solicitud", "new request", "nuevo"),
            "in_progress": ("en progreso", "in progress"),
            "review": ("revision", "revisión"),
            "billing_hes": ("por facturar - hes", "por facturar", "facturacion"),
            "done": ("finalizado", "done"),
            "unassigned": ("sin referencia / sin responsable", "sin referencia", "sin responsable"),
        }
        claimed = self.browse()
        stages_by_code = {}
        for code, name, sequence, done in definitions:
            stage = self.search([("pmant_code", "=", code)], limit=1)
            if not stage:
                for candidate in self.search([("id", "not in", claimed.ids)]):
                    normalized = re.sub(r"\s+", " ", (candidate.name or "").strip().lower())
                    if normalized in aliases[code]:
                        stage = candidate
                        break
            values = {"name": name, "sequence": sequence, "done": done, "pmant_code": code}
            if stage:
                stage.write(values)
            else:
                stage = self.create(values)
            claimed |= stage
            stages_by_code[code] = stage

        # Consolidar columnas heredadas de versiones anteriores. Primero se
        # conservan sus órdenes trasladándolas a la etapa oficial equivalente;
        # solamente después se elimina la columna obsoleta del kanban.
        legacy_stage_map = {
            "reparado": "done",
            "repaired": "done",
            "desechar": "done",
            "descartar": "done",
            "scrap": "done",
        }
        for legacy in self.search([("id", "not in", claimed.ids)]):
            normalized = re.sub(r"\s+", " ", (legacy.name or "").strip().lower())
            target = stages_by_code.get(legacy_stage_map.get(normalized))
            if not target:
                continue
            orders = self.env["maintenance.request"].sudo().search([("stage_id", "=", legacy.id)])
            if orders:
                orders.with_context(pmant_stage_migration=True).write({"stage_id": target.id})
            legacy.unlink()
        return True


class PmantConformityImage(models.Model):
    _name = "pmant.conformity.image"
    _description = "Fotografía del acta de conformidad"
    _order = "id"

    work_order_id = fields.Many2one(
        "maintenance.request", string="Orden de trabajo", required=True,
        ondelete="cascade", index=True,
    )
    name = fields.Char(string="Archivo", required=True)
    image = fields.Binary(string="Fotografía", required=True, attachment=True)
    mimetype = fields.Char(string="Tipo MIME")


class MaintenanceRequestConformity(models.Model):
    _inherit = "maintenance.request"

    conformity_token = fields.Char(string="Token del acta", copy=False, readonly=True, index=True)
    conformity_url = fields.Char(string="URL del acta", compute="_compute_conformity_access")
    conformity_qr = fields.Binary(string="QR del acta", compute="_compute_conformity_access", attachment=True)
    conformity_state = fields.Selection([
        ("pending", "Pendiente"),
        ("received", "Recibida"),
        ("pdf", "PDF generado"),
    ], string="Estado del acta", default="pending", required=True, copy=False, readonly=True)
    conformity_name = fields.Char(string="Persona que otorga la conformidad", copy=False, readonly=True)
    conformity_document = fields.Char(string="Documento", copy=False, readonly=True)
    conformity_notes = fields.Text(string="Observaciones", copy=False, readonly=True)
    conformity_received_at = fields.Datetime(string="Fecha de recepción", copy=False, readonly=True)
    conformity_image_ids = fields.One2many(
        "pmant.conformity.image", "work_order_id", string="Fotografías", copy=False, readonly=True,
    )
    conformity_pdf_attachment_id = fields.Many2one(
        "ir.attachment", string="Acta de conformidad PDF", copy=False, readonly=True,
        ondelete="set null",
    )
    billing_notified = fields.Boolean(string="Facturación notificada", copy=False, readonly=True)
    conformity_planner_notified = fields.Boolean(string="Planner notificado", copy=False, readonly=True)

    @api.model
    def _default_stage(self):
        return self.env["maintenance.stage"].search(
            [("pmant_code", "=", "new")], limit=1
        ) or super()._default_stage()

    stage_id = fields.Many2one(default=_default_stage)

    @api.depends("conformity_token")
    def _compute_conformity_access(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        for order in self:
            if not order.conformity_token:
                order.conformity_url = False
                order.conformity_qr = False
                continue
            url = "%s/pmant/acta/%s" % (base_url.rstrip("/"), order.conformity_token)
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
            qr.add_data(url)
            qr.make(fit=True)
            stream = BytesIO()
            qr.make_image().save(stream, format="PNG")
            order.conformity_url = url
            order.conformity_qr = base64.b64encode(stream.getvalue())

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values.setdefault("conformity_token", uuid.uuid4().hex)
        return super().create(vals_list)

    def action_regenerate_conformity_token(self):
        self.ensure_one()
        if self.conformity_state != "pending":
            raise UserError(_("No puede cambiar el enlace después de recibir el acta."))
        self.conformity_token = uuid.uuid4().hex
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_conformity_portal(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": self.conformity_url, "target": "new"}

    def action_download_conformity_pdf(self):
        self.ensure_one()
        if not self.conformity_pdf_attachment_id:
            raise UserError(_("Todavía no existe un acta de conformidad en PDF."))
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % self.conformity_pdf_attachment_id.id,
            "target": "self",
        }

    def _generate_conformity_pdf(self):
        self.ensure_one()
        report = self.env.ref("pmant.action_reporte_acta").sudo()
        pdf, _ = self.env["ir.actions.report"].sudo()._render_qweb_pdf(report, res_ids=self.ids)
        if self.conformity_pdf_attachment_id:
            self.conformity_pdf_attachment_id.sudo().unlink()
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "Acta de Conformidad - %s.pdf" % self.name,
            "type": "binary",
            "raw": pdf,
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
        })
        self.sudo().write({
            "conformity_pdf_attachment_id": attachment.id,
            "conformity_state": "pdf",
            "fecha_acta": fields.Date.context_today(self),
        })
        self.message_post(
            body=_("Acta de conformidad recibida desde el portal y convertida a PDF."),
            attachment_ids=[attachment.id],
        )
        self._notify_conformity_planner()
        return attachment

    def _receive_conformity_pdf(self, filename, content):
        """Guarda sin transformar el acta PDF cargada desde el portal público."""
        self.ensure_one()
        if self.conformity_pdf_attachment_id:
            self.conformity_pdf_attachment_id.sudo().unlink()
        safe_name = (filename or "Acta de conformidad.pdf").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        attachment = self.env["ir.attachment"].sudo().create({
            "name": safe_name,
            "type": "binary",
            "raw": content,
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
        })
        self.sudo().write({
            "conformity_pdf_attachment_id": attachment.id,
            "conformity_received_at": fields.Datetime.now(),
            "conformity_state": "pdf",
            "fecha_acta": fields.Date.context_today(self),
        })
        self.message_post(
            body=_("Acta de conformidad PDF recibida desde el portal."),
            attachment_ids=[attachment.id],
        )
        self._notify_conformity_planner()
        return attachment

    def _notify_conformity_planner(self):
        self.ensure_one()
        planner = self.create_uid if self.create_uid and not self.create_uid.share else False
        recipients = planner or self.env["pmant.notification"].pmant_planner_users()
        self.env["pmant.notification"].notify_users(
            recipients,
            _("Acta de conformidad lista"),
            _("El acta de %(order)s fue cargada y ya puede revisar la finalización.", order=self.display_name),
            notification_type="success", sticky=True, record=self,
        )
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if planner and activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=planner.id,
                summary=_("Revisar acta de conformidad"),
                note=_("El cliente cargó el acta de conformidad en PDF. Revísela antes de finalizar la OT."),
            )
        self.sudo().conformity_planner_notified = True

    def _notify_billing_users(self):
        group = self.env.ref("pmant.group_pmant_user_notifi_fac", raise_if_not_found=False)
        users = group.user_ids if group else self.env["res.users"]
        for order in self.filtered(lambda item: not item.billing_notified):
            self.env["pmant.notification"].notify_users(
                users,
                _("OT lista para facturar - HES"),
                _("La orden %(order)s pasó a Por facturar - HES.", order=order.display_name),
                notification_type="warning", sticky=True, record=order,
            )
            order.message_post(body=_("Se notificó al equipo de facturación/HES."))
            order.sudo().billing_notified = True

    def write(self, vals):
        target_stage = self.env["maintenance.stage"].browse(vals.get("stage_id")) if vals.get("stage_id") else False
        if (
            target_stage
            and target_stage.pmant_code == "done"
            and not self.env.context.get("pmant_stage_migration")
        ):
            missing = self.filtered(lambda order: not order.conformity_pdf_attachment_id)
            if missing:
                raise UserError(_("Debe recibir y generar el Acta de conformidad antes de pasar la OT a Finalizado."))
        previous_stages = {order.id: order.stage_id for order in self}
        result = super().write(vals)
        if "stage_id" in vals:
            billing = self.filtered(
                lambda order: order.stage_id.pmant_code == "billing_hes"
                and previous_stages[order.id] != order.stage_id
            )
            billing._notify_billing_users()
        return result
