from odoo import fields, models


class HrEmployee(models.Model):
    """Extend employee with workshop labor rate used in job costing."""

    _inherit = "hr.employee"

    hourly_cost = fields.Float(
        string="Workshop Hourly Cost",
        default=0.0,
        help="Labor rate used for workshop job costing (Actual Hours × Hourly Cost).",
    )
