from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round


EXPENSE_TYPES = [
    ("fuel", "Fuel"),
    ("travel", "Travel / Transport"),
    ("lodging", "Lodging"),
    ("meals", "Meals / Per Diem"),
    ("parts", "Parts bought locally"),
    ("other", "Other"),
]


def billable_from_cost(amount, margin_percent):
    """Return customer price that yields `margin_percent` profit on `amount`."""
    amount = amount or 0.0
    margin = margin_percent or 0.0
    if margin >= 100.0:
        margin = 99.99
    if margin <= 0.0:
        return amount
    return amount / (1.0 - (margin / 100.0))


class WorkshopExpense(models.Model):
    """Field-staff out-of-pocket expense tied to a Job Order (TO)."""

    _name = "workshop.expense"
    _description = "Workshop Field Expense"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Expense No.",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index=True,
    )
    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Job Order",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        related="job_order_id.partner_id",
        store=True,
        readonly=True,
    )
    equipment_id = fields.Many2one(
        related="job_order_id.equipment_id",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Field Staff",
        default=lambda self: self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid)], limit=1
        ),
        tracking=True,
        index=True,
    )
    submitted_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Submitted By",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string="Expense Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    expense_type = fields.Selection(
        selection=EXPENSE_TYPES,
        string="Type",
        required=True,
        default="other",
        tracking=True,
    )
    description = fields.Char(string="Description", required=True)
    amount = fields.Monetary(
        string="Amount Paid (Personal Money)",
        required=True,
        tracking=True,
        help="What the technician paid out of pocket.",
    )
    margin_percent = fields.Float(
        string="Company Margin (%)",
        help="Locked from company settings on submit. Billing = cost ÷ (1 − margin).",
    )
    billable_amount = fields.Monetary(
        string="Billable to Customer",
        compute="_compute_billable_amount",
        store=True,
        help="Approved cost with company profit margin applied.",
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    receipt_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="workshop_expense_receipt_rel",
        column1="expense_id",
        column2="attachment_id",
        string="Receipts",
        copy=False,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Waiting Foreman"),
            ("approved", "Approved"),
            ("refused", "Refused"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    approved_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Validated By",
        copy=False,
        tracking=True,
    )
    approved_on = fields.Datetime(string="Validated On", copy=False)
    refuse_reason = fields.Text(string="Refusal Reason", copy=False)
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Line",
        copy=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="job_order_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    notes = fields.Text(string="Notes")

    @api.depends("amount", "margin_percent")
    def _compute_billable_amount(self):
        for rec in self:
            rec.billable_amount = float_round(
                billable_from_cost(rec.amount, rec.margin_percent),
                precision_digits=2,
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.expense"
                ) or "New"
            if "margin_percent" not in vals:
                company = self.env.company
                if vals.get("job_order_id"):
                    job = self.env["workshop.job.order"].browse(vals["job_order_id"])
                    company = job.company_id or company
                vals["margin_percent"] = company.workshop_expense_margin_percent
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft expenses can be submitted."))
            if float_compare(rec.amount, 0.0, precision_digits=2) <= 0:
                raise UserError(_("Enter the amount paid out of pocket."))
            if not rec.receipt_ids:
                raise UserError(_(
                    "Attach a scanned receipt or photo before submitting to the Foreman."
                ))
            rec.write({
                "state": "submitted",
                "margin_percent": rec.company_id.workshop_expense_margin_percent,
            })
            rec._notify_foremen()
            rec.job_order_id.message_post(body=_(
                "Field expense %s submitted for Foreman validation (%.2f)."
            ) % (rec.name, rec.amount))

    def action_approve(self):
        if not self.env.user.has_group("workshop_management.group_workshop_supervisor"):
            raise UserError(_("Only a Foreman / Supervisor can validate field expenses."))
        for rec in self:
            if rec.state != "submitted":
                raise UserError(_("Only submitted expenses can be approved."))
            rec.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_on": fields.Datetime.now(),
            })
            rec._ensure_sale_line()
            rec.activity_ids.action_feedback(feedback=_("Approved"))
            rec.job_order_id.message_post(body=_(
                "Foreman approved expense %s. Cost %.2f billed at %.2f (%.1f%% margin)."
            ) % (rec.name, rec.amount, rec.billable_amount, rec.margin_percent))

    def action_refuse(self):
        if not self.env.user.has_group("workshop_management.group_workshop_supervisor"):
            raise UserError(_("Only a Foreman / Supervisor can refuse field expenses."))
        for rec in self:
            if rec.state != "submitted":
                raise UserError(_("Only submitted expenses can be refused."))
            rec.write({
                "state": "refused",
                "approved_by_id": self.env.user.id,
                "approved_on": fields.Datetime.now(),
            })
            rec.activity_ids.action_feedback(feedback=_("Refused"))
            rec.job_order_id.message_post(body=_(
                "Foreman refused expense %s."
            ) % rec.name)

    def action_reset_draft(self):
        for rec in self:
            if rec.state != "refused":
                raise UserError(_("Only refused expenses can be reset to draft."))
            rec.write({
                "state": "draft",
                "approved_by_id": False,
                "approved_on": False,
                "refuse_reason": False,
            })

    def _notify_foremen(self):
        self.ensure_one()
        group = self.env.ref(
            "workshop_management.group_workshop_supervisor",
            raise_if_not_found=False,
        )
        users = group.all_user_ids.filtered(lambda u: u.active and not u.share) if group else self.env["res.users"]
        summary = _("Validate field expense %s") % self.name
        body = _(
            "Field staff <b>%(user)s</b> submitted personal-money expense "
            "<b>%(exp)s</b> (%(amount)s) on Job Order <b>%(job)s</b>. "
            "Please validate before billing."
        ) % {
            "user": self.submitted_by_id.display_name,
            "exp": self.name,
            "amount": "%.2f" % self.amount,
            "job": self.job_order_id.display_name,
        }
        for user in users[:20]:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=summary,
                note=body,
            )
        self.message_post(body=body)

    def _expense_product(self):
        self.ensure_one()
        product = self.company_id.workshop_expense_product_id
        if product:
            return product
        return self.env.ref(
            "workshop_management.product_workshop_field_expense",
            raise_if_not_found=False,
        ) or self.env["product.product"]

    def _ensure_sale_line(self):
        """Add/update a billable SO line at cost + company margin."""
        for rec in self:
            if rec.state != "approved":
                continue
            so = rec.job_order_id.sale_order_id
            if not so or so.state == "cancel":
                continue
            product = rec._expense_product()
            if not product:
                rec.message_post(body=_(
                    "No Field Expense Recovery product is configured; "
                    "the expense is on job cost only until a product is set in Workshop Settings."
                ))
                continue
            name = _("%s — %s") % (rec.name, rec.description)
            vals = {
                "name": name,
                "product_uom_qty": 1.0,
                "price_unit": rec.billable_amount,
                "workshop_coverage": "billable",
                "workshop_expense_id": rec.id,
            }
            if rec.sale_line_id and rec.sale_line_id.order_id == so:
                rec.sale_line_id.write(vals)
                continue
            create_vals = {
                **vals,
                "order_id": so.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
            }
            rec.sale_line_id = self.env["sale.order.line"].create(create_vals)
