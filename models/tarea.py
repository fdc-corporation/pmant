# -*- coding: utf-8 -*-
from datetime import datetime, date, timedelta, time
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AdjuntoEvaluacion(models.Model):
    _name = 'adjunto.evaluacion'
    _description = 'Adjuntos de evaluación'

    tarea = fields.Many2one('tarea.mantenimiento', string="Tarea")
    adjuntoimage = fields.Binary(attachment=True)
    comentario = fields.Text()


class EtapaTarea(models.Model):
    _name = "etapa.tarea.mantenimiento"
    _description = "Etapas de Tarea de Mantenimiento"

    name = fields.Char(required=True, string='Nombre')
    sequence = fields.Integer(string='Secuencia', default=1,
                              help="Orden en que se muestran las etapas.")
    dias_promedio = fields.Integer(string="Días de estadía")
    color_error = fields.Integer(string="Color error")
    color_warning = fields.Integer(string="Color warning")


class TipoTarea(models.Model):
    _name = 'tipotarea.mantenimiento'
    name = fields.Char(required=True, string='Nombre')


class Tarea(models.Model):
    _name = 'tarea.mantenimiento'
    _description = 'Tareas de mantenimiento'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ----------------------------
    # Campos principales
    # ----------------------------
    name = fields.Char(required=True, string='Nombre', tracking=True)
    tipo = fields.Many2one('tipotarea.mantenimiento', string="Tipo")
    cliente = fields.Many2one('res.partner', string="Cliente", tracking=True,
                              domain=[('is_company', '=', True)])
    ubicacion = fields.Many2one('res.partner', string="Ubicacion", tracking=True)
    planequipo = fields.One2many('planequipo.mantenimiento', 'tarea', string='Equipo / Plan', required=True)
    clasi1 = fields.Char(string="Clasificacion 1")
    clasi2 = fields.Char(string="Clasificacion 2")
    prioridad = fields.Selection(related="ots.priority")
    adjunto = fields.Binary(attachment=True)
    ots = fields.One2many('maintenance.request', 'tarea', string="ots")
    procesos = fields.One2many('planequipoproceso.mantenimiento', 'tarea', string="Estado de Procesos")
    stage_id = fields.Many2one('etapa.tarea.mantenimiento', string="Etapa", store=True, tracking=True,
                               ondelete='set null', group_expand='_read_group_stage_ids',
                               default=lambda self: self.env["etapa.tarea.mantenimiento"].search([], limit=1).id)
    kanban_state = fields.Selection([
        ('inportante', 'Importante'),
        ('realizado', 'Realizado'),
        ('atrasado', 'Atrasado'),
    ], string='Estado Kanban')
    revisar = fields.Boolean()
    archive = fields.Boolean(related="ots.archive", store=True)
    namefirma = fields.Char(string="Nombre del Firmante")
    dni = fields.Char(string="DNI del Firmante")
    is_admin = fields.Boolean(compute="_is_admin", default=True)
    comentario = fields.Text('Comentario del firmante')
    fecha_entrada = fields.Date(string="Fecha de ingreso", compute="_compute_fecha_entrada", store=False)
    create_user = fields.Many2one('res.users', string='Creado por', default=lambda self: self.env.user)
    compania = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, required=True)
    comentario_tecnico = fields.Text(string="Comentario ingreso")
    adjuntos_evaluaciones = fields.One2many("adjunto.evaluacion", 'tarea', string='Adjuntos de Evaluacion')
    id_tipo = fields.Integer()
    fecha_hoy = fields.Char(string="Fecha Formateada", compute="_compute_fecha_formateada")
    is_evaluacion = fields.Boolean(string="Es Hoja de Recepcion")
    is_tecnico = fields.Boolean(compute='_compute_is_tecnico', string='Is Técnico', store=False)
    firma_evaluacion = fields.Binary(
        string="Firma Evaluación",
        attachment=True,
        compute='_compute_firma_firmante',
        store=True,
        copy=False,
        readonly=False,
    )
    firmante = fields.Char(
        string="Nombre del firmante",
        compute='_compute_firma_firmante',
        store=True,
        copy=False,
        readonly=False,
    )
    comentario_firma = fields.Text('Comentario del firmante')
    action_servicio = fields.Boolean(string="Is init servicio")
    active_servicio = fields.Boolean(string="Tiene Programacion?", compute="_compute_active_servicio")
    fecha_etapa = fields.Date(string="Fecha de movimiento de etapa")
    color = fields.Integer(string='Color')
    sale_order = fields.Many2many("sale.order", string="Orden de venta")
    cotizacion_cantidad = fields.Integer(compute="_compute_total_cotizaciones", store=False)
    notas = fields.Html(string="Notas", sanitize_style=True, sanitize_tags=False)
    user_id = fields.Many2one('res.users', string='Responsable', related='ots.user_id', store=True)
    prioridad = fields.Selection(related="ots.priority", string="Prioridad", store=True)
    count_ots = fields.Integer(string="Cantidad de OTs", compute="_compute_count_ots", store=False)


    # ----------------------------
    # Computed / Constraints
    # ----------------------------
    def search_sale_order(self):
        for res in self:
            sales = self.env["sale.order"].search([("ots", "in", res.id)])
            self.sale_order = sales
            for sale in sales:
                res.notas = sale.template_format_nota(sale) if sale else ""


    @api.depends('ots', 'ots.user_id', 'ots.user_id.employee_id', 'ots.user_id.employee_id.firma')
    def _compute_firma_firmante(self):
        import base64
        for rec in self:
            employee = None
            if rec.ots and rec.ots[0].user_id and rec.ots[0].user_id.employee_id:
                employee = rec.ots[0].user_id.employee_id

            rec.firmante = employee.name if employee else False

            if not employee or not employee.firma:
                rec.firma_evaluacion = False
                continue

            try:
                firma = employee.firma
                if isinstance(firma, bytes):
                    firma = firma.decode('utf-8')
                missing = len(firma) % 4
                if missing:
                    firma += '=' * (4 - missing)
                base64.b64decode(firma, validate=True)
                rec.firma_evaluacion = firma
            except Exception:
                rec.firma_evaluacion = False


    def _compute_count_ots(self):
        for rec in self:
            
            rec.count_ots = len(rec.ots)

    def _compute_total_cotizaciones(self):
        sales = self.env["sale.order"].search([("ots", "in", self.id)])
        self.cotizacion_cantidad = len(sales)
        self.search_sale_order()


    def action_view_cotizaciones(self):
        if not self.sale_order:
            return {'type': 'ir.actions.act_window_close'}
        return {
            "type": "ir.actions.act_window",
            "name": "Ventas",
            "view_mode": "form",
            "res_model": "sale.order",
            "res_id": self.sale_order.id,
            "context": {"create": False},
        }

    def action_print_report(self):
        return self.env.ref("pmant.action_ot_mantenimiento").report_action(self)

    def _read_group_stage_ids(self, stages, domain):
        stage_ids = stages.sudo()._search([], order=stages._order)
        return stages.browse(stage_ids)

    def name_get(self):
        result = []
        for record in self:
            estado = dict(self._fields['state'].selection).get(record.state, '')
            display = f"{record.name} / [{estado}]"
            result.append((record.id, display))
        return result

    @api.depends('ots')
    def _compute_active_servicio(self):
        """Activa 'active_servicio' si la primera OT tiene al menos una hora programada."""
        for record in self:
            record.active_servicio = False
            if record.ots:
                primera_ot = record.ots[0]
                # usar search_count para mejor rendimiento si es necesario
                horas_count = self.env['programacion.mantenimiento'].search_count([('ot_id', '=', primera_ot.id)])
                record.active_servicio = horas_count > 0

    @api.onchange('tipo')
    def tipo_click(self):
        for record in self:
            if record.tipo and record.tipo.name and record.tipo.name.lower().startswith('evalu'):
                record.id_tipo = record.tipo.id
            else:
                record.id_tipo = 0

    @api.model
    def _compute_fecha_formateada(self):
        # Este compute lo convertimos a un método que establece el campo por registro
        # pero mantenemos compatibilidad con tu uso anterior.
        meses = {
            "January": "enero", "February": "febrero", "March": "marzo",
            "April": "abril", "May": "mayo", "June": "junio",
            "July": "julio", "August": "agosto", "September": "septiembre",
            "October": "octubre", "November": "noviembre", "December": "diciembre"
        }
        hoy = datetime.now()
        mes_en = hoy.strftime("%B")
        mes_es = meses.get(mes_en, mes_en)
        fecha_formato = hoy.strftime("Lima, %d de %B del %Y").replace(mes_en, mes_es)
        for record in self:
            record.fecha_hoy = fecha_formato
            # actualizar fecha_hoy en planequipo si existe el campo
            for plan in record.planequipo:
                if 'fecha_hoy' in plan._fields:
                    plan.fecha_hoy = fecha_formato

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        try:
            rec._set_fecha_movimiento()
        except Exception as e:
            _logger.exception("Error al establecer fecha_movimiento en create(): %s", e)
            rec.message_post(body=_("Error al setear fecha de movimiento: %s") % e)
        return rec

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            try:
                self._set_fecha_movimiento()
            except Exception as e:
                _logger.exception("Error en _set_fecha_movimiento desde write(): %s", e)
                self.message_post(body=_("Error al actualizar fecha de movimiento: %s") % e)
        return res

    def _set_fecha_movimiento(self):
        for record in self:
            record.fecha_etapa = fields.Date.today()

    @api.model
    def _cron_fecha_movimiento(self):
        """Cron: colorea tareas según días en la etapa."""
        hoy = fields.Date.today()
        for lead in self.search([]):
            if not lead.fecha_etapa:
                continue
            dias = (hoy - lead.fecha_etapa).days
            etapa = lead.stage_id
            if etapa and etapa.dias_promedio:
                if dias > etapa.dias_promedio:
                    lead.color = etapa.color_error
                elif dias == (etapa.dias_promedio - 1):
                    lead.color = etapa.color_warning

    def _compute_fecha_entrada(self):
        for rec in self:
            rec.fecha_entrada = fields.Date.today()

    def _fecha_ejecutada(self):
        """Marcar fecha ejecutada en planequipo solo cuando aplique"""
        fecha_actual = fields.Date.today()
        for record in self:
            for equipo in record.planequipo:
                if not equipo.is_informe_file:
                    try:
                        equipo.fecha_ejec = fecha_actual
                    except Exception:
                        _logger.exception("No se pudo actualizar fecha_ejec en planequipo %s", equipo.id)

    def _compute_is_tecnico(self):
        for rec in self:
            rec.is_tecnico = self.env.user.has_group('pmant.group_pmant_tecnico')

    # ----------------------------
    # Evento calendario: solo acciones explícitas
    # ----------------------------
    def _evento_calendario_proximo_servicio(self):
        """
        Crea eventos agrupados por fecha para el próximo servicio.
        Los eventos se crean como el usuario Jesús Dávila (correo configurado).
        """
        for rec in self:
            cliente = rec.cliente.name if rec.cliente else "Cliente"
            ubicacion_name = rec.ubicacion.name if rec.ubicacion else False
            group = (self.env.ref('pmant.group_pmant_planner', raise_if_not_found=False) or self.env.ref('pmant.group_pmant_admin', raise_if_not_found=False)) 
            user = False
            # Buscar usuario Jesús Dávila por login
            if group: 
                user = self.env['res.users'].sudo().search([('group_ids', 'in', group.id), ('share', '=', False)], limit=1) 
            # Recolectar partners invitados
            partner_ids = set()
            for ot in rec.ots:
                if ot.user_id and ot.user_id.partner_id:
                    partner_ids.add(ot.user_id.partner_id.id)
                if ot.employee_id and getattr(ot.employee_id, 'user_id', None) and ot.employee_id.user_id.partner_id:
                    partner_ids.add(ot.employee_id.user_id.partner_id.id)
                if ot.empresa:
                    partner_ids.add(ot.empresa.id)
                if ot.ubicacion:
                    partner_ids.add(ot.ubicacion.id)

            if user.partner_id:
                partner_ids.add(user.partner_id.id)
            partner_ids = list(partner_ids)

            # Agrupar planes por fecha
            planes_por_fecha = {}
            for plan in rec.planequipo:
                if not plan.fecha_ejecprox:
                    continue
                equipo_nombre = plan.equipo.name if plan.equipo else "Equipo"
                planes_por_fecha.setdefault(plan.fecha_ejecprox, []).append((plan, equipo_nombre, plan.plan.alarm_ids))

            for fecha, items in planes_por_fecha.items():
                descripcion_equipos = ", ".join([nombre for _, nombre, _ in items])
                start_datetime = datetime.combine(fecha, time(hour=13))
                stop_datetime = datetime.combine(fecha, time(hour=14))

                event_name = f'Proximo servicio - {cliente} / {descripcion_equipos}'

                domain = [
                    ('name', '=', event_name),
                    ('ots_id', '=', rec.ots[0].id if rec.ots else False),
                ]
                existing_event = self.env['calendar.event'].search(domain, limit=1)

                vals_event = {
                    'name': event_name,
                    'start': start_datetime,
                    'stop': stop_datetime,
                    'allday': False,
                    'description': f'Servicios de equipos: {descripcion_equipos}',
                    'partner_ids': [(6, 0, partner_ids)] if partner_ids else False,
                    'location': ubicacion_name,
                    'current_status': 'accepted',
                    'user_id': user.id,
                    'equipos_ids': [(6, 0, [p.equipo.id for p, _, _ in items if p.equipo])]
                }

                try:
                    if existing_event:
                        write_vals = {}
                        if existing_event.description != vals_event['description']:
                            write_vals['description'] = vals_event['description']
                        if existing_event.location != vals_event['location']:
                            write_vals['location'] = vals_event['location']
                        if set(existing_event.partner_ids.ids) != set(partner_ids):
                            write_vals['partner_ids'] = [(6, 0, partner_ids)]
                        if existing_event.start != vals_event['start']:
                            write_vals['start'] = vals_event['start']
                        if set(existing_event.equipos_ids.ids) != set([p.equipo.id for p, _, _ in items if p.equipo]):
                            write_vals['equipos_ids'] = [(6, 0, [p.equipo.id for p, _, _ in items if p.equipo])]

                        if write_vals:
                            existing_event.with_user(user).write(write_vals)
                            _logger.info("Evento actualizado correctamente por %s", user.name)
                    else:
                        create_vals = {k: v for k, v in vals_event.items() if v}
                        if rec.ots:
                            create_vals['ots_id'] = rec.ots[0].id

                        event = self.with_user(user).env['calendar.event'].create(create_vals)
                        _logger.info("Evento creado correctamente por %s", user.name)

                        # Agregar alarmas si hay
                        for _, _, alertas in items:
                            if alertas:
                                event.sudo().alarm_ids = [(4, a.id) for a in alertas]

                        # Enviar invitación como Jesús Dávila
                        event.sudo().action_sendmail()
                        eventos = self.env["mail.mail"].sudo().search([("res_id", "=", event.id), ("model", "=", "calendar.event"), ("state", "=", "outgoing")])
                        for mail in eventos:
                            mail.sudo().action_send_and_close()
 
                except Exception as e:
                    _logger.exception("❌ Error creando/actualizando evento calendario para tarea %s: %s", rec.id, e)
                    rec.message_post(body=_("⚠️ Error al crear evento de calendario: %s") % e)

    # ----------------------------
    # Email / Reporte / Firma
    # ----------------------------
    def action_send_email_recepcion(self):
        template = self.env.ref('pmant.email_template_hoja_recepcion', raise_if_not_found=False)
        statement_report_action = self.env.ref('pmant.action_reporte_recepcion', raise_if_not_found=False)
        ir_actions_report = self.env['ir.actions.report'].sudo()

        if not template or not statement_report_action:
            raise UserError(_("No se encuentra la plantilla o el reporte configurado."))

        # Abrir composer con contexto para el usuario (mantener comportamiento actual)
        for record in self:
            try:
                content, _ = ir_actions_report._render_qweb_pdf(statement_report_action, [record.id])
            except Exception as e:
                _logger.exception("Error generando PDF para hoja de recepción %s: %s", record.id, e)
                raise UserError(_("No se pudo generar el PDF: %s") % e)

            ctx = {
                'default_model': 'tarea.mantenimiento',
                'default_res_ids': [record.id],
                'default_use_template': True,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',
                'force_email': True,
            }

            return {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'mail.compose.message',
                'views': [(False, 'form')],
                'view_id': False,
                'target': 'new',
                'context': ctx,
            }

    def create_ot(self):
        for record in self:
            if not record.tipo:
                raise ValidationError(_("El campo 'Tipo de Servicio' es obligatorio para programar la tarea."))
            if record.planequipo:
                for plan in record.planequipo:
                    if not plan.plan:
                        raise ValidationError(_("El campo 'Plan de Tarea' es obligatorio para programar la tarea."))

        self.stage_id = self.env['etapa.tarea.mantenimiento'].search([], order='sequence asc', limit=1).id
        return {
            "type": "ir.actions.act_window",
            "name": "Crear Solicitud de Mantenimiento",
            "res_model": "maintenance.request",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_name": self.name,
                "default_tarea": self.id,
                "default_empresa": self.cliente.id if self.cliente else False,
                "default_ubicacion": self.ubicacion.id if self.ubicacion else False,
                "default_notas_venta": self.notas,
                "default_schedule_date": datetime.now(),
                "default_order_compra": self.oc_id.id if 'oc_id' in self._fields and self.oc_id else False,
            },
        }   

    def init_servicio(self):
        for record in self:
            if record.ots:
                record.action_servicio = True
                hoja = self.env["programacion.mantenimiento"].search([("ot_id", "=", record.ots[0].id), ("fecha_inicio", "=", False)], limit=1)
                if hoja:
                    hoja.fecha_inicio = datetime.now()
                # Cambiar etapa OT (buscar stage por sequence)
                stage = self.env["maintenance.stage"].search([("sequence", "=", 2)], limit=1)
                if stage and record.ots:
                    record.ots[0].stage_id = stage.id

    def cancel_servicio(self):
        for record in self:
            if not record.ots:
                continue
            horas = self.env["programacion.mantenimiento"].search([("ot_id", "=", record.ots[0].id), ("fecha_fin", "=", False)], limit=1)
            return {
                "type": "ir.actions.act_window",
                "name": "Finalizar actividad",
                "res_model": "wizars.inconvenientes",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_programacion_id": horas.id if horas else False,
                    "default_ot_id": record.ots[0].id if record.ots else False,
                    "default_tarea_id": record.id,
                },
            }

    def crm_oportunidad_create(self):
        for rec in self:
            equipos = rec.planequipo.mapped("equipo.id") if rec.planequipo else []
            valores = {
                "name": rec.name,
                "user_id": rec.create_user.id if rec.create_user else False,
                "partner_id": rec.cliente.id if rec.cliente else False,
                "ubicacion": rec.ubicacion.id if rec.ubicacion else False,
                "orden_trabajo": rec.id,
                "equipo_tarea": [(6, 0, equipos)],
            }
            lead = self.env["crm.lead"].create(valores)
            rec.oportunidad = lead.id

    # ----------------------------
    # Utilidades / Validaciones
    # ----------------------------
    def _set_fecha_movimiento_manual(self):
        """Método público para setear fecha de movimiento (llamar explícitamente)."""
        self._set_fecha_movimiento()

    def action_trigger_proximo_servicio(self):
        """Método público para generar/actualizar eventos de próximo servicio.
        Llamar desde botón o cron, nunca automáticamente en read/compute."""
        self._evento_calendario_proximo_servicio()

    # ----------------------------
    # REDIREC VIEWS
    # ----------------------------
    def action_view_services (self):
        return {
            "type": "ir.actions.act_window",
            "name": "Servicios",
            "view_mode": "form",
            "res_model": "maintenance.request",
            "res_id": self.ots[0].id,
            "context": {"create": False},
        }