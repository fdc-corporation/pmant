from odoo import models, fields, api, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class Inconvenientes(models.Model):
    _name = 'inconveniente.servicio'
    _description = "Inconvenientes en los servicios"

    programacion_id = fields.Many2one("programacion.mantenimiento", string="Hoja de horas")
    ot_id = fields.Many2one("maintenance.request", string="OT")
    file_ref = fields.Binary(string="Imagen de ref.", attachment=True)
    comentario = fields.Text(string="Comentario del inconveniente")


class HojaHoras(models.Model):
    _name = "programacion.mantenimiento"
    _description = "Hoja de horas de servicios técnicos"

    fecha_date = fields.Datetime(string="Fecha programada", required=True)
    ot_id = fields.Many2one("maintenance.request", string="OT", required=True)
    duracion = fields.Float(string="Duración (H)", required=True)
    event_calendario = fields.Many2one(
        "calendar.event", compute="_set_evento", string="Evento calendario", store=True
    )
    fecha_inicio = fields.Datetime(string="Fecha de inicio")
    fecha_fin = fields.Datetime(string="Fecha de finalización")
    horas_trabajado = fields.Float(string="Horas marcadas")
    horas_active = fields.Boolean(string="Horas activas")
    tecnicos = fields.Many2many("res.users", string="Técnicos", required=True)
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
        """Crea o actualiza el evento en el calendario sin reenviar correos si no hay cambios reales."""
        for record in self:
            evento = False
            try:
                if not record.ot_id or not record.fecha_date or not record.duracion:
                    _logger.info(f"⚠️ Faltan datos para crear evento en OT {record.ot_id.name if record.ot_id else 'Sin OT'}")
                    record.event_calendario = False
                    continue

                # Obtener partners válidos
                partner_ids = []
                for user in record.tecnicos:
                    if user.partner_id and user.partner_id.id:
                        partner_ids.append(user.partner_id.id)

                if record.ot_id.empresa and record.ot_id.empresa.id:
                    partner_ids.append(record.ot_id.empresa.id)
                if record.ot_id.ubicacion and record.ot_id.ubicacion.id:
                    partner_ids.append(record.ot_id.ubicacion.id)

                partner_ids = list(set(pid for pid in partner_ids if pid))

                valores_evento = {
                    "name": f"Servicio programado / {record.ot_id.name or 'Sin nombre'}",
                    "start": record.fecha_date,
                    "stop": record.fecha_date + timedelta(hours=record.duracion),
                    "duration": record.duracion,
                    "ots_id": record.ot_id.id,
                    "programacion_id": record.id,
                    "partner_ids": [(6, 0, partner_ids)],
                }

                # Buscar evento existente
                evento = record.event_calendario or self.env["calendar.event"].search(
                    [("ots_id", "=", record.ot_id.id), ("programacion_id", "=", record.id)],
                    limit=1,
                )

                if evento:
                    # Solo actualiza si hay diferencias reales
                    cambios = {}
                    for campo, valor in valores_evento.items():
                        if campo in evento._fields and evento[campo] != valor:
                            cambios[campo] = valor
                    if cambios:
                        _logger.info(f"🔁 Actualizando evento {evento.id} con cambios: {list(cambios.keys())}")
                        evento.with_context(no_mail_to_attendees=True).write(cambios)
                    else:
                        _logger.debug(f"✅ Sin cambios en evento {evento.id}, no se actualiza ni se reenvían correos.")
                else:
                    _logger.info(f"🆕 Creando nuevo evento para OT {record.ot_id.name}")
                    evento = self.env["calendar.event"].with_context(no_mail_to_attendees=True).create(valores_evento)

            except Exception as e:
                _logger.error(f"❌ Error al generar evento: {e}")

            record.event_calendario = evento

    @api.depends("fecha_inicio", "fecha_fin")
    def _compute_horas_trabajado(self):
        for record in self:
            if record.fecha_inicio and record.fecha_fin:
                diferencia = record.fecha_fin - record.fecha_inicio
                horas = diferencia.total_seconds() / 3600
                record.horas_trabajado = round(horas, 2)
                if record.es_servicio_finalizado:
                    record.h_optimizado = record.duracion - record.horas_trabajado
            else:
                record.horas_trabajado = 0.0

    def action_view_registro(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Programación",
            "res_model": "programacion.mantenimiento",
            "view_mode": "form",
            "res_id": self.id,
        }

    def action_validacion_time(self):
        for record in self:
            if not record.horas_trabajado:
                raise UserError(_("No puedes aceptar una incidencia sin horas trabajadas"))
            if record.es_servicio_finalizado:
                record.h_optimizado = record.duracion - record.horas_trabajado
                record.h_faltantes = 0.00
            else:
                record.h_faltantes = record.duracion - record.horas_trabajado
                record.h_optimizado = 0.00

    def action_validacion_time_cancel(self):
        for record in self:
            record.h_optimizado = 0.00
            record.h_faltantes = 0.00
