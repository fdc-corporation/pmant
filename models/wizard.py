from odoo import models, fields, api
from odoo.exceptions import ValidationError

class EquipmentSelectionWizard(models.TransientModel):
    _name = 'wizard.equipment.selection'
    _description = 'Asistente para seleccionar equipo'

    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipos')
    order_id = fields.Many2one('sale.order', string='Orden de Venta', default=lambda self: self.env.context.get('default_order_id'))
    ubicacion = fields.Many2one(
        "res.partner",
        string="Dirección de Envío",
        default=lambda self: (
            self.env["sale.order"]
            .browse(self.env.context.get("default_order_id"))
            .partner_shipping_id.id
            if self.env.context.get("default_order_id")
            else False
        ),
    )

    def action_add_equipment(self):
        sale_order = self.order_id
        for equipment in self.equipment_ids:
            sale_order.order_line.create({
                'order_id': sale_order.id,
                'name' : equipment.name + ' / ' + equipment.serial_no,
                'display_type' : 'line_section',
                'id_equipo' : equipment.id
            })
        return {'type': 'ir.actions.act_window_close'}


class SaleCancelOrder(models.TransientModel):
    _name = 'wizard.order.cancel'
    _description = 'Asistente para cancelar orden de venta'

    sale_id = fields.Many2one("sale.order", string="Venta", default=lambda self: self.env.context.get("default_sale_id"))

    def action_cancel(self):
        if not self.sale_id:
            raise ValidationError("No se ha seleccionado ninguna orden de venta.")
        if self.sale_id.state not in ['draft', 'sent', 'sale']:
            raise ValidationError("Solo se pueden cancelar órdenes en estado Borrador, Enviado o Confirmado.")
        self.sale_id.action_cancel()



    def action_cancel_all(self):
        if not self.sale_id:
            raise ValidationError("No se ha seleccionado ninguna orden de venta.")
        if self.sale_id.state not in ['draft', 'sent', 'sale']:
            raise ValidationError("Solo se pueden cancelar órdenes en estado Borrador, Enviado o Confirmado.")
        
        # Cancelar la orden de venta
        self.sale_id.action_cancel()
        self.sale_id.delete_mantenimiento()