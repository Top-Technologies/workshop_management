# -*- coding: utf-8 -*-


def _rename_legacy_char_column(cr, column, legacy):
    cr.execute(
        """
        SELECT data_type
          FROM information_schema.columns
         WHERE table_name = 'workshop_equipment'
           AND column_name = %s
        """,
        [column],
    )
    row = cr.fetchone()
    if row and row[0] in ("character varying", "varchar", "text", "character"):
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'workshop_equipment'
               AND column_name = %s
            """,
            [legacy],
        )
        if not cr.fetchone():
            cr.execute(
                "ALTER TABLE workshop_equipment RENAME COLUMN %s TO %s"
                % (column, legacy)
            )


def migrate(cr, version):
    """Selection fields become Many2one integers; keep old values for post-migrate."""
    _rename_legacy_char_column(cr, "equipment_type", "equipment_type_legacy")
    _rename_legacy_char_column(cr, "work_type", "work_type_legacy")
