# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import re


class PmantTaskStandardName(models.Model):
    _inherit = "tarea.mantenimiento"

    name = fields.Char(
        string="Nombre",
        required=True,
        readonly=True,
        tracking=True,
        default=lambda self: _("Nuevo"),
    )
    pmant_sequence = fields.Char(
        string="Secuencia PMANT", readonly=True, copy=False, index=True,
    )

    def _pmant_standard_name(self):
        self.ensure_one()
        reference = self.pmant_sequence or _("Nuevo")
        description = (
            self.tipo.display_name
            if self.tipo
            else re.sub(r"^TAR[/\-]\d+\s*-\s*", "", self.name or "").strip()
        ) or _("Mantenimiento")
        return "%s - %s" % (reference, description)

    @api.model
    def _pmant_next_task_sequence(self):
        """Continuar la numeración TAR sin modificar tareas históricas."""
        sequence = self.env["ir.sequence"].search(
            [("code", "=", "pmant.task.sequence")], limit=1
        )
        if sequence:
            historical_numbers = []
            for name in self.search([("name", "=like", "TAR%")]).mapped("name"):
                match = re.match(r"^TAR[/\-](\d+)", name or "")
                if match:
                    historical_numbers.append(int(match.group(1)))
            next_number = max(historical_numbers, default=0) + 1
            if sequence.number_next_actual < next_number:
                sequence.number_next_actual = next_number
        return self.env["ir.sequence"].next_by_code("pmant.task.sequence")

    def _pmant_refresh_standard_name(self):
        for record in self:
            if not record.pmant_sequence:
                continue
            record.with_context(pmant_skip_standard_name=True).write(
                {"name": record._pmant_standard_name()}
            )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get("pmant_sequence"):
                values["pmant_sequence"] = self._pmant_next_task_sequence()
        records = super().create(vals_list)
        records._pmant_refresh_standard_name()
        return records

    def write(self, values):
        result = super().write(values)
        if not self.env.context.get("pmant_skip_standard_name") and any(
            field_name in values
            for field_name in ("cliente", "ubicacion", "tipo", "sale_order")
        ):
            self._pmant_refresh_standard_name()
        return result

    @api.model
    def pmant_migrate_standard_names(self):
        # Los registros históricos conservan exactamente su nombre actual.
        return True

    @api.model
    def pmant_apply_maintenance_menu_labels(self):
        """Aplicar etiquetas PMANT incluso sobre registros estándar noupdate."""
        labels = {
            "maintenance.menu_m_request_form": "Órdenes de trabajo",
            "maintenance.menu_m_request_calendar": "Calendario de mantenimiento",
        }
        for xmlid, label in labels.items():
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                for language in self.env["res.lang"].sudo().search([("active", "=", True)]).mapped("code"):
                    menu.sudo().with_context(lang=language).write({"name": label})
        actions = {
            "maintenance.hr_equipment_request_action": "Órdenes de trabajo",
            "maintenance.hr_equipment_request_action_cal": "Calendario de mantenimiento",
        }
        for xmlid, label in actions.items():
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                for language in self.env["res.lang"].sudo().search([("active", "=", True)]).mapped("code"):
                    action.sudo().with_context(lang=language).write({"name": label})
        return True


class PmantWorkOrderStandardName(models.Model):
    _inherit = "maintenance.request"

    name = fields.Char(
        string="Nombre",
        required=True,
        readonly=True,
        default=lambda self: _("Nuevo"),
    )
    pmant_sequence = fields.Char(
        string="Secuencia PMANT", readonly=True, copy=False, index=True,
    )

    def _pmant_standard_name(self):
        self.ensure_one()
        task = self.tarea
        reference = self.pmant_sequence or _("Sin secuencia")
        description = (
            task.tipo.display_name
            if task and task.tipo
            else re.sub(r"^OT[/\-]\d+\s*-\s*", "", self.name or "").strip()
        ) or _("Mantenimiento")
        return "%s - %s" % (reference, description)

    @api.model
    def _pmant_next_work_order_sequence(self):
        """Continuar después del mayor OT histórico sin renombrarlo."""
        sequence = self.env["ir.sequence"].search(
            [("code", "=", "ot.mantenimiento.sequence")], limit=1
        )
        if sequence:
            historical_numbers = []
            for name in self.search([("name", "=like", "OT%")]).mapped("name"):
                match = re.match(r"^OT[/\-](\d+)", name or "")
                if match:
                    historical_numbers.append(int(match.group(1)))
            next_number = max(historical_numbers, default=0) + 1
            if sequence.number_next_actual < next_number:
                sequence.number_next_actual = next_number
        return self.env["ir.sequence"].next_by_code("ot.mantenimiento.sequence")

    def _pmant_refresh_standard_name(self):
        for record in self:
            if not record.pmant_sequence:
                continue
            record.with_context(pmant_skip_standard_name=True).write(
                {"name": record._pmant_standard_name()}
            )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get("pmant_sequence"):
                values["pmant_sequence"] = self._pmant_next_work_order_sequence()
            # El correo de programación se genera dentro de otros create()
            # heredados. El nombre definitivo debe existir antes de llamar a
            # super(), no después, para que asunto y cuerpo nunca muestren
            # el valor temporal "Nuevo".
            task = self.env["tarea.mantenimiento"].browse(values.get("tarea"))
            service_type = task.tipo.display_name if task and task.tipo else _("Mantenimiento")
            values["name"] = "%s - %s" % (values["pmant_sequence"], service_type)
        records = super().create(vals_list)
        records._pmant_refresh_standard_name()
        return records

    def write(self, values):
        result = super().write(values)
        if not self.env.context.get("pmant_skip_standard_name") and "tarea" in values:
            self.filtered("pmant_sequence")._pmant_refresh_standard_name()
        return result
