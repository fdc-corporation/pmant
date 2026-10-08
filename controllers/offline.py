# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

from odoo.http import Controller, request, route
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)
_STATIC = Path(__file__).resolve().parent.parent / "static" / "offline"


class PmantOffline(Controller):
    @route("/pmant/offline", type="http", auth="public", methods=["GET"])
    def shell(self, **kwargs):
        # El HTML es idéntico para todos; nunca contiene sesión ni datos privados.
        return request.make_response((_STATIC / "index.html").read_text(encoding="utf-8"), headers=[
            ("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-cache"),
        ])

    @route("/pmant/offline/sw.js", type="http", auth="public", methods=["GET"])
    def worker(self, **kwargs):
        return request.make_response((_STATIC / "sw.js").read_text(encoding="utf-8"), headers=[
            ("Content-Type", "application/javascript; charset=utf-8"),
            ("Service-Worker-Allowed", "/pmant/offline"), ("Cache-Control", "no-cache"),
        ])

    @route("/pmant/offline/api", type="jsonrpc", auth="user", methods=["POST"])
    def api(self, action, payload=None):
        origin = request.httprequest.headers.get("Origin")
        if origin != request.httprequest.host_url.rstrip("/"):
            raise AccessError("La solicitud debe proceder de esta aplicación.")
        user = request.env.user
        if not (user.has_group("pmant.group_pmant_tecnico") or user.has_group("pmant.group_pmant_supervisor")) or user.share:
            raise AccessError("Esta función requiere el rol Técnico o Supervisor PMANT.")
        if request.httprequest.content_length and request.httprequest.content_length > 40 * 1024 * 1024:
            raise ValidationError("El envío supera los 40 MB. Envíe menos fotografías por informe.")
        try:
            with request.env.cr.savepoint():
                if action == "identity":
                    return {"key": "%s:%s" % (request.db, user.id), "name": user.name, "companies": request.env.companies.ids}
                if action == "download":
                    orders = request.env["maintenance.request"].search([
                        ("user_id", "=", user.id), ("tarea", "!=", False),
                        ("company_id", "in", request.env.companies.ids), ("stage_id.sequence", "in", [1, 2]),
                    ], limit=101, order="schedule_date, id")
                    if len(orders) > 100:
                        raise ValidationError("Tiene más de 100 órdenes pendientes; reduzca la asignación antes de descargar.")
                    return {"orders": [order._kd_offline_snapshot() for order in orders],
                        "states": request.env["estadoproceso.mantenimiento"].search([]).read(["name"])}
                if action == "sync":
                    if not isinstance(payload, dict):
                        raise ValidationError("Informe no válido.")
                    order = request.env["maintenance.request"].browse(int(payload.get("id", 0))).exists()
                    if not order:
                        raise ValidationError("La orden ya no está disponible. Su borrador se conserva.")
                    return {"order": order._kd_offline_apply(payload)}
                if action == "review":
                    order = request.env["maintenance.request"].browse(int((payload or {}).get("id", 0))).exists()
                    if not order:
                        raise ValidationError("La orden ya no está disponible.")
                    return {"order": order._kd_offline_snapshot()}
                raise ValidationError("Acción desconocida.")
        except (AccessError, UserError, ValidationError) as error:
            return {
                "error": str(error),
                "rejected": True,
                "conflict": bool(getattr(error, "kd_offline_conflict", False)),
            }
        except (TypeError, ValueError, KeyError):
            return {"error": "Los datos enviados no son válidos. Su borrador se conserva.", "rejected": True, "conflict": False}


