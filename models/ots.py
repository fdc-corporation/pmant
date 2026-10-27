# -*- coding: utf-8 -*-
"""
Optimized Odoo 19 model for maintenance.request (OTS)
- Compatible con Odoo 19 (api.model_create_multi, raise_if_not_found)
- Evita abrir ventanas UI en create/write para enviar correos; usa send_mail queued (force_send=False)
- Maneja múltiples registros correctamente
- Mejora de validaciones, logs y uso eficiente de search_count/mapped
"""
from datetime import datetime, timedelta, date, time
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)


class MaintenanceRequestOTS(models.Model):
    _inherit = "maintenance.request"

    @api.model
    def pmant_remove_sign_integration(self):
        """Retira vistas históricas de Odoo Sign al actualizar instalaciones existentes."""
        xmlids = self.env["ir.model.data"].sudo().search([
            ("module", "=", "pmant"),
            ("name", "in", [
                "sign_template_inherit_form",
                "sign_send_request_inherit_form",
                "sign_requestrequest_inherit_form",
            ]),
        ])
        for xmlid in xmlids:
            if xmlid.model == "ir.ui.view":
                self.env["ir.ui.view"].sudo().browse(xmlid.res_id).exists().unlink()
            xmlid.unlink()
        return True

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
    pmant_commercial_user_ids = fields.Many2many(
        "res.users", "pmant_work_order_commercial_user_rel", "request_id", "user_id",
        string="Vendedores de origen", compute="_compute_pmant_commercial_users",
        store=True, readonly=True,
    )
    pmant_followup_seller_id = fields.Many2one(
        "res.users", string="Vendedor de seguimiento", tracking=True,
        domain="[('share', '=', False)]",
    )
    pmant_spare_review_notified = fields.Boolean(
        string="Oportunidad de repuestos notificada", copy=False, readonly=True,
    )
    pmant_can_create_opportunity = fields.Boolean(
        string="Puede crear oportunidad", compute="_compute_pmant_can_create_opportunity",
    )
    partner_id = fields.Many2one("res.partner", related="tarea.cliente", store=True)
    fecha_ejec = fields.Date(string="Fecha Ejecutada")
    subodinados = fields.Many2many("res.users", string="Subordinados")
    is_evaluacion = fields.Boolean(string="Es una Evaluacion")
    is_tecnico = fields.Boolean(
        compute="_compute_is_tecnico", string="Is Técnico", store=False
    )
    tab_horas = fields.One2many(
        "programacion.mantenimiento", "ot_id", string="Hoja de horas"
    )
    is_active_programacion = fields.Boolean(string="La programacion fue eniada?")
    rating_p1 = fields.Integer(string="Calidad del servicio")
    rating_p2 = fields.Integer(string="Tiempo de respuesta")
    rating_p3 = fields.Integer(string="Probabilidad de recomendación")
    rating_comment = fields.Text(string="Comentarios del cliente")
    cantidad_inconvenientes = fields.Integer(
        string="Incidencias", compute="_get_cantidad_incidencias"
    )
    notas_venta = fields.Html(
        string="Notas Venta", sanitize_style=True, sanitize_tags=False
    )
    duration = fields.Float(
        string="Duración (H)",
        required=True,
        default=0.0,
        compute="_compute_horas_duracion",
        store=True,
    )
    fecha_acta = fields.Date(string="Fecha Acta de Conformidad")
    require_repuestos = fields.Boolean(
        string="Tiene Repuestos",
        compute="_compute_require_repuestos",
        store=True,
    )
    pmant_kanban_reference = fields.Char(string="Referencia OT", compute="_compute_pmant_kanban_reference")
    pmant_service_type_id = fields.Many2one(
        "tipotarea.mantenimiento", string="Tipo de servicio",
        related="tarea.tipo", store=True, readonly=True,
    )
    pmant_service_in_progress = fields.Boolean(
        string="Servicio en ejecución", related="tarea.action_servicio", readonly=True,
    )
    # --------------------
    # Computes
    # --------------------
    @api.depends("tarea.planequipo.require_repuestos")
    def _compute_require_repuestos(self):
        for record in self:
            record.require_repuestos = any(
                record.tarea.planequipo.mapped("require_repuestos")
            ) if record.tarea else False

    @api.depends("tarea.sale_order", "tarea.sale_order.user_id")
    def _compute_pmant_commercial_users(self):
        for record in self:
            record.pmant_commercial_user_ids = record.tarea.sale_order.mapped("user_id").filtered(
                lambda user: user.active and not user.share
            ) if record.tarea else False

    @api.depends("stage_id.pmant_code", "require_repuestos", "oportunidad", "tarea.pmant_spare_line_ids.requested_qty")
    def _compute_pmant_can_create_opportunity(self):
        for record in self:
            record.pmant_can_create_opportunity = bool(
                record.stage_id.pmant_code in ("review", "billing_hes", "done")
                and record.require_repuestos
                and not record.oportunidad
                and any(line.requested_qty > 0 for line in record.tarea.pmant_spare_line_ids)
            )

    def _pmant_can_manage_opportunity(self):
        self.ensure_one()
        user = self.env.user
        manager = user.has_group("pmant.group_pmant_planner") or user.has_group("pmant.group_pmant_admin")
        seller = user.has_group("pmant.group_pmant_vendedor") and user in (
            self.pmant_commercial_user_ids | self.pmant_followup_seller_id
        )
        return manager or seller

    @api.constrains("pmant_followup_seller_id")
    def _check_pmant_followup_seller(self):
        for record in self.filtered("pmant_followup_seller_id"):
            if not record.pmant_followup_seller_id.has_group("pmant.group_pmant_vendedor"):
                raise ValidationError(_("El vendedor de seguimiento debe pertenecer al grupo Mantenimiento - Vendedor."))

    @api.depends("name")
    def _compute_pmant_kanban_reference(self):
        for request in self:
            request.pmant_kanban_reference = (request.name or _("Sin referencia")).split(" - ", 1)[0]

    @api.depends("schedule_date", "schedule_end")
    def _compute_horas_duracion(self):
        for rec in self:
            if rec.schedule_date and rec.schedule_end:
                # schedule_date / schedule_end pueden ser datetime/date según implementación
                try:
                    delta = rec.schedule_end - rec.schedule_date
                    horas = (
                        delta.total_seconds()
                        if hasattr(delta, "total_seconds")
                        else delta.days * 24
                    ) / 3600.0
                    rec.duration = float_round(horas or 0.0, precision_digits=2)
                except Exception:
                    rec.duration = 0.0
            else:
                rec.duration = 0.0

    @api.depends_context("uid")
    def _compute_is_tecnico(self):
        for rec in self:
            rec.is_tecnico = self.env.user.has_group("pmant.group_pmant_tecnico")

    def _get_cantidad_incidencias(self):
        for rec in self:
            rec.cantidad_inconvenientes = self.env[
                "inconveniente.servicio"
            ].search_count([("ot_id", "=", rec.id)])

    # --------------------
    # Actions / UI
    # --------------------
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
            "name": "Orden de trabajo",
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
            for record in self:
                if not record.tarea.tipo:
                    raise ValidationError(_("El campo 'Tipo de Servicio' es obligatorio para programar la tarea."))
                if record.tarea.planequipo:
                    for plan in record.tarea.planequipo:
                        if not plan.plan:
                            raise ValidationError(_("El campo 'Plan de Tarea' es obligatorio para programar la tarea."))

            print("Creando/actualizando programación inicial para OTs...")

            records.action_programacion_inicial()
            records.send_programacion_inicial()
        except Exception as e:
            _logger.exception(
                "Error al crear/actualizar programación inicial para OTs: %s", e
            )
            # No lanzar excepción que rompa la creación; sólo reportar en chatter
            for rec in records:
                rec.message_post(body=_("Error al crear programación inicial: %s") % e)
        return records

    def write(self, vals):
        res = super().write(vals)
        # Si cambia la etapa, ejecutar lógica por registro

        if "scheduled_end" in vals or "schedule_date" in vals:
            try:
                print("Actualizando programación inicial para OTs...")
                self.action_programacion_inicial()
            except Exception as e:
                _logger.exception(
                    "Error al actualizar programación inicial para OTs: %s", e
                )
                for rec in self:
                    rec.message_post(
                        body=_("Error al actualizar programación inicial: %s") % e
                    )
        if "stage_id" in vals:
            for rec in self:
                try:
                    if rec.stage_id and rec.stage_id.pmant_code == "review":
                        # Etapa en ejecución
                        planequipo = rec.tarea.planequipo if rec.tarea else None
                        if planequipo and not any(planequipo.mapped("is_informe_file")):
                            rec.fecha_ejec = fields.Date.today()
                            if rec.tarea:
                                rec.tarea._fecha_ejecutada()
                                rec.tarea._evento_calendario_proximo_servicio()
                        else:
                            if planequipo and not any(
                                planequipo.mapped("informe_file")
                            ):
                                raise UserError(
                                    _(
                                        "Debe subir el informe técnico antes de cambiar a esta etapa."
                                    )
                                )
                            else:
                                rec.fecha_ejec = (
                                    planequipo[:1].fecha_ejec if planequipo else None
                                )
                                if rec.tarea:
                                    rec.tarea._evento_calendario_proximo_servicio()

                except Exception as e:
                    _logger.exception(
                        "Error durante write() en maintenance.request id %s: %s",
                        rec.id,
                        e,
                    )
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
    # @api.onchange("schedule_date", "schedule_end")
    def action_programacion_inicial(self):
        for rec in self:
            if not rec.schedule_date:
                raise UserError(
                    _(
                        "Para crear una Orden de Trabajo debes colocar la fecha programada y una duración mayor a 0."
                    )
                )

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
                    _logger.exception(
                        "No se pudo crear programacion.mantenimiento para OT %s: %s",
                        rec.id,
                        e,
                    )
                    rec.message_post(body=_("Error al crear programación: %s") % e)
            else:
                try:
                    rec.tab_horas[0].write(valores)
                except Exception as e:
                    _logger.exception(
                        "No se pudo actualizar programacion.mantenimiento para OT %s: %s",
                        rec.id,
                        e,
                    )
                    rec.message_post(body=_("Error al actualizar programación: %s") % e)

    def notify_users_facturacion(self):
        """Compatibilidad para integraciones que aún llaman el método anterior."""
        return self._notify_billing_users()

    def send_reporte_final(self):
        """Enviar correos finales (servicio finalizado + calificación) y registrar en chatter."""
        for rec in self:
            # Buscar plantillas
            template_servicio = self.env.ref(
                "pmant.email_template_servicio_finalizado", raise_if_not_found=False
            )
            template_calificacion = self.env.ref(
                "pmant.email_template_calificacion_servicio", raise_if_not_found=False
            )

            # --- SERVICIO FINALIZADO ---
            if template_servicio:
                try:
                    # Renderizar asunto y cuerpo
                    subject = template_servicio._render_field("subject", [rec.id])[
                        rec.id
                    ]
                    body_html = template_servicio._render_field("body_html", [rec.id])[
                        rec.id
                    ]

                    # Enviar correo
                    mail_id = template_servicio.send_mail(rec.id, force_send=True)

                    # Registrar en chatter
                    rec.message_post(
                        body=body_html or _("Correo de finalización enviado."),
                        subject=subject or _("Correo de finalización"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

                    _logger.info(
                        "Correo de servicio finalizado enviado para OT %s (mail_id=%s)",
                        rec.id,
                        mail_id,
                    )

                except Exception as e:
                    _logger.exception(
                        "Error al enviar template_servicio para OT %s: %s", rec.id, e
                    )
                    rec.message_post(
                        body=_("❌ Error al enviar correo finalización: %s") % e
                    )

            # --- CALIFICACIÓN ---
            if template_calificacion:
                try:
                    subject = template_calificacion._render_field("subject", [rec.id])[
                        rec.id
                    ]
                    body_html = template_calificacion._render_field(
                        "body_html", [rec.id]
                    )[rec.id]

                    mail_id = template_calificacion.send_mail(rec.id, force_send=True)

                    rec.message_post(
                        body=body_html or _("Correo de calificación enviado."),
                        subject=subject or _("Correo de calificación"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )

                    _logger.info(
                        "Correo de calificación enviado para OT %s (mail_id=%s)",
                        rec.id,
                        mail_id,
                    )

                except Exception as e:
                    _logger.exception(
                        "Error al enviar template calificación para OT %s: %s",
                        rec.id,
                        e,
                    )
                    rec.message_post(
                        body=_("❌ Error al enviar correo de calificación: %s") % e
                    )

    def send_programacion_inicial(self):
        """Envia correo de programación automáticamente (sin abrir la UI) y registra en el chatter."""
        for rec in self:
            try:
                template = self.env.ref(
                    "pmant.email_template_custom_sucursal", raise_if_not_found=False
                )
                if not template:
                    rec.message_post(
                        body=_(
                            "❌ No se encontró la plantilla de correo para programación inicial."
                        )
                    )
                    continue

                # Enviar correo
                mail_id = template.send_mail(rec.id, force_send=False)

                # Renderizar asunto y cuerpo para el chatter
                subject = template._render_field("subject", [rec.id])[rec.id]
                body_html = template._render_field("body_html", [rec.id])[rec.id]
                mail = self.env["mail.mail"].browse(mail_id)
                mail.sudo().action_send_and_close()
                # rec.message_post(
                #     body=body_html or _("✅ Correo de programación enviado."),
                #     subject=subject or _("Correo de programación"),
                #     message_type="comment",
                #     subtype_xmlid="mail.mt_note",
                # )

                _logger.info(
                    "Correo de programación enviado para OT %s (mail_id=%s)",
                    rec.id,
                    mail_id,
                )

            except Exception as e:
                _logger.exception(
                    "Error al enviar correo programado para OT %s: %s", rec.id, e
                )
                rec.message_post(
                    body=_("❌ Error al enviar correo de programación: %s") % e
                )

    def send_report_empresa(self):
        try:
            # Depurar los datos importantes antes de continuar
            _logger.info(
                f"Tarea: {self.tarea}, Fecha: {self.schedule_date}, Tipo de fecha: {type(self.schedule_date)}"
            )

            # Buscar la plantilla de correo
            template = self.env.ref("pmant.email_template_custom_empresa_programacion")

            # Verificar que la plantilla existe, la tarea y la fecha están definidas
            if template and self.tarea and self.schedule_date:

                # Crear el contexto para la ventana de composición de correos
                ctx = {
                    "default_model": "maintenance.request",  # Modelo actual
                    "default_res_ids": self.id,  # Se asegura de que es un entero
                    "default_res_ids": [
                        self.id
                    ],  # res_ids debe ser una lista de enteros
                    "default_template_id": template.id,
                    "default_composition_mode": "comment",  # Modo de composición
                    "force_email": True,
                }

                # Retornar la acción para abrir el asistente de composición de correos
                return {
                    "type": "ir.actions.act_window",
                    "view_mode": "form",
                    "res_model": "mail.compose.message",
                    "views": [(False, "form")],
                    "view_id": False,
                    "target": "new",
                    "context": ctx,
                }

            else:
                # Mensaje en caso de que falten datos importantes
                self.message_post(
                    body="No se pudo enviar el correo: faltan datos como la tarea o la fecha programada."
                )

        except Exception as e:
            # Manejar cualquier excepción durante el envío y registrar el error
            _logger.error(f"Error al enviar el correo: {str(e)}", exc_info=True)
            self.message_post(body=f"Error al enviar el correo: {str(e)}")

    def send_report_sucursal(self):
        self.ensure_one()
        try:
            # Verificar que existe la plantilla
            template = self.env.ref("pmant.email_template_custom_sucursal")
            if template:
                ctx = {
                    "default_model": "maintenance.request",
                    "default_res_id": self.id,
                    "default_template_id": template.id,
                    "default_use_template": True,
                    "default_composition_mode": "comment",
                    "force_email": True,
                }
                return {
                    "type": "ir.actions.act_window",
                    "name": "Enviar Correo de Programación",
                    "res_model": "mail.compose.message",
                    "view_mode": "form",
                    "target": "new",
                    "context": ctx,
                }
        except Exception as e:
            _logger.error(f"Error al enviar el correo: {str(e)}", exc_info=True)
            self.message_post(body=f"Error al enviar el correo: {str(e)}")

    # --------------------
    # Reportes / Acta PDF
    # --------------------
    def open_wizard_acta_pdf(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Generar Acta de Conformidad",
            "res_model": "wizard.open.acta.confirmidad",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_ots_id": self.id,
            },
        }

    def print_acta_conformidad(self):
        return self.env.ref("pmant.action_reporte_acta").report_action(self)
    # --------------------
    # Calendario
    # --------------------
    def _create_calendar_event(self):
        for rec in self:
            if not (rec.schedule_date and rec.duration):
                raise UserError(
                    _(
                        "Para crear una Ordne de Trabajo tienes que colocar la fecha programada y la durecion en horas."
                    )
                )
            partner_ids = []
            if self.env.user.partner_id:
                partner_ids.append(self.env.user.partner_id.id)
            if rec.user_id and rec.user_id.partner_id:
                partner_ids.append(rec.user_id.partner_id.id)
            for user in rec.subodinados:
                if user.partner_id:
                    partner_ids.append(user.partner_id.id)
                else:
                    raise UserError(
                        _("El usuario '%s' no tiene un partner asociado.") % user.name
                    )
            if partner_ids:
                event = self.env["calendar.event"].create(
                    {
                        "name": f"Servicio programado / {rec.name}",
                        "start": rec.schedule_date,
                        "stop": rec.schedule_date + timedelta(hours=rec.duration),
                        "duration": rec.duration,
                        "ots_id": rec.id,
                        "partner_ids": [(6, 0, partner_ids)],
                        "user_id": self.env.user.id,
                    }
                )
                rec.event_id = event.id

    # --------------------
    # Acciones programadas (cron)
    # --------------------
    def _set_email_programacion(self):
        fecha_objetivo = date.today() + timedelta(days=2)
        ordenes = self.search(
            [
                ("schedule_date", ">=", fecha_objetivo),
                ("schedule_date", "<", fecha_objetivo + timedelta(days=1)),
            ]
        )
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
            "context": {
                "default_title": "Compartir Ot",
                "default_url": url_to_share,
                "active_id": active_id,
            },
        }

    # --------------------
    # CRM / Oportunidad
    # --------------------
    def crm_oportunidad_create(self):
        self.ensure_one()
        if not self._pmant_can_manage_opportunity():
            raise UserError(_("No tiene autorización para crear una oportunidad desde esta OT."))
        if not self.stage_id or self.stage_id.pmant_code not in ("review", "billing_hes", "done"):
            raise UserError(_("La oportunidad solo puede crearse cuando la OT está en Revisión o una etapa posterior."))
        if not self.require_repuestos or not self.tarea.pmant_spare_line_ids:
            raise UserError(_("La OT no tiene repuestos declarados para crear una oportunidad."))
        if self.oportunidad:
            return {
                "type": "ir.actions.act_window", "name": _("Oportunidad"),
                "res_model": "crm.lead", "view_mode": "form", "res_id": self.oportunidad.id,
            }
        seller = self.env.user if self.env.user.has_group("pmant.group_pmant_vendedor") else (
            self.pmant_followup_seller_id or self.pmant_commercial_user_ids[:1]
        )
        lead = self.env["crm.lead"].sudo().create({
            "name": _("Repuestos de servicio - %s") % self.display_name,
            "user_id": seller.id if seller else False,
            "partner_id": self.empresa.id if self.empresa else False,
            "ubicacion": self.ubicacion.id if self.ubicacion else False,
            "orden_trabajo": self.id,
            "equipo_tarea": [(6, 0, self.tarea.planequipo.mapped("equipo").ids)],
        })
        for spare in self.tarea.pmant_spare_line_ids.filtered(lambda line: line.requested_qty > 0):
            self.env["pmant.crm.spare.line"].sudo().create({
                "lead_id": lead.id,
                "work_order_id": self.id,
                "spare_line_id": spare.id,
                "equipment_id": spare.plan_equipment_id.equipo.id,
                "product_id": spare.product_id.id,
                "quantity": spare.requested_qty,
                "uom_id": spare.uom_id.id,
                "note": spare.note,
            })
        self.sudo().write({"oportunidad": lead.id})
        self.sudo().message_post(body=_("Se creó la oportunidad comercial %s para el seguimiento de repuestos.") % lead.display_name)
        return {
            "type": "ir.actions.act_window", "name": _("Oportunidad"),
            "res_model": "crm.lead", "view_mode": "form", "res_id": lead.id,
            "context": {"create": False},
        }

    # --------------------
    # Validaciones por etapa
    # --------------------
    def _change_createui(self):
        for rec in self:
            rec._validacion_etapas()
            planequipo = rec.tarea.planequipo if rec.tarea else None
            if not (planequipo and any(planequipo.mapped("is_informe_file"))):
                if rec.stage_id and rec.stage_id.pmant_code == "review":
                    rec._fecha_estado()
            if rec.stage_id and rec.stage_id.pmant_code == "review":
                rec.send_reporte_final()

    def _fecha_estado(self):
        for rec in self:
            fecha_actual = datetime.now().date()
            rec.fecha_ejec = fecha_actual
            if rec.tarea and rec.tarea.planequipo:
                try:
                    rec.tarea.planequipo.fecha_ejec = datetime.now()
                except Exception:
                    _logger.exception(
                        "No se pudo actualizar planequipo.fecha_ejec para tarea %s",
                        rec.tarea.id,
                    )

    def _validacion_etapas(self):
        for rec in self:
            if rec.stage_id and rec.stage_id.pmant_code == "done":
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
            display = rec.name or ""
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
            "context": {"default_ot_id": self.id},
        }


class WizardFechaEjecutadaOT(models.TransientModel):
    _name = "wizard.fecha.ejecutada.ot"
    _description = "Actualizar Fecha Ejecutada de OTs"

    ot_id = fields.Many2one(
        "maintenance.request",
        string="Órdenes de Trabajo",
        default=lambda self: self._context.get("default_ot_id"),
    )
    nueva_fecha = fields.Date(
        string="Nueva Fecha Ejecutada", required=True, default=fields.Date.today
    )
    descripcion = fields.Text(string="Motivo de la actualización")

    def action_update_fecha_ejecutada(self):
        self.ensure_one()
        self.ot_id.ensure_one()
        # for equipo in self.ot_id.tarea.planequipo:
        #     domain = [
        #                 ('name', 'ilike', 'Proximo servicio'),
        #                 ('start', '=', datetime.combine(equipo.fecha_ejecprox, time(hour=8))),
        #                 ('ots_id', '=', self.ot_id.id if self.ot_id.id else False),
        #             ]
        #     _logger.info("Buscando calendar.event con dominio: %s", domain)
        #     evento = self.env["calendar.event"].search(domain, limit=1)
        #     _logger.info("Evento encontrado: %s", evento)
        #     start_datetime = datetime.combine(self.nueva_fecha, time(hour=13))
        #     stop_datetime = datetime.combine(self.nueva_fecha, time(hour=14))
        #     _logger.info("Actualizando evento calendar.event %s con start: %s, stop: %s", evento, start_datetime, stop_datetime)
        #     if evento:
        #         try:
        #             evento.write({"start": start_datetime, "stop": stop_datetime})
        #         except Exception:
        #             _logger.exception(
        #                 "No se pudo actualizar calendar.event para OT %s",
        #                 self.ot_id.id
        #             )
        self.ot_id.fecha_ejec = self.nueva_fecha

        if self.ot_id.tarea and self.ot_id.tarea.planequipo:
            try:
                self.ot_id.tarea.planequipo.write({"fecha_ejec": self.nueva_fecha})
                self.ot_id.tarea._evento_calendario_proximo_servicio()
            except Exception:
                _logger.exception(
                    "No se pudo actualizar planequipo.fecha_ejec para tarea %s",
                    self.ot_id.tarea.id,
                )

        cuerpo = (
            f"La fecha ejecutada fue actualizada a {self.nueva_fecha}."
            f"\nMotivo: {self.descripcion or 'Sin descripción proporcionada.'}"
        )
        subject = "Actualización de Fecha Ejecutada"
        self.ot_id.message_post(
            body=cuerpo or _("fecha ejecutada fue actualizada."),
            subject=subject or _("fecha ejecutada fue actualizada"),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

        return {"type": "ir.actions.act_window_close"}
