from odoo import models, fields, api, exceptions
from datetime import date, datetime, timedelta, time
from odoo.exceptions import UserError
import logging
from odoo.exceptions import UserError
import base64
_logger = logging.getLogger(__name__)


class AdjuntoEvaluacion (models.Model):
    _name = 'adjunto.evaluacion'
    _description = 'Adjuntos de evaluación'

    tarea  = fields.Many2one('tarea.mantenimiento', string="Tarea")
    adjuntoimage     = fields.Binary()
    comentario       = fields.Text()

class EstapaTarea(models.Model):
    _name = "etapa.tarea.mantenimiento"
    _description = "Etapas de Tarea de Mantenimiento"

    name = fields.Char(size=60, required=True, string='Nombre')
    sequence = fields.Integer(string='Secuencia', default=1, help="Determina el orden en que se muestran las etapas de la tarea de mantenimiento. Las etapas con menor número se mostrarán primero.")
    dias_promedio    = fields.Integer(string="Dias de estadia")
    color_error     = fields.Integer(string="Color error")
    color_warning   = fields.Integer(string="Color warning")
    fold = fields.Boolean(string="Folded in Kanban", default=False)

class TipoTarea(models.Model):
   _name = 'tipotarea.mantenimiento'
   name = fields.Char(size=25, required=True, string='Nombre')

class Tarea(models.Model):
    _name = 'tarea.mantenimiento'
    _description = 'Tareas de mantenimiento'

    _inherit = ['mail.thread', 'mail.activity.mixin']  # Hereda de mail.thread y mail.activity.mixin
    
    name = fields.Char(size=60, required=True, string='Nombre', tracking=True)
    tipo = fields.Many2one('tipotarea.mantenimiento', string="Tipo")
    cliente = fields.Many2one('res.partner', string="Cliente", tracking=True, domain=[('is_company', '=', 'True')], required=False)
    ubicacion = fields.Many2one('res.partner', string="Ubicacion", tracking=True)
    planequipo = fields.One2many('planequipo.mantenimiento', 'tarea', string='Equipo / Plan', required=True, store=True)
    clasi1 = fields.Char(size=50, string="Clasificacion 1")
    clasi2 = fields.Char(size=50, string="Clasificacion 2")
    prioridad = fields.Selection(related="ots.priority")
    adjunto = fields.Binary()
    ots = fields.One2many('maintenance.request', 'tarea', string="ots")
    procesos = fields.One2many('planequipoproceso.mantenimiento', 'tarea', string="Estado de Procesos")
    state_id = fields.Many2one('maintenance.stage', string="Etapa", store=True, tracking=True, ondelete='set null')
    stage_id = fields.Many2one(
        'etapa.tarea.mantenimiento',
        string="Etapa",
        store=True,
        tracking=True, group_expand='_group_expand_stages',
        ondelete='set null',copy=False, index=True,
        default=lambda self: self.env["etapa.tarea.mantenimiento"].search([], limit=1).id
    )
    kanban_state = fields.Selection([
        ('inportante', 'Importante'),
        ('realizado', 'Realizado'),
        ('atrasado', 'Atrasado'),
    ], string='Estado Kanban', default='normal')
    revisar = fields.Boolean()
    archive = fields.Boolean(related="ots.archive", store=True)
    namefirma = fields.Char(string="Nombre del Firmante")
    dni = fields.Char(string="DNI del Firmante")
    is_admin = fields.Boolean(compute="_is_admin", default=True)
    comentario = fields.Text('Comentario del firmante')
    creado_por = fields.Many2one('res.users', string="Creado por")
    fecha_entrada = fields.Date( string="Fecha de ingreso", compute="_fecha_entrada")
    create_user     = fields.Many2one('res.users', string='Creado por', default=lambda self: self.env.user)
    compania        = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    comentario_tecnico = fields.Text(string="Comentario ingreso")
    adjuntos_evaluaciones     = fields.One2many("adjunto.evaluacion", 'tarea', string='Adjuntos de Evaluacion')
    id_tipo = fields.Integer()
    fecha_hoy = fields.Char(string="Fecha Formateada", compute="_fecha_formateada")
    is_evaluacion = fields.Boolean(string="Es Hoja de Recepcion")
    oc_id = fields.Many2one('oc.compras', string="OC")
    is_tecnico = fields.Boolean(
        compute='_compute_is_tecnico',
        string='Is Técnico',
        store=False
    )
    firma_evaluacion = fields.Binary()
    firmante = fields.Char(string="Nombre del firmante")
    comentario_firma = fields.Text('Comentario del firmante')
    action_servicio = fields.Boolean(string="Is init servicio")

    active_servicio =  fields.Boolean(string="Tiene Programacion?", compute="_set_action")
    fecha_etapa = fields.Date(string="Fecha de movimiento de etapa")
    color = fields.Integer(
        string='Color',
        help='Color de la tarea, utilizado en el kanban y en la vista de lista.'
    )


    @api.model
    def _group_expand_stages(self, stages, domain, order):
        return self.env['etapa.tarea.mantenimiento'].search([], order=order)


    def _set_action(self):
        """Activa 'active_servicio' si la primera OT tiene al menos una hora programada."""
        for record in self:
            record.active_servicio = False
            print("INICIO DE LA FUNCION ACTIVESERVICIO")
            if record.ots:
                primera_ot = record.ots[0].tab_horas
                print("DATOPS DE LA PROGRAMACION")
                print(primera_ot)
                print(len(primera_ot))                
                if len(primera_ot) > 0:
                    record.active_servicio = True

    @api.onchange('tipo')
    def tipo_click(self):
        for record in self:
            if record.tipo.name == 'Evaluación' or record.tipo.name == 'Evaluacion':
                record.id_tipo = record.tipo.id
            else:
                record.id_tipo = 0

    @api.model
    def _fecha_formateada(self):
        # Diccionario para traducir el mes al español
        meses_espanol = {
            "January": "enero", "February": "febrero", "March": "marzo",
            "April": "abril", "May": "mayo", "June": "junio",
            "July": "julio", "August": "agosto", "September": "septiembre",
            "October": "octubre", "November": "noviembre", "December": "diciembre"
        }
        
        # Obtener la fecha actual
        fecha_actual = datetime.now()
        # Formatear la fecha con el mes en inglés y luego traducir
        fecha_formateada = fecha_actual.strftime("Lima, %d de %B del %Y")
        
        # Obtener el nombre del mes en inglés y buscar su traducción en el diccionario
        mes_en_ing = fecha_actual.strftime("%B")
        mes_en_espanol = meses_espanol.get(mes_en_ing, mes_en_ing)  # Usa el mes en inglés si no se encuentra en el diccionario
        fecha_formateada = fecha_formateada.replace(mes_en_ing, mes_en_espanol)

        # Asignar la fecha formateada a los registros
        for record in self:
            record.fecha_hoy = fecha_formateada
            for plan in record.planequipo:
                plan.fecha_hoy = fecha_formateada  # Asegúrate de que el campo exista en el modelo relacionado

        
    @api.model
    def create(self, vals):
        record = super(Tarea, self).create(vals)
        if 'create_user' not in vals:
            vals['create_user'] = self.env.user.id
        if 'compania' not in vals:
            vals['compania'] = self.env.company.id
            # Notificar a los usuarios del grupo específico
        group_xml_id = 'pmant.group_pmant_admin'  # Ajusta si tu módulo se llama distinto
        group = self.env.ref(group_xml_id)

        if group:
            for user in group.users:
                record.message_post(
                    body=(
                        f"{user.name}, se te ha asignado una nueva tarea "
                        f"{record.name}. Debes programarla y crear la OT correspondiente."
                    ),
                    partner_ids=[user.partner_id.id],
                )

        record._set_fecha_movimiento()
        return record

    def write(self, vals):
        res = super().write(vals)
        if "stage_id" in vals:
            self._set_fecha_movimiento()
        return res

    def _set_fecha_movimiento(self):
        for record in self:
            record.fecha_etapa = fields.Date.today()

    @api.model
    def _cron_fecha_movimiento(self):
        leads = self.search([])
        hoy = fields.Date.today()
        for lead in leads:
            dias = (hoy - lead.fecha_etapa).days
            if lead.stage_id.dias_promedio:
                if dias > lead.stage_id.dias_promedio:
                    lead.color = lead.stage_id.color_error
                elif dias == (lead.stage_id.dias_promedio - 1):
                    lead.color = lead.stage_id.color_warning
                    
    def _fecha_entrada(self):
        for record in self:
            record.fecha_entrada = fields.Date.today()
                    
    def _fecha_ejecutada(self):
        fecha_actual = fields.Date.today()
        for record in self:
            for equipo in record.planequipo:
                equipo.write({'fecha_ejec': fecha_actual})


    def _compute_is_tecnico(self):
        for record in self:
            record.is_tecnico = self.env.user.has_group('pmant.group_pmant_tecnico')

    def _evento_calendario_proximo_servicio(self):
        for record in self:
            cliente = record.cliente.name
            ubicacion = record.ubicacion.name
            planes_por_fecha = {}
            partner_ids = set()
            
            for ot in record.ots:
                if ot.user_id:
                    partner_ids.add(ot.user_id.partner_id.id)
                if ot.employee_id:
                    partner_ids.add(ot.employee_id.user_id.partner_id.id)
                if ot.empresa:
                    partner_ids.add(ot.empresa.id)
                if ot.ubicacion:
                    partner_ids.add(ot.ubicacion.id)
            partner_ids = list(partner_ids)

            for plan in record.planequipo:
                fecha_ejecprox = plan.fecha_ejecprox
                equipo = plan.equipo.name
                alertas = plan.plan.alarm_ids
                if fecha_ejecprox not in planes_por_fecha:
                    planes_por_fecha[fecha_ejecprox] = []

                planes_por_fecha[fecha_ejecprox].append((equipo, alertas))
            # for planequipo in self.planequipo:
            #     print("DATOS DEL EQUIPO FECHAS  PROXIMAS DE SERVICIO")
            #     print(planequipo.equipo.fecha_prox)
            for fecha, equipos_alertas in planes_por_fecha.items():
                descripcion_equipos = ", ".join([equipo for equipo, _ in equipos_alertas])
                
                existing_event = self.env['calendar.event'].search([
                    ('name', '=', f'Proximo servicio - {cliente}'),
                    ('start', '=', fecha),
                    ('ots_id', '=', record.ots[0].id if record.ots else False),
                ], limit=1)
                
                if not existing_event :
                    event = self.env['calendar.event'].create({
                        'name': f'Proximo servicio - {cliente}',
                        'start': fecha,
                        'stop': fecha,
                        'allday': False,
                        'ots_id': record.ots[0].id if record.ots else False,
                        'location': ubicacion,
                        'description': f'Servicios de equipos: {descripcion_equipos}',
                        'partner_ids': [(6, 0, partner_ids)],
                    })

                    for _, alertas in equipos_alertas:
                        if alertas:
                            event.alarm_ids = [(4, alarma.id) for alarma in alertas]

    def action_send_email_recepcion(self):
        template = self.env.ref('pmant.email_template_hoja_recepcion')
        statement_report_action = self.env.ref('pmant.action_reporte_recepcion')
        ir_actions_report_sudo = self.env['ir.actions.report'].sudo()

        if not template or not statement_report_action:
            raise UserError("No se encuentra la plantilla o el reporte configurado.")

        for record in self:
            # Generar el reporte PDF
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(
                statement_report_action, [record.id]
            )

            # Crear el archivo adjunto
            # attachment = self.env['ir.attachment'].create({
            #     'name': f'Hoja_Recepcion_{record.name}.pdf',  # Nombre del archivo
            #     'type': 'binary',
            #     'datas': base64.b64encode(content).decode('utf-8'),  # Codificar el PDF a base64
            #     'res_model': record._name,  # Modelo relacionado
            #     'res_id': record.id,  # ID del registro relacionado
            #     'mimetype': 'application/pdf',
            #     'public': True,
            # })

            # Preparar el contexto para enviar el correo
            ctx = {
                'default_model': 'tarea.mantenimiento',  # Modelo actual
                'default_res_ids': [record.id],  # ID del registro
                'default_use_template': True,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',  # Modo de composición
                'force_email': True,
                # 'attachment_ids': [(4, attachment.id)],  # Agregar el archivo adjunto
            }

            # Verificar el contexto (Debugging)
            print("Contexto de envío:", ctx)

            # Retornar la acción para abrir el asistente de composición de correos
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
        ot = self.env["maintenance.request"].create({
            "name": self.name,
            "tarea": self.id,
            "empresa": self.cliente.id,
            "ubicacion": self.ubicacion.id,
            "order_compra" : self.oc_id.id
        })

        self.oc_id.ot_servicio = ot.id

        return {
            "type" : "ir.actions.act_window",
            "name" : "Crear Solicitud de Mantenimiento",
            "res_model" : "maintenance.request",
            "view_mode" : "form",
            "res_id" : ot.id,

        }


    def init_servicio (self):
        for record in self:
            if record.ots:
                record.action_servicio = True
                horas = self.env["programacion.mantenimiento"].search([("ot_id", "=", record.ots[0].id), ("fecha_inicio", "=", False)], limit=1)
                horas.fecha_inicio = datetime.now()
                record.ots[0].stage_id = self.env["maintenance.stage"].search([("sequence", "=", 2)], limit=1).id
                # hoja_horas._compute_horas_trabajado()
        # return ''
    
    def cancel_servicio(self):
        for record in self:
            horas = self.env["programacion.mantenimiento"].search([("ot_id", "=", record.ots[0].id), ("fecha_inicio", "!=", False)], limit=1)
            return {
                "type": "ir.actions.act_window",
                "name": "Finalizar actividad",
                "res_model": "wizars.inconvenientes",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_programacion_id": horas.id,  # si estás dentro de programacion.mantenimiento
                    "default_ot_id": self.id,  # si estás dentro de programacion.mantenimiento
                },
            }

    # @api.multi
    # @api.onchange('state_id')
    # def fecha_prox_equipo(self):
    #     for record in self:
    #         print('----------------------------------')
    #         print(self.id)
    #         # Busca una solicitud de mantenimiento relacionada con la tarea actual
    #         ot = self.env['maintenance.request'].search([("tarea.id", "=", self.id)])
    #         print('----------------------------------')
    #         print(ot)
    #         if ot:
                
    #             ot.stage_id = record.state_id.id
    #             print('----------------------------------')
    #             print(ot.stage_id)
    #        # Si el estado tiene una secuencia específica (en este caso, 3)
    #         if record.state_id.sequence == 3:
    #             # Llama a métodos internos para realizar acciones adicionales
    #             self._notify_on_change()
    #             self._fecha_ejecutada()
    #             self._evento_calendario_proximo_servicio()

