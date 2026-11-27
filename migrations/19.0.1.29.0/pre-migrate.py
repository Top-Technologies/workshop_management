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
    _add_column(cr, "res_company", "workshop_expense_margin_percent", "double precision")
    cr.execute(
        """
        UPDATE res_company
           SET workshop_expense_margin_percent = 20
         WHERE workshop_expense_margin_percent IS NULL
        """
    )
    _add_column(cr, "res_company", "workshop_expense_product_id", "integer")
    _add_column(cr, "sale_order_line", "workshop_expense_id", "integer")
