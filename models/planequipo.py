from odoo import models, fields, api, _
from datetime import datetime, timedelta
import base64
from odoo.exceptions import UserError
from odoo import http
from odoo.http import request
import requests
from bs4 import BeautifulSoup

class PlanEquipo(models.Model):
    _name = 'planequipo.mantenimiento'

    name = fields.Char(compute='_generate_name')
    plan = fields.Many2one('plan.mantenimiento', string='Plan de Tarea')
    equipo = fields.Many2one('maintenance.equipment', string='Equipo', required=True)
    ubicacion = fields.Many2one('res.partner', string='Ubicacion' , default=lambda self: self.env.get('default_ubicacion'))
    cliente = fields.Many2one('res.partner', string='Cliente', default=lambda self: self.env.get('default_cliente'))
    tarea = fields.Many2one('tarea.mantenimiento', string='Tarea', required=True, default=lambda self: self.env.get('default_tarea'))
    ots = fields.One2many('maintenance.request', 'tarea', related="tarea.ots")
    procesos = fields.One2many('planequipoproceso.mantenimiento', 'planequipo', string="Procesos a Utilizar")
    fecha_ejec = fields.Date(string="Fecha Ejecutada", store=True)
    is_admin = fields.Boolean(compute="_generate_tecnico", default=True)
    creador_id = fields.Integer(compute="_generate_tecnico")
    fecha_ejecprox = fields.Datetime(store=True)
    avisado = fields.Boolean(default=False)
    estado = fields.Char(string="Estado", related="ots.stage_id.name")
    fecha_hoy = fields.Char(string="Fecha Formateada")
    
    voltaje_ids = fields.One2many("voltaje.linea","planequipo_id", string="Lecturas de Voltaje")
    amperaje_ids = fields.One2many('amperaje.linea',"planequipo_id", string="Lecturas de Amperaje")
    nota_mantenimiento = fields.Html(
        string="Conclusiones",
        default=lambda self: self._default_nota_mantenimiento()
    )
    nota_recomendaciones = fields.Html(string="Recomendaciones")
    parametro_ids = fields.One2many("paremetros.operacion","planequipo_id", string="")
    nota_observaciones = fields.Html(string="Observaciones general")
    is_informe_file = fields.Boolean(string="Subir Informe Tecnico", default=False)
    informe_file = fields.Binary(string="Informe Técnico", attachment=True)
    informe_filename = fields.Char(string="Nombre del archivo")
    stage_informe = fields.Selection([("registrado","Registrado"),("sin_realizar","Sin Realizar")], string="Estado del Informe", default="sin_realizar")
    evento = fields.Many2one('calendar.event', string='Evento relacionado')


    def data_parametros(self):
        return [
            {"paremetro_id": "Horas Marcha", "unidad_medida": "Horas"},
            {"paremetro_id": "Horas Carga", "unidad_medida": "Horas"},
            {"paremetro_id": "Relé de carga", "unidad_medida": ""},
            {"paremetro_id": "Temperatura de salida de elemento 1", "unidad_medida": "°C"},
            {"paremetro_id": "Temperatura de salida de elemento 2", "unidad_medida": "°C"},
            {"paremetro_id": "Temperatura ambiente", "unidad_medida": "°C"},
            {"paremetro_id": "Temperatura de refrigeración", "unidad_medida": "°C"},
            {"paremetro_id": "Presión de salida", "unidad_medida": "Bar"},
            {"paremetro_id": "Presión de aceite", "unidad_medida": "Bar"},
            {"paremetro_id": "Dp tanque separador", "unidad_medida": "Bar"},
            {"paremetro_id": "Dp entrada de aire", "unidad_medida": "Bar"},
            {"paremetro_id": "Nivel de aceite", "unidad_medida": ""},
            {"paremetro_id": "Estado del radiador", "unidad_medida": ""},
        ]

    @api.onchange("informe_file")
    def _onchange_informe_file(self):
        if self.informe_file:
            self.stage_informe = "registrado"
        else:
            self.stage_informe = "sin_realizar"

    def _default_nota_mantenimiento(self):
        return """
        
        """

    @api.model
    def create(self, vals):
        vals.setdefault('cliente', self.env.context.get('default_cliente'))
        vals.setdefault('ubicacion', self.env.context.get('default_ubicacion'))
        vals.setdefault('tarea', self.env.context.get('default_tarea'))

        parametro_commands = []
        if not vals.get('parametro_ids'):
            for data in self.data_parametros():
                parametro_commands.append((
                    0, 0,
                    {
                        'paremetro_c': data['paremetro_id'],   # (mantengo tu nombre de campo)
                        'medida_c': data['unidad_medida'],
                    }
                ))
            vals['parametro_ids'] = parametro_commands

        record = super(PlanEquipo, self).create(vals)
        return record

    @api.depends('fecha_ejec')
    def _generate_tecnico(self):
        for record in self:
            record.creador_id = record.equipo.create_uid.id
            record.is_admin = self.env.user.has_group('pmant.group_pmant_admin')


            # if record.fecha_ejec:
            #     fecha_prox = datetime.strptime(str(record.fecha_ejec), '%Y-%m-%d')
            #     fecha_prox += timedelta(days=(record.plan.frecuencia * record.plan.tipo.dias))
            #     record.fecha_ejecprox = fecha_prox


    @api.onchange("fecha_ejecprox")
    def _onchange_fecha_ejecprox(self):
        if self.fecha_ejecprox:
            self.equipo.fecha_prox = self.fecha_ejecprox
            self._create_event_proximo_mantenimiento(fecha=self.fecha_ejecprox)


    def _create_event_proximo_mantenimiento(self, fecha):
        for record in self:

            partner_ids = set()

            # Iterar OTS correctamente (One2many)
            for ot in record.ots:

                if ot.user_id and ot.user_id.partner_id:
                    partner_ids.add(ot.user_id.partner_id.id)

                if ot.employee_id and ot.employee_id.user_id and ot.employee_id.user_id.partner_id:
                    partner_ids.add(ot.employee_id.user_id.partner_id.id)

                if ot.empresa:
                    partner_ids.add(ot.empresa.id)

                if ot.ubicacion:
                    partner_ids.add(ot.ubicacion.id)

            partner_ids = list(partner_ids)

            # Datos seguros
            cliente = record.tarea.cliente.name if record.tarea.cliente else "Cliente"
            ubicacion = record.tarea.ubicacion.name if record.tarea.ubicacion else "Ubicación"
            fecha_cierre = fecha + timedelta(hours=3)

            # SI existe evento → actualizar
            if record.evento:
                record.evento.write({
                    'name': f'Próximo servicio - {cliente}',
                    'start': fecha,
                    'stop': fecha_cierre,
                    'allday': False,
                    'ots_id': record.ots[0].id if record.ots else False,
                    'location': ubicacion,
                    'description': f'Servicios de equipos: {record.equipo.name}',
                    'partner_ids': [(6, 0, partner_ids)],
                })
                continue

            # SI NO existe → crear
            event = self.env['calendar.event'].create({
                'name': f'Próximo servicio - {cliente}',
                'start': fecha,
                'stop': fecha_cierre,
                'allday': False,
                'ots_id': record.ots[0].id if record.ots else False,
                'location': ubicacion,
                'description': f'Servicios de equipos: {record.equipo.name}',
                'partner_ids': [(6, 0, partner_ids)],
            })

            record.evento = event



    def _generate_name(self):
        for record in self:
            if record.fecha_ejec:
                fechaj = " - " + str(record.fecha_ejec)
            else:
                fechaj = " - EN PROCESO"
            record.name = f"{record.equipo.name} - {record.plan.name}{fechaj}"

    @api.onchange('plan')
    def _onchange_procesos(self):
        if self.plan and self.plan.proceso:
            self.procesos = [(5, 0, 0)]  # Limpia los procesos existentes
            procesos_list = []
            for proceso_plan in self.plan.proceso:
                procesos_list.append((0, 0, {
                    'proceso': proceso_plan.id,
                    'grupo': proceso_plan.grupo.id,
                    'planequipo': self.id,
                    'tarea': self.tarea.id,
                    'plan': self.plan.id,
                }))
            self.procesos = procesos_list





   
    def create_certificado_operatividad(self):
        ir_actions_report_sudo = self.env["ir.actions.report"].sudo()
        statement_report_action = self.env.ref("pmant.action_reporte_cert_operatividad")
        for statement in self:
            statement_report = statement_report_action.sudo()
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(
                statement_report, res_ids=statement.ids
            )

            # Crear el adjunto con el PDF generado
            attachment = self.env["ir.attachment"].create(
                {
                    "name": "Certificado " + self.equipo.name,
                    "type": "binary",
                    "mimetype": "application/pdf",
                    "raw": content,
                    "res_model": "sign.template",  # Asociar al modelo sign.template
                    "res_id": None,
                }
            )

            vals_template = {
                "name": "Certificado " + self.equipo.name,
                "attachment_id": attachment.id,  # Asociar el adjunto creado
                "equipo_id": self.equipo.id,
            }

            vals_template.pop("attachment_count", None)

            sign_template = self.env["sign.template"].create(vals_template)

            # Redirigir al formulario del sign.template
        return {
            "type": "ir.actions.act_window",
            "name": "Certificado " + self.equipo.name,
            "res_model": "sign.template",
            "view_mode": "kanban",  # Esto es para ver primero la lista (tree)
            "target": "current",
        }


    def create_report_equipo (self) : 
        return self.env.ref('pmant.action_report_equipo').report_action(self)
