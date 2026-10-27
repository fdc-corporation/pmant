from odoo import models, fields
from datetime import timedelta
import logging
import pytz

_logger = logging.getLogger(__name__)
LIMA_TZ = pytz.timezone("America/Lima")


class TareaMantenimiento(models.Model):
    _description = "Tarea de Mantenimiento"
    _inherit = "tarea.mantenimiento"


    fecha_planeada = fields.Datetime(string="Fecha Planeada", tracking=True, index=True)
    recordatorios_ids = fields.Many2many(
        comodel_name="calendar.alarm",
        string="Recordatorios",
        help="Recordatorios asociados a esta tarea de mantenimiento",
        default=lambda self: self._default_recordatorios(),
        tracking=True,
    )
    # Evita notificaciones duplicadas si el cron corre 2 veces el mismo minuto
    last_reminder_key = fields.Char(index=True)

    def write(self, vals):
        # si cambia de etapa, opcionalmente limpia fecha y repone recordatorios
        if "stage_id" in vals:
            vals = vals.copy()
            vals["fecha_planeada"] = False
            new_id = vals.get("stage_id") or False
            if new_id:
                new_stage = self.env["etapa.tarea.mantenimiento"].browse(new_id)
                vals["recordatorios_ids"] = [(6, 0, new_stage.recordatorios_ids.ids)]
            else:
                # sin etapa -> sin recordatorios
                vals["recordatorios_ids"] = [(5, 0, 0)]
        return super().write(vals)

    # ============== VERIFICACIÓN DE ALARMAS ==================
    def _check_and_send_alarms(self):
        # 1) AHORA en Lima (truncado a minuto)
        now_utc = fields.Datetime.now().replace(second=0, microsecond=0)
        now_lima = (
            pytz.UTC.localize(now_utc)
            .astimezone(LIMA_TZ)
            .replace(second=0, microsecond=0)
        )
        _logger.info("🔍 Verificando alarmas (Lima=%s)", now_lima.strftime("%Y-%m-%d %H:%M"))

        mult = {"minutes": 1, "hours": 60, "days": 1440}

        # 2) Recorre tareas con fecha_planeada
        for tarea in self.search([("fecha_planeada", "!=", False)]):
            # convertir fecha_planeada UTC -> Lima
            fp_utc = tarea.fecha_planeada.replace(second=0, microsecond=0)
            fp_lima = (
                pytz.UTC.localize(fp_utc)
                .astimezone(LIMA_TZ)
                .replace(second=0, microsecond=0)
            )

            for alarm in tarea.recordatorios_ids:
                mins_before = (alarm.duration or 0) * mult.get(alarm.interval, 1)

                # 3) Calcular trigger en Lima
                trigger_lima = (fp_lima - timedelta(minutes=mins_before)).replace(second=0, microsecond=0)

                # 4) Evitar duplicados con clave única
                key = f"{tarea.id}:{alarm.id}:{trigger_lima.strftime('%Y-%m-%d %H:%M')}-LIMA"
                if tarea.last_reminder_key == key:
                    continue

                _logger.info(
                    "🕒 Tarea %s | alarm=%s %s min | FP=%s | Trigger=%s | Now=%s",
                    tarea.id, alarm.alarm_type, mins_before,
                    fp_lima.strftime("%Y-%m-%d %H:%M"),
                    trigger_lima.strftime("%Y-%m-%d %H:%M"),
                    now_lima.strftime("%Y-%m-%d %H:%M"),
                )

                # 5) Comparación con tolerancia de ±1 minuto
                diff = abs((now_lima - trigger_lima).total_seconds())
                if diff <= 60:
                    title = "Recordatorio de Mantenimiento"
                    msg = f"La tarea “{tarea.name}” tiene una fecha de seguimiento que está por vencer: {fp_lima.strftime('%Y-%m-%d %H:%M')}."

                    if alarm.alarm_type == "notification":
                        users = self._get_users_to_notify(tarea)
                        self._queue_popup(
                            users, title, msg, notif_type="warning",
                            sticky=True, record=tarea,
                        )

                    elif alarm.alarm_type == "email":
                        self._send_email_notification_for(tarea, alarm)

                    tarea.write({"last_reminder_key": key})

    # ============== USUARIOS A NOTIFICAR ==================
    def _get_users_to_notify(self, tarea):
        """Devuelve todos los usuarios activos con el grupo planner."""
        xmlid = 'pmant.group_pmant_planner'
        group = self.env.ref(xmlid, raise_if_not_found=False)

        if not group:
            group = self.env['res.groups'].sudo().search([
                ('name', '=', 'Mantenimiento - Autoasignacion tareas (planner)')
            ], limit=1)

        if not group:
            _logger.info("⚠️ No existe el grupo planner '%s'. Usando admin como fallback.", xmlid)
            return self.env.ref('base.user_admin')

        users = group.user_ids.filtered(lambda u: u.active)
        if not users:
            _logger.info("⚠️ El grupo planner '%s' no tiene usuarios activos. Usando admin.", xmlid)
            return self.env.ref('base.user_admin')

        return users  # ahora devuelve todos

    # ============== ENVÍO DE EMAIL ==================
    def _send_email_notification_for(self, tarea, alarm):
        template = self.env.ref(
            "pmant.template_notification_maintenance_email",
            raise_if_not_found=False
        )
        if template:
            template.send_mail(tarea.id, force_send=True)

    # ============== POPUP NOTIFICATION ==================
    def _queue_popup(
        self, users, title, message, notif_type="info", sticky=True,
        when=None, record=None,
    ):
        return self.env["pmant.notification"].sudo().notify_users(
            users,
            title,
            message,
            notification_type=notif_type,
            sticky=sticky,
            record=record,
            scheduled_at=when or fields.Datetime.now(),
        )

    # ============== DEFAULTS ==================
    def _default_recordatorios(self):
        return self.stage_id.recordatorios_ids if self.stage_id else self.env["calendar.alarm"].search([], limit=1)


class EtapaTarea(models.Model):
    _inherit = "etapa.tarea.mantenimiento"
    recordatorios_ids = fields.Many2many("calendar.alarm", string="Recordatorios")





