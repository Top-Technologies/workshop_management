# -*- coding: utf-8 -*-

DOMAIN = "['|', ('user_id', '=', user.id), ('technician_id.user_id', '=', user.id)]"


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_rule
           SET domain_force = %s
         WHERE id = (
            SELECT res_id
              FROM ir_model_data
             WHERE module = 'workshop_management'
               AND name = 'rule_work_order_technician'
               AND model = 'ir.rule'
             LIMIT 1
         )
        """,
        [DOMAIN],
    )
    cr.execute(
        """
        UPDATE workshop_work_order wo
           SET user_id = emp.user_id
          FROM hr_employee emp
         WHERE wo.technician_id = emp.id
           AND emp.user_id IS NOT NULL
           AND (wo.user_id IS NULL OR wo.user_id != emp.user_id)
        """
    )
