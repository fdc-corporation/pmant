# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class KdPmantNotification(models.Model):
    _name = "pmant.notification"
    _description = "Notificación interna PMANT"
    _order = "id desc"

    title = fields.Char(string="Título", required=True)
    message = fields.Text(string="Mensaje", required=True)
    notification_type = fields.Selection(
        [("info", "Información"), ("success", "Éxito"), ("warning", "Advertencia"), ("danger", "Error")],
        string="Tipo", default="info", required=True,
    )
    sticky = fields.Boolean(string="Persistente", default=False)
    scheduled_at = fields.Datetime(string="Programada para", default=fields.Datetime.now, required=True, index=True)
    is_sent = fields.Boolean(string="Enviada", default=False, index=True)
    sent_at = fields.Datetime(string="Fecha de envío", readonly=True)
    user_id = fields.Many2one("res.users", string="Destinatario", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True)
    res_model = fields.Char(string="Modelo relacionado", index=True)
    res_id = fields.Integer(string="Registro relacionado", index=True)
    seen = fields.Boolean(string="Vista", default=False, index=True)
    seen_at = fields.Datetime(string="Fecha de lectura", readonly=True)

    @api.model
    def notify_users(self, users, title, message, notification_type="info", sticky=False, record=None):
        record = record.exists()[:1] if record else record
        company = (
            record.company_id
            if record and "company_id" in record._fields and record.company_id
            else record.compania
            if record and "compania" in record._fields and record.compania
            else self.env.company
        )
        users = users.exists().filtered(
            lambda user: user.active
            and not user.share
            and company in user.company_ids
        )
        if not users:
            return self.browse()
        values = []
        for user in users:
            values.append({
                "title": title,
                "message": message,
                "notification_type": notification_type,
                "sticky": sticky,
                "user_id": user.id,
                "company_id": company.id,
                "res_model": record._name if record else False,
                "res_id": record.id if record else False,
            })
        return self.with_user(self.env.ref("base.user_root")).create(values)

    @api.model
    def pmant_manager_users(self):
        users = self.env["res.users"]
        for xmlid in ("pmant.group_pmant_planner", "pmant.group_pmant_admin"):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                users |= group.user_ids
        return users.filtered(lambda user: user.active and not user.share)

    @api.model
    def pmant_planner_users(self):
        group = self.env.ref("pmant.group_pmant_planner", raise_if_not_found=False)
        return group.user_ids.filtered(lambda user: user.active and not user.share) if group else self.env["res.users"]


class PmantWorkOrderNotification(models.Model):
    _inherit = "maintenance.request"

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        notifier = self.env["pmant.notification"]
        for order in orders.filtered("user_id"):
            if order.user_id != self.env.user:
                notifier.notify_users(
                    order.user_id,
                    _("Nueva orden de trabajo asignada"),
                    _("Se le asignó la orden %s.") % order.display_name,
                    notification_type="info",
                    sticky=True,
                    record=order,
                )
        return orders

    def write(self, vals):
        previous = {order.id: (order.user_id, order.stage_id) for order in self}
        result = super().write(vals)
        notifier = self.env["pmant.notification"]
        for order in self:
            old_user, old_stage = previous[order.id]
            if "user_id" in vals and order.user_id and order.user_id != old_user and order.user_id != self.env.user:
                notifier.notify_users(
                    order.user_id,
                    _("Orden de trabajo asignada"),
                    _("Ahora es responsable de la orden %s.") % order.display_name,
                    notification_type="warning",
                    sticky=True,
                    record=order,
                )
            elif "stage_id" in vals and order.user_id and order.stage_id != old_stage and order.user_id != self.env.user:
                notifier.notify_users(
                    order.user_id,
                    _("Estado de orden actualizado"),
                    _("La orden %(order)s pasó a %(stage)s.", order=order.display_name, stage=order.stage_id.display_name),
                    notification_type="info",
                    record=order,
                )
        return result


class PmantServiceRequestNotification(models.Model):
    _inherit = "servicio.solicitud"

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        notifier = self.env["pmant.notification"]
        recipients = notifier.pmant_manager_users()
        for service_request in requests:
            notifier.notify_users(
                recipients,
                _("Nueva solicitud de servicio"),
                _("Se registró una solicitud para %s.") % service_request.equipo_id.display_name,
                notification_type="warning",
                sticky=True,
                record=service_request,
            )
        return requests
