# -*- coding: utf-8 -*-
from odoo import fields, models


class OfflineIncidentWizard(models.TransientModel):
    _inherit = "wizars.inconvenientes"

    def action_set_data(self):
        result = super().action_set_data()
        now = fields.Datetime.now()
        for wizard in self.filtered("is_finalizo_servicio"):
            sheet = wizard.programacion_id
            active_sessions = sheet.kd_session_ids.filtered(lambda session: not session.ended_at)
            if active_sessions:
                active_sessions.sudo().write({"ended_at": now})
            sheet.sudo().write({
                "kd_time_state": "finished",
                "kd_last_event_at": now,
            })
            if wizard.tarea_id:
                wizard.tarea_id.sudo().write({"service_started_at": False})
            sheet._compute_horas_trabajado()
        return result
