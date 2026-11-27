# -*- coding: utf-8 -*-


def _rename_if_char(cr, table, column, legacy):
    cr.execute(
        """
        SELECT data_type
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        [table, column],
    )
    row = cr.fetchone()
    if row and row[0] in ("character varying", "varchar", "text", "character"):
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = %s
            """,
            [table, legacy],
        )
        if not cr.fetchone():
            cr.execute(
                'ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
                % (table, column, legacy)
            )


def migrate(cr, version):
    _rename_if_char(cr, "workshop_work_order", "department", "department_legacy")
    _rename_if_char(cr, "workshop_task_master", "department", "department_legacy")
    _rename_if_char(cr, "workshop_quality_checklist_item", "department", "department_legacy")
