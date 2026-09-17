from odoo import models, fields, api
class Contacto(models.Model):
    _name    = 'res.partner'
    _inherit = 'res.partner'
    equipos  = fields.One2many('maintenance.equipment','propietario' ,string="Equipos de Mantenimiento")
    #user_cli = fields.Many2one('res.users',string="Usuario ")
    @api.onchange('street')
    def _change_stree(self):
        if self.name==False:
            self.name='Escribir aqui'

class Empleado(models.Model):
    _name    = 'hr.employee'
    _inherit = 'hr.employee'
    firma    = fields.Binary(attachment=True)
    dni      = fields.Char(string="N° Documento para la firma")