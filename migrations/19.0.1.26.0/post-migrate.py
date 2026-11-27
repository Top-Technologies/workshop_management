# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Mark equipment that still has an unreleased job as in-workshop."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    equipment = env["workshop.equipment"].search([])
    if equipment:
        equipment._sync_workshop_status_from_jobs()
