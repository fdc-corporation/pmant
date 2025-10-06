from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = "sale.order"

    ots = fields.Many2one("tarea.mantenimiento", string="Tarea")
    servicios_cantidad = fields.Integer(compute="_total_tareas", store=True)
    is_servicio = fields.Boolean(string="Es servicio", compute="_compute_verify_service")
    titulo_cotizacion = fields.Char(string="Título de la cotización")



    def action_print_sale(self):
        return self.env.ref("sale.action_report_saleorder").report_action(self)

    def action_open_wizard_sale(self):
        return {
            "name": "Confirmacion de venta",
            "type": "ir.actions.act_window",
            "res_model": "wizard.sale.order",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }  

    @api.depends("order_line", "order_line.product_template_id", "order_line.id_equipo")
    def _compute_verify_service(self):
        for order in self:
            if not order.order_line:
                order.is_servicio = False
                continue

            # Si hay alguna línea con id_equipo, no es servicio
            if any(line.id_equipo for line in order.order_line):
                order.is_servicio = False
            else:
                # Si hay al menos un producto de tipo servicio, es servicio
                order.is_servicio = any(
                    line.product_template_id.type == "service"
                    for line in order.order_line
                )

    def action_confirm(self):
        res = super().action_confirm()
        self.create_mantenimiento()
        return res

 


    def delete_mantenimiento(self):
        for record in self:
            tareas = self.env["tarea.mantenimiento"].search([("sale_order", "=", record.id)])
            print("Tareas encontradas para eliminar:", tareas)
            for mantenimiento in tareas:
                if not mantenimiento.ots:
                    mantenimiento.planequipo.unlink()
                    mantenimiento.unlink()
            self.action_cancel()

    def create_mantenimiento(self):
        for order in self:
            if order.ots:
                continue  # Ya tiene tarea asignada

            equipo_lines = order.order_line.filtered(lambda l: l.id_equipo)
            if not equipo_lines:
                continue

            try:
                group = self.env.ref('pmant.group_pmant_planner', raise_if_not_found=False)
                print("Group:", group)
                print("Group:", group.name)

                user = self.env['res.users'].search([('group_ids', 'in', group.id), ('share', '=', False)], limit=1) if group else False
                print("User:", user)
                format_html_nota = self.template_format_nota(order)
                
                mantenimiento_vals = {
                    "name": f"{order.name} - {order.titulo_cotizacion or 'Servicios de mantenimiento'}",
                    "cliente": order.partner_id.id,
                    "ubicacion": order.partner_shipping_id.id,
                    "create_user": user.id,
                    # "oc_id": order.oc_id.id if order.oc_id else False,
                    "sale_order": order.id,
                    "notas": format_html_nota,
                }
                mantenimiento = self.env["tarea.mantenimiento"].create(mantenimiento_vals)

                lines_to_add = []
                for line in equipo_lines:
                    lines_to_add.append((0, 0, {
                        "tarea": mantenimiento.id,
                        "cliente": order.partner_id.id,
                        "ubicacion": order.partner_shipping_id.id,
                        "equipo": line.id_equipo.id,
                    }))

                if lines_to_add:
                    mantenimiento.write({"planequipo": lines_to_add})
                    mantenimiento.write({"create_user": user.id})
                    order.ots = mantenimiento

                    # Actualizar estado de OC si aplica
                    # if order.oc_id:
                    #     estado = self.env.ref("oc_compras.estado_servicios", raise_if_not_found=False)
                    #     if estado:
                    #         order.oc_id.state = estado.id

            except Exception as e:
                raise UserError(f"Error al crear la solicitud de mantenimiento: {str(e)}")

    def template_format_nota(self, order):
        formato = ""
        productos = []

        for line in order.order_line:
            if line.display_type == 'line_section':
                # Si hay productos acumulados antes, los agregamos y reiniciamos
                if productos:
                    formato += "<ul>" + "".join(productos) + "</ul>"
                    productos = []
                formato += f"<h3 style='color:#2c3e50; margin-top:10px;'>{line.name}</h3>"

            elif line.display_type == 'line_note':
                if productos:
                    formato += "<ul>" + "".join(productos) + "</ul>"
                    productos = []
                formato += f"<p style='color:#7f8c8d; font-style:italic; margin-left:10px;'>{line.name}</p>"

            else:
                productos.append(
                    f"<li><b>Producto:</b> {line.name} "
                    f"/ <b>Cantidad:</b> {line.product_uom_qty}</li>"
                )

        # Agregar los últimos productos si quedaron pendientes
        if productos:
            formato += "<ul>" + "".join(productos) + "</ul>"

        return formato

    def action_view_services(self):
        self.ensure_one()
        if not self.ots:
            raise UserError("No hay tarea de mantenimiento asociada a esta orden.")
        return {
            "type": "ir.actions.act_window",
            "name": "Tareas de Mantenimiento",
            "view_mode": "form",
            "res_model": "tarea.mantenimiento",
            "res_id": self.ots.id,
            "context": {"create": False},
        }

    @api.depends("ots")
    def _total_tareas(self):
        for record in self:
            record.servicios_cantidad = bool(record.ots)


class SaleOrderLine(models.Model):
    _inherit="sale.order.line"
    _description ="Lineas de la orden"


    id_equipo = fields.Many2one("maintenance.equipment", string="Equipo")



class WizardConfirmSaleOrder(models.TransientModel):
    _name = "wizard.sale.order"
    _description = "Wizard Sale Order"

    sale_id = fields.Many2one("sale.order", string="Venta", default= lambda self: self.env.context.get("default_order_id"))


    def confirm_sale(self):
        self.sale_id.action_confirm()