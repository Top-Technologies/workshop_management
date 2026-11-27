from odoo import fields, models


class PurchaseOrder(models.Model):
    """Tag purchase RFQs / orders raised from spare shortages to a Job Order."""

    _inherit = "purchase.order"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Workshop Job Order",
        index=True,
        ondelete="set null",
        copy=False,
    )
