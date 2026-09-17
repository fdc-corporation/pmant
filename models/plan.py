from odoo import models, fields, api


class FrecuenciaPlan(models.Model):
    _name        ='tipoplan.mantenimiento'
    name         = fields.Char(size=25,required=True,string='Nombre')
    dias         = fields.Integer(required=True,string='Equivalencia en N° de Dias')

class Plan(models.Model):
    _name  = 'plan.mantenimiento'
    name         = fields.Char(size=60,required=True,string='Nombre')
    frecuencia   = fields.Integer(required=True,string="Unidad Frecuencia")
    tipo         = fields.Many2one('tipoplan.mantenimiento',string="Tipo Frecuencia")
    proceso      = fields.One2many('proceso.mantenimiento','plan',string="procesos")
    descripcion  = fields.Text()
    alarm_ids    = fields.Many2many('calendar.alarm',string="Recordatorios")
