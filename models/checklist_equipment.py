from odoo import models, fields, api
from odoo.http import request
import qrcode
import base64
from io import BytesIO
from datetime import date, datetime, timedelta



class Equipo(models.Model):
    _inherit = "maintenance.equipment"
    _description = "Equipo de Mantenimiento"

    plantilla_preguntas = fields.Many2one(
        comodel_name="pmant.checklist",
        string="Plantilla de Preguntas",
        help="Plantilla de preguntas asociada a este equipo",
    )

    url_checklist = fields.Char(
        string="QR Checklist",
        help="Código QR asociado al checklist de este equipo",
        compute="_compute_qr_checklist",
        store=True,
    )
    qr_checklist_image = fields.Binary(
        string="Imagen QR Checklist",
        help="Imagen del código QR asociado al checklist de este equipo",
        compute="_compute_qr_checklist_image",
        attachment=True,
        store=True,
    )
    qr_checklist_image_2 = fields.Binary(
        string="Imagen QR Checklist 2",
        help="Segunda imagen del código QR asociado al checklist de este equipo",
        compute="_compute_qr_checklist_image",
        attachment=True,
        store=True,
    )
    respuestas_ids = fields.One2many(
        comodel_name="pmant.checklist.respuesta",
        inverse_name="equipo_id",
        string="Respuestas del Checklist",
        help="Respuestas asociadas a las preguntas del checklist de este equipo",
    )
    respuestas_count = fields.Integer(
        string="Cantidad de Respuestas",
        compute="_compute_respuestas_count",
        help="Cantidad de respuestas asociadas a las preguntas del checklist de este equipo",
    )
    
    def _compute_respuestas_count(self):
        for rec in self:
            rec.respuestas_count = self.env["pmant.checklist.group"].search_count([
                ("equipo_id", "=", rec.id)
            ])


    @api.depends('plantilla_preguntas')
    def _compute_qr_checklist(self):
        for record in self:
            if record.plantilla_preguntas:
                base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
                url = f"{base_url}/my/equipos/{record.id}/checklist/{record.plantilla_preguntas.id}"
                record.url_checklist = url
            else:
                record.url_checklist = False
    
    @api.depends('plantilla_preguntas')
    def _compute_qr_checklist_image(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        for record in self:
            if record.plantilla_preguntas:
                url = f"{base_url}/my/equipos/{record.id}/checklist/{record.plantilla_preguntas.id}"

                qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
                qr.add_data(url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                qr_image_b64 = base64.b64encode(buffer.getvalue())

                record.qr_checklist_image = qr_image_b64
                record.qr_checklist_image_2 = qr_image_b64
            else:
                record.qr_checklist_image = False
                record.qr_checklist_image_2 = False

    def action_view_respuestas(self):
        self.ensure_one()
        cant_data = self.env["pmant.checklist.group"].search(
                [("equipo_id", "=", self.id)]
            )
        return {
                "name": "Respuestas del Checklist",
                "type": "ir.actions.act_window",  # ¡Este es el campo que faltaba!
                "domain": [("id", "in", cant_data.ids)],
                "view_mode": "list,form",  # puedes permitir también la vista formulario
                "res_model": "pmant.checklist.group",
                "context": {"create": False},
            }


