# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PmantSparePlanWizard(models.TransientModel):
    _name = "pmant.spare.plan.wizard"
    _description = "Selección de equipo / plan para repuestos"

    task_id = fields.Many2one("tarea.mantenimiento", string="Tarea", required=True)
    plan_equipment_id = fields.Many2one(
        "planequipo.mantenimiento", string="Equipo / Plan", required=True,
        domain="[('tarea', '=', task_id), ('pmant_spares_requested', '=', False), ('pmant_spares_pending', '=', False)]",
    )

    @api.onchange("task_id")
    def _onchange_task_id(self):
        plans = self.task_id.planequipo.filtered(
            lambda plan: plan.pmant_spare_line_ids and not plan.pmant_spares_requested and not plan.pmant_spares_pending
        )
        if len(plans) == 1:
            self.plan_equipment_id = plans

    def action_confirm(self):
        self.ensure_one()
        if not self.plan_equipment_id.pmant_spare_line_ids:
            raise UserError(_("El equipo / plan seleccionado no tiene repuestos."))
        self.task_id._pmant_request_spares_for_plan(self.plan_equipment_id)
        return {"type": "ir.actions.act_window", "res_model": "tarea.mantenimiento", "view_mode": "form", "res_id": self.task_id.id}
