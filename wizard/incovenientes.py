from odoo import models, fields, api, _
from datetime import date, datetime, timedelta, time



class WizardInconvenientes(models.TransientModel):
    _name = "wizars.inconvenientes"
    _description = "Model para los inconvenientes de Servicios"

    programacion_id = fields.Many2one("programacion.mantenimiento", default=lambda self: self._context.get("programacion_id"), string="Hoja de horas")
    ot_id = fields.Many2one("tarea.mantenimiento", default=lambda self: self._context.get("ot_id"), string="Tarea")
    file_ref = fields.Binary(string="Imagen de ref.")
    comentario = fields.Text(string="Comentario del inconveniente")


    def action_set_data(self):
        for record in self:
            self.env["inconveniente.servicio"].create({
                "programacion_id" : record.programacion_id.id,
                "file_ref" : record.file_ref ,
                "comentario" : record.comentario,
                "ot_id" : record.ot_id,
            })


            

            # Si finaliza, mover etapa
            if record.is_finalizo_servicio:
                print("EL SERVICIO ESTA FINALIZADO")
                print(datetime.now())
                etapa_final = self.env["maintenance.stage"].search([("sequence", "=", 3)], limit=1)
                if etapa_final:
                    record.ot_id.stage_id = etapa_final.id
                    # Actualizar si finalizó el servicio
                record.programacion_id.write({
                    "es_servicio_finalizado": True,
                    "fecha_fin": datetime.now(),
                })
                # Desactivar acción de servicio
                record.tarea_id.action_servicio = False

            # Recalcular horas trabajadas
            record.programacion_id._compute_horas_trabajado()
