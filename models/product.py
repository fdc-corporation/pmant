from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_equipo = fields.Boolean(string='Es un equipo')
    # n_serie = fields.Char(string='Número de Serie')
    # id_equipo = fields.Char(string='ID del Equipo')
    is_repuesto = fields.Boolean(string='Es un Repuesto')
