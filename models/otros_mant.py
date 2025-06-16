from odoo import models, fields, api, _


# class WizardMant (models.TransientModel):
#     _name = "wiizard.mantenimiento"
#     _description = "Wizard add mantenimiento"


#     name = fields.Char(string="Nombre")
#     planequipo = fields.Many2one("planequipo.mantenimiento", string="Plan de mantenimiento")
#     fecha_eject = fields.Date(string="Fecha ejecutada")
#     file_adjunto = fields.Binary(string="Reporte Tecnico")
#     file_name = fields.Char(string="Nombre de archivo")
#     tipo = fields.Many2one("tipotarea.mantenimiento", string="tipo de mantenimiento")
#     equipo_id = fields.Many2one("maintenance.equipment", string="Equipo", default=lambda self: slef.env.context.get("equipo_id"))



