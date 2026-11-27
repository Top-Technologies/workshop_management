# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Customer Request numbers use CR- instead of WR-."""
    cr.execute(
        """
        UPDATE ir_sequence
           SET prefix = 'CR-'
         WHERE code = 'workshop.request'
           AND (prefix = 'WR-' OR prefix IS NULL)
        """
    )
