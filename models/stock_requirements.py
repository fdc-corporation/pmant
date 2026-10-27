from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RequerimientosStock(models.Model):
    _name = "requerimientos.stock"
    _description = "Requerimientos de Repuestos"

    tarea_id = fields.Many2one("tarea.mantenimiento", string="Tarea de mantenimiento", required=True)
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        domain=[("type", "in", ["consu", "combo"])],
        required=True,
    )
    cantidad = fields.Integer(string="Cantidad requerida", required=True)
    nota = fields.Text(string="Nota")
    state_requerimiento = fields.Selection(
        [
            ("pendiente", "Pendiente"),
            ("consumido", "Consumido"),
        ],
        string="Estado del requerimiento",
        default="pendiente",
        readonly=True,
    )
    cant_consumido = fields.Integer(string="Cantidad consumida", readonly=True)

    def write(self, vals):
        res = super().write(vals)
        for record in self:
            record._update_estado_tarea()
        return res

    def _update_estado_tarea(self):
        """Actualizar banderas confirm_desecho y confirm_devolucion en la tarea relacionada"""
        if self.tarea_id:
            self.tarea_id.confirm_desecho = any(r.cantidad > 0 for r in self.tarea_id.requerimientos_ids)
            self.tarea_id.confirm_devolucion = any(r.cant_consumido > 0 for r in self.tarea_id.requerimientos_ids)

    def action_wizard_repuesto_consumido(self):
        return {
            "name": _("Confirmación de repuesto consumido"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.repuesto.consumido",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_tarea_id": self.tarea_id.id,
                "default_requerimiento_id": self.id,
            },
        }


class WizardRepuestoConsumido(models.TransientModel):
    _name = "wizard.repuesto.consumido"
    _description = "Asistente para confirmar repuesto consumido"

    tarea_id = fields.Many2one("tarea.mantenimiento", string="Tarea de mantenimiento", required=True)
    requerimiento_id = fields.Many2one("requerimientos.stock", string="Requerimiento de repuesto", required=True)
    cantidad_consumida = fields.Integer(string="Cantidad consumida", required=True)

    def action_confirmar_consumo(self):
        self.ensure_one()

        if self.cantidad_consumida <= 0:
            raise UserError(_("La cantidad consumida debe ser mayor que cero."))

        if self.cantidad_consumida > self.requerimiento_id.cantidad:
            raise UserError(_("La cantidad consumida no puede ser mayor que la cantidad requerida."))

        # Actualizar cantidades
        self.requerimiento_id.cantidad -= self.cantidad_consumida
        self.requerimiento_id.cant_consumido += self.cantidad_consumida

        # Cambiar estado si ya no queda nada por consumir
        if self.requerimiento_id.cantidad == 0:
            self.requerimiento_id.state_requerimiento = "consumido"

        # Actualizar estado en la tarea
        self.requerimiento_id._update_estado_tarea()

        return {"type": "ir.actions.act_window_close"}


