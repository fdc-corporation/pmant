from odoo import api, models, fields
from odoo.exceptions import UserError

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    orden_trabajo = fields.Many2one('maintenance.request', string='Orden de Trabajo')
    ubicacion = fields.Many2one('res.partner', string='Ubicacion')
    equipo_tarea = fields.Many2many('maintenance.equipment', string='Equipos')
    pmant_service_spare_line_ids = fields.One2many(
        'pmant.crm.spare.line', 'lead_id', string='Repuestos de servicio', readonly=True,
    )

    @api.depends(
        'email_domain_criterion', 'email_normalized', 'partner_id',
        'phone_sanitized',
    )
    def _compute_potential_lead_duplicates(self):
        """No expone duplicados de CRM que el vendedor no puede consultar."""
        if not self.env.user.has_group('pmant.group_pmant_vendedor'):
            return super()._compute_potential_lead_duplicates()

        elevated_leads = self.sudo()
        super(CrmLead, elevated_leads)._compute_potential_lead_duplicates()
        Lead = self.env['crm.lead'].with_context(active_test=False)
        for lead, elevated_lead in zip(self, elevated_leads):
            visible_duplicates = Lead.search([
                ('id', 'in', elevated_lead.duplicate_lead_ids.ids),
            ])
            lead.duplicate_lead_ids = visible_duplicates
            lead.duplicate_lead_count = len(visible_duplicates - lead)


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

                return {
                    "type": "ir.actions.act_window",
                    "name": "Cotización",
                    "view_mode": "form",
                    "res_model": "sale.order",
                    "res_id": cotizacion.id,
                    "context": {"create": False},
                }
            else :
                raise UserError('Debe seleccionar un equipo para generar la cotización.')


class PmantCrmSpareLine(models.Model):
    _name = "pmant.crm.spare.line"
    _description = "Repuesto de servicio en oportunidad"
    _order = "equipment_id, id"

    lead_id = fields.Many2one("crm.lead", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", related="lead_id.company_id", store=True, index=True)
    work_order_id = fields.Many2one("maintenance.request", string="OT de origen", required=True, readonly=True)
    spare_line_id = fields.Many2one("pmant.spare.line", string="Línea técnica", readonly=True, ondelete="set null")
    equipment_id = fields.Many2one("maintenance.equipment", string="Equipo", required=True, readonly=True)
    product_id = fields.Many2one("product.product", string="Repuesto", required=True, readonly=True)
    quantity = fields.Float(string="Cantidad", required=True, readonly=True)
    uom_id = fields.Many2one("uom.uom", string="Unidad", readonly=True)
    note = fields.Char(string="Nota técnica", readonly=True)
