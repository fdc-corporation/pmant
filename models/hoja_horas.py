from odoo import models, fields, api, _
from datetime import date, datetime, timedelta, time
from odoo.exceptions import UserError
import datetime
import logging
# from odoo.models import NewId
_logger = logging.getLogger(__name__)


class Inconvenientes(models.Model):
    _name = 'inconveniente.servicio'
    _description = "Inconvenientes en los servicos"

    programacion_id = fields.Many2one("programacion.mantenimiento", string="Hoja de horas")
    ot_id = fields.Many2one("maintenance.request", string="OT")
    file_ref = fields.Binary(string="Imagen de ref.", attachment=True)
    comentario = fields.Text(string="Comentario del inconveniente")

class HojaHoras(models.Model):
    _name = "programacion.mantenimiento"
    _description = "Hoja de horas de servicios tecnicos"

    fecha_date = fields.Datetime(string="Fecha programada", required=True)
    ot_id = fields.Many2one("maintenance.request", string="Ot", required=True)
    duracion = fields.Float(string="Duracion (H)", required=True)
    event_calendario = fields.Many2one(
        "calendar.event", compute="_set_evento", string="Evento calendario"
    )
    fecha_inicio = fields.Datetime(string="Fecha de inicio")
    fecha_fin = fields.Datetime(string="Fecha de finalización")
    horas_trabajado = fields.Float(string="Horas marcadas")
    horas_active = fields.Boolean(string="Horas activo")
    tecnicos = fields.Many2many("res.users", string="Tecnicos", required=True)
    tab_comentarios = fields.One2many("inconveniente.servicio", "programacion_id", string="Incidencias")
    h_faltantes = fields.Float(string="Horas faltantes")
    es_servicio_finalizado = fields.Boolean(string="Servicio finalizado?")
    h_optimizado = fields.Float(string="Horas de trabajo optimizado")
    
    def unlink(self):
        for record in self:
            if record.event_calendario:
                record.event_calendario.unlink()
        return super().unlink()


    @api.depends("fecha_date", "duracion", "tecnicos")
    def _set_evento(self):
        for record in self:
            evento = False  # usar False, no None

            try:
                if not record.ot_id or not record.fecha_date or not record.duracion:
                    _logger.info(f"⚠️ Faltan datos para crear evento en OT {record.ot_id.name if record.ot_id else 'Sin OT'}")

                elif any(
                    not user.partner_id
                    or isinstance(user.partner_id.id, (bool, type(None)))
                    for user in record.tecnicos
                ):
                    _logger.warning(f"⚠️ Técnicos sin partner persistido en OT {record.ot_id.name if record.ot_id else 'Sin OT'}")

                else:
                    partner_ids = [
                        user.partner_id.id
                        for user in record.tecnicos
                        if user.partner_id and user.partner_id.id
                    ]

                    if record.ot_id.empresa and record.ot_id.empresa.id:
                        partner_ids.append(record.ot_id.empresa.id)
                    if record.ot_id.ubicacion and record.ot_id.ubicacion.id:
                        partner_ids.append(record.ot_id.ubicacion.id)

                    partner_ids = list(set([pid for pid in partner_ids if pid]))

                    valores_evento = {
                        "name": f"Servicio programado / {record.ot_id.name or record.name}",
                        "start": record.fecha_date,
                        "stop": record.fecha_date + timedelta(hours=record.duracion),
                        "duration": record.duracion,
                        "ots_id": record.ot_id.id,
                        "programacion_id": record.id,
                        "partner_ids": [(6, 0, partner_ids)],
                    }

                    # Reutilizar evento si ya existe
                    evento = record.event_calendario or self.env["calendar.event"].search(
                        [("ots_id", "=", record.ot_id.id), ("programacion_id", "=", record.id)],
                        limit=1,
                    )

                    if evento:
                        evento.write(valores_evento)
                    else:
                        evento = self.env["calendar.event"].create(valores_evento)

            except Exception as e:
                _logger.error(f"❌ Error al generar evento: {e}")

            # 🔒 Siempre asigna algo, aunque sea False
            record.event_calendario = evento

    # def init_cronograma(self):
    #     if self.fecha_inicio:
    #         raise UserError(_("Ya se inició el servicio."))
    #     self.fecha_inicio = fields.Datetime.now()
    #     self.horas_active = True

    # def cancel_cronograma(self):
    #     if self.fecha_fin:
    #         raise UserError(
    #             _("El servicio ya se finalizó y ya cuenta con sus horas trabajadas.")
    #         )
    #     self.fecha_fin = fields.Datetime.now()
    #     self.horas_active = False
    #     self._compute_horas_trabajado()

    @api.depends("fecha_inicio", "fecha_fin")
    def _compute_horas_trabajado(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin:
                diferencia = record.fecha_fin - record.fecha_inicio
                horas = diferencia.total_seconds() / 3600  # Pasar de segundos a horas
                record.horas_trabajado = round(horas, 2)
                if record.es_servicio_finalizado:
                    record.h_optimizado = record.duracion - record.horas_trabajado
            else:
                record.horas_trabajado = 0.0

    def action_view_registro(self):
        return {
            "type" : "ir.actions.act_window",
            "name" : "Programación",
            "res_model" : "programacion.mantenimiento",
            "view_mode" : "form",
            "res_id" : self.id
        }


    def action_validacion_time(self):
        for record in self:
            if not record.horas_trabajado:
                raise UserError(_("No puedes aceptar una incidencia sin horas trabajadas"))
            if record.es_servicio_finalizado :
                record.h_optimizado = record.duracion - record.horas_trabajado
                record.h_faltantes = 0.00
            else :
                record.h_faltantes = record.duracion - record.horas_trabajado
                record.h_optimizado = 0.00


    def action_validacion_time_cancel(self):
        for record in self:
            record.h_optimizado = 0.00
            record.h_faltantes = 0.00
