# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    overhaul = env.ref(
        "workshop_management.task_engine_overhaul", raise_if_not_found=False
    )
    if overhaul:
        overhaul.write({
            "is_warrantable": True,
            "warranty_kind": "engine_overhaul",
        })
    transmission = env.ref(
        "workshop_management.task_transmission_repair", raise_if_not_found=False
    )
    if transmission:
        transmission.write({
            "is_warrantable": True,
            "warranty_kind": "gearbox",
        })
    gearbox = env.ref(
        "workshop_management.task_gearbox_overhaul", raise_if_not_found=False
    )
    if gearbox:
        gearbox.write({
            "is_warrantable": True,
            "warranty_kind": "gearbox",
        })
