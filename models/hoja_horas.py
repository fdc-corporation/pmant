from odoo import models, fields, api, _
from datetime import date, datetime, timedelta, time
from odoo.exceptions import UserError
import datetime


class HojaHoras(models.Model):
    _name = "programacion.mantenimiento"
    _description = "Hoja de horas de servicios tecnicos"

    fecha_date = fields.Datetime(string="Fecha programado")
    ot_id = fields.Many2one("tarea.mantenimiento", string="Ot")
    duracion = fields.Float(string="Duracion (H)")
    event_calendario = fields.Many2one(
        "calendar.event", compute="_set_evento", string="Evento calendario"
    )
    fecha_inicio = fields.Datetime(string="Fecha de incio")
    fecha_fin = fields.Datetime(string="Fecha de finalizacion")
    horas_trabajado = fields.Float(string="Horas trabajados")
    horas_active = fields.Boolean(string="Horas activo")

    @api.depends("fecha_date", "duracion")
    def _set_evento(self):
        for record in self:
            if record.ot_id.ots:
                if record.fecha_date and record.duracion:
                    partner_ids = []
                    if self.env.user.partner_id:
                        partner_ids.append(self.env.user.partner_id.id)
                    if record.ot_id.ots.user_id:
                        partner_ids.append(record.ot_id.ots.user_id.partner_id.id)
                    else:
                        raise UserError(
                            _("El usuario actual '%s' no tiene un partner asociado.")
                            % self.env.user.name
                        )

                    for user in record.ot_id.ots.subodinados:
                        if user.partner_id:
                            partner_ids.append(user.partner_id.id)
                        else:
                            raise UserError(
                                _("El usuario '%s' no tiene un partner asociado.")
                                % user.name
                            )

                    if partner_ids:
                        evento_id = self.env["calendar.event"].create(
                            {
                                "name": "Servicio / " + record.ot_id.ots.name
                                or record.name,
                                "start": record.fecha_date,
                                "stop": record.fecha_date
                                + timedelta(hours=record.duracion),
                                "duration": record.duracion,
                                "ots_id": record.ot_id.ots.id,
                            }
                        )
                        record.event_calendario = evento_id.id
                    else: 
                        record.event_calendario = None
            else : 
                record.event_calendario = None
    def init_cronograma(self):
        if self.fecha_inicio:
            raise UserError(_("Ya se inició el servicio."))
        self.fecha_inicio = fields.Datetime.now()
        self.horas_active = True

    def cancel_cronograma(self):
        if self.fecha_fin:
            raise UserError(
                _("El servicio ya se finalizó y ya cuenta con sus horas trabajadas.")
            )
        self.fecha_fin = fields.Datetime.now()
        self.horas_active = False
        self._compute_horas_trabajado()

    @api.depends("fecha_inicio", "fecha_fin")
    def _compute_horas_trabajado(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin:
                diferencia = record.fecha_fin - record.fecha_inicio
                horas = diferencia.total_seconds() / 3600  # Pasar de segundos a horas
                record.horas_trabajado = round(horas, 2)
            else:
                record.horas_trabajado = 0.0
