from odoo import fields, models


class ResPartner(models.Model):
    """Workshop client class drives the two-way vehicle-release financial gate."""

    _inherit = "res.partner"

    workshop_customer_type_id = fields.Many2one(
        comodel_name="workshop.customer.type",
        string="Customer Type",
        ondelete="restrict",
        index=True,
        help="Used to look up Workshop labour rates (customer type + pricelist rule).",
    )
    workshop_client_class = fields.Selection(
        selection=[
            ("standard", "Standard / New Client"),
            ("credit", "Corporate / Trusted / Credit Client"),
        ],
        string="Workshop Client Class",
        default="standard",
        tracking=True,
        help="Two-way vehicle-release financial gate:\n"
             "• Standard / New: the vehicle cannot be released until every "
             "customer invoice is fully paid.\n"
             "• Corporate / Trusted / Credit: the vehicle may be released "
             "before payment for urgent turnaround; outstanding invoices stay "
             "open and are tracked as payment-pending.",
    )
