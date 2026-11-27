from odoo import fields, models


class StockPicking(models.Model):
    """Extend stock.picking to tag pickings from spare requests with job_order_id."""

    _inherit = "stock.picking"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Workshop Job Order",
        index=True,
        ondelete="set null",
    )
