from odoo import models, fields, api, _

class ResPartner(models.Model):
    _inherit = "res.partner"

    # Campo Booleano que indica si un partner tiene áreas
    tienen_areas = fields.Boolean(string="¿Tiene áreas?")

    # Campo Booleano que indica si este partner es un área
    is_area = fields.Boolean(string="¿Es un área?")

    # Relación One2many: Un partner puede tener muchas áreas (sub-partners)
    areas = fields.One2many(
        "res.partner",        # El modelo de destino es 'res.partner'
        'id_sede',            # El campo en 'res.partner' que hace referencia a la sede
        string="Áreas"
    )

    # Relación Many2one: Un partner puede estar vinculado a una sede
    id_sede = fields.Many2one(
        "res.partner",        # El modelo de destino es 'res.partner'
        string="Sede"         # Etiqueta del campo
    )
