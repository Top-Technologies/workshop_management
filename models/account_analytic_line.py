from odoo import fields, models


class AccountAnalyticLine(models.Model):
    """Extend account.analytic.line (timesheets) to link to workshop.work.order."""

    _inherit = "account.analytic.line"

    work_order_id = fields.Many2one(
        comodel_name="workshop.work.order",
        string="Work Dispatch",
        index=True,
        ondelete="set null",
    )
    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        related="work_order_id.job_order_id",
        string="Workshop Job Order",
        store=True,
        readonly=True,
    )
