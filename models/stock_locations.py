from odoo import models, fields, api, _
from odoo.exceptions import UserError


class Ubicacion (models.Model):
    _name = "conf.pmant.ubicacion"
    _description = "Ubicación de mantenimiento"

    name = fields.Char(string="Nombre", required=True)
    # CAMPOS PARA EL INGRESO DE LOS EQUIPOS
    property_stock_inventory = fields.Many2one('stock.location', string="Ubicación de inventario", ondelete="set null", domain=[('usage', '=', 'internal')])
    property_stock_customer = fields.Many2one('stock.location', string="Ubicación de proveedor (cliente)",  ondelete="set null", domain=[('usage', '=', 'customer')])
    predeterminado = fields.Boolean(string="Predeterminado", default=True)
    operacion_entrada = fields.Many2one('stock.picking.type', string="Tipo de operación de entrada", ondelete="set null", domain=[('code', '=', 'incoming')])
    operacion_salida = fields.Many2one('stock.picking.type', string="Tipo de operación de salida", ondelete="set null", domain=[('code', '=', 'outgoing')])
    # CAMPOS PARA LOS TRASLADOS INTERNOS
    is_trasporte_interno = fields.Boolean(string="¿Es ubicacion de traslado interno?", default=False)
    tipo_operacion_traslado = fields.Many2one('stock.picking.type', string="Tipo de operación de traslado interno", ondelete="set null", domain=[('code', '=', 'internal')])
    ubicacion_origen_traslado = fields.Many2one('stock.location', string="Ubicación origen traslado interno", ondelete="set null", domain=[('usage', '=', 'internal')])
    ubicacion_destino_traslado = fields.Many2one('stock.location', string="Ubicación destino traslado interno", ondelete="set null", domain=[('usage', '=', 'internal')])
    # CAMPOS PARA EL DESECHO DE REPUESTOS
    is_ubicacion_desecho = fields.Boolean(string="¿Es ubicación de desecho de repuestos?", default=False)
    ubicacion_desecho = fields.Many2one('stock.location', string="Ubicación de desecho", ondelete="set null", domain=[('usage', '=', 'internal')])
    motivo_desecho = fields.Many2many('stock.scrap.reason.tag', string="Motivo de desecho")
    scrap_location_id = fields.Many2one('stock.location', string="Ubicación scrap", ondelete="set null")


    @api.constrains('predeterminado')
    def _check_only_one_default(self):
        if self.predeterminado:
            others = self.search([
                ('id', '!=', self.id),
                ('predeterminado', '=', True)
            ])
            if others:
                raise UserError(_("Solo una ubicación puede estar marcada como predeterminada."))


class CategoriasEquipos(models.Model):
    _inherit = "maintenance.equipment.category"
    _description = "Categoría de equipos"

    product_id = fields.Many2one('product.product', string="Producto relacionado", ondelete="set null",)


