from odoo import http
from odoo.http import request
from markupsafe import escape as esc
import logging

_logger = logging.getLogger(__name__)


class WebForm(http.Controller):

    @staticmethod
    def _equipment_is_allowed(equipment):
        commercial_partner = request.env.user.partner_id.commercial_partner_id
        return bool(
            equipment
            and (
                equipment.propietario.commercial_partner_id == commercial_partner
                or equipment.ubicacion.commercial_partner_id == commercial_partner
            )
        )

    @http.route(
        "/my/equipos/<int:equipo_id>/checklist/<int:plantilla_id>",
        type="http", auth="user", website=True
    )
    def show_checklist(self, equipo_id, plantilla_id, **kwargs):
        env = request.env
        equipo = env["maintenance.equipment"].sudo().browse(equipo_id)
        plantilla = env["pmant.checklist"].sudo().browse(plantilla_id)
        if not equipo.exists() or not plantilla.exists() or not self._equipment_is_allowed(equipo):
            return request.not_found()

        return request.render(
            "pmant.checklist_template",
            {"equipo": equipo, "plantilla": plantilla},
        )

    @http.route(
        "/my/equipo/<int:equipo_id>/checklist/historial",
        type="http", auth="user", website=True
    )
    def checklist_historial(self, equipo_id, **kwargs):
        env = request.env
        equipo = env["maintenance.equipment"].sudo().browse(equipo_id)
        if not equipo.exists() or not self._equipment_is_allowed(equipo):
            return request.not_found()

        grupos = env["pmant.checklist.group"].sudo().search(
            [("equipo_id", "=", equipo.id)],
            order="create_date desc"
        )

        return request.render(
            "pmant.respuestas_pmant",
            {"equipo": equipo, "respuestas": grupos},
        )

    @http.route(
        "/checklist/submit/<int:equipo_id>/<int:plantilla_id>",
        type="http", auth="user", website=True, methods=["POST"], csrf=True
    )
    def submit_checklist(self, equipo_id, plantilla_id, **post):
        env = request.env
        equipo = env["maintenance.equipment"].sudo().browse(equipo_id)
        plantilla = env["pmant.checklist"].sudo().browse(plantilla_id)
        if not equipo.exists() or not plantilla.exists() or not self._equipment_is_allowed(equipo):
            return request.not_found()

        # URL para botones del correo
        base_url = (
            env["ir.config_parameter"].sudo()
            .get_param("web.base.url", request.httprequest.host_url.rstrip("/"))
        )
        url_detalle = f"{base_url}/my/equipos/{equipo.id}/detalles"

        respuestas_creadas = []
        preguntas_con_no = []

        # Un solo grupo por envío
        grupo = env["pmant.checklist.group"].sudo().create({
            "equipo_id": equipo.id,
            "name": "New",  # tu modelo puede renombrarlo con secuencia en create()
        })

        # === Parseo de respuestas del formulario ===
        for pregunta in plantilla.line_questions:
            vals = {
                "question_id": pregunta.id,
                "equipo_id": equipo.id,
                "group_id": grupo.id,
                "usuario_responsable": env.user.id,
            }

            # Respuesta principal
            if pregunta.tipo_respuesta == "si_no":
                raw = post.get(f"respuesta_{pregunta.id}_si_no")
                raw = raw if raw in ("si", "no") else "no"
                is_yes = (raw == "si")
                vals["respuesta_si_no"] = is_yes
                if not is_yes:
                    preguntas_con_no.append(pregunta)

            elif pregunta.tipo_respuesta == "texto":
                texto = (post.get(f"respuesta_{pregunta.id}_texto") or "").strip()
                if texto:
                    vals["respuesta_texto"] = texto

            # Comentario por pregunta (checkbox + textarea)
            if post.get(f"comentario_{pregunta.id}"):
                vals["is_comentario"] = True
                comentario_txt = (post.get(f"comentario_texto_{pregunta.id}") or "").strip()
                vals["comentario"] = comentario_txt

            resp = env["pmant.checklist.respuesta"].sudo().create(vals)
            respuestas_creadas.append(resp)

        # ==============================
        #   DESTINATARIOS y PLANNER
        # ==============================
        # Planner (solo para ALERTA)
        planner_group = env.ref("pmant.group_pmant_planner", raise_if_not_found=False)
        planner_user = env["res.users"]
        if planner_group:
            active_users = planner_group.sudo().user_ids.filtered(lambda u: u.active)
            if active_users:
                # si hay varios, escoge uno determinístico (menor id)
                planner_user = active_users.sorted("id")[:1]

        planner_email = planner_user and planner_user.email or False

        # Resumen completo: propietario / ubicación (NO planner)
        resumen_recipients = set()
        if getattr(equipo, "propietario", False) and equipo.propietario.email:
            resumen_recipients.add(equipo.propietario.email)
        if getattr(equipo, "ubicacion", False) and equipo.ubicacion.email:
            resumen_recipients.add(equipo.ubicacion.email)
        # quitar al planner si por algún motivo coincide
        if planner_email and planner_email in resumen_recipients:
            resumen_recipients.remove(planner_email)

        email_from = (env.company.sudo().email) or "fdccorp@fdc-corporation.com"


        # ==============================
        #   CORREO 1: RESUMEN COMPLETO
        # ==============================
        try:
            if resumen_recipients:
                items_html = []
                for r in respuestas_creadas:
                    if r.respuesta_texto:
                        respuesta_txt = esc(r.respuesta_texto)
                    else:
                        respuesta_txt = "Sí" if getattr(r, "respuesta_si_no", False) else "No"

                    li = f"<li><strong>{esc(r.question_id.name)}</strong>: {respuesta_txt}"
                    if getattr(r, "is_comentario", False) and getattr(r, "comentario", ""):
                        li += f"<br/><span style='color:#666'><em>Comentario:</em> {esc(r.comentario)}</span>"
                    li += "</li>"
                    items_html.append(li)

                cuerpo_html = f"""
                <div style="font-family: Arial, sans-serif; font-size:14px; color:#333; line-height:1.6; max-width:680px;">
                  <p>Hola,</p>
                  <p>Se ha completado un checklist para el equipo
                     <strong style="color:#004080;">{esc(equipo.name)}</strong>.
                  </p>
                  <ul style="padding-left:20px; margin: 10px 0;">
                    {''.join(items_html)}
                  </ul>
                  <div style="margin:24px 0;">
                    <a href="{url_detalle}" style="
                        background:#004080; color:#fff; padding:12px 18px;
                        text-decoration:none; border-radius:6px; font-weight:600; display:inline-block;">
                      Ver detalles del equipo
                    </a>
                  </div>
                  <p style="color:#999;">Este es un mensaje automático, por favor no responder.</p>
                </div>
                """

                request.env["mail.mail"].sudo().create({
                    "subject": f"Checklist completado - {equipo.name}",
                    "body_html": cuerpo_html,
                    "email_to": ",".join(sorted(resumen_recipients)),
                    "email_from": email_from,
                }).send()
            else:
                _logger.info("Checklist resumen: sin destinatarios (propietario/ubicación).")
        except Exception as e:
            _logger.exception("Error al enviar correo resumen de checklist: %s", e)

        # ===========================================
        #   CORREO 2: ALERTA SOLO AL PLANNER (si 'No')
        # ===========================================
        try:
            if preguntas_con_no and planner_email:
                items_no = "".join(
                    f"<li><strong>{esc(p.name)}</strong></li>" for p in preguntas_con_no
                )
                cuerpo_alerta = f"""
                <div style="font-family: Arial, sans-serif; font-size:14px; color:#333; line-height:1.6; max-width:680px;">
                  <p>
                    <strong style="color:#dc3545;">⚠ Atención:</strong>
                    Se detectaron respuestas negativas en el checklist del equipo
                    <strong style="color:#004080;">{esc(equipo.name)}</strong>.
                  </p>
                  <p>Preguntas con respuesta <strong style="color:#dc3545;">"No"</strong>:</p>
                  <ul style="padding-left:20px; margin: 10px 0 20px;">
                    {items_no}
                  </ul>
                  <div style="margin:24px 0;">
                    <a href="{url_detalle}" style="
                        background:#dc3545; color:#fff; padding:12px 18px;
                        text-decoration:none; border-radius:6px; font-weight:600; display:inline-block;">
                      Ver detalles del equipo
                    </a>
                  </div>
                  <p style="color:#999;">Por favor, revise el estado del equipo.</p>
                </div>
                """

                request.env["mail.mail"].sudo().create({
                    "subject": f"⚠ Alerta - Respuestas negativas en checklist de {equipo.name}",
                    "body_html": cuerpo_alerta,
                    "email_to": planner_email,         # ← SOLO planner
                    "email_from": email_from,
                }).action_send_and_close()

                # (Opcional) Crear Oportunidad en CRM asignada SOLO al planner
                if planner_user:
                    # partner_id: usa propietario si existe; si no, ubicación (ambos son res.partner)
                    partner_id = False
                    if getattr(equipo, "propietario", False):
                        partner_id = equipo.propietario.id
                    elif getattr(equipo, "ubicacion", False):
                        partner_id = equipo.ubicacion.id

                    lead_values = {
                        "name": f"⚠ Alerta Checklist - {equipo.name}",
                        "type": "opportunity",
                        "partner_id": partner_id or False,
                        "user_id": planner_user.id,  # ← asignado al planner (res.users)
                        "description": "Se detectaron respuestas negativas en el checklist del equipo.",
                        "automated_probability": 50,
                        # Campos personalizados (si existen en tu modelo):
                    }
                    lead_model = request.env["crm.lead"]
                    if "equipo_tarea" in lead_model._fields:
                        lead_values["equipo_tarea"] = [(6, 0, [equipo.id])]
                    if "ubicacion" in lead_model._fields and equipo.ubicacion:
                        lead_values["ubicacion"] = equipo.ubicacion.id
                    lead_model.sudo().create(lead_values)
            elif preguntas_con_no and not planner_email:
                _logger.warning("Checklist alerta: hay 'No' pero no hay planner con email.")
        except Exception as e:
            _logger.exception("Error al enviar correo de alerta del checklist: %s", e)

        return request.render("pmant.template_checklist_thanks", {"equipo": equipo})


