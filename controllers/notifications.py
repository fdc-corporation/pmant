# -*- coding: utf-8 -*-
from odoo import fields
from odoo.http import Controller, request, route


class KdPmantNotificationController(Controller):

    @route("/pmant/notify/poll", type="jsonrpc", auth="user", methods=["POST"])
    def poll(self):
        if request.env.user.share:
            return []
        notifications = request.env["pmant.notification"].with_user(request.env.ref("base.user_root")).search([
            ("user_id", "=", request.env.user.id),
            ("seen", "=", False),
            ("scheduled_at", "<=", fields.Datetime.now()),
        ], order="scheduled_at asc, id asc", limit=50)
        return [{
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "type": notification.notification_type,
            "sticky": notification.sticky,
        } for notification in notifications]

    @route("/pmant/notify/ack", type="jsonrpc", auth="user", methods=["POST"])
    def acknowledge(self, ids=None):
        safe_ids = [int(value) for value in (ids or []) if str(value).isdigit()][:100]
        if not safe_ids:
            return True
        notifications = request.env["pmant.notification"].with_user(request.env.ref("base.user_root")).search([
            ("id", "in", safe_ids),
            ("user_id", "=", request.env.user.id),
            ("seen", "=", False),
        ])
        now = fields.Datetime.now()
        notifications.write({
            "seen": True,
            "seen_at": now,
            "is_sent": True,
            "sent_at": now,
        })
        return True

