from odoo import api, models, fields


class EventoCalendario (models.Model):
    _inherit = 'calendar.event'
    
    ots_id = fields.Many2one('maintenance.request', string='OTS')
    programacion_id = fields.Many2one("programacion.mantenimiento", string="Hoja de horas")
    equipos_ids = fields.Many2many(
        'maintenance.equipment',
        string='Equipos'
    )

    # GENERA UN LEED PARA EL SEGUIMIENTO DE LA OT PROXIMA
    def action_create_crm(self):
        lead = self.env["crm.lead"].create({
            "name" : f"Oportunidad - {self.name}",
            "partner_id" : self.ots_id.empresa.id,
            "ubicacion" : self.ots_id.ubicacion.id,
            "user_id" : self.user_id.id
        })
        if lead :
            self.active = False
            return {
                "type": "ir.actions.act_window",
                "name": "Oportunidad",
                "view_mode": "form",
                "res_model": "crm.lead",
                "res_id": lead.id,
                "context": "{'create' : False}",
            }
        else : 
            raise UserError(_("No se pudo crear el lead, soborne al de sistemas para que lo soluciones :v"))