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
    _add_column(cr, "res_partner", "workshop_customer_type_id", "integer")
