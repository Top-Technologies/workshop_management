# -*- coding: utf-8 -*-


def migrate(cr, version):
    """agreement_id used to point at sale.order; drop so it can target workshop.agreement."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'workshop_request'
           AND column_name = 'agreement_id'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE workshop_request DROP COLUMN IF EXISTS agreement_id")

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'workshop_job_order'
           AND column_name = 'agreement_id'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE workshop_job_order DROP COLUMN IF EXISTS agreement_id")
