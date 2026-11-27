# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


EQUIPMENT_TYPE_MAP = {
    "vehicle": "equipment_type_vehicle",
    "machinery": "equipment_type_machinery",
    "generator": "equipment_type_generator",
    "pump": "equipment_type_pump",
    "compressor": "equipment_type_compressor",
    "other": "equipment_type_other",
}
WORK_TYPE_MAP = {
    "repair": "work_type_repair",
    "maintenance": "work_type_maintenance",
    "inspection": "work_type_inspection",
    "overhaul": "work_type_overhaul",
    "diagnosis": "work_type_diagnosis",
    "other": "work_type_other",
}


def _map_legacy(env, cr, legacy_column, target_column, xmlid_map, fallback_xmlid=None):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'workshop_equipment'
           AND column_name = %s
        """,
        [legacy_column],
    )
    if not cr.fetchone():
        return
    fallback_id = False
    if fallback_xmlid:
        rec = env.ref("workshop_management.%s" % fallback_xmlid, raise_if_not_found=False)
        fallback_id = rec.id if rec else False
    cr.execute(
        "SELECT id, %s FROM workshop_equipment WHERE %s IS NOT NULL"
        % (legacy_column, legacy_column)
    )
    for rec_id, key in cr.fetchall():
        xmlid = xmlid_map.get(key)
        rec = env.ref("workshop_management.%s" % xmlid, raise_if_not_found=False) if xmlid else None
        new_id = rec.id if rec else fallback_id
        if new_id:
            cr.execute(
                "UPDATE workshop_equipment SET %s = %%s WHERE id = %%s"
                % target_column,
                [new_id, rec_id],
            )
    cr.execute("ALTER TABLE workshop_equipment DROP COLUMN IF EXISTS %s" % legacy_column)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _map_legacy(
        env, cr, "equipment_type_legacy", "equipment_type", EQUIPMENT_TYPE_MAP, "equipment_type_vehicle"
    )
    _map_legacy(env, cr, "work_type_legacy", "work_type", WORK_TYPE_MAP)
