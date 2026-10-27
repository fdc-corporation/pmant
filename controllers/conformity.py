# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request


class PmantConformityPortal(http.Controller):

    def _order_from_token(self, token):
        return request.env["maintenance.request"].sudo().search([
            ("conformity_token", "=", token),
        ], limit=1)

    @http.route("/pmant/acta/<string:token>", type="http", auth="public", website=True, sitemap=False)
    def conformity_form(self, token, **kwargs):
        order = self._order_from_token(token)
        if not order:
            return request.not_found()
        return request.render("pmant.portal_conformity_form", {"order": order, "token": token})

    @http.route(
        "/pmant/acta/<string:token>/submit", type="http", auth="public",
        website=True, methods=["POST"], csrf=True, sitemap=False,
    )
    def conformity_submit(self, token, **post):
        order = self._order_from_token(token)
        if not order:
            return request.not_found()
        if order.conformity_state == "pdf":
            return request.render("pmant.portal_conformity_success", {"order": order})

        upload = request.httprequest.files.get("conformity_pdf")
        content = upload.read() if upload else b""
        filename = (upload.filename or "").strip() if upload else ""
        mimetype = (upload.mimetype or "").lower() if upload else ""
        if not content:
            return request.render("pmant.portal_conformity_form", {
                "order": order, "token": token,
                "error": _("Seleccione el acta de conformidad en formato PDF."),
            })
        if len(content) > 20 * 1024 * 1024:
            return request.render("pmant.portal_conformity_form", {
                "order": order, "token": token,
                "error": _("El archivo PDF no puede superar los 20 MB."),
            })
        if mimetype != "application/pdf" or not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            return request.render("pmant.portal_conformity_form", {
                "order": order, "token": token,
                "error": _("El archivo seleccionado debe ser un PDF válido."),
            })

        order.sudo()._receive_conformity_pdf(filename, content)
        return request.render("pmant.portal_conformity_success", {"order": order})
