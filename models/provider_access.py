from odoo import api, models, tools


class PmantProviderUsers(models.Model):
    _inherit = "res.users"

    def _pmant_apply_provider_home_action(self):
        provider_group = self.env.ref("pmant.group_pmant_proveedor", raise_if_not_found=False)
        maintenance_action = self.env.ref(
            "maintenance.hr_equipment_request_action", raise_if_not_found=False
        )
        if not provider_group or not maintenance_action:
            return
        providers = self.filtered(
            lambda user: provider_group in user.group_ids
            and not user.has_group("pmant.group_pmant_admin")
            and not user.has_group("base.group_system")
        )
        if providers:
            super(PmantProviderUsers, providers).write(
                {"action_id": maintenance_action.id}
            )

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._pmant_apply_provider_home_action()
        return users

    def write(self, vals):
        result = super().write(vals)
        if "group_ids" in vals:
            self._pmant_apply_provider_home_action()
        return result


class PmantProviderMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    @tools.ormcache("frozenset(self.env.user._get_group_ids())", "debug")
    def _visible_menu_ids(self, debug=False):
        visible_ids = super()._visible_menu_ids(debug=debug)
        user = self.env.user
        if (
            not user.has_group("pmant.group_pmant_proveedor")
            or user.has_group("pmant.group_pmant_admin")
            or user.has_group("base.group_system")
        ):
            return visible_ids

        maintenance_root = self.env.ref(
            "maintenance.menu_maintenance_title", raise_if_not_found=False
        )
        if not maintenance_root:
            return frozenset()
        maintenance_ids = set(
            self.sudo().search([("id", "child_of", maintenance_root.id)]).ids
        )
        return frozenset(set(visible_ids) & maintenance_ids)
