# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


DEPT_MAP = {
    "mechanical": "workshop_department_mechanical",
    "body": "workshop_department_body",
    "electrical": "workshop_department_electrical",
    "painting": "workshop_department_painting",
    "inspection": "workshop_department_inspection",
}


def _map_table(env, cr, table, fallback_xmlid=None):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = 'department_legacy'
        """,
        [table],
    )
    if not cr.fetchone():
        return
    fallback_id = False
    if fallback_xmlid:
        rec = env.ref("workshop_management.%s" % fallback_xmlid, raise_if_not_found=False)
        fallback_id = rec.id if rec else False
    cr.execute("SELECT id, department_legacy FROM %s" % table)
    for rec_id, key in cr.fetchall():
        xmlid = DEPT_MAP.get(key)
        rec = env.ref("workshop_management.%s" % xmlid, raise_if_not_found=False) if xmlid else None
        new_id = rec.id if rec else fallback_id
        if new_id:
            cr.execute(
                "UPDATE %s SET department = %%s WHERE id = %%s" % table,
                [new_id, rec_id],
            )
    cr.execute("ALTER TABLE %s DROP COLUMN IF EXISTS department_legacy" % table)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _map_table(env, cr, "workshop_work_order", "workshop_department_mechanical")
    _map_table(env, cr, "workshop_task_master", "workshop_department_mechanical")
    _map_table(env, cr, "workshop_quality_checklist_item")
