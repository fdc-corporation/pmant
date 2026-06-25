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
    # order_compra = fields.Many2one(
    #     "oc.compras", string="Orden de compra", ondelete="set null"
    # )
    factura = fields.Many2one("account.move", string="Factura")
    factura_sunat = fields.Char(string="Factura Sunat")
    selec_sunat = fields.Boolean(string="Factura Sunat?")
    oportunidad = fields.Many2one("crm.lead", string="Oportunidad")
    partner_id = fields.Many2one("res.partner", related="tarea.cliente")
    fecha_ejec = fields.Date(string="Fecha Ejecutada", readonly=False)
    subodinados = fields.Many2many("res.users", string="Subordinados")
    # event_id = fields.Many2one("calendar.event", string="Evento en calendario")
    is_evaluacion = fields.Boolean(string="Es una Evaluacion")
    is_tecnico = fields.Boolean(
        compute="_compute_is_tecnico", string="Is Técnico", store=False
    )
    # oc_cliente = fields.Char(related="order_compra.oc", store=True)
    # not_oc = fields.Boolean(string="No tiene OC?")
    tab_horas = fields.One2many(
        "programacion.mantenimiento", "ot_id", string="Hoja de horas"
    )
    is_active_programacion = fields.Boolean(string="La programacion fue eniada?")
    rating_p1 = fields.Integer(string="Calidad del servicio")
    rating_p2 = fields.Integer(string="Tiempo de respuesta")
    rating_p3 = fields.Integer(string="Probabilidad de recomendación")
    rating_comment = fields.Text(string="Comentarios del cliente")
    document_count = fields.Integer(
        string="Documentos firmados", compute="get_cantidad_documentos"
    )
    cantidad_inconvenientes = fields.Integer(string="Incidencias", compute="_get_cantidad_incidencias")
    notas_venta = fields.Html(string="Notas Venta", sanitize_style=True, sanitize_tags=False)


    @api.depends("estado")
    def _get_tex(self):
        if self.estado:
            self.tex = "Urgente"

    # OBTENER LA OC DE LA TAREA PARA EL MODULO DE OC_COMPRAS
    # @api.onchange("tarea", "order_compra")
    # def _compute_order_compra(self):
    #     for record in self:
    #         if record.tarea and record.tarea.oc_id:
    #             record.order_compra = record.tarea.oc_id.id
    #             if record.tarea.oc_id:
    #                 record.tarea.oc_id.ot_servicio = self.id
    #         else:
    #             record.order_compra = False

    # ACCION PARA VER TODOS LOS DOCUMENTOS RELACIONADOS A LA OT
    def action_view_documentos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Documentos Firmados",
            "res_model": "sign.request",
            "view_mode": "kanban,form",
            "target": "current",  # O usa 'new' si deseas que se abra como ventana modal
            "domain": [("state", "=", "signed"), ("ot_id", "=", self.id)],
            "context": {
                "default_ot_id": self.id,
            },
        }

    # OBTENER LA CANTIDAD DE DOCUMENTOS FIRMADOS SE TIENE RELACIONADO
    def get_cantidad_documentos(self):
        documentos_firmados = self.env["sign.request"].search_count(
            ["&", ("state", "=", "signed"), ("ot_id", "=", self.id)]
        )
        self.document_count = documentos_firmados

    # ACCION PARA ABRIR UN WIZARD DE WHATSAPP
    def action_open_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Enviar por WhatsApp",
            "res_model": "acrux.chat.message.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.empresa.id,
                "full_name": True,
            },
        }

    @api.depends_context("uid")
    def _compute_is_tecnico(self):
        for record in self:
            record.is_tecnico = self.env.user.has_group("pmant.group_pmant_tecnico")

    @api.model
    def create(self, vals):
        record = super(OTS, self).create(vals)
        if "duration" in vals and "schedule_date" in vals:
            print("EJECUCION DE CREATE PROGRAMACION DE OT")
            record.send_programacion_inicial()
            record.action_programacion_inicial()
        return record

    def write(self, vals):
        res = super(OTS, self).write(vals)

        if "stage_id" in vals:
            for record in self:

                tarea = record.tarea
                plane = tarea.planequipo if tarea else False

                # Seguridad: validar planequipo
                if not plane:
                    raise UserError(_("No existe un plan de equipo asociado a la orden."))

                # --- ETAPA 3: EN EJECUCIÓN ---
                if record.stage_id.sequence == 3:

                    if not plane.fecha_ejecprox:
                        raise UserError(_("Antes de pasar a revisión, registre la fecha del próximo mantenimiento."))

                    # Caso automático
                    if not plane.is_informe_file:
                        fecha_actual = fields.Date.today()
                        record.fecha_ejec = fecha_actual
                        tarea._fecha_ejecutada()

                    # Caso manual
                    else:
                        if not plane.informe_file:
                            raise UserError(_("Debe subir el informe técnico antes de cambiar a esta etapa."))

                        if not plane.fecha_ejec:
                            raise UserError(_("Debe registrar la fecha de ejecución manual."))

                        record.fecha_ejec = plane.fecha_ejec

                # --- ETAPA 4: FACTURACIÓN ---
                if record.stage_id.sequence == 4:
                    record.notify_users_facturacion()

            # Se ejecuta solo una vez por lote
            self._change_createui()

        # --- Sincronizar programación ---
        if {"schedule_date", "duration", "subodinados", "user_id"} & set(vals.keys()):
            self.action_programacion_inicial()

        return res

    def notify_users_facturacion (self):
        # Nombre exacto del grupo
        group_xml_id = 'pmant.group_pmant_user_notifi_fac'
        
        # Buscar el grupo
        group = self.env.ref(group_xml_id)
        
        # Obtener los usuarios del grupo
        users = group.users
        if not users:
            return  # No hay usuarios para notificar

        # Notificar a cada usuario
        for user in users:
            self.message_post(
                body=f"{self.name}: La tarea ha pasado a la etapa {self.stage_id.name}, lista para facturar.",
                partner_ids=[user.partner_id.id]
            )




    def action_programacion_inicial(self):
        for record in self:
            # Obtener lista de IDs de técnicos asignados
            lista_user = []
            if record.user_id:
                lista_user.append(record.user_id.id)
            lista_user += record.subodinados.ids  # optimizado

            # Validar datos obligatorios
            if not record.schedule_date or not record.duration or record.duration <= 0:
                raise UserError(_("Para crear una Orden de Trabajo debes colocar la fecha programada y una duración mayor a 0."))

            valores = {
                "fecha_date": record.schedule_date,
                "duracion": record.duration,
                "ot_id": record.id,
                "tecnicos": [(6, 0, lista_user)],
            }

            if not record.tab_horas:
                print("CREAR UN EVENTO NUEVO")
                self.env["programacion.mantenimiento"].create(valores)
            else:
                print("ACTUALIZAR EL EVENTO EXISTENTE")
                record.tab_horas[0].write(valores)

    # CUANDO SE CREA UNA OT ESTA FUNCION SE EJECUTARA PARA EL ENVIO DE CORREO AL CLIENTE
    def send_programacion_inicial(self):
        self.ensure_one()
        try:
            # Verificar que existe la plantilla
            template = self.env.ref("pmant.email_template_custom_sucursal")
            if template:
                # Enviar el correo
                template.send_mail(self.id, force_send=True)
                # Publicar el contenido del correo en el Chatter
                self.message_post(
                    body=f"✅ Correo de programación enviado exitosamente a la sucursal.",
                    subtype_xmlid="mail.mt_comment",
                )
            else:
                self.message_post(
                    body="⚠️ No se pudo enviar el correo: Plantilla no encontrada.",
                    subtype_xmlid="mail.mt_comment",
                )
        except Exception as e:
            _logger.error(f"Error al enviar el correo: {str(e)}", exc_info=True)
            self.message_post(
                body=f"❌ Error al enviar el correo: {str(e)}",
                subtype_xmlid="mail.mt_comment",
            )

    # ESTA FUNCION EJECUTA FUCIONES PARA ACTUALIZACION DE ESTADOS, FECHAS DE EJECUCION
    def _change_createui(self):
        for record in self:
            self._validacion_etapas()
            if any(plan.is_informe_file for plan in record.mapped("tarea.planequipo")):
                if self.stage_id.sequence == 3:
                    self._fecha_estado()
                    # self.action_open_wizard()
            if self.stage_id.sequence == 5:
                self.send_reporte_final()
                # self.action_open_wizard()

    # CREAR LA FECHA DE EJECUCION DE LA OT
    def _fecha_estado(self):
        # Obtener la fecha actual
        fecha_actual = datetime.now()
        fecha_formato = fecha_actual.strftime("%Y-%m-%d")
        # Asignar la fecha actual al campo del modelo actual
        self.fecha_ejec = fecha_formato

        # Verificar que 'tarea' y 'planequipo' existan antes de asignarles valores
        if self.tarea and self.tarea.planequipo:
            self.tarea.planequipo.fecha_ejec = fecha_actual

    # RESTRICCIONES DE ESTADOS
    def _validacion_etapas(self):
        for record in self:
            if record.stage_id.sequence == 5:
                if not record.selec_sunat and not record.factura:
                    raise UserError(_("Debe registrar la factura"))
                elif record.selec_sunat and not record.factura_sunat:
                    raise UserError(_("Debe registrar la factura Sunat"))

    # ACCION PARA EL ENVIO DE CORREOS AL FINALIZAR EL SERVICIO
    def send_reporte_final(self):
        template_servicio = self.env.ref("pmant.email_template_servicio_finalizado")
        calificacion = self.env.ref("pmant.email_template_calificacion_servicio")

        if template_servicio:
            template_servicio.send_mail(self.id, force_send=True)

        if calificacion:
            calificacion.send_mail(self.id, force_send=True)

    # ACCION PARA EL ENVIO DE REPORTE A LA EMPRESA
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

    # ACCION PARA EL ENVIO DE REPORTE A LA SUCURSAL
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

    # CREAR UN LEAD DENTRO DEL CRM
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

    # SOLICITAR FIRMA AL CLIENTE DEL SERVICIO REALIZADO
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
                "ot_id": self.id,
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
                "ot_id": self.id,
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
                            "name": f"Servicio programado / {record.name}",
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
            else:
                raise UserError(
                    _(
                        "Para crear una Ordne de Trabajo tienes que colocar la fecha programada y la durecion en horas."
                    )
                )

    # ESTA FUNCION EJECUTA MEDIANTE ACCIONES DE SERVIDOR
    def _set_email_programacion(self):
        try:
            fecha_objetivo = date.today() + timedelta(days=2)
            # Buscar las órdenes donde la fecha programada coincide solo en fecha (no en hora)
            ordenes = self.env["maintenance.request"].search(
                [
                    ("schedule_date", ">=", fecha_objetivo),
                    ("schedule_date", "<", fecha_objetivo + timedelta(days=1)),
                ]
            )

            for orden in ordenes:
                correos = []
                if orden.ubicacion and orden.ubicacion.email_jefe:
                    correos.append(orden.ubicacion.email_jefe)
                if orden.ubicacion and orden.ubicacion.email:
                    correos.append(orden.ubicacion.email)
                if orden.empresa and orden.empresa.email:
                    correos.append(orden.empresa.email)

                email_to = ",".join(filter(None, correos))

                template = self.env.ref(
                    "pmant.email_template_custom_sucursal"
                ).with_context(email_to=email_to)

                if template and orden.tarea and orden.schedule_date:
                    template.send_mail(
                        orden.id,
                        force_send=True,
                        email_values={"email_from": orden.employee_id.work_email},
                    )
                else:
                    orden.message_post(
                        body="No se pudo enviar el correo: faltan datos como la tarea o la fecha programada."
                    )

        except Exception as e:
            orden.message_post(body=f"Error al enviar el correo: {str(e)}")

    # ACCION DE VENTANA PARA GENERAR UN ENLACE DE COMPARTIR
    def compartir_ot(self):
        # Obtener la URL base de la configuración de Odoo
        dominio = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        # Obtener el ID activo desde el contexto (o usar active_id si no está disponible)
        active_id = self._context.get("active_id", False)
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


    def _get_cantidad_incidencias(self):
        cant_data = self.env["inconveniente.servicio"].search([("ot_id", "=", self.id)])
        self.cantidad_inconvenientes = len(cant_data)

    def action_view_incidencias(self):
        cant_data = self.env["inconveniente.servicio"].search([("ot_id", "=", self.id)])
        return {
                "name": "Incidencias",
                "type": "ir.actions.act_window",  # ¡Este es el campo que faltaba!
                "domain": [("id", "in", cant_data.ids)],
                "view_mode": "tree,form",  # puedes permitir también la vista formulario
                "res_model": "inconveniente.servicio",
                "context": {"create": False},
            }

    def action_view_ots(self):
        return {
                "name": "Solicitud de Mantenimiento",
                "type": "ir.actions.act_window",  # ¡Este es el campo que faltaba!
                "res_id" : self.id,
                "view_mode": "form",  # puedes permitir también la vista formulario
                "res_model": "maintenance.request",
                "context": {"create": False},
            }


    def action_print_report (self):
        return self.env.ref("pmant.action_mantenimiento_ot").report_action(self)