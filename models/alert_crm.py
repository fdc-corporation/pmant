from odoo import models, fields
from datetime import timedelta
import logging
import pytz

_logger = logging.getLogger(__name__)
LIMA_TZ = pytz.timezone("America/Lima")


class leadMantenimiento(models.Model):
    _description = "CRM LEAD"
    _inherit = "crm.lead"


    fecha_planeada = fields.Datetime(string="Fecha Llamada", tracking=True, index=True)
    recordatorios_ids = fields.Many2many(
        comodel_name="calendar.alarm",
        string="Recordatorios",
        help="Recordatorios asociados a esta lead de mantenimiento",
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
                new_stage = self.env["crm.stage"].browse(new_id)
                vals["recordatorios_ids"] = [(6, 0, new_stage.recordatorios_ids.ids)]
            else:
                # sin etapa -> sin recordatorios
                vals["recordatorios_ids"] = [(5, 0, 0)]
        return super().write(vals)

    def _check_and_send_alarms(self):
        # 1) AHORA en Lima (truncado a minuto)
        now_utc = fields.Datetime.now().replace(second=0, microsecond=0)  # naive UTC (Odoo)
        now_lima = (
            pytz.UTC.localize(now_utc)
            .astimezone(LIMA_TZ)
            .replace(second=0, microsecond=0)
        )
        _logger.info("🔍 Verificando alarmas (Lima=%s)", now_lima.strftime("%Y-%m-%d %H:%M"))

        mult = {"minutes": 1, "hours": 60, "days": 1440}

        # 2) Recorre leads con fecha_planeada
        for lead in self.search([("fecha_planeada", "!=", False)]):
            # convertir fecha_planeada (naive UTC) -> Lima y truncar a minuto
            fp_utc = lead.fecha_planeada.replace(second=0, microsecond=0)
            fp_lima = (
                pytz.UTC.localize(fp_utc)
                .astimezone(LIMA_TZ)
                .replace(second=0, microsecond=0)
            )

            for alarm in lead.recordatorios_ids:
                mins_before = (alarm.duration or 0) * mult.get(alarm.interval, 1)

                # 3) Trigger en LIMA: fecha_planeada (Lima) - minutos del recordatorio
                trigger_lima = (fp_lima - timedelta(minutes=mins_before)).replace(second=0, microsecond=0)

                # 4) Evitar duplicados (clave en hora LIMA al minuto)
                key = f"{lead.id}:{alarm.id}:{trigger_lima.strftime('%Y-%m-%d %H:%M')}-LIMA"
                if lead.last_reminder_key == key:
                    continue

                _logger.info(
                    "🕒 lead %s | alarm=%s %s min | FP Lima=%s | Trigger Lima=%s | Now Lima=%s",
                    lead.id, alarm.alarm_type, mins_before,
                    fp_lima.strftime("%Y-%m-%d %H:%M"),
                    trigger_lima.strftime("%Y-%m-%d %H:%M"),
                    now_lima.strftime("%Y-%m-%d %H:%M"),
                )

                # 5) Comparación EXACTA en LIMA (fecha+hora+minuto)
                if now_lima == trigger_lima:
                    title = "Recordatorio de Seguimiento"
                    msg = f"El lead “{lead.name}” tiene una fecha de seguimiento a las {fp_lima.strftime('%Y-%m-%d %H:%M')}."
                    _logger.info("⚠️ EJECUCION DE TIPO" +  str(alarm.alarm_type))

                    if alarm.alarm_type == "notification":
                        users = self._get_users_to_notify(lead)
                        _logger.info("⚠️ EJECUCION DE CONTACTO NOTIFICACION" +  str(users))

                        self._queue_popup(
                            users, title, msg, notif_type="warning",
                            sticky=True, record=lead,
                        )

                    elif alarm.alarm_type == "email":
                        self._send_email_notification_for(lead, alarm)

                    lead.write({"last_reminder_key": key})
                # else: no es el minuto exacto → no dispara
    def _get_users_to_notify(self, lead):
        """Solo el vendedor (lead.user_id). Fallback: admin."""
        # 'lead' es un registro crm.lead (no un recordset)
        user = lead.user_id
        if user and user.active:
            return user                    # un único res.users
        # (opcional) fallback al líder del equipo
        if getattr(lead, "team_id", False) and lead.team_id.user_id and lead.team_id.user_id.active:
            return lead.team_id.user_id
        # último fallback
        return self.env.ref("base.user_admin")

    def _send_email_notification_for(self, lead, alarm):
        template = self.env.ref(
            "pmant.template_crm_notificacion",
            raise_if_not_found=False
        )
        if template:
            template.send_mail(lead.id, force_send=True)

    def _queue_popup(
        self, users, title, message, notif_type="info", sticky=False,
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

    # ===== Defaults =====
    def _default_recordatorios(self):
        return self.stage_id.recordatorios_ids if self.stage_id else self.env["calendar.alarm"].search([], limit=1)


class Etapalead(models.Model):
    _inherit = "crm.stage"
    recordatorios_ids = fields.Many2many("calendar.alarm", string="Recordatorios")


