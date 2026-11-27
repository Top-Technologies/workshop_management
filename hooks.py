# -*- coding: utf-8 -*-

TECHNICIAN_WO_RULE_DOMAIN = (
    "['|', ('user_id', '=', user.id), ('technician_id.user_id', '=', user.id)]"
)


def post_init_hook(env):
    """Ensure Workshop Documents folders exist after install."""
    helper = env["workshop.documents.helper"]
    for company in env["res.company"].search([]):
        company.documents_workshop_settings = True
        helper.ensure_workshop_folders(company)
    fix_technician_work_order_rule(env)


def fix_technician_work_order_rule(env):
    """Technicians must see WOs linked via user_id or employee.user_id."""
    rule = env.ref(
        "workshop_management.rule_work_order_technician",
        raise_if_not_found=False,
    )
    if rule and rule.domain_force != TECHNICIAN_WO_RULE_DOMAIN:
        rule.sudo().write({"domain_force": TECHNICIAN_WO_RULE_DOMAIN})
