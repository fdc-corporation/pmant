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
    def notify_users(
        self, users, title, message, notification_type="info", sticky=False,
        record=None, scheduled_at=None,
    ):
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
                "scheduled_at": scheduled_at or fields.Datetime.now(),
                "user_id": user.id,
                "company_id": company.id,
                "res_model": record._name if record else False,
                "res_id": record.id if record else False,
            })
        notifications = self.with_user(self.env.ref("base.user_root")).create(values)
        now = fields.Datetime.now()
        for item in notifications.filtered(lambda notification: notification.scheduled_at <= now):
            self.env["bus.bus"]._sendone(
                item.user_id.partner_id,
                "pmant.notification",
                {
                    "id": item.id,
                    "title": item.title,
                    "message": item.message,
                    "type": item.notification_type,
                    "sticky": item.sticky,
                    "res_model": item.res_model,
                    "res_id": item.res_id,
                },
            )
        return notifications

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

    @api.model
    def pmant_technician_users(self):
        group = self.env.ref("pmant.group_pmant_tecnico", raise_if_not_found=False)
        return group.user_ids.filtered(lambda user: user.active and not user.share) if group else self.env["res.users"]

    @api.model
    def pmant_billing_users(self):
        group = self.env.ref("pmant.group_pmant_user_notifi_fac", raise_if_not_found=False)
        return group.user_ids.filtered(lambda user: user.active and not user.share) if group else self.env["res.users"]


class PmantTaskNotification(models.Model):
    _inherit = "tarea.mantenimiento"

    pmant_creation_notified = fields.Boolean(
        string="Creación notificada al planner", copy=False, readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        notifier = self.env["pmant.notification"]
        planners = notifier.pmant_planner_users()
        for task in tasks.filtered(lambda item: not item.pmant_creation_notified):
            sales = task.sale_order
            salesperson = sales.mapped("user_id")
            quotation = ", ".join(sales.mapped("name")) or _("sin cotización")
            notifier.notify_users(
                planners,
                _("Nueva tarea pendiente de revisión y programación"),
                _(
                    "Se creó la tarea %(task)s desde %(quotation)s. "
                    "Revise los equipos, el tipo de servicio y programe la OT. "
                    "Vendedor: %(seller)s.",
                    task=task.display_name,
                    quotation=quotation,
                    seller=", ".join(salesperson.mapped("name")) or _("No asignado"),
                ),
                notification_type="warning",
                sticky=True,
                record=task,
            )
            task.sudo().pmant_creation_notified = True
        return tasks

    def write(self, vals):
        old_stages = {task.id: task.stage_id for task in self}
        result = super().write(vals)
        if "stage_id" in vals:
            notifier = self.env["pmant.notification"]
            for task in self.filtered(lambda item: item.stage_id != old_stages[item.id]):
                recipients = (task.create_user | notifier.pmant_planner_users()).filtered(
                    lambda user: user.active and not user.share and user != self.env.user
                )
                notifier.notify_users(
                    recipients,
                    _("Etapa de tarea actualizada"),
                    _(
                        "La tarea %(task)s pasó a %(stage)s.",
                        task=task.display_name,
                        stage=task.stage_id.display_name,
                    ),
                    notification_type="info",
                    record=task,
                )
        return result


class PmantWorkOrderNotification(models.Model):
    _inherit = "maintenance.request"

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        notifier = self.env["pmant.notification"]
        planners = notifier.pmant_planner_users()
        for order in orders:
            notifier.notify_users(
                planners,
                _("Nueva orden de trabajo creada"),
                _(
                    "Se creó la orden %(order)s para %(customer)s. "
                    "Revise la programación y el personal técnico asignado.",
                    order=order.display_name,
                    customer=order.empresa.display_name or _("cliente no definido"),
                ),
                notification_type="warning",
                sticky=True,
                record=order,
            )
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
            if set(vals) & {"schedule_date", "scheduled_end", "duration", "subodinados"}:
                technicians = (order.user_id | order.subodinados).filtered(
                    lambda user: user.active and not user.share and user != self.env.user
                )
                notifier.notify_users(
                    technicians,
                    _("Programación de servicio actualizada"),
                    _(
                        "La programación de %(order)s fue actualizada. Fecha: %(date)s; duración: %(duration)s horas.",
                        order=order.display_name,
                        date=order.schedule_date or _("Pendiente"),
                        duration=order.duration or 0,
                    ),
                    notification_type="warning",
                    sticky=True,
                    record=order,
                )
            if (
                "pmant_followup_seller_id" in vals
                and order.pmant_followup_seller_id
                and order.stage_id.pmant_code in ("review", "billing_hes", "done")
                and order.require_repuestos
            ):
                notifier.notify_users(
                    order.pmant_followup_seller_id,
                    _("OT con repuestos asignada para seguimiento"),
                    _("La orden %(order)s contiene repuestos. Revísela y cree la oportunidad comercial.") % {"order": order.display_name},
                    notification_type="warning", sticky=True, record=order,
                )
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
            entered_review = (
                "stage_id" in vals
                and order.stage_id != old_stage
                and order.stage_id.pmant_code == "review"
                and order.require_repuestos
                and not order.pmant_spare_review_notified
            )
            if entered_review:
                sellers = (order.pmant_commercial_user_ids | order.pmant_followup_seller_id).filtered(
                    lambda user: user.active and not user.share
                    and user.has_group("pmant.group_pmant_vendedor")
                )
                if sellers:
                    notifier.notify_users(
                        sellers,
                        _("OT con repuestos lista para seguimiento"),
                        _("La orden %(order)s llegó a Revisión y contiene repuestos. Revísela y cree la oportunidad comercial.") % {"order": order.display_name},
                        notification_type="warning", sticky=True, record=order,
                    )
                else:
                    planners = notifier.pmant_planner_users()
                    notifier.notify_users(
                        planners,
                        _("OT con repuestos sin vendedor"),
                        _("La orden %(order)s llegó a Revisión con repuestos, pero no tiene vendedor relacionado. Asigne o notifique a un vendedor para crear la oportunidad.") % {"order": order.display_name},
                        notification_type="warning", sticky=True, record=order,
                    )
                    activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
                    for planner in planners:
                        if activity_type:
                            order.activity_schedule(
                                activity_type_id=activity_type.id,
                                user_id=planner.id,
                                summary=_("Asignar vendedor para repuestos"),
                                note=_("La OT tiene repuestos y necesita seguimiento comercial."),
                            )
                order.sudo().pmant_spare_review_notified = True
            stage_changed = "stage_id" in vals and order.stage_id != old_stage
            if stage_changed and order.stage_id.pmant_code in ("in_progress", "review", "done"):
                planners = notifier.pmant_planner_users().filtered(lambda user: user != self.env.user)
                notifier.notify_users(
                    planners,
                    _("Avance de orden de trabajo"),
                    _(
                        "La orden %(order)s pasó a %(stage)s.",
                        order=order.display_name,
                        stage=order.stage_id.display_name,
                    ),
                    notification_type="success" if order.stage_id.pmant_code == "done" else "info",
                    sticky=order.stage_id.pmant_code in ("review", "done"),
                    record=order,
                )
            if stage_changed and order.stage_id.pmant_code in ("review", "done"):
                sellers = (order.pmant_commercial_user_ids | order.pmant_followup_seller_id).filtered(
                    lambda user: user.active and not user.share and user != self.env.user
                )
                notifier.notify_users(
                    sellers,
                    _("Servicio listo para seguimiento comercial"),
                    _(
                        "La orden %(order)s pasó a %(stage)s. Revise el resultado del servicio y continúe el seguimiento comercial.",
                        order=order.display_name,
                        stage=order.stage_id.display_name,
                    ),
                    notification_type="success" if order.stage_id.pmant_code == "done" else "warning",
                    sticky=True,
                    record=order,
                )
        return result


class PmantCrmNotification(models.Model):
    _inherit = "crm.lead"

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        notifier = self.env["pmant.notification"]
        for lead in leads.filtered("orden_trabajo"):
            recipients = lead.user_id.filtered(
                lambda user: user.active and not user.share and user != self.env.user
            )
            notifier.notify_users(
                recipients,
                _("Nueva oportunidad de repuestos asignada"),
                _(
                    "Se creó la oportunidad %(lead)s desde la orden %(order)s. Revise los repuestos y prepare el seguimiento comercial.",
                    lead=lead.display_name,
                    order=lead.orden_trabajo.display_name,
                ),
                notification_type="warning",
                sticky=True,
                record=lead,
            )
        return leads


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
