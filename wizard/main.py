from odoo import models, fields, api


class WizardShare(models.TransientModel):
    _name = "wizard.share"
    _description = "Wizard para compartir OT"

    url = fields.Char(string="URL", compute="_share_url", store=True)

    @api.model
    def create(self, vals):
        # Llamada correcta a super()
        res = super(WizardShare, self).create(vals)
        active_id = self._context.get("active_id")
        if active_id:
            # Obtener la URL del modelo de mantenimiento
            dominio = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            url_to_share = f"{dominio}/reporte/?id={active_id}"
            self.url = url_to_share

        print(url)
        return res

    def write(self, vals):
        res = super(WizardShare, self).write(vals)
        active_id = self._context.get("active_id")
        if active_id:
            # Obtener la URL del modelo de mantenimiento
            dominio = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            url_to_share = f"{dominio}/reporte/?id={active_id}"
            self.url = url_to_share

        print(url)
        return res
