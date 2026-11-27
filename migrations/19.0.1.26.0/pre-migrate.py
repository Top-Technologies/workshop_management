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
    """Create vehicle-release columns before the ORM reads them."""
    _add_column(cr, "res_partner", "workshop_client_class", "varchar")
    cr.execute(
        """
        UPDATE res_partner
           SET workshop_client_class = 'standard'
         WHERE workshop_client_class IS NULL
        """
    )

    _add_column(cr, "res_company", "workshop_financial_gate", "boolean")
    cr.execute(
        """
        UPDATE res_company
           SET workshop_financial_gate = TRUE
         WHERE workshop_financial_gate IS NULL
        """
    )

    _add_column(cr, "workshop_equipment", "workshop_status", "varchar")
    _add_column(cr, "workshop_equipment", "release_date", "timestamp")
    cr.execute(
        """
        UPDATE workshop_equipment
           SET workshop_status = 'available'
         WHERE workshop_status IS NULL
        """
    )

    _add_column(cr, "workshop_job_order", "workshop_client_class", "varchar")
    _add_column(cr, "workshop_job_order", "vehicle_released", "boolean")
    _add_column(cr, "workshop_job_order", "vehicle_release_date", "timestamp")
    _add_column(cr, "workshop_job_order", "vehicle_release_mode", "varchar")
    _add_column(cr, "workshop_job_order", "released_by_id", "integer")
    _add_column(cr, "workshop_job_order", "outstanding_invoice_amount", "numeric")
    _add_column(cr, "workshop_job_order", "invoices_fully_paid", "boolean")
    _add_column(cr, "workshop_job_order", "payment_pending", "boolean")
    cr.execute(
        """
        UPDATE workshop_job_order
           SET vehicle_released = FALSE
         WHERE vehicle_released IS NULL
        """
    )
