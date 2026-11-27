# -*- coding: utf-8 -*-


def _add_column(cr, table, column, definition):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        [table, column],
    )
    if not cr.fetchone():
        cr.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, definition))


def migrate(cr, version):
    _add_column(cr, "workshop_equipment_type", "is_vehicle", "boolean")
    _add_column(cr, "workshop_work_type", "is_punch", "boolean")
    _add_column(cr, "workshop_task_master", "is_punch", "boolean")
    cr.execute(
        """
        UPDATE workshop_equipment_type t
           SET is_vehicle = TRUE
          FROM ir_model_data d
         WHERE d.module = 'workshop_management'
           AND d.name = 'equipment_type_vehicle'
           AND d.model = 'workshop.equipment.type'
           AND d.res_id = t.id
           AND (t.is_vehicle IS NULL OR t.is_vehicle IS FALSE)
        """
    )
    cr.execute(
        """
        UPDATE workshop_work_type t
           SET is_punch = TRUE
          FROM ir_model_data d
         WHERE d.module = 'workshop_management'
           AND d.name = 'work_type_overhaul'
           AND d.model = 'workshop.work.type'
           AND d.res_id = t.id
           AND (t.is_punch IS NULL OR t.is_punch IS FALSE)
        """
    )
