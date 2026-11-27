from odoo import api, fields, models, _
from odoo.exceptions import UserError

AGREEMENT_LINE_TYPES = [
    ("labor", "Labor"),
    ("parts", "Spare Parts"),
    ("external", "External Job / Outsourcing"),
    ("travel", "Travel / Transport"),
    ("mileage", "Mileage"),
    ("per_diem", "Per Diem"),
    ("fuel", "Fuel"),
    ("other", "Other Charges"),
]


class WorkshopAgreement(models.Model):
    """Customer service contract with coverage rules, period, and visit/hour limits."""

    _name = "workshop.agreement"
    _description = "Workshop Service Agreement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(
        string="Agreement No.",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        required=True,
        tracking=True,
        index=True,
        ondelete="restrict",
    )
    date_start = fields.Date(
        string="Start Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_end = fields.Date(string="End Date", tracking=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("running", "Running"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
        index=True,
    )
    equipment_ids = fields.Many2many(
        comodel_name="workshop.equipment",
        relation="workshop_agreement_equipment_rel",
        column1="agreement_id",
        column2="equipment_id",
        string="Covered Equipment/Vehicle",
        help="Leave empty to cover all of this customer's equipment.",
        domain="[('partner_id', '=', partner_id)]",
    )
    line_ids = fields.One2many(
        comodel_name="workshop.agreement.line",
        inverse_name="agreement_id",
        string="Coverage",
    )
    included_visits = fields.Integer(
        string="Included Visits",
        default=0,
        help="0 means unlimited visits during the agreement period.",
    )
    included_hours = fields.Float(
        string="Included Labor Hours",
        default=0.0,
        help="0 means unlimited labor hours. Extra hours use Extra Labor Rate.",
    )
    extra_labor_rate = fields.Monetary(
        string="Extra Labor Rate",
        help="Used for labor after included hours or visits are exhausted.",
    )
    used_visits = fields.Integer(
        string="Used Visits",
        compute="_compute_usage",
    )
    remaining_visits = fields.Integer(
        string="Remaining Visits",
        compute="_compute_usage",
    )
    used_hours = fields.Float(
        string="Used Hours",
        compute="_compute_usage",
    )
    remaining_hours = fields.Float(
        string="Remaining Hours",
        compute="_compute_usage",
    )
    visits_unlimited = fields.Boolean(compute="_compute_usage")
    hours_unlimited = fields.Boolean(compute="_compute_usage")
    request_ids = fields.One2many(
        comodel_name="workshop.request",
        inverse_name="agreement_id",
        string="Customer Requests",
    )
    job_order_ids = fields.Many2many(
        comodel_name="workshop.job.order",
        compute="_compute_job_order_ids",
        string="Job Orders",
    )
    request_count = fields.Integer(compute="_compute_counts")
    job_order_count = fields.Integer(compute="_compute_counts")
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract Sales Order",
        ondelete="set null",
        help="Optional sales order that sold this maintenance contract.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    notes = fields.Html(string="Terms & Notes")
    active = fields.Boolean(default=True)
    warranty_rule_ids = fields.One2many(
        comodel_name="workshop.warranty.rule",
        inverse_name="agreement_id",
        string="Warranty Periods",
        help="Optional client-specific Engine Overhaul / Gearbox warranty durations.",
    )

    @api.depends("request_ids.job_order_ids")
    def _compute_job_order_ids(self):
        for rec in self:
            rec.job_order_ids = rec.request_ids.job_order_ids

    @api.depends("request_ids", "request_ids.job_order_ids")
    def _compute_counts(self):
        for rec in self:
            rec.request_count = len(rec.request_ids)
            rec.job_order_count = len(rec.request_ids.job_order_ids)

    @api.depends(
        "included_visits",
        "included_hours",
        "request_ids.job_order_ids.state",
        "request_ids.job_order_ids.actual_hours",
    )
    def _compute_usage(self):
        for rec in self:
            jobs = rec.request_ids.job_order_ids.filtered(
                lambda j: j.state in ("completed", "closed")
            )
            rec.used_visits = len(jobs)
            rec.used_hours = sum(jobs.mapped("actual_hours"))
            rec.visits_unlimited = not rec.included_visits
            rec.hours_unlimited = not rec.included_hours
            rec.remaining_visits = (
                0 if rec.visits_unlimited else max(rec.included_visits - rec.used_visits, 0)
            )
            rec.remaining_hours = (
                0.0 if rec.hours_unlimited else max(rec.included_hours - rec.used_hours, 0.0)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.agreement"
                ) or "New"
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if rec.date_end and rec.date_end < rec.date_start:
                raise UserError(_("End date cannot be before start date."))
            rec._expire_if_needed()
            if rec.state == "expired":
                continue
            rec.state = "running"

    def action_cancel(self):
        self.filtered(lambda a: a.state != "expired").write({"state": "cancelled"})

    def action_draft(self):
        self.filtered(lambda a: a.state in ("cancelled", "expired")).write({"state": "draft"})

    def _expire_if_needed(self):
        today = fields.Date.context_today(self)
        to_expire = self.filtered(
            lambda a: a.state == "running" and a.date_end and a.date_end < today
        )
        if to_expire:
            to_expire.write({"state": "expired"})

    def has_visit_allowance(self):
        self.ensure_one()
        return self.visits_unlimited or self.used_visits < self.included_visits

    def has_hours_allowance(self):
        self.ensure_one()
        return self.hours_unlimited or self.used_hours < self.included_hours

    def is_applicable_for(self, partner, equipment=False, on_date=False):
        self.ensure_one()
        self._expire_if_needed()
        on_date = on_date or fields.Date.context_today(self)
        if self.state != "running" or self.partner_id != partner:
            return False
        if self.date_start and self.date_start > on_date:
            return False
        if self.date_end and self.date_end < on_date:
            return False
        if self.equipment_ids and equipment and equipment not in self.equipment_ids:
            return False
        return True

    @api.model
    def _find_applicable(self, partner, equipment=False, on_date=False):
        if not partner:
            return self.browse()
        on_date = on_date or fields.Date.context_today(self)
        agreements = self.search([
            ("partner_id", "=", partner.id),
            ("state", "=", "running"),
            ("date_start", "<=", on_date),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", on_date),
        ], order="date_end desc, id desc")
        agreements._expire_if_needed()
        agreements = agreements.filtered(lambda a: a.state == "running")
        if equipment:
            specific = agreements.filtered(lambda a: equipment in a.equipment_ids)
            if specific:
                return specific[:1]
            general = agreements.filtered(lambda a: not a.equipment_ids)
            return general[:1]
        return agreements.filtered(lambda a: not a.equipment_ids)[:1] or agreements[:1]

    def _match_cover_line(self, product, line_type=False):
        self.ensure_one()
        product = product or self.env["product.product"]
        if product:
            by_product = self.line_ids.filtered(lambda l: l.product_id == product)
            if by_product:
                return by_product[:1]
        if line_type:
            by_type = self.line_ids.filtered(
                lambda l: not l.product_id and l.line_type == line_type
            )
            if by_type:
                return by_type[:1]
        catch_all = self.line_ids.filtered(lambda l: not l.product_id and not l.line_type)
        return catch_all[:1]

    def get_line_billing(self, product, line_type=False, fallback_price=0.0):
        """Return coverage/price/discount for a quotation or sales order line."""
        self.ensure_one()
        self._expire_if_needed()
        if self.state != "running":
            return False

        cover = self._match_cover_line(product, line_type)
        visit_ok = self.has_visit_allowance()
        hours_ok = self.has_hours_allowance()
        is_labor = line_type == "labor"

        if not visit_ok:
            price = self.extra_labor_rate if is_labor and self.extra_labor_rate else fallback_price
            return {
                "coverage": "billable",
                "price_unit": price,
                "discount": 0.0,
            }

        if not cover:
            if is_labor and not hours_ok and self.extra_labor_rate:
                return {
                    "coverage": "billable",
                    "price_unit": self.extra_labor_rate,
                    "discount": 0.0,
                }
            return False

        if cover.coverage_type == "included":
            if is_labor and not hours_ok and self.extra_labor_rate:
                return {
                    "coverage": "billable",
                    "price_unit": self.extra_labor_rate,
                    "discount": 0.0,
                }
            return {
                "coverage": "agreement",
                "price_unit": cover.price_unit or fallback_price,
                "discount": 100.0,
            }
        if cover.coverage_type == "fixed_price":
            return {
                "coverage": "agreement",
                "price_unit": cover.price_unit,
                "discount": 0.0,
            }
        price = fallback_price
        if is_labor and self.extra_labor_rate:
            price = self.extra_labor_rate
        elif cover.price_unit:
            price = cover.price_unit
        return {
            "coverage": "billable",
            "price_unit": price,
            "discount": 0.0,
        }

    def action_view_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Requests"),
            "res_model": "workshop.request",
            "view_mode": "list,form",
            "domain": [("agreement_id", "=", self.id)],
            "context": {"default_agreement_id": self.id, "default_partner_id": self.partner_id.id},
        }

    def action_view_job_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Job Orders"),
            "res_model": "workshop.job.order",
            "view_mode": "list,form,kanban",
            "domain": [("agreement_id", "=", self.id)],
        }


class WorkshopAgreementLine(models.Model):
    """Coverage rule: included, fixed agreement price, or extra/billable."""

    _name = "workshop.agreement.line"
    _description = "Workshop Service Agreement Coverage"
    _order = "sequence, id"

    agreement_id = fields.Many2one(
        comodel_name="workshop.agreement",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product / Service",
        help="Leave empty to apply this rule to every product of the selected service type.",
    )
    line_type = fields.Selection(
        selection=AGREEMENT_LINE_TYPES,
        string="Service Type",
        help="Used when Product is empty. Leave both empty for a catch-all rule.",
    )
    task_id = fields.Many2one(
        comodel_name="workshop.task.master",
        string="Job Description",
        ondelete="set null",
    )
    coverage_type = fields.Selection(
        selection=[
            ("included", "Included (not billed)"),
            ("fixed_price", "Fixed Agreement Price"),
            ("extra", "Extra / Billable"),
        ],
        string="Coverage",
        required=True,
        default="included",
    )
    price_unit = fields.Float(
        string="Agreement Price",
        help="Used for Fixed Agreement Price. For Included, kept as reference.",
    )
    name = fields.Char(string="Job Description")
    company_id = fields.Many2one(related="agreement_id.company_id", store=True)
    currency_id = fields.Many2one(related="agreement_id.currency_id")

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id and not self.name:
            self.name = self.product_id.display_name
            self.price_unit = self.product_id.list_price

    @api.onchange("task_id")
    def _onchange_task_id(self):
        if self.task_id:
            # Do not overwrite Service Type — user may have set it before Job Description.
            if not self.name:
                self.name = self.task_id.name
