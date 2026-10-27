from odoo import models, fields, api, _ 
from odoo.exceptions import UserError


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    def crm_oportunidad_create(self):
        return super().crm_oportunidad_create()




class CRMLead(models.Model):
    _inherit = "crm.lead"

    repuestos_ids = fields.Many2many("requerimientos.stock", string="Repuestos requeridos")

    def btn_cotizacion (self):
        res = super().btn_cotizacion()
        cotizacion_id = res['res_id']

        for record in self:
            for repuesto in record.repuestos_ids:
                self.env['sale.order.line'].create({
                    'order_id' : cotizacion_id,
                    'ots' : self.orden_trabajo.id,
                    'product_id' : repuesto.product_id.id,
                    'product_uom_qty' : repuesto.cantidad,
                })
            return {
                "type": "ir.actions.act_window",
                "name": "Cotización",
                "view_mode": "form",
                "res_model": "sale.order",
                "res_id": cotizacion_id,
                "context": {"create": False},
            }


