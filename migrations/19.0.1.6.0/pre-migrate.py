# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'res_company'
           AND column_name = 'workshop_default_labor_rate'
        """
    )
    if not cr.fetchone():
        cr.execute(
            """
            ALTER TABLE res_company
            ADD COLUMN workshop_default_labor_rate double precision
            """
        )
        cr.execute(
            """
            UPDATE res_company
               SET workshop_default_labor_rate = 50.0
             WHERE workshop_default_labor_rate IS NULL
            """
        )
