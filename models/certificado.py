from odoo import fields, models


class CertificadoOperatividadManual(models.Model):
    _name = "pmant.certificado.operatividad"
    _description = "Certificado de operatividad firmado"
    _order = "fecha_firma desc, id desc"

    name = fields.Char(string="Certificado", required=True)
    equipo_id = fields.Many2one(
        "maintenance.equipment",
        string="Equipo",
        required=True,
        index=True,
        ondelete="cascade",
    )
    archivo_firmado = fields.Binary(
        string="PDF firmado",
        required=True,
        attachment=True,
    )
    nombre_archivo = fields.Char(string="Nombre del archivo", required=True)
    fecha_firma = fields.Date(
        string="Fecha del certificado",
        required=True,
        default=fields.Date.context_today,
    )
    usuario_id = fields.Many2one(
        "res.users",
        string="Registrado por",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    origen = fields.Selection(
        [("backend", "Interno"), ("portal", "Portal")],
        string="Origen",
        required=True,
        default="backend",
        readonly=True,
    )
