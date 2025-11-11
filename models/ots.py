# -*- coding: utf-8 -*-
"""
Optimized Odoo 19 model for maintenance.request (OTS)
- Compatible con Odoo 19 (api.model_create_multi, raise_if_not_found)
- Evita abrir ventanas UI en create/write para enviar correos; usa send_mail queued (force_send=False)
- Maneja múltiples registros correctamente
- Mejora de validaciones, logs y uso eficiente de search_count/mapped
"""
from datetime import datetime, timedelta, date
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)


class MaintenanceRequestOTS(models.Model):
    _inherit = 'maintenance.request'
    _name = 'maintenance.request'  # asegúrate de no duplicar este modelo

    # 👇 Agregamos herencia de mail.thread y mail.activity.mixin
    _inherit = ['maintenance.request', 'mail.thread', 'mail.activity.mixin']

    # --------------------
    # Campos
    # --------------------
    tarea = fields.Many2one("tarea.mantenimiento", string="Tarea", required=True)
    tex = fields.Char(string="Text")
    empresa = fields.Many2one("res.partner", related="tarea.cliente", store=True)
    ubicacion = fields.Many2one("res.partner", related="tarea.ubicacion", store=True)
    factura = fields.Many2one("account.move", string="Factura")
    factura_sunat = fields.Char(string="Factura Sunat")
    selec_sunat = fields.Boolean(string="Factura Sunat?")
    oportunidad = fields.Many2one("crm.lead", string="Oportunidad")
    partner_id = fields.Many2one("res.partner", related="tarea.cliente", store=True)
    fecha_ejec = fields.Date(string="Fecha Ejecutada")
    subodinados = fields.Many2many("res.users", string="Subordinados")
    is_evaluacion = fields.Boolean(string="Es una Evaluacion")
    is_tecnico = fields.Boolean(compute="_compute_is_tecnico", string="Is Técnico", store=False)
    tab_horas = fields.One2many("programacion.mantenimiento", "ot_id", string="Hoja de horas")
    is_active_programacion = fields.Boolean(string="La programacion fue eniada?")
    rating_p1 = fields.Integer(string="Calidad del servicio")
    rating_p2 = fields.Integer(string="Tiempo de respuesta")
    rating_p3 = fields.Integer(string="Probabilidad de recomendación")
    rating_comment = fields.Text(string="Comentarios del cliente")
    document_count = fields.Integer(string="Documentos firmados", compute="get_cantidad_documentos")
    cantidad_inconvenientes = fields.Integer(string="Incidencias", compute="_get_cantidad_incidencias")
    notas_venta = fields.Html(string="Notas Venta", sanitize_style=True, sanitize_tags=False)
    duration = fields.Float(
        string="Duración (H)", required=True, default=0.0, compute="_compute_horas_duracion", store=True
    )

    # --------------------
    # Computes
    # --------------------
    @api.depends("schedule_date", "schedule_end")
    def _compute_horas_duracion(self):
        for rec in self:
            if rec.schedule_date and rec.schedule_end:
                # schedule_date / schedule_end pueden ser datetime/date según implementación
                try:
                    delta = rec.schedule_end - rec.schedule_date
                    horas = (delta.total_seconds() if hasattr(delta, 'total_seconds') else delta.days * 24) / 3600.0
                    rec.duration = float_round(horas or 0.0, precision_digits=2)
                except Exception:
                    rec.duration = 0.0
            else:
                rec.duration = 0.0

    def get_cantidad_documentos(self):
        for rec in self:
            rec.document_count = self.env["sign.request"].search_count([
                ("state", "=", "signed"), ("ot_id", "=", rec.id)
            ])

    @api.depends_context("uid")
    def _compute_is_tecnico(self):
        for rec in self:
            rec.is_tecnico = self.env.user.has_group("pmant.group_pmant_tecnico")

    def _get_cantidad_incidencias(self):
        for rec in self:
            rec.cantidad_inconvenientes = self.env["inconveniente.servicio"].search_count([("ot_id", "=", rec.id)])

    # --------------------
    # Actions / UI
    # --------------------
    def action_view_documentos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Documentos Firmados",
            "res_model": "sign.request",
            "view_mode": "kanban,form",
            "target": "current",
            "domain": [("state", "=", "signed"), ("ot_id", "=", self.id)],
            "context": {"default_ot_id": self.id},
        }

    def action_open_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Enviar por WhatsApp",
            "res_model": "acrux.chat.message.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.empresa.id, "full_name": True},
        }

    def action_view_incidencias(self):
        if not self.ids:
            return {
                "type": "ir.actions.act_window_close",
            }
        cant_data = self.env["inconveniente.servicio"].search([("ot_id", "=", self.id)])
        return {
            "name": "Incidencias",
            "type": "ir.actions.act_window",
            "domain": [("id", "in", cant_data.ids)],
            "view_mode": "list,form",
            "res_model": "inconveniente.servicio",
            "context": {"create": False},
        }

    def action_view_ots(self):
        self.ensure_one()
        return {
            "name": "Solicitud de Mantenimiento",
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "view_mode": "form",
            "res_model": "maintenance.request",
            "context": {"create": False},
        }

    # --------------------
    # Create / Write overrides
    # --------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Evitar abrir UI: encolar envíos de correo en background si hay plantilla
        try:
            records.send_programacion_inicial()
            records.action_programacion_inicial()
        except Exception as e:
            _logger.exception("Error al crear/actualizar programación inicial para OTs: %s", e)
            # No lanzar excepción que rompa la creación; sólo reportar en chatter
            for rec in records:
                rec.message_post(body=_("Error al crear programación inicial: %s") % e)
        return records

    def write(self, vals):
        res = super().write(vals)
        # Si cambia la etapa, ejecutar lógica por registro

        if 'scheduled_end' in vals or 'duration' in vals:
            try:
                self.action_programacion_inicial()
            except Exception as e:
                _logger.exception("Error al actualizar programación inicial para OTs: %s", e)
                for rec in self:
                    rec.message_post(body=_("Error al actualizar programación inicial: %s") % e)
        if "stage_id" in vals:
            for rec in self:
                try:
                    if rec.stage_id and rec.stage_id.sequence == 3:
                        # Etapa en ejecución
                        planequipo = rec.tarea.planequipo if rec.tarea else None
                        if planequipo and not any(planequipo.mapped("is_informe_file")):
                            rec.fecha_ejec = fields.Date.today()
                            if rec.tarea:
                                rec.tarea._fecha_ejecutada()
                                rec.tarea._evento_calendario_proximo_servicio()
                        else:
                            if planequipo and not any(planequipo.mapped("informe_file")):
                                raise UserError(_("Debe subir el informe técnico antes de cambiar a esta etapa."))
                            else:
                                rec.fecha_ejec = planequipo[:1].fecha_ejec if planequipo else None
                                if rec.tarea:
                                    rec.tarea._evento_calendario_proximo_servicio()

                    if rec.stage_id and rec.stage_id.sequence == 4:
                        # Notificar grupos de facturacion
                        rec.notify_users_facturacion()

                except Exception as e:
                    _logger.exception("Error durante write() en maintenance.request id %s: %s", rec.id, e)
                    rec.message_post(body=_("Error durante actualización: %s") % e)
            # Validaciones y acciones dependientes
            try:
                self._change_createui()
            except Exception as e:
                _logger.exception("_change_createui error: %s", e)
        return res

    # --------------------
    # Lógica de programación y notificaciones
    # --------------------
    @api.depends("scheduled_end", "duration")
    def action_programacion_inicial(self):
        for rec in self:
            if not rec.schedule_date:
                raise UserError(_("Para crear una Orden de Trabajo debes colocar la fecha programada y una duración mayor a 0."))

            lista_user = []
            if rec.user_id:
                lista_user.append(rec.user_id.id)
            lista_user += rec.subodinados.ids if rec.subodinados else []

            valores = {
                "fecha_date": rec.schedule_date,
                "duracion": rec.duration,
                "ot_id": rec.id,
                "tecnicos": [(6, 0, lista_user)],
            }

            if not rec.tab_horas:
                try:
                    self.env["programacion.mantenimiento"].create(valores)
                except Exception as e:
                    _logger.exception("No se pudo crear programacion.mantenimiento para OT %s: %s", rec.id, e)
                    rec.message_post(body=_("Error al crear programación: %s") % e)
            else:
                try:
                    rec.tab_horas[0].write(valores)
                except Exception as e:
                    _logger.exception("No se pudo actualizar programacion.mantenimiento para OT %s: %s", rec.id, e)
                    rec.message_post(body=_("Error al actualizar programación: %s") % e)

    def notify_users_facturacion(self):
        group_xml_id = "pmant.group_pmant_user_notifi_fac"
        try:
            group = self.env.ref(group_xml_id, raise_if_not_found=False)
        except Exception:
            group = None
        if not group:
            _logger.debug("Grupo de notificación de facturación no encontrado: %s", group_xml_id)
            return
        for user in group.user_ids:
            for rec in self:
                rec.message_post(
                    body=f"{rec.name}: La tarea ha pasado a la etapa {rec.stage_id.name}, lista para facturar.",
                    partner_ids=[user.partner_id.id] if user.partner_id else [],
                )

    def send_reporte_final(self):
        """Enviar correos finales (servicio finalizado + calificación) y registrar en chatter."""
        for rec in self:
            # Buscar plantillas
            template_servicio = self.env.ref("pmant.email_template_servicio_finalizado", raise_if_not_found=False)
            template_calificacion = self.env.ref("pmant.email_template_calificacion_servicio", raise_if_not_found=False)

            # --- SERVICIO FINALIZADO ---
            if template_servicio:
                try:
                    # Renderizar asunto y cuerpo
                    subject = template_servicio._render_field("subject", [rec.id])[rec.id]
                    body_html = template_servicio._render_field("body_html", [rec.id])[rec.id]

                    # Enviar correo
                    mail_id = template_servicio.send_mail(rec.id, force_send=True)

                    # Registrar en chatter
                    rec.message_post(
                        body=body_html or _("Correo de finalización enviado."),
                        subject=subject or _("Correo de finalización"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

                    _logger.info("Correo de servicio finalizado enviado para OT %s (mail_id=%s)", rec.id, mail_id)

                except Exception as e:
                    _logger.exception("Error al enviar template_servicio para OT %s: %s", rec.id, e)
                    rec.message_post(body=_("❌ Error al enviar correo finalización: %s") % e)

            # --- CALIFICACIÓN ---
            if template_calificacion:
                try:
                    subject = template_calificacion._render_field("subject", [rec.id])[rec.id]
                    body_html = template_calificacion._render_field("body_html", [rec.id])[rec.id]

                    mail_id = template_calificacion.send_mail(rec.id, force_send=True)

                    rec.message_post(
                        body=body_html or _("Correo de calificación enviado."),
                        subject=subject or _("Correo de calificación"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

                    _logger.info("Correo de calificación enviado para OT %s (mail_id=%s)", rec.id, mail_id)

                except Exception as e:
                    _logger.exception("Error al enviar template calificación para OT %s: %s", rec.id, e)
                    rec.message_post(body=_("❌ Error al enviar correo de calificación: %s") % e)

    def send_programacion_inicial(self):
        """Enviar correo de programación inicial y registrar en chatter (envío inmediato con validación)."""
        for rec in self:
            template_servicio = self.env.ref("pmant.email_tempemail_template_custom_sucursallate_servicio_finalizado", raise_if_not_found=False)

            # --- SERVICIO FINALIZADO ---
            if template_servicio:
                try:
                    # Renderizar asunto y cuerpo
                    subject = template_servicio._render_field("subject", [rec.id])[rec.id]
                    body_html = template_servicio._render_field("body_html", [rec.id])[rec.id]

                    # Enviar correo
                    mail_id = template_servicio.send_mail(rec.id, force_send=True)

                    # Registrar en chatter
                    rec.message_post(
                        body=body_html or _("Correo de trabajo programado enviado."),
                        subject=subject or _("Correo de trabajo programado"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

                    _logger.info("Correo de trabajo programado enviado para OT %s (mail_id=%s)", rec.id, mail_id)

                except Exception as e:
                    _logger.exception("Error al enviar template_servicio para OT %s: %s", rec.id, e)
                    rec.message_post(body=_("❌ Error al enviar correo trabajo programado: %s") % e)

    def send_report_empresa(self):
        for rec in self:
            template = self.env.ref("pmant.email_template_custom_empresa_programacion", raise_if_not_found=False)
            if not template or not rec.tarea or not rec.schedule_date:
                rec.message_post(body=_("No se pudo enviar el correo: faltan datos como la tarea o la fecha programada."))
                continue
            correos = []
            if rec.ubicacion and getattr(rec.ubicacion, "email_jefe", None):
                correos.append(rec.ubicacion.email_jefe)
            if rec.ubicacion and getattr(rec.ubicacion, "email", None):
                correos.append(rec.ubicacion.email)
            if rec.empresa and getattr(rec.empresa, "email", None):
                correos.append(rec.empresa.email)
            email_to = ",".join(filter(None, correos)) if correos else None
            try:
                template.with_context(email_to=email_to).send_mail(rec.id, force_send=False)
            except Exception as e:
                _logger.exception("Error al encolar correo empresa (OT %s): %s", rec.id, e)
                rec.message_post(body=_("Error al enviar correo a empresa: %s") % e)

    def send_report_sucursal(self):
        for rec in self:
            template = self.env.ref("pmant.email_template_custom_sucursal", raise_if_not_found=False)
            if not template:
                rec.message_post(body=_("Plantilla de sucursal no encontrada."))
                continue
            correos = []
            if rec.ubicacion and getattr(rec.ubicacion, "email_jefe", None):
                correos.append(rec.ubicacion.email_jefe)
            if rec.ubicacion and getattr(rec.ubicacion, "email", None):
                correos.append(rec.ubicacion.email)
            if rec.empresa and getattr(rec.empresa, "email", None):
                correos.append(rec.empresa.email)
            email_to = ",".join(filter(None, correos)) if correos else None
            try:
                template.with_context(email_to=email_to).send_mail(rec.id, force_send=False)
            except Exception as e:
                _logger.exception("Error al encolar correo sucursal (OT %s): %s", rec.id, e)
                rec.message_post(body=_("Error al enviar correo a sucursal: %s") % e)

    # --------------------
    # Reportes / Firma
    # --------------------
    def set_firma_cliente_mantenimiento(self):
        for rec in self:
            ir_actions_report_sudo = self.env["ir.actions.report"].sudo()
            statement_report_action = self.env.ref("pmant.action_mantenimiento_ot")
            statement_report = statement_report_action.sudo()
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(statement_report, res_ids=rec.ids)
            attachment = self.env["ir.attachment"].create({
                "name": f"OT {rec.name}",
                "type": "binary",
                "mimetype": "application/pdf",
                "raw": content,
                "res_model": "sign.template",
                "res_id": None,
            })
            vals_template = {"name": f"OT {rec.name}", "attachment_id": attachment.id, "ot_id": rec.id}
            vals_template.pop("attachment_count", None)
            self.env["sign.template"].create(vals_template)
        return {
            "type": "ir.actions.act_window",
            "name": f"OT {self.name}",
            "res_model": "sign.template",
            "view_mode": "kanban",
            "target": "current",
        }

    def set_firma_empresa_acta(self):
        for rec in self:
            ir_actions_report_sudo = self.env["ir.actions.report"].sudo()
            statement_report_action = self.env.ref("pmant.action_reporte_acta")
            statement_report = statement_report_action.sudo()
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(statement_report, res_ids=rec.ids)
            attachment = self.env["ir.attachment"].create({
                "name": f"Acta - {rec.name}",
                "type": "binary",
                "raw": content,
                "mimetype": "application/pdf",
                "res_model": "sign.template",
                "res_id": None,
            })
            vals_template = {"name": f"Acta - {rec.name}", "attachment_id": attachment.id, "ot_id": rec.id}
            vals_template.pop("attachment_count", None)
            self.env["sign.template"].create(vals_template)
        return {
            "type": "ir.actions.act_window",
            "name": f"Acta - {self.name}",
            "res_model": "sign.template",
            "view_mode": "kanban",
            "target": "current",
        }

    # --------------------
    # Calendario
    # --------------------
    def _create_calendar_event(self):
        for rec in self:
            if not (rec.schedule_date and rec.duration):
                raise UserError(_("Para crear una Ordne de Trabajo tienes que colocar la fecha programada y la durecion en horas."))
            partner_ids = []
            if self.env.user.partner_id:
                partner_ids.append(self.env.user.partner_id.id)
            if rec.user_id and rec.user_id.partner_id:
                partner_ids.append(rec.user_id.partner_id.id)
            for user in rec.subodinados:
                if user.partner_id:
                    partner_ids.append(user.partner_id.id)
                else:
                    raise UserError(_("El usuario '%s' no tiene un partner asociado.") % user.name)
            if partner_ids:
                event = self.env["calendar.event"].create({
                    "name": f"Servicio programado / {rec.name}",
                    "start": rec.schedule_date,
                    "stop": rec.schedule_date + timedelta(hours=rec.duration),
                    "duration": rec.duration,
                    "ots_id": rec.id,
                    "partner_ids": [(6, 0, partner_ids)],
                    "user_id": self.env.user.id,
                })
                rec.event_id = event.id

    # --------------------
    # Acciones programadas (cron)
    # --------------------
    def _set_email_programacion(self):
        fecha_objetivo = date.today() + timedelta(days=2)
        ordenes = self.search([
            ("schedule_date", ">=", fecha_objetivo),
            ("schedule_date", "<", fecha_objetivo + timedelta(days=1)),
        ])
        for orden in ordenes:
            orden.send_programacion_inicial()

    # --------------------
    # Compartir OT
    # --------------------
    def compartir_ot(self):
        dominio = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        active_id = self._context.get("active_id") or (self.ids and self.ids[0])
        if not active_id:
            raise ValueError("No se encontró un ID activo para compartir la OT")
        url_to_share = f"{dominio}/reporte/?id={active_id}"
        return {
            "type": "ir.actions.act_window",
            "name": "Compartir Ot",
            "res_model": "wizard.share",
            "view_mode": "form",
            "target": "new",
            "context": {"default_title": "Compartir Ot", "default_url": url_to_share, "active_id": active_id},
        }

    # --------------------
    # CRM / Oportunidad
    # --------------------
    def crm_oportunidad_create(self):
        for rec in self:
            equipos = rec.tarea.planequipo.mapped("equipo.id") if rec.tarea else []
            valores = {
                "name": rec.name,
                "user_id": rec.employee_id.user_id.id if rec.employee_id and rec.employee_id.user_id else False,
                "partner_id": rec.empresa.id if rec.empresa else False,
                "ubicacion": rec.ubicacion.id if rec.ubicacion else False,
                "orden_trabajo": rec.id,
                "equipo_tarea": [(6, 0, equipos)],
            }
            lead = self.env["crm.lead"].create(valores)
            rec.oportunidad = lead.id

    # --------------------
    # Validaciones por etapa
    # --------------------
    def _change_createui(self):
        for rec in self:
            rec._validacion_etapas()
            planequipo = rec.tarea.planequipo if rec.tarea else None
            if not (planequipo and any(planequipo.mapped("is_informe_file"))):
                if rec.stage_id and rec.stage_id.sequence == 3:
                    rec._fecha_estado()
            if rec.stage_id and rec.stage_id.sequence == 3:
                rec.send_reporte_final()

    def _fecha_estado(self):
        for rec in self:
            fecha_actual = datetime.now().date()
            rec.fecha_ejec = fecha_actual
            if rec.tarea and rec.tarea.planequipo:
                try:
                    rec.tarea.planequipo.fecha_ejec = datetime.now()
                except Exception:
                    _logger.exception("No se pudo actualizar planequipo.fecha_ejec para tarea %s", rec.tarea.id)

    def _validacion_etapas(self):
        for rec in self:
            if rec.stage_id and rec.stage_id.sequence == 5:
                if not rec.selec_sunat and not rec.factura:
                    raise UserError(_("Debe registrar la factura"))
                if rec.selec_sunat and not rec.factura_sunat:
                    raise UserError(_("Debe registrar la factura Sunat"))

    # --------------------
    # Report action
    # --------------------
    def action_print_report(self):
        return self.env.ref("pmant.action_mantenimiento_ot").report_action(self)

    # --------------------
    # Name get util
    # --------------------
    def name_get(self):
        res = []
        for rec in self:
            display = rec.name or ''
            if not display:
                display = _("Solicitud de mantenimiento %s") % rec.id
            res.append((rec.id, f"[{rec.id}] {display}"))
        return res

    # --------------------
    # Update Fecha Ejecutada from Planequipo
    # --------------------
    def action_fech_up(self):
        return { 
            "type": "ir.actions.act_window",
            "name": "Actualizar Fecha Ejecutada",
            "res_model": "wizard.fecha.ejecutada.ot",
            "view_mode": "form",
            "target": "new",
            "context": {"default_ot_ids": [(6, 0, self.ids)]},
        }




class WizardFechaEjecutadaOT(models.TransientModel):
    _name = "wizard.fecha.ejecutada.ot"
    _description = "Actualizar Fecha Ejecutada de OTs"

    ot_id = fields.Many2one("maintenance.request", string="Órdenes de Trabajo")
    nueva_fecha = fields.Date(string="Nueva Fecha Ejecutada", required=True, default=fields.Date.today)
    descripcion = fields.Text(string="Motivo de la actualización")
    def action_update_fecha_ejecutada(self):
        self.ot_id.fecha_ejec = self.nueva_fecha
        if self.ot_id.tarea and self.ot_id.tarea.planequipo:
            try:
                self.ot_id.tarea.planequipo.fecha_ejec = self.nueva_fecha
            except Exception:
                _logger.exception("No se pudo actualizar planequipo.fecha_ejec para tarea %s", self.ot_id.tarea.id)
        self.ot_id.ensure_one()
        self.ot_id.message_post(body=f"La fecha ejecutada fue actualizada a {self.nueva_fecha}.\nMotivo: {self.descripcion}")
        return {"type": "ir.actions.act_window_close"}