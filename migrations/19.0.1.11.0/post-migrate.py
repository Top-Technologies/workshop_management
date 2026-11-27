# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api

from odoo.addons.workshop_management.models.workshop_equipment import INTAKE_TERMS_HTML


def migrate(cr, version):
    """Fill intake terms and 54 checklist lines on existing equipment."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Equipment = env["workshop.equipment"]
    empty_terms = Equipment.search(["|", ("intake_terms", "=", False), ("intake_terms", "=", "")])
    if empty_terms:
        empty_terms.write({"intake_terms": INTAKE_TERMS_HTML})
    empty_lines = Equipment.search([("intake_line_ids", "=", False)])
    if empty_lines:
        empty_lines._load_intake_checklist()
