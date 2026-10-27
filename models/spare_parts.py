# -*- coding: utf-8 -*-
import odoo

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PmantSpareLine(models.Model):
    _name = "pmant.spare.line"
    _description = "Repuesto de equipo / plan PMANT"
    _rec_name = "product_id"

    plan_equipment_id = fields.Many2one(
        "planequipo.mantenimiento", string="Equipo / Plan", required=True,
        ondelete="cascade", index=True,
    )
    task_id = fields.Many2one(
        "tarea.mantenimiento", related="plan_equipment_id.tarea",
        string="Tarea", store=True, index=True,
    )
    company_id = fields.Many2one(
        "res.company", related="task_id.compania", string="Compañía",
        store=True, index=True,
    )
    product_id = fields.Many2one(
        "product.product", string="Repuesto", required=True,
        domain=[("is_repuesto", "=", True)],
    )
    requested_qty = fields.Float(string="Cantidad solicitada", default=1.0, required=True)
    delivered_qty = fields.Float(string="Cantidad entregada", readonly=True, copy=False)
    consumed_qty = fields.Float(string="Cantidad consumida", copy=False)
    returned_qty = fields.Float(string="Cantidad devuelta", readonly=True, copy=False)
    scrapped_qty = fields.Float(string="Cantidad descartada", readonly=True, copy=False)
    moved_consumed_qty = fields.Float(string="Consumo movido", readonly=True, copy=False)
    moved_returned_qty = fields.Float(string="Devolución movida", readonly=True, copy=False)
    uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", string="Unidad")
    note = fields.Char(string="Nota")

    def _is_pure_technician(self):
        user = self.env.user
        return user.has_group("pmant.group_pmant_tecnico") and not any(
            user.has_group(group) for group in (
                "pmant.group_pmant_planner", "pmant.group_pmant_supervisor",
                "pmant.group_pmant_admin",
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            plan = self.env["planequipo.mantenimiento"].browse(vals.get("plan_equipment_id"))
            if plan and self._is_pure_technician() and (plan.pmant_spares_requested or plan.pmant_spares_pending):
                raise UserError(_("No puede agregar repuestos porque la solicitud ya fue enviada."))
        records = super().create(vals_list)
        if self._is_pure_technician():
            for task in records.mapped("task_id"):
                creator = task._pmant_ot_creator()
                if creator and not creator.share:
                    products = ", ".join(records.filtered(lambda line: line.task_id == task).mapped("product_id.display_name"))
                    self.env["pmant.notification"].notify_users(
                        creator, _("Repuestos agregados por el técnico"),
                        _("%(technician)s agregó %(products)s en la tarea %(task)s.",
                          technician=self.env.user.name, products=products, task=task.display_name),
                        record=task,
                    )
        return records

    def write(self, vals):
        if self._is_pure_technician() and set(vals) - {"consumed_qty", "note"}:
            if any(line.plan_equipment_id.pmant_spares_requested or line.plan_equipment_id.pmant_spares_pending for line in self):
                raise UserError(_("La solicitud ya fue enviada; solo puede registrar consumo y notas."))
        return super().write(vals)

    def unlink(self):
        if self._is_pure_technician() and any(
            line.plan_equipment_id.pmant_spares_requested or line.plan_equipment_id.pmant_spares_pending
            for line in self
        ):
            raise UserError(_("No puede eliminar repuestos de una solicitud enviada."))
        return super().unlink()

    @api.constrains("requested_qty", "consumed_qty")
    def _check_quantities(self):
        for line in self:
            if line.requested_qty <= 0 or line.consumed_qty < 0:
                raise ValidationError(_("La cantidad solicitada debe ser positiva y el consumo no puede ser negativo."))
            limit = line.delivered_qty or line.requested_qty
            if line.consumed_qty > limit:
                raise ValidationError(_("La cantidad consumida no puede superar la cantidad entregada."))
            if line.consumed_qty < line.moved_consumed_qty:
                raise ValidationError(_("No puede reducir un consumo que ya generó un movimiento."))


class PmantStockMove(models.Model):
    _inherit = "stock.move"

    pmant_spare_line_id = fields.Many2one("pmant.spare.line", ondelete="set null", index=True)


class PmantStockPicking(models.Model):
    _inherit = "stock.picking"

    is_pmant_spare = fields.Boolean(string="Movimiento de repuestos PMANT", index=True, copy=False)
    pmant_task_id = fields.Many2one("tarea.mantenimiento", string="Tarea PMANT", ondelete="set null", index=True)
    pmant_plan_id = fields.Many2one("planequipo.mantenimiento", string="Equipo / Plan", ondelete="set null", index=True)
    pmant_movement_type = fields.Selection([
        ("delivery", "Entrega al taller"),
        ("consume", "Consumo / Desecho"),
        ("return", "Devolución al almacén"),
    ], string="Tipo de movimiento de repuesto", copy=False)

    def _action_done(self):
        result = super()._action_done()
        for picking in self.filtered(lambda item: item.is_pmant_spare and item.pmant_movement_type == "delivery"):
            for move in picking.move_ids.filtered("pmant_spare_line_id"):
                done_qty = sum(move.move_line_ids.filtered(lambda line: line.state == "done").mapped("quantity"))
                spare = move.pmant_spare_line_id
                spare.with_user(odoo.SUPERUSER_ID).delivered_qty += done_qty or move.quantity
            users = picking.pmant_task_id.ots.mapped("user_id").filtered(lambda user: not user.share)
            self.env["pmant.notification"].notify_users(
                users, _("Repuestos entregados"),
                _("La entrega %s fue validada y los repuestos están disponibles para consumo.") % picking.name,
                notification_type="success", sticky=True, record=picking,
            )
            picking.message_post(body=_("Entrega de repuestos validada."))
        return result

    def _action_cancel(self):
        result = super()._action_cancel()
        for picking in self.filtered(lambda item: item.is_pmant_spare and item.pmant_movement_type == "delivery"):
            plan = picking.pmant_plan_id
            if plan and not self.sudo().search_count([
                ("pmant_plan_id", "=", plan.id), ("is_pmant_spare", "=", True),
                ("pmant_movement_type", "=", "delivery"), ("state", "!=", "cancel"),
            ]):
                plan.sudo().pmant_spares_requested = False
        return result


class PmantTaskSpare(models.Model):
    _inherit = "tarea.mantenimiento"

    pmant_spare_line_ids = fields.One2many("pmant.spare.line", "task_id", string="Repuestos", readonly=True)
    pmant_spare_picking_count = fields.Integer(compute="_compute_spare_status")
    pmant_consume_picking_count = fields.Integer(compute="_compute_spare_status")
    pmant_return_picking_count = fields.Integer(compute="_compute_spare_status")
    pmant_pending_consumption = fields.Boolean(compute="_compute_spare_status")
    pmant_pending_return = fields.Boolean(compute="_compute_spare_status")
    pmant_can_request_spares = fields.Boolean(compute="_compute_spare_status")
    pmant_spares_pending_count = fields.Integer(compute="_compute_spare_status")

    def _spare_config(self):
        config = self.env["conf.pmant.ubicacion"].search([
            ("predeterminado", "=", True), ("is_trasporte_interno", "=", True),
        ], limit=1) or self.env["conf.pmant.ubicacion"].search([("predeterminado", "=", True)], limit=1)
        if not config or not all((config.tipo_operacion_traslado, config.ubicacion_origen_traslado, config.ubicacion_destino_traslado)):
            raise UserError(_("Configure en Mantenimiento > Configuración > Ubicaciones la operación interna, el almacén de repuestos y la ubicación del taller."))
        return config

    def _compute_spare_status(self):
        Picking = self.env["stock.picking"]
        for task in self:
            base = [("pmant_task_id", "=", task.id), ("is_pmant_spare", "=", True)]
            task.pmant_spare_picking_count = Picking.search_count(base)
            task.pmant_consume_picking_count = Picking.search_count(base + [("pmant_movement_type", "=", "consume")])
            task.pmant_return_picking_count = Picking.search_count(base + [("pmant_movement_type", "=", "return")])
            lines = task.pmant_spare_line_ids
            task.pmant_pending_consumption = any(line.consumed_qty > line.moved_consumed_qty for line in lines)
            task.pmant_pending_return = any(
                line.delivered_qty - line.consumed_qty - line.moved_returned_qty > 0 for line in lines
            )
            task.pmant_spares_pending_count = len(task.planequipo.filtered("pmant_spares_pending"))
            task.pmant_can_request_spares = (
                task.tipo.service_kind == "corrective"
                and any(
                    plan.pmant_spare_line_ids
                    and not plan.pmant_spares_pending
                    and not plan.pmant_spares_requested
                    for plan in task.planequipo
                )
            )

    def _pmant_ot_creator(self):
        self.ensure_one()
        return self.ots.filtered("create_uid")[:1].create_uid

    def _pmant_check_can_request_spares(self):
        self.ensure_one()
        if self.tipo.service_kind != "corrective":
            raise UserError(_("Solo se pueden solicitar repuestos en servicios correctivos."))
        if not self.pmant_can_request_spares:
            if not self.pmant_spare_line_ids:
                raise UserError(_("Registre al menos un repuesto en el equipo / plan."))
            raise UserError(_("Los repuestos de esta tarea ya fueron solicitados."))

    def action_pmant_request_spares(self):
        self.ensure_one()
        self._pmant_check_can_request_spares()
        available = self.planequipo.filtered(lambda plan: plan.pmant_spare_line_ids and not plan.pmant_spares_pending and not plan.pmant_spares_requested)
        if len(available) == 1:
            self._pmant_request_spares_for_plan(available)
            return {"type": "ir.actions.client", "tag": "reload"}
        return {
            "type": "ir.actions.act_window", "name": _("Solicitar repuestos por equipo"),
            "res_model": "pmant.spare.plan.wizard", "view_mode": "form", "target": "new",
            "context": {"default_task_id": self.id},
        }

    def _pmant_request_spares_for_plan(self, plan):
        self.ensure_one()
        if plan.tarea != self or not plan.pmant_spare_line_ids:
            raise UserError(_("Seleccione un equipo / plan válido con repuestos."))
        plan.pmant_spares_pending = True
        creator = self._pmant_ot_creator()
        recipients = creator if creator and not creator.share else self.env["pmant.notification"].pmant_planner_users()
        self.env["pmant.notification"].notify_users(
            recipients, _("Solicitud de repuestos"),
            _("Se solicitaron repuestos para %(plan)s en la tarea %(task)s.", plan=plan.display_name, task=self.display_name),
            notification_type="warning", sticky=True, record=self,
        )
        self.message_post(body=_("Solicitud de repuestos enviada para confirmación."))

    def _create_spare_picking(self, plan, lines, movement_type, source, destination, quantities, validate=False):
        config = self._spare_config()
        picking = self.env["stock.picking"].with_company(self.compania).create({
            "company_id": self.compania.id,
            "picking_type_id": config.tipo_operacion_traslado.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "origin": "%s - %s" % (self.display_name, dict(self.env["stock.picking"]._fields["pmant_movement_type"].selection).get(movement_type)),
            "is_pmant_spare": True,
            "pmant_task_id": self.id,
            "pmant_plan_id": plan.id,
            "pmant_movement_type": movement_type,
        })
        for line in lines:
            qty = quantities(line)
            if qty <= 0:
                continue
            self.env["stock.move"].with_company(self.compania).create({
                "description_picking": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": qty,
                "product_uom": line.uom_id.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "picking_id": picking.id,
                "pmant_spare_line_id": line.id,
            })
        if validate:
            picking.action_confirm()
            picking.button_validate()
        return picking

    def action_pmant_confirm_spares(self):
        self.ensure_one()
        plans = self.planequipo.filtered("pmant_spares_pending")
        if not plans:
            raise UserError(_("No hay repuestos pendientes de confirmación."))
        config = self._spare_config()
        result = False
        for plan in plans:
            lines = plan.pmant_spare_line_ids.filtered(lambda line: line.requested_qty > line.delivered_qty)
            picking = self._create_spare_picking(
                plan, lines, "delivery", config.ubicacion_origen_traslado,
                config.ubicacion_destino_traslado,
                lambda line: line.requested_qty - line.delivered_qty,
            )
            plan.write({"pmant_spares_pending": False, "pmant_spares_requested": True})
            picking.message_post(body=_("Entrega creada. Inventario debe reservar y validar los repuestos."))
            result = {"type": "ir.actions.act_window", "res_model": "stock.picking", "view_mode": "form", "res_id": picking.id}
        return result

    def action_pmant_consume_spares(self):
        self.ensure_one()
        config = self._spare_config()
        waste = config.scrap_location_id or config.ubicacion_desecho
        if not waste:
            raise UserError(_("Configure la ubicación de desecho/scrap en la ubicación PMANT."))
        lines = self.pmant_spare_line_ids.filtered(lambda line: line.consumed_qty > line.moved_consumed_qty)
        if not lines:
            raise UserError(_("No hay consumos pendientes."))
        returned = False
        for plan in lines.mapped("plan_equipment_id"):
            plan_lines = lines.filtered(lambda line: line.plan_equipment_id == plan)
            self._create_spare_picking(
                plan, plan_lines, "consume", config.ubicacion_destino_traslado, waste,
                lambda line: line.consumed_qty - line.moved_consumed_qty, validate=True,
            )
            for line in plan_lines:
                line.sudo().write({"moved_consumed_qty": line.consumed_qty, "scrapped_qty": line.consumed_qty})
            returned |= self._return_spares_for_plan(plan, plan.pmant_spare_line_ids)
        self._notify_spare_result(consumed=True, returned=returned)
        return {"type": "ir.actions.client", "tag": "reload"}

    def _return_spares_for_plan(self, plan, lines):
        config = self._spare_config()
        return_lines = lines.filtered(lambda line: line.delivered_qty - line.consumed_qty - line.moved_returned_qty > 0)
        if not return_lines:
            return False
        self._create_spare_picking(
            plan, return_lines, "return", config.ubicacion_destino_traslado,
            config.ubicacion_origen_traslado,
            lambda line: line.delivered_qty - line.consumed_qty - line.moved_returned_qty,
            validate=True,
        )
        for line in return_lines:
            qty = line.delivered_qty - line.consumed_qty
            line.sudo().write({"moved_returned_qty": qty, "returned_qty": qty})
        return True

    def action_pmant_return_spares(self):
        self.ensure_one()
        changed = False
        for plan in self.planequipo:
            changed |= self._return_spares_for_plan(plan, plan.pmant_spare_line_ids)
        if not changed:
            raise UserError(_("No hay repuestos disponibles para devolución."))
        self._notify_spare_result(consumed=False, returned=True)
        return {"type": "ir.actions.client", "tag": "reload"}

    def _notify_spare_result(self, consumed=False, returned=False):
        recipients = self.env["pmant.notification"].pmant_planner_users() | self._pmant_ot_creator()
        action = _("consumo y devolución") if consumed and returned else _("consumo") if consumed else _("devolución")
        self.env["pmant.notification"].notify_users(
            recipients, _("Movimiento de repuestos registrado"),
            _("Se registró %(action)s de repuestos en %(task)s.", action=action, task=self.display_name),
            sticky=True, record=self,
        )

    def _view_spare_pickings(self, movement_type=False):
        self.ensure_one()
        domain = [("pmant_task_id", "=", self.id), ("is_pmant_spare", "=", True)]
        if movement_type:
            domain.append(("pmant_movement_type", "=", movement_type))
        return {"type": "ir.actions.act_window", "name": _("Movimientos de repuestos"), "res_model": "stock.picking", "view_mode": "list,form", "domain": domain, "context": {"create": False}}

    def action_pmant_view_spare_movements(self):
        return self._view_spare_pickings()

    def action_pmant_view_consume_movements(self):
        return self._view_spare_pickings("consume")

    def action_pmant_view_return_movements(self):
        return self._view_spare_pickings("return")


class PmantPlanEquipmentSpare(models.Model):
    _inherit = "planequipo.mantenimiento"

    pmant_spare_line_ids = fields.One2many("pmant.spare.line", "plan_equipment_id", string="Repuestos")
    pmant_spares_requested = fields.Boolean(string="Repuestos solicitados", copy=False)
    pmant_spares_pending = fields.Boolean(string="Pendientes de confirmación", copy=False)


class PmantWorkOrderSpare(models.Model):
    _inherit = "maintenance.request"

    pmant_spares_pending_count = fields.Integer(related="tarea.pmant_spares_pending_count")

    def action_pmant_confirm_spares(self):
        self.ensure_one()
        return self.tarea.action_pmant_confirm_spares()
