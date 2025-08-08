from odoo import models, fields, api
from odoo.exceptions import ValidationError


class EquipmentSelectionWizard(models.TransientModel):
    _name = "wizard.equipment.selection"
    _description = "Asistente para seleccionar equipo"

    equipment_ids = fields.Many2many("maintenance.equipment", string="Equipos")
    order_id = fields.Many2one(
        "sale.order",
        string="Orden de Venta",
        default=lambda self: self.env.context.get("default_order_id"),
    )

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
            sale_order.order_line.create(
                {
                    "order_id": sale_order.id,
                    "name": equipment.name + " / " + equipment.serial_no,
                    "display_type": "line_section",
                    "id_equipo": equipment.id,
                }
            )
        return {"type": "ir.actions.act_window_close"}
