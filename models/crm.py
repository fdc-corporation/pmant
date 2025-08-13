from odoo import models, fields
from odoo.exceptions import UserError

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    orden_trabajo = fields.Many2one('maintenance.request', string='Orden de Trabajo')
    ubicacion = fields.Many2one('res.partner', string='Ubicacion')
    equipo_tarea = fields.Many2many('maintenance.equipment', string='Equipos')


    def btn_cotizacion (self):
        for record in self:
            if record.equipo_tarea:
                cotizacion = self.env['sale.order'].create({
                    'partner_id' : record.partner_id.id,
                    'partner_shipping_id' : record.ubicacion.id,
                    'opportunity_id' : record.id,
                })
                for equipo in record.equipo_tarea:
                    self.env['sale.order.line'].create({
                        'order_id' : cotizacion.id,
                        'name' : equipo.name + ' / ' + equipo.serial_no,
                        'display_type' : 'line_section',
                        'id_equipo' : equipo.id

                    })
                    
            else :
                raise UserError('Debe seleccionar un equipo para generar la cotización.')