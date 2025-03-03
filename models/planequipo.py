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
    ubicacion = fields.Many2one('res.partner', string='Ubicacion')
    cliente = fields.Many2one('res.partner', string='Cliente')
    tarea = fields.Many2one('tarea.mantenimiento', string='Tarea', required=True)
    ots = fields.One2many('maintenance.request', 'tarea', related="tarea.ots")
    procesos = fields.One2many('planequipoproceso.mantenimiento', 'planequipo', string="Procesos a Utilizar")
    fecha_ejec = fields.Date(string="Fecha", readonly="True", store=True)
    is_admin = fields.Boolean(compute="_generate_tecnico", default=True)
    creador_id = fields.Integer(compute="_generate_tecnico")
    fecha_ejecprox = fields.Date(compute="_generate_tecnico", store=True)
    avisado = fields.Boolean(default=False)
    estado = fields.Char(string="Estado", related="tarea.state_id.name")
    fecha_hoy = fields.Char(string="Fecha Formateada")


    @api.model
    def create(self, vals):
        # Usa valores predeterminados del contexto si no están definidos explícitamente
        vals['cliente'] = vals.get('cliente', self.env.context.get('default_cliente'))
        vals['ubicacion'] = vals.get('ubicacion', self.env.context.get('default_ubicacion'))
        vals['tarea'] = vals.get('tarea', self.env.context.get('default_tarea'))
        return super(PlanEquipo, self).create(vals)

    @api.depends('fecha_ejec')
    def _generate_tecnico(self):
        for record in self:
            record.creador_id = record.equipo.create_uid.id
            record.is_admin = self.env['res.users'].has_group('pmant.group_pmant_admin')

            if record.fecha_ejec:
                fecha_prox = datetime.strptime(str(record.fecha_ejec), '%Y-%m-%d')
                fecha_prox += timedelta(days=(record.plan.frecuencia * record.plan.tipo.dias))
                record.fecha_ejecprox = fecha_prox

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
                    'planequipo': self.id,
                    'tarea': self.tarea.id,
                    'plan': self.plan.id,
                }))
            self.procesos = procesos_list



    def _create_certificado_operatividad(self):
        ir_actions_report_sudo = self.env['ir.actions.report'].sudo()
        statement_report_action = self.env.ref('pmant.action_reporte_cert_operatividad')
        for statement in self:
            statement_report = statement_report_action.sudo()
            content, _content_type = ir_actions_report_sudo._render_qweb_pdf(statement_report, res_ids=statement.ids)
            certificado = self.env['ir.attachment'].create({
                'name': "Certificado-operatividad-" + statement.equipo.name + ".pdf",
                'type': 'binary',
                'mimetype': 'application/pdf',
                'raw': content,
                'res_model': statement._name,
                'res_id': statement.id,
                'id_equipo': statement.equipo.id,
            })

            statement.equipo.certificados = [(4, certificado.id)]




   
    def create_certificado_operatividad(self):
        self._create_certificado_operatividad()
        return self.env.ref('pmant.action_reporte_cert_operatividad').report_action(self)
