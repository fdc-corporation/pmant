from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    ots = fields.Many2one("tarea.mantenimiento", string="Tarea")
    servicios_cantidad = fields.Integer(compute="_total_tareas")

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        self.create_mantenimiento()
        return res

    def create_mantenimiento(self):
        for order in self:
            if not order.ots:
                try:
                    if any(
                        product.product_template_id.detailed_type == "service"
                        for product in order.order_line
                    ):
                        # Crear el registro de mantenimiento
                        valores = {
                            "name": order.name + " - Servicios de mantenimiento",
                            "cliente": order.partner_id.id,
                            "ubicacion": order.partner_shipping_id.id,
                            "oc_id": order.oc_id.id if order.oc_id else False,
                        }
                        mantenimiento = self.env["tarea.mantenimiento"].create(valores)

                        # Crear una lista de líneas de equipos a añadir
                        lines_to_add = []
                        for line in order.order_line:
                            if line.display_type == "line_section":
                                partes = line.name.split(" / ")
                                if len(partes) > 1:
                                    serial_no = partes[1].strip()
                                    equipo = self.env["maintenance.equipment"].search(
                                        [("serial_no", "=", serial_no)], limit=1
                                    )
                                    if equipo:
                                        planequipo_vals = {
                                            "tarea": mantenimiento.id,
                                            "cliente": order.partner_id.id,
                                            "ubicacion": order.partner_shipping_id.id,
                                            "equipo": equipo.id,
                                        }
                                        lines_to_add.append((0, 0, planequipo_vals))

                        # Añadir todas las líneas a la tarea de mantenimiento
                        if lines_to_add:
                            mantenimiento.write({"planequipo": lines_to_add})

                        # Asignar la tarea de mantenimiento al pedido de venta
                        order.ots = mantenimiento

                        # Actualizar el estado del pedido de compra si existe
                        if order.oc_id:
                            estado = self.env.ref("oc_compras.estado_servicios", raise_if_not_found=False)
                            if estado:
                                order.oc_id.state = estado.id
                    return {
                        "type": "ir.actions.act_window",
                        "name": "Tareas",
                        "view_mode": "form",
                        "res_model": "tarea.mantenimiento",
                        "res_id": self.ots.id,
                        "context": {"create": False},
                    }
                except Exception as e:
                    raise UserError(f"Ups, no se logró crear la solicitud de mantenimiento: {str(e)}")

    def action_view_services(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tareas",
            "view_mode": "form",
            "res_model": "tarea.mantenimiento",
            "res_id": self.ots.id,
            "context": {"create": False},
        }

    @api.depends("ots")
    def _total_tareas(self):
        for record in self:
            record.servicios_cantidad = self.env["tarea.mantenimiento"].search_count(
                [("id", "=", record.ots.id)]
            )
