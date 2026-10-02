from odoo import models, fields, api, _
from datetime import datetime, timedelta
import base64
from odoo.exceptions import UserError
from odoo import http
from odoo.http import request
import requests
from bs4 import BeautifulSoup


class VoltajeLinea(models.Model):
    _name = "voltaje.linea"

    l1_l2 = fields.Float("L1/L2")
    l2_l3 = fields.Float("L2/L3")
    l1_l3 = fields.Float("L1/L3")
    l1_gnd = fields.Float("L1/GND")
    l2_gnd = fields.Float("L2/GND")
    l3_gnd = fields.Float("L3/GND")
    supply = fields.Float("Supply")
    planequipo_id = fields.Many2one('planequipo.mantenimiento', string="Plan equipo")

class AmperajeLinea(models.Model):
    _name = 'amperaje.linea'
    _description = 'Medición de amperaje por línea y fase'

    linea = fields.Char(string='Línea')

    carga_linea = fields.Float("Carga Línea")
    descarga_linea = fields.Float("Descarga Línea")

    fase = fields.Char("Fase")
    carga_fase = fields.Char("Carga Fase")
    descarga_fase = fields.Char("Descarga Fase")
    planequipo_id = fields.Many2one('planequipo.mantenimiento', string="Plan equipo")


class ModeluParametro(models.Model):
    _name = "parametro.modulo"
    _description = "Parametros de modulo"

    name = fields.Char(string="Nombre")
class UnidadMedidaModulo(models.Model):
    _name = 'unidad.medida.modulo'
    _description = 'Unidad de Medida del Parámetro'

    name = fields.Char(string="Unidad", required=True)



class ParametrosOperacion (models.Model):
    _name = 'paremetros.operacion'
    _descripcion = "Parámetros de operación del compresor"

    paremetro_c = fields.Char( string="Párametros del modulo")
    paremetro_id = fields.Many2one("parametro.modulo", string="Párametros del modulo")
    valor_trabajo = fields.Char(string="Valores de trabajo")
    valor_parada = fields.Char(string="Valores de parada")
    unidad_medida = fields.Many2one("unidad.medida.modulo", string="Unidad de medida")
    medida_c = fields.Char(string="Unidad de medida")
    planequipo_id = fields.Many2one('planequipo.mantenimiento', string="Plan equipo")
class PlanEquipo(models.Model):
    _name = 'planequipo.mantenimiento'

    name = fields.Char(compute='_generate_name')
    plan = fields.Many2one('plan.mantenimiento', string='Plan de Tarea')
    equipo = fields.Many2one('maintenance.equipment', string='Equipo', required=True)
    ubicacion = fields.Many2one('res.partner', string='Ubicacion', store=True)
    cliente = fields.Many2one('res.partner', string='Cliente', store=True)
    tarea = fields.Many2one('tarea.mantenimiento', string='Tarea', required=True)
    ots = fields.One2many('maintenance.request', 'tarea', related="tarea.ots")
    procesos = fields.One2many('planequipoproceso.mantenimiento', 'planequipo', string="Procesos a Utilizar")

    fecha_ejec = fields.Date(string="Fecha Ejecutada", store=True)
    is_admin = fields.Boolean(compute="_generate_tecnico", default=True)
    creador_id = fields.Integer(compute="_generate_tecnico")
    fecha_ejecprox = fields.Date(compute="_generate_tecnico", store=True)
    avisado = fields.Boolean(default=False)
    estado = fields.Char(string="Estado", related="ots.stage_id.name")
    fecha_hoy = fields.Char(string="Fecha Formateada")
    nota_recomendaciones = fields.Html(string="Recomendaciones")
    nota_mantenimiento = fields.Html(
        string="Conclusiones",
    )
    nota_observaciones = fields.Html(string="Observaciones general")
    is_informe_file = fields.Boolean(string="Subir Informe Tecnico", default=False)
    informe_file = fields.Binary(string="Informe Técnico", attachment=True)
    informe_filename = fields.Char(string="Nombre del archivo")
    # decibel_equipo_ids = fields.One2many('decibel.equipo', 'planequipo_id', string="Decibel del equipo")
    require_repuestos = fields.Boolean(string="Requiere repuestos", default=False)
    voltaje_ids = fields.One2many("voltaje.linea","planequipo_id", string="Lecturas de Voltaje")
    amperaje_ids = fields.One2many('amperaje.linea',"planequipo_id", string="Lecturas de Amperaje")
    parametro_ids = fields.One2many("paremetros.operacion","planequipo_id", string="")






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




    @api.model_create_multi
    def create(self, vals_list):
        """Crea correctamente una o varias líneas desde el one2many de tarea.

        En Odoo 19 ``create`` recibe una lista de diccionarios cuando el cliente
        guarda varias líneas a la vez. Cada línea necesita sus propios comandos
        de parámetros para evitar compartir estructuras mutables.
        """
        default_cliente = self.env.context.get('default_cliente')
        default_ubicacion = self.env.context.get('default_ubicacion')
        default_tarea = self.env.context.get('default_tarea')

        for vals in vals_list:
            if default_cliente:
                vals.setdefault('cliente', default_cliente)
            if default_ubicacion:
                vals.setdefault('ubicacion', default_ubicacion)
            if default_tarea:
                vals.setdefault('tarea', default_tarea)

            if not vals.get('parametro_ids'):
                vals['parametro_ids'] = [
                    (0, 0, {
                        'paremetro_c': data['paremetro_id'],
                        'medida_c': data['unidad_medida'],
                    })
                    for data in self.data_parametros()
                ]

        return super().create(vals_list)

    @api.depends('fecha_ejec')
    def _generate_tecnico(self):
        for record in self:
            record.creador_id = record.equipo.create_uid.id
            record.is_admin = self.env.user.has_group('pmant.group_pmant_planner') or self.env.user.has_group('pmant.group_pmant_admin')


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





   
    def create_certificado_operatividad(self):
        return self.env.ref("pmant.action_reporte_cert_operatividad").report_action(self)
        # ir_actions_report_sudo = self.env["ir.actions.report"].sudo()
        # statement_report_action = self.env.ref("pmant.action_reporte_cert_operatividad")
        # for statement in self:
        #     statement_report = statement_report_action.sudo()
        #     content, _content_type = ir_actions_report_sudo._render_qweb_pdf(
        #         statement_report, res_ids=statement.ids
        #     )

        #     attachment = self.env["ir.attachment"].create(
        #         {
        #             "name": "Certificado " + self.equipo.name,
        #             "type": "binary",
        #             "mimetype": "application/pdf",
        #             "raw": content,
        #             "res_model": "sign.template", 
        #             "res_id": None,
        #         }
        #     )

        #     vals_template = {
        #         "name": "Certificado " + self.equipo.name,
        #         "equipo_id": self.equipo.id,
        #     }

        #     vals_template.pop("attachment_count", None)

        #     sign_template = self.env["sign.template"].create(vals_template)
        #     vals_sign_document = {
        #         "name": f"Certificado {self.equipo.name}",
        #         "attachment_id": attachment.id,
        #         "template_id": sign_template.id,
        #     }
        #     document_sign = self.env["sign.document"].create(vals_sign_document)
        #     attachment.res_id = sign_template

        # return {
        #     "type": "ir.actions.act_window",
        #     "name": "Certificado " + self.equipo.name,
        #     "res_model": "sign.template",
        #     "view_mode": "kanban", 
        #     "target": "current",
        # }


    def create_report_equipo (self) : 
        return self.env.ref('pmant.action_report_equipo').report_action(self)



