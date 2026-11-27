from odoo import fields, models


class AccountMove(models.Model):
    """Extend account.move for invoice/bill-to-job traceability."""

    _inherit = "account.move"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Workshop Job Order",
        index=True,
        ondelete="set null",
        copy=False,
    )

    def write(self, vals):
        res = super().write(vals)
        jobs = self.mapped("job_order_id")
        if jobs:
            jobs._compute_release_payment()
        return res
