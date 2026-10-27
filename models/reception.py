# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


MANAGER_GROUPS = ("pmant.group_pmant_planner", "pmant.group_pmant_admin")


class PmantReception(models.Model):
    _name = "pmant.recepcion.mantenimiento"
    _description = "Recepción de equipos de mantenimiento"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "received_at desc, id desc"

    name = fields.Char(string="Recepción", default="Nueva", readonly=True, copy=False)
    customer_id = fields.Many2one("res.partner", string="Cliente", required=True, tracking=True)
    site_id = fields.Many2one("res.partner", string="Sede", required=True, tracking=True)
    equipment_ids = fields.Many2many(
        "maintenance.equipment", string="Equipos", required=True, tracking=True,
    )
    equipment_count = fields.Integer(string="Cantidad de equipos", compute="_compute_counts")
    technician_id = fields.Many2one(
        "res.users", string="Técnico responsable", required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    received_at = fields.Datetime(
        string="Fecha y hora de recepción", default=fields.Datetime.now,
        required=True, tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("inventory", "Ingreso de inventario"),
            ("received", "Recepcionado"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado", default="draft", required=True, tracking=True, copy=False,
    )
    reason = fields.Text(string="Motivo de ingreso", required=True)
    accessories = fields.Text(string="Accesorios recibidos")
    reported_condition = fields.Text(string="Estado del equipo")
    notes = fields.Text(string="Observaciones")
    image_ids = fields.One2many(
        "pmant.recepcion.mantenimiento.imagen", "reception_id", string="Evidencias",
    )
    customer_signature = fields.Binary(string="Firma del cliente", attachment=True)
    customer_signer_name = fields.Char(string="Nombre del cliente firmante")
    technician_signature = fields.Binary(string="Firma del técnico", attachment=True)
    technician_signer_name = fields.Char(string="Nombre del técnico firmante")
    task_ids = fields.One2many(
        "tarea.mantenimiento", "reception_id", string="Tareas", readonly=True,
    )
    task_count = fields.Integer(string="Tareas", compute="_compute_counts")
    picking_ids = fields.One2many(
        "stock.picking", "pmant_reception_id", string="Ingresos de inventario", readonly=True,
    )
    picking_count = fields.Integer(string="Movimientos", compute="_compute_counts")
    active_picking_id = fields.Many2one(
        "stock.picking", string="Ingreso actual", readonly=True, copy=False,
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company,
        required=True, index=True,
    )

    @api.depends("equipment_ids", "task_ids", "picking_ids")
    def _compute_counts(self):
        for reception in self:
            reception.equipment_count = len(reception.equipment_ids)
            reception.task_count = len(reception.task_ids)
            reception.picking_count = len(reception.picking_ids)

    @api.constrains("company_id", "customer_id", "site_id", "equipment_ids")
    def _check_site_customer(self):
        for reception in self:
            if reception.site_id.commercial_partner_id != reception.customer_id.commercial_partner_id:
                raise ValidationError(_("La sede seleccionada no pertenece al cliente indicado."))
            if any(
                equipment.company_id and equipment.company_id != reception.company_id
                for equipment in reception.equipment_ids
            ):
                raise ValidationError(_("Todos los equipos deben pertenecer a la compañía de la recepción."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nueva") == "Nueva":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "pmant.recepcion.mantenimiento"
                ) or "Nueva"
            vals.setdefault("technician_id", self.env.user.id)
        return super().create(vals_list)

    def _check_task_manager(self):
        if not any(self.env.user.has_group(group) for group in MANAGER_GROUPS):
            raise AccessError(_("Solo el Planner o Administrador puede crear tareas desde una recepción."))

    def _get_stock_configuration(self):
        self.ensure_one()
        configuration = self.env["conf.pmant.ubicacion"].search(
            [("predeterminado", "=", True)], limit=1,
        )
        if not configuration:
            raise UserError(_("Configure una ubicación predeterminada en Configuración de PMANT."))
        missing = []
        if not configuration.property_stock_customer:
            missing.append(_("ubicación de cliente"))
        if not configuration.property_stock_inventory:
            missing.append(_("ubicación de inventario"))
        if not configuration.operacion_entrada:
            missing.append(_("tipo de operación de entrada"))
        if missing:
            raise UserError(_("Complete en conf.pmant.ubicacion: %s.") % ", ".join(missing))
        return configuration

    def _create_inventory_receipt(self):
        self.ensure_one()
        configuration = self._get_stock_configuration()
        picking = self.env["stock.picking"].with_company(self.company_id).create({
            "partner_id": self.site_id.id or self.customer_id.id,
            "location_id": configuration.property_stock_customer.id,
            "location_dest_id": configuration.property_stock_inventory.id,
            "picking_type_id": configuration.operacion_entrada.id,
            "origin": self.name,
            "pmant_reception_id": self.id,
        })

        for equipment in self.equipment_ids:
            product = equipment.category_id.product_id
            if not product:
                raise UserError(_(
                    "La categoría del equipo %s no tiene un producto configurado."
                ) % equipment.display_name)
            values = {
                "name": equipment.display_name,
                "description_picking": equipment.display_name,
                "product_id": product.id,
                "product_uom_qty": 1.0,
                "product_uom": product.uom_id.id,
                "picking_id": picking.id,
                "picking_type_id": picking.picking_type_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            }
            if product.tracking != "none":
                if not equipment.serial_no:
                    raise UserError(_(
                        "El equipo %s necesita número de serie para ingresar el producto %s."
                    ) % (equipment.display_name, product.display_name))
                lot = self.env["stock.lot"].search([
                    ("name", "=", equipment.serial_no),
                    ("product_id", "=", product.id),
                    ("company_id", "in", [False, self.company_id.id]),
                ], limit=1)
                if not lot:
                    lot = self.env["stock.lot"].create({
                        "name": equipment.serial_no,
                        "product_id": product.id,
                        "company_id": self.company_id.id,
                    })
                values["lot_ids"] = [Command.set(lot.ids)]
            self.env["stock.move"].create(values)

        picking.action_confirm()
        picking.action_assign()
        self.active_picking_id = picking
        return picking

    def action_confirm(self):
        self.ensure_one()
        self._check_task_manager()
        if self.state != "draft":
            raise UserError(_("Solo puede confirmar una recepción en borrador."))
        if not self.equipment_ids:
            raise UserError(_("Debe seleccionar al menos un equipo."))
        picking = self._create_inventory_receipt()
        self.write({"state": "inventory"})
        self.message_post(body=_(
            "Recepción confirmada por %(user)s. Se creó el ingreso %(picking)s.",
            user=self.env.user.display_name, picking=picking.display_name,
        ))
        return self.action_view_active_picking()

    def action_set_draft(self):
        self._check_task_manager()
        for reception in self:
            if reception.active_picking_id.state == "done":
                raise UserError(_("No puede volver a borrador una recepción cuyo ingreso ya fue validado."))
            if reception.active_picking_id and reception.active_picking_id.state != "cancel":
                reception.active_picking_id.action_cancel()
            reception.write({"state": "draft", "active_picking_id": False})
        return True

    def action_cancel(self):
        self._check_task_manager()
        for reception in self:
            if reception.active_picking_id.state == "done":
                raise UserError(_("No puede cancelar una recepción cuyo ingreso ya fue validado."))
            if reception.active_picking_id and reception.active_picking_id.state != "cancel":
                reception.active_picking_id.action_cancel()
            reception.state = "cancelled"
        return True

    def action_open_create_task_wizard(self):
        self.ensure_one()
        self._check_task_manager()
        if self.state != "received":
            raise UserError(_("Valide primero el ingreso de inventario de la recepción."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Crear tarea"),
            "res_model": "pmant.reception.task.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_reception_id": self.id},
        }

    def action_view_tasks(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window", "name": _("Tareas"),
            "res_model": "tarea.mantenimiento", "view_mode": "list,form",
            "domain": [("reception_id", "=", self.id)],
        }
        if self.task_count == 1:
            action.update({"view_mode": "form", "res_id": self.task_ids.id})
        return action

    def action_view_active_picking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Ingreso de inventario"),
            "res_model": "stock.picking", "view_mode": "form",
            "res_id": self.active_picking_id.id,
        }

    def action_view_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Ingresos de inventario"),
            "res_model": "stock.picking", "view_mode": "list,form",
            "domain": [("pmant_reception_id", "=", self.id)],
        }


class PmantReceptionImage(models.Model):
    _name = "pmant.recepcion.mantenimiento.imagen"
    _description = "Evidencia de recepción"

    sequence = fields.Integer(string="Secuencia", default=10)
    reception_id = fields.Many2one(
        "pmant.recepcion.mantenimiento", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        "res.company", related="reception_id.company_id", store=True, index=True,
    )
    image = fields.Image(string="Imagen", required=True)
    comment = fields.Text(string="Descripción / comentario")


class PmantReceptionTask(models.Model):
    _inherit = "tarea.mantenimiento"

    reception_id = fields.Many2one(
        "pmant.recepcion.mantenimiento", string="Recepción de origen",
        readonly=True, copy=False, ondelete="set null", index=True,
    )

    def action_view_reception(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Recepción de origen"),
            "res_model": "pmant.recepcion.mantenimiento", "view_mode": "form",
            "res_id": self.reception_id.id,
        }

    def create_ot(self):
        action = super().create_ot()
        if self.reception_id and isinstance(action, dict):
            context = dict(action.get("context", {}))
            context["default_pmant_reception_id"] = self.reception_id.id
            action["context"] = context
        return action


class PmantReceptionWorkOrder(models.Model):
    _inherit = "maintenance.request"

    pmant_reception_id = fields.Many2one(
        "pmant.recepcion.mantenimiento", string="Recepción de origen",
        readonly=True, copy=False, ondelete="set null", index=True,
    )


class PmantReceptionPicking(models.Model):
    _inherit = "stock.picking"

    pmant_reception_id = fields.Many2one(
        "pmant.recepcion.mantenimiento", string="Recepción PMANT",
        readonly=True, copy=False, ondelete="set null", index=True,
    )

    def button_validate(self):
        result = super().button_validate()
        for picking in self.filtered(lambda item: item.state == "done" and item.pmant_reception_id):
            picking.pmant_reception_id.write({
                "state": "received", "active_picking_id": picking.id,
            })
            picking.pmant_reception_id.message_post(body=_(
                "Ingreso de inventario %s validado. Recepción completada."
            ) % picking.display_name)
        return result

