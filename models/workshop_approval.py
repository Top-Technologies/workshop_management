from odoo import fields, models


class WorkshopApprovalRule(models.Model):
    """Approval rule engine – value thresholds to required approver groups."""

    _name = "workshop.approval.rule"
    _description = "Workshop Approval Rule"
    _order = "amount_threshold desc"

    name = fields.Char(
        string="Rule Name",
        required=True,
    )
    amount_threshold = fields.Monetary(
        string="Amount Threshold",
        required=True,
        help="Job Order estimated cost at or above which this approval rule triggers.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    group_id = fields.Many2one(
        comodel_name="res.groups",
        string="Approver Group",
        required=True,
        help="Workshop group used to pick approvers when no Approvals category is set.",
    )
    category_id = fields.Many2one(
        comodel_name="approval.category",
        string="Approvals Category",
        help="Odoo Approvals category used when a Job Order matches this rule.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)


class WorkshopApprovalLog(models.Model):
    """Audit log of who approved/rejected what and when."""

    _name = "workshop.approval.log"
    _description = "Workshop Approval Audit Log"
    _order = "date desc, id desc"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Job Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Approver",
        required=True,
        default=lambda self: self.env.user,
    )
    action = fields.Selection(
        selection=[
            ("submit", "Submitted for Approval"),
            ("approve", "Approved"),
            ("reject", "Rejected"),
        ],
        string="Action",
        required=True,
    )
    comments = fields.Text(string="Comments / Reason")
    date = fields.Datetime(
        string="Timestamp",
        default=fields.Datetime.now,
        required=True,
    )
