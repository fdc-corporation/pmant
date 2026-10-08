# -*- coding: utf-8 -*-
"""Captura de tiempos e informes; las escrituras offline pasan por el ORM normal."""
import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from markupsafe import escape
from psycopg2 import IntegrityError
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


def utc_stamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc).replace(tzinfo=None)
    except (AttributeError, TypeError, ValueError):
        raise ValidationError(_("La marca de tiempo debe incluir su zona horaria."))


def wire_stamp(value):
    return value.isoformat() + "Z" if value else None


class WorkSession(models.Model):
    _name = "pmant.work.session"
    _description = "Tramo de trabajo PMANT"
    _order = "started_at, id"

    sheet_id = fields.Many2one("programacion.mantenimiento", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="sheet_id.ot_id.company_id", store=True, index=True)
    technician_id = fields.Many2one("res.users", required=True, index=True)
    started_at = fields.Datetime("Inicio", required=True)
    ended_at = fields.Datetime("Fin")
    source = fields.Selection([("online", "En línea"), ("offline", "Sin conexión"), ("legacy", "Registro previo")], required=True)
    hours = fields.Float("Horas efectivas", compute="_compute_hours")

    @api.depends("started_at", "ended_at")
    def _compute_hours(self):
        for record in self:
            record.hours = max(0, ((record.ended_at or fields.Datetime.now()) - record.started_at).total_seconds()) / 3600

    @api.constrains("started_at", "ended_at")
    def _check_dates(self):
        for record in self:
            if record.ended_at and record.ended_at < record.started_at:
                raise ValidationError(_("El fin de un tramo no puede preceder a su inicio."))

    def init(self):
        self.env.cr.execute("CREATE UNIQUE INDEX IF NOT EXISTS pmant_one_active_session ON pmant_work_session (technician_id) WHERE ended_at IS NULL")


class SyncReceipt(models.Model):
    _name = "pmant.sync.receipt"
    _description = "Recepción de cambios offline PMANT"

    operation_id = fields.Char(required=True, index=True)
    order_id = fields.Many2one("maintenance.request", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True)
    payload_hash = fields.Char(required=True)
    result_json = fields.Json(readonly=True)
    _operation_unique = models.Constraint("UNIQUE(operation_id)", "La operación ya fue recibida.")


class OfflineTimesheet(models.Model):
    _inherit = "programacion.mantenimiento"

    kd_session_ids = fields.One2many("pmant.work.session", "sheet_id", string="Tramos de trabajo", readonly=True)
    kd_time_state = fields.Selection([
        ("new", "Sin iniciar"), ("running", "En curso"),
        ("paused", "Pausado"), ("finished", "Finalizado"),
    ], default="new", string="Estado del tiempo", readonly=True, copy=False)
    kd_last_event_at = fields.Datetime(readonly=True, copy=False)
    kd_sync_revision = fields.Integer(default=0, readonly=True, copy=False)

    def write(self, vals):
        if not self.env.su and set(vals) & {"kd_time_state", "kd_last_event_at", "kd_sync_revision", "kd_session_ids"}:
            raise AccessError(_("Utilice los botones del servicio para modificar sus tiempos."))
        return super().write(vals)

    def _kd_lock(self):
        self.ensure_one()
        # UPDATE fuerza un reintento de PostgreSQL si otra petición ha cambiado
        # la hoja desde el snapshot de la transacción (REPEATABLE READ de PMANT).
        self.env.cr.execute("UPDATE programacion_mantenimiento SET kd_sync_revision = COALESCE(kd_sync_revision, 0) + 1 WHERE id = %s", [self.id])
        self.invalidate_recordset()

    def _kd_create_session(self, values):
        try:
            with self.env.cr.savepoint():
                return self.env["pmant.work.session"].sudo().create(values)
        except IntegrityError as error:
            if error.diag.constraint_name == "pmant_one_active_session":
                raise ValidationError(_("Ya existe un servicio activo para este técnico. Pause o finalice ese servicio antes de continuar.")) from error
            raise

    def _kd_time_event(self, action, stamp=None, source="online"):
        self.ensure_one()
        order = self.ot_id
        if source == "offline":
            order._kd_offline_check()
        else:
            order._kd_service_check()
        if order.stage_id.sequence not in (1, 2):
            raise ValidationError(_("Solo puede registrar tiempos en órdenes nuevas o en progreso."))
        self.check_access("write")
        self._kd_lock()
        stamp = stamp or fields.Datetime.now()
        if stamp > fields.Datetime.now() + timedelta(minutes=5):
            raise ValidationError(_("La hora capturada está en el futuro. Revise el reloj del dispositivo."))
        if self.kd_last_event_at and stamp < self.kd_last_event_at:
            raise ValidationError(_("Las marcas de tiempo deben estar en orden cronológico."))
        sessions = self.kd_session_ids.sudo()
        if not sessions and self.fecha_inicio and not self.fecha_fin:
            sessions = self._kd_create_session({
                "sheet_id": self.id, "technician_id": order.user_id.id,
                "started_at": self.fecha_inicio, "source": "legacy",
            })
            self.sudo().write({"kd_time_state": "running"})
        active = sessions.filtered(lambda item: not item.ended_at)
        state = self.kd_time_state
        if action not in {"start", "pause", "resume", "finish"}:
            raise ValidationError(_("Acción de tiempo desconocida."))
        allowed = {"start": {"new"}, "pause": {"running"}, "resume": {"paused"}, "finish": {"running", "paused"}}
        if state not in allowed[action]:
            raise ValidationError(_("La acción no corresponde al estado actual del servicio."))
        if self.fecha_fin or self.es_servicio_finalizado:
            raise ValidationError(_("Esta hoja de horas ya está finalizada."))
        values = {"kd_last_event_at": stamp}
        if action in {"start", "resume"}:
            # Serializar también entre distintas órdenes del mismo técnico.
            self.env.cr.execute("SELECT id FROM res_users WHERE id = %s FOR UPDATE", [order.user_id.id])
            other = self.env["pmant.work.session"].sudo().search([
                ("technician_id", "=", order.user_id.id), ("ended_at", "=", False),
            ], limit=1)
            legacy = self.env["programacion.mantenimiento"].sudo().search([
                ("ot_id.user_id", "=", order.user_id.id), ("fecha_inicio", "!=", False),
                ("fecha_fin", "=", False), ("kd_time_state", "in", ["new", "running"]), ("id", "!=", self.id),
            ], limit=1)
            if other or legacy:
                raise ValidationError(_("Pause o finalice el otro servicio activo antes de continuar."))
            if action == "start":
                order._kd_start_service()
                values["fecha_inicio"] = stamp
            self._kd_create_session({
                "sheet_id": self.id, "technician_id": order.user_id.id,
                "started_at": stamp, "source": source,
            })
            values["kd_time_state"] = "running"
        else:
            if active:
                if stamp < active.started_at:
                    raise ValidationError(_("La hora de cierre precede al inicio del tramo."))
                active.write({"ended_at": stamp})
            values["kd_time_state"] = "paused" if action == "pause" else "finished"
            if action == "finish":
                if any(plan.is_informe_file and not plan.informe_file for plan in order.tarea.planequipo):
                    raise ValidationError(_("Adjunte el informe técnico de cada equipo que usa la opción Subir informe."))
                values.update(fecha_fin=stamp, es_servicio_finalizado=True)
                stage = self.env["maintenance.stage"].search([("sequence", "=", 3)], limit=1)
                if not stage:
                    raise ValidationError(_("No se encontró la etapa de revisión."))
                if source == "offline":
                    executed_date = fields.Datetime.context_timestamp(self, stamp).date()
                    # Campo derivado y acotado, una vez comprobados responsable,
                    # compañía, acceso, estado y cronología de la finalización.
                    order.sudo().write({"fecha_ejec": executed_date})
                order.write({"stage_id": stage.id})
        self.sudo().write(values)
        self._compute_horas_trabajado()
        task_values = {"action_servicio": action != "finish", "service_started_at": stamp if action in {"start", "resume"} else False}
        order.tarea.write(task_values)

    def _compute_horas_trabajado(self):
        with_sessions = self.filtered("kd_session_ids")
        for record in with_sessions:
            record.horas_trabajado = round(sum(record.kd_session_ids.filtered("ended_at").mapped("hours")), 2)
            if record.es_servicio_finalizado:
                record.h_optimizado = record.duracion - record.horas_trabajado
        return super(OfflineTimesheet, self - with_sessions)._compute_horas_trabajado()


class OfflineTask(models.Model):
    _inherit = "tarea.mantenimiento"

    service_started_at = fields.Datetime(string="Servicio iniciado", readonly=True)
    service_elapsed_hours = fields.Float(string="Tiempo transcurrido", compute="_compute_service_elapsed_hours")
    kd_time_state = fields.Selection([
        ("new", "Sin iniciar"), ("running", "En curso"), ("paused", "Pausado"), ("finished", "Finalizado"),
    ], compute="_kd_compute_timer", string="Estado del tiempo")
    kd_elapsed_seconds = fields.Float(compute="_kd_compute_timer")
    kd_active_since = fields.Datetime(compute="_kd_compute_timer")

    @api.depends("ots.tab_horas.kd_session_ids.started_at", "ots.tab_horas.kd_session_ids.ended_at", "ots.tab_horas.kd_time_state", "ots.tab_horas.fecha_date", "service_started_at")
    def _kd_compute_timer(self):
        for task in self:
            sheet = task.ots[:1]._kd_sheet() if task.ots else self.env["programacion.mantenimiento"]
            sessions = sheet.kd_session_ids
            task.kd_elapsed_seconds = sum((item.ended_at - item.started_at).total_seconds() for item in sessions if item.ended_at)
            active = sessions.filtered(lambda item: not item.ended_at)[:1]
            task.kd_active_since = active.started_at if active else (task.service_started_at if not sessions else False)
            task.kd_time_state = task.ots[:1].kd_time_state if task.ots else "new"

    @api.depends("kd_elapsed_seconds", "kd_active_since")
    def _compute_service_elapsed_hours(self):
        now = fields.Datetime.now()
        for task in self:
            active_seconds = max(0, (now - task.kd_active_since).total_seconds()) if task.kd_active_since else 0
            task.service_elapsed_hours = (task.kd_elapsed_seconds + active_seconds) / 3600

    def _kd_require_sheet(self):
        self.ensure_one()
        if not self.ots:
            raise ValidationError(_("Debe programar la orden de trabajo antes de iniciar el servicio."))
        sheet = self.ots[:1]._kd_sheet()
        if not sheet:
            raise ValidationError(_("La orden necesita una hoja de horas programada."))
        return sheet

    def init_servicio(self):
        for task in self:
            sheet = task._kd_require_sheet()
            sheet._kd_time_event("start")
        return True

    def action_pause_service(self):
        for task in self:
            task._kd_require_sheet()._kd_time_event("pause")
        return True

    def action_resume_service(self):
        for task in self:
            task._kd_require_sheet()._kd_time_event("resume")
        return True


class OfflineOrder(models.Model):
    _inherit = "maintenance.request"

    kd_time_state = fields.Selection([
        ("new", "Sin iniciar"), ("running", "En curso"), ("paused", "Pausado"), ("finished", "Finalizado"),
    ], compute="_kd_compute_time_state", string="Estado del tiempo")

    @api.depends("tab_horas.kd_time_state", "tab_horas.fecha_inicio", "tab_horas.fecha_fin", "tab_horas.fecha_date")
    def _kd_compute_time_state(self):
        for order in self:
            sheet = order._kd_sheet()
            order.kd_time_state = ("finished" if sheet.fecha_fin else "running" if sheet.fecha_inicio and sheet.kd_time_state == "new" else sheet.kd_time_state) or "new"

    def _kd_sheet(self):
        self.ensure_one()
        return self.tab_horas.sorted(key=lambda item: (item.fecha_date or datetime.min, item.id), reverse=True)[:1]

    def _kd_start_service(self):
        """Inicia la OT respetando el flujo de etapas existente en PMANT."""
        self.ensure_one()
        self.check_access("read")
        self.tarea.check_access("write")
        stage = self.env["maintenance.stage"].search([("sequence", "=", 2)], limit=1)
        if stage and self.stage_id != stage:
            self.write({"stage_id": stage.id})

    def _kd_service_check(self):
        self.ensure_one()
        self.check_access("read")
        manager = self.env.user.has_group("pmant.group_pmant_admin") or self.env.user.has_group("pmant.group_pmant_planner")
        if not self.tarea or (not manager and self.user_id != self.env.user) or self.company_id not in self.env.companies:
            raise AccessError(_("Solo el técnico responsable puede registrar este servicio."))
        self.tarea.check_access("write")

    def _kd_offline_check(self):
        self._kd_service_check()
        user = self.env.user
        if not (user.has_group("pmant.group_pmant_tecnico") or user.has_group("pmant.group_pmant_supervisor")) or self.user_id != user:
            raise AccessError(_("Esta función requiere el rol Técnico o Supervisor PMANT y una orden propia."))

    def _kd_offline_token(self):
        self.ensure_one()
        parts = [(self._name, self.id, str(self.write_date)), ("task", self.tarea.id, str(self.tarea.write_date))]
        for collection in (self.tab_horas, self.tab_horas.kd_session_ids, self.tarea.planequipo, self.tarea.planequipo.procesos, self.tarea.planequipo.procesos.adjuntos):
            parts.extend((item._name, item.id, str(item.write_date)) for item in collection.sorted("id"))
        # write_date tiene resolución limitada y no distingue dos escrituras
        # dentro de una misma transacción: incluir el contenido editable.
        parts.append(("order", self.user_id.id, self.company_id.id, self.stage_id.id))
        customer_signature = self.tarea.adjunto or b""
        if isinstance(customer_signature, str):
            customer_signature = customer_signature.encode()
        parts.append(("customer_signature", self.tarea.namefirma, self.tarea.dni, self.tarea.comentario,
                      hashlib.sha256(customer_signature).hexdigest()))
        for sheet in self.tab_horas.sorted("id"):
            parts.append(("sheet", sheet.id, str(sheet.fecha_date), str(sheet.fecha_inicio), str(sheet.fecha_fin), sheet.kd_time_state, sheet.tecnicos.ids))
        for session in self.tab_horas.kd_session_ids.sorted("id"):
            parts.append(("session", session.id, str(session.started_at), str(session.ended_at)))
        for plan in self.tarea.planequipo.sorted("id"):
            file_value = plan.informe_file or b""
            if isinstance(file_value, str):
                file_value = file_value.encode()
            parts.append(("report", plan.id, plan.equipo.id, plan.nota_observaciones, plan.nota_mantenimiento, plan.nota_recomendaciones,
                          plan.is_informe_file, plan.informe_filename, hashlib.sha256(file_value).hexdigest()))
            for process in plan.procesos.sorted("id"):
                parts.append(("process", process.id, process.estado.id, process.descripcion))
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    def _kd_offline_snapshot(self):
        self._kd_offline_check()
        # Las etapas recalculan campos almacenados de los equipos. El token
        # debe reflejar esos cambios antes de devolver la confirmación HTTP.
        self.env.flush_all()
        sheet = self._kd_sheet()
        customer_signature = self.tarea.adjunto or b""
        if isinstance(customer_signature, bytes):
            customer_signature = customer_signature.decode()
        return {
            "id": self.id, "name": self.name, "site": self.ubicacion.display_name,
            "stage": self.stage_id.name, "stage_sequence": self.stage_id.sequence,
            "token": self._kd_offline_token(), "sheet_id": sheet.id,
            "time_state": self.kd_time_state,
            "sessions": [{"start": wire_stamp(item.started_at), "end": wire_stamp(item.ended_at)} for item in sheet.kd_session_ids],
            "legacy_start": wire_stamp(sheet.fecha_inicio) if not sheet.kd_session_ids and not sheet.fecha_fin else None,
            "signature": {"data": customer_signature, "name": self.tarea.namefirma or "",
                "document": self.tarea.dni or "", "comment": self.tarea.comentario or ""},
            "plans": [{"id": plan.id, "equipment": plan.equipo.display_name,
                "observations": html2plaintext(plan.nota_observaciones or ""), "conclusions": html2plaintext(plan.nota_mantenimiento or ""),
                "recommendations": html2plaintext(plan.nota_recomendaciones or ""), "file_mode": plan.is_informe_file,
                "filename": plan.informe_filename or "", "has_file": bool(plan.informe_file),
                "processes": [{"id": process.id, "name": process.proceso.display_name,
                    "instructions": process.descripcion_proceso or "", "state_id": process.estado.id or False,
                    "comment": process.descripcion or "", "photo_count": len(process.adjuntos), "photos": [],
                    "existing_photos": [{"id": attachment.id, "name": attachment.name or "Fotografía",
                        "comment": attachment.comentario or ""} for attachment in process.adjuntos],
                } for process in plan.procesos],
            } for plan in self.tarea.planequipo],
        }

    def _kd_offline_apply(self, payload):
        self._kd_offline_check()
        sheet = self._kd_sheet()
        if not sheet or payload.get("sheet_id") != sheet.id:
            error = ValidationError(_("La programación cambió en PMANT. Su borrador se conserva; revise las diferencias."))
            error.kd_offline_conflict = True
            raise error
        sheet._kd_lock()
        # Proteger el conjunto también frente a edición normal concurrente.
        for table, ids in (("maintenance_request", self.ids), ("tarea_mantenimiento", self.tarea.ids), ("planequipo_mantenimiento", self.tarea.planequipo.ids), ("planequipoproceso_mantenimiento", self.tarea.planequipo.procesos.ids)):
            if ids:
                self.env.cr.execute('SELECT id FROM "%s" WHERE id IN %%s ORDER BY id FOR UPDATE' % table, [tuple(ids)])
        operation_id = payload.get("operation_id", "")
        try:
            UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError(_("La operación necesita un identificador válido."))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipts = self.env["pmant.sync.receipt"].sudo()
        receipt = receipts.search([("operation_id", "=", operation_id)], limit=1)
        if receipt:
            if receipt.user_id != self.env.user or receipt.order_id != self or receipt.payload_hash != digest:
                raise ValidationError(_("El identificador ya pertenece a otra operación."))
            return receipt.result_json or self._kd_offline_snapshot()
        if payload.get("token") != self._kd_offline_token():
            error = ValidationError(_("La orden o el informe cambiaron en PMANT. Su borrador se conserva; revise las diferencias antes de enviarlo."))
            error.kd_offline_conflict = True
            raise error
        if self.stage_id.sequence not in (1, 2):
            error = ValidationError(_("La orden cambió de etapa en PMANT. Su borrador se conserva; revise la versión actual."))
            error.kd_offline_conflict = True
            raise error
        if "signature" in payload:
            signature = payload["signature"]
            if not isinstance(signature, dict):
                raise ValidationError(_("La firma del cliente no es válida."))
            signature_values = {
                "namefirma": str(signature.get("name", ""))[:255],
                "dni": str(signature.get("document", ""))[:64],
                "comentario": str(signature.get("comment", "")),
            }
            if signature.get("data"):
                signature_values["adjunto"] = self._kd_validate_file(signature["data"])
            self.tarea.write(signature_values)
        plans = payload.get("plans", [])
        if not isinstance(plans, list) or len(plans) > 100:
            raise ValidationError(_("El informe contiene demasiados equipos."))
        used_plans = set()
        for data in plans:
            if not isinstance(data, dict):
                raise ValidationError(_("El informe del equipo no es válido."))
            plan = self.tarea.planequipo.filtered(lambda item: item.id == data.get("id"))
            if not plan or plan.id in used_plans:
                raise ValidationError(_("Equipo ajeno o duplicado en el informe."))
            used_plans.add(plan.id)
            values = {
                "nota_observaciones": str(escape(data.get("observations", ""))).replace("\n", "<br/>"),
                "nota_mantenimiento": str(escape(data.get("conclusions", ""))).replace("\n", "<br/>"),
                "nota_recomendaciones": str(escape(data.get("recommendations", ""))).replace("\n", "<br/>"),
                "is_informe_file": bool(data.get("file_mode")),
            }
            if data.get("file"):
                values.update(informe_file=self._kd_validate_file(data["file"]), informe_filename=str(data.get("filename", "informe"))[:255])
            plan.write(values)
            used_processes = set()
            details = data.get("processes", [])
            if not isinstance(details, list) or len(details) > 500:
                raise ValidationError(_("La lista de procesos no es válida."))
            for detail in details:
                if not isinstance(detail, dict):
                    raise ValidationError(_("El proceso no es válido."))
                process = plan.procesos.filtered(lambda item: item.id == detail.get("id"))
                if not process or process.id in used_processes:
                    raise ValidationError(_("Proceso ajeno o duplicado en el informe."))
                used_processes.add(process.id)
                state_id = detail.get("state_id") or False
                if state_id and not self.env["estadoproceso.mantenimiento"].search_count([("id", "=", state_id)]):
                    raise ValidationError(_("El resultado del proceso no existe o no está disponible."))
                process.write({
                    "descripcion": str(detail.get("comment", "")), "estado": state_id,
                    "tarea": self.tarea.id, "ots": self.id,
                })
                photos = detail.get("photos", [])
                if not isinstance(photos, list) or len(photos) > 100:
                    raise ValidationError(_("La lista de fotografías no es válida."))
                for photo in photos:
                    if not isinstance(photo, dict):
                        raise ValidationError(_("La fotografía no es válida."))
                    self.env["adjuntoimage.mantenimiento"].create({
                        "planequipoproceso": process.id, "name": str(photo.get("name", "Foto"))[:60],
                        "adjunto": self._kd_validate_file(photo["data"]), "comentario": str(photo.get("comment", "")),
                    })
        events = payload.get("events", [])
        if not isinstance(events, list) or len(events) > 1000:
            raise ValidationError(_("Cantidad de marcas de tiempo no válida."))
        for event in events:
            if not isinstance(event, dict):
                raise ValidationError(_("La marca de tiempo no es válida."))
            sheet._kd_time_event(event.get("action"), utc_stamp(event.get("at")), "offline")
        snapshot = self._kd_offline_snapshot()
        receipts.create({"operation_id": operation_id, "order_id": self.id, "user_id": self.env.uid, "payload_hash": digest, "result_json": snapshot})
        return snapshot

    def _kd_validate_file(self, value):
        try:
            if not isinstance(value, str) or len(value) > 21 * 1024 * 1024:
                raise ValueError()
            content = base64.b64decode(value, validate=True)
            if not content or len(content) > 15 * 1024 * 1024:
                raise ValueError()
            return value
        except (ValueError, TypeError):
            raise ValidationError(_("El archivo no es válido o supera los 15 MB."))
