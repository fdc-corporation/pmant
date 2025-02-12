from datetime import date, datetime, timedelta, time
from odoo import _, models, fields, api
from odoo.exceptions import UserError
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import base64
from odoo.tools import html2plaintext

# Crear un logger
_logger = logging.getLogger(__name__)


class OTS(models.Model):
    _inherit = "maintenance.request"
    _description = "Peticion de mantenimiento"

    sequence = fields.Char()
    tarea = fields.Many2one("tarea.mantenimiento", string="Tarea")
    estado = fields.Boolean(related="tarea.revisar", string="Estado")
    tex = fields.Char(string="Text")
    empresa = fields.Many2one("res.partner", related="tarea.cliente")
    ubicacion = fields.Many2one("res.partner", related="tarea.ubicacion")
    order_compra = fields.Many2one(
        "oc.compras", string="Orden de compra", ondelete="set null"
    )
    factura = fields.Many2one("account.move", string="Factura")
    factura_sunat = fields.Char(string="Factura Sunat")
    selec_sunat = fields.Boolean(string="Factura Sunat?")
    oportunidad = fields.Many2one("crm.lead", string="Oportunidad")
    partner_id = fields.Many2one("res.partner", related="tarea.cliente")
    fecha_ejec = fields.Date(string="Fecha Ejecutada", readonly=False)
    subodinados = fields.Many2many("res.users", string="Subordinados")
    event_id = fields.Many2one("calendar.event", string="Evento en calendario")
    is_evaluacion = fields.Boolean(string="Es una Evaluacion")
    is_tecnico = fields.Boolean(
        compute="_compute_is_tecnico", string="Is Técnico", store=False
    )
    oc_cliente = fields.Char(related="order_compra.oc", store=True)
    not_oc = fields.Boolean(string="No tiene OC?")

    @api.depends("estado")
    def _get_tex(self):
        if self.estado:
            self.tex = "Urgente"

    @api.onchange("tarea", "order_compra")
    def _compute_order_compra(self):
        for record in self:
            if record.tarea and record.tarea.oc_id:
                record.order_compra = record.tarea.oc_id.id
                if record.tarea.oc_id:
                    record.tarea.oc_id.ot_servicio = record.id
            else:
                record.order_compra = False

    @api.depends_context("uid")
    def _compute_is_tecnico(self):
        for record in self:
            record.is_tecnico = self.env.user.has_group("pmant.group_pmant_tecnico")

    @api.model
    def create(self, vals):
        if "tarea" in vals and vals["tarea"]:
            vals["partner_id"] = (
                self.env["tarea.mantenimiento"].browse(vals["tarea"]).cliente.id
            )
        if vals.get("sequence", "New") == "New":
            vals["sequence"] = (
                self.env["ir.sequence"].next_by_code("ot.mantenimiento.sequence")
                or "New"
            )

        record = super(OTS, self).create(vals)
        record._create_calendar_event()
        return record

    def write(self, vals):
        res = super(OTS, self).write(vals)
        if not self.event_id:
            self._create_calendar_event()
        if "stage_id" in vals:
            self._change_createui()
        if "tarea" in vals:
            self._compute_order_compra()
        return res

    def _change_createui(self):
        for record in self:
            self._validacion_etapas()
            if record.tarea:
                record.tarea.write({"state_id": record.stage_id.id})
            if self.stage_id.sequence == 3:
                self._fecha_estado()
            if self.stage_id.sequence == 5:
                self.send_reporte_final()

    def _fecha_estado(self):
        # Obtener la fecha actual
        fecha_actual = datetime.now()
        fecha_formato = fecha_actual.strftime("%Y-%m-%d")
        # Asignar la fecha actual al campo del modelo actual
        self.fecha_ejec = fecha_formato

        # Verificar que 'tarea' y 'planequipo' existan antes de asignarles valores
        if self.tarea and self.tarea.planequipo:
            self.tarea.planequipo.fecha_ejec = fecha_actual

    def _validacion_etapas(self):
        for record in self:
            if record.not_oc == False:
                if record.stage_id.sequence == 4 and not record.order_compra:
                    raise UserError(
                        _("Debe registrar la OC en el mudlo de Orden de compras")
                    )

            elif record.stage_id.sequence == 5:
                if not record.selec_sunat and not record.factura:
                    raise UserError(_("Debe registrar la factura"))
                elif record.selec_sunat and not record.factura_sunat:
                    raise UserError(_("Debe registrar la factura Sunat"))

    def send_reporte_final(self):
        template = self.env.ref("pmant.email_template_custom_sucursal")

        if template:
            template.send_mail(self.id, force_send=True)

    def send_report_empresa(self):
        try:
            # Depurar los datos importantes antes de continuar
            _logger.info(
                f"Tarea: {self.tarea}, Fecha: {self.schedule_date}, Tipo de fecha: {type(self.schedule_date)}"
            )

            # Buscar la plantilla de correo
            template = self.env.ref("pmant.email_template_custom_empresa")

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
        try:
            # Depurar los datos importantes antes de continuar
            _logger.info(
                f"Tarea: {self.tarea}, Fecha: {self.schedule_date}, Tipo de fecha: {type(self.schedule_date)}"
            )

            # Buscar la plantilla de correo
            template = self.env.ref("pmant.email_template_custom_sucursal")

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

    def crm_oportunidad_create(self):
        for record in self:
            equipos = record.tarea.planequipo.mapped("equipo.id")

            valores = {
                "name": record.name,
                "user_id": record.employee_id.user_id.id,
                "partner_id": record.empresa.id,
                "ubicacion": record.ubicacion.id,
                "orden_trabajo": record.id,
                "equipo_tarea": [(6, 0, equipos)],
            }
            lead = self.env["crm.lead"].create(valores)
            record.oportunidad = lead.id

    def set_firma_cliente_mantenimiento(self):

        ir_actions_report_sudo = self.env["ir.actions.report"].sudo()
        statement_report_action = self.env.ref("pmant.action_mantenimiento_ot")
        for statement in self:
            statement_report = statement_report_action.sudo()
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(
                statement_report, res_ids=statement.ids
            )

            # Crear el adjunto con el PDF generado
            attachment = self.env["ir.attachment"].create(
                {
                    "name": "OT " + self.name,
                    "type": "binary",
                    "mimetype": "application/pdf",
                    "raw": content,
                    "res_model": "sign.template",  # Asociar al modelo sign.template
                    "res_id": None,
                }
            )

            vals_template = {
                "name": "OT " + self.name,
                "attachment_id": attachment.id,  # Asociar el adjunto creado
            }

            vals_template.pop("attachment_count", None)

            sign_template = self.env["sign.template"].create(vals_template)

            # Redirigir al formulario del sign.template
        return {
            "type": "ir.actions.act_window",
            "name": "OT " + self.name,
            "res_model": "sign.template",
            "view_mode": "kanban",  # Esto es para ver primero la lista (tree)
            "target": "current",
        }

    def set_firma_empresa_acta(self):
        ir_actions_report_sudo = self.env["ir.actions.report"].sudo()
        statement_report_action = self.env.ref("pmant.action_reporte_acta")
        for statement in self:
            statement_report = statement_report_action.sudo()
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(
                statement_report, res_ids=statement.ids
            )

            attachment = self.env["ir.attachment"].create(
                {
                    "name": "Acta - " + self.name,
                    "type": "binary",
                    "raw": content,
                    "mimetype": "application/pdf",
                    "res_model": "sign.template",  # Asociar al modelo sign.template
                    "res_id": None,  # No se asocia a un registro específico en este momento
                }
            )

            vals_template = {
                "name": "Acta - " + self.name,
                "attachment_id": attachment.id,  # Asociar el adjunto creado
            }

            # Eliminar 'attachment_count' si está presente en los valores
            vals_template.pop("attachment_count", None)

            # Crear la plantilla de firma sin 'attachment_count'
            sign_template = self.env["sign.template"].create(vals_template)

            # Redirigir al formulario de sign.template
        return {
            "type": "ir.actions.act_window",
            "name": "Acta - " + self.name,
            "res_model": "sign.template",
            "view_mode": "kanban",  # Esto es para ver primero la lista (tree)
            "target": "current",
        }

    def _create_calendar_event(self):
        for record in self:
            if record.schedule_date and record.duration:
                partner_ids = []

                # Ensure the current user has an associated partner
                if self.env.user.partner_id:
                    partner_ids.append(self.env.user.partner_id.id)
                if record.user_id:
                    partner_ids.append(record.user_id.partner_id.id)
                else:
                    raise UserError(
                        _("El usuario actual '%s' no tiene un partner asociado.")
                        % self.env.user.name
                    )

                # Ensure all subordinates have partners
                for user in record.subodinados:
                    if user.partner_id:
                        partner_ids.append(user.partner_id.id)
                    else:
                        raise UserError(
                            _("El usuario '%s' no tiene un partner asociado.")
                            % user.name
                        )

                if partner_ids:
                    # Create the event in the calendar
                    event = self.env["calendar.event"].create(
                        {
                            "name": record.name,
                            "start": record.schedule_date,
                            "stop": record.schedule_date
                            + timedelta(hours=record.duration),
                            "duration": record.duration,
                            "ots_id": record.id,
                            "partner_ids": [(6, 0, partner_ids)],
                            "user_id": self.env.user.id,
                        }
                    )
                    record.event_id = event.id
                else:
                    raise UserError(_("No hay asistentes válidos para el evento."))
    def compartir_ot(self):
        # Obtener la URL base de la configuración de Odoo
        dominio = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        # Obtener el ID activo desde el contexto (o usar active_id si no está disponible)
        active_id = self._context.get('active_id', False)
        if not active_id:
            raise ValueError("No se encontró un ID activo para compartir la OT")

        # Construir la URL para compartir
        url_to_share = f"{dominio}/reporte/?id={active_id}"

        # Redirigir al enlace de compartir
        return {
            "type": "ir.actions.act_window",
            "name": "Compartir Ot",
            "res_model": "wizard.share",
            "view_mode": "form",
            "view_type": "form",
            "target": "new",
            "context": {
                "default_title": "Compartir Ot",
                "default_url": url_to_share,
                "active_id": active_id,
            },
        }

