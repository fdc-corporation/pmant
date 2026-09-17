from odoo import api, fields, models
class PmantSettings(models.TransientModel):
    _inherit     = 'res.config.settings'
    ruta_web     = fields.Char()
    correo       = fields.Char()
    clave_correo = fields.Char()
    smtp         = fields.Char(string="Server SMTP")
    def set_values(self):
        res = super(PmantSettings,self).set_values()
        self.env['ir.config_parameter'].set_param('pmant.correo',self.correo)
        self.env['ir.config_parameter'].set_param('pmant.ruta_web', self.ruta_web)
        self.env['ir.config_parameter'].set_param('pmant.clave_correo', self.clave_correo)
        self.env['ir.config_parameter'].set_param('pmant.smtp', self.smtp)
        return res

    @api.model
    def get_values(self):
        res = super(PmantSettings, self).get_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        correos = ICPSudo.get_param('pmant.correo')
        ruta_web = ICPSudo.get_param('pmant.ruta_web')
        clave_correo = ICPSudo.get_param('pmant.clave_correo')
        smtp = ICPSudo.get_param('pmant.smtp')
        res.update(
            correo=correos,
            ruta_web = ruta_web,
            clave_correo = clave_correo,
            smtp = smtp

        )
        return res
