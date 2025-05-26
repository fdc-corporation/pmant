from odoo import models, fields, api, _
from datetime import date, datetime, timedelta, time



class WizardInconvenientes(models.TransientModel):
    _name = "wizars.inconvenientes"
    _description = "Model para los inconvenientes de Servicios"

    programacion_id = fields.Many2one("programacion.mantenimiento", default=lambda self: self._context.get("programacion_id"), string="Hoja de horas")
    ot_id = fields.Many2one("maintenance.request", default=lambda self: self._context.get("ot_id"), string="OT")
    tarea_id = fields.Many2one("tarea.mantenimiento", default=lambda self: self._context.get("tarea_id"), string="Tarea")
    is_finalizo_servicio = fields.Boolean(string="Finalizo el servicio?")
    file_ref = fields.Binary(string="Imagen de ref.")
    comentario = fields.Text(string="Comentario del inconveniente")
    

    def action_set_data(self):
        for record in self:
            if not record.is_finalizo_servicio:
                self.env["inconveniente.servicio"].create({
                    "programacion_id" : record.programacion_id.id,
                    "file_ref" : record.file_ref ,
                    "comentario" : record.comentario,
                    "ot_id" : record.ot_id.id,
                })
            record.programacion_id.fecha_fin = datetime.now()
            if record.is_finalizo_servicio:
                record.tarea_id.state_id = self.env["maintenance.stage"].search([("sequence", "=", 3)], limit=1).id
            record.tarea_id.action_servicio = False
            record.programacion_id._compute_horas_trabajado()
