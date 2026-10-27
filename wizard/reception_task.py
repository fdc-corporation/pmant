# -*- coding: utf-8 -*-
from odoo import Command, _, fields, models
from odoo.exceptions import UserError


class PmantReceptionTaskWizard(models.TransientModel):
    _name = "pmant.reception.task.wizard"
    _description = "Crear tarea desde recepción"

    reception_id = fields.Many2one(
        "pmant.recepcion.mantenimiento", string="Recepción",
        required=True, readonly=True, ondelete="cascade",
    )
    service_type_id = fields.Many2one(
        "tipotarea.mantenimiento", string="Tipo de servicio", required=True,
    )
    plan_id = fields.Many2one(
        "plan.mantenimiento", string="Plan de mantenimiento",
        help="Plan que se asignará a todos los equipos recibidos.",
    )

    def action_create_task(self):
        self.ensure_one()
        reception = self.reception_id
        reception._check_task_manager()
        if reception.state != "received":
            raise UserError(_("Valide primero el ingreso de inventario de la recepción."))
        duplicate = self.env["tarea.mantenimiento"].search([
            ("reception_id", "=", reception.id),
            ("tipo", "=", self.service_type_id.id),
        ], limit=1)
        if duplicate:
            raise UserError(_(
                "Ya existe una tarea de este tipo para la recepción: %s"
            ) % duplicate.display_name)

        task = self.env["tarea.mantenimiento"].create({
            "name": _("Servicio desde %s") % reception.display_name,
            "tipo": self.service_type_id.id,
            "cliente": reception.customer_id.id,
            "ubicacion": reception.site_id.id,
            "compania": reception.company_id.id,
            "reception_id": reception.id,
            "planequipo": [Command.create({
                "equipo": equipment.id,
                "plan": self.plan_id.id,
                "cliente": reception.customer_id.id,
                "ubicacion": reception.site_id.id,
            }) for equipment in reception.equipment_ids],
        })
        reception.message_post(body=_("Tarea %s creada.") % task.display_name)
        task.message_post(body=_(
            "Tarea creada desde la recepción %s."
        ) % reception.display_name)
        return {
            "type": "ir.actions.act_window", "res_model": "tarea.mantenimiento",
            "view_mode": "form", "res_id": task.id,
        }

