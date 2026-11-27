from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero

from .workshop_field_service_mixin import FIELD_CHARGE_LINE_TYPES


class WorkshopJobOrder(models.Model):
    """Central Job Order record — owns all work/parts/cost for one service visit."""

    _name = "workshop.job.order"
    _description = "Workshop Job Order"
    _inherit = ["mail.thread", "mail.activity.mixin", "workshop.field.service.location.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="Job Order No.",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order Origin",
        tracking=True,
        ondelete="set null",
    )
    request_id = fields.Many2one(
        comodel_name="workshop.request",
        string="Customer Request",
        tracking=True,
        index=True,
        ondelete="restrict",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        related="request_id.partner_id",
        store=True,
        readonly=True,
    )
    equipment_id = fields.Many2one(
        comodel_name="workshop.equipment",
        string="Equipment/Vehicle",
        related="request_id.equipment_id",
        store=True,
        readonly=True,
    )
    warranty_status = fields.Selection(
        related="equipment_id.warranty_status",
        string="Warranty Status",
        store=True,
        readonly=True,
    )
    agreement_id = fields.Many2one(
        comodel_name="workshop.agreement",
        string="Service Agreement",
        related="request_id.agreement_id",
        store=True,
        readonly=True,
    )
    is_warranty_job = fields.Boolean(
        string="Warranty Job",
        compute="_compute_billing_flags",
        store=True,
        help="This visit is covered by an active Engine Overhaul or Gearbox warranty.",
    )
    is_agreement_job = fields.Boolean(
        string="Agreement Customer",
        compute="_compute_billing_flags",
        store=True,
        help="Billed per negotiated service agreement terms.",
    )
    estimated_cost = fields.Monetary(
        string="Estimated Cost (from SO)",
        compute="_compute_estimated_cost",
        store=True,
        help="Sales Order total used as estimated job value for approval thresholds.",
    )
    priority = fields.Selection(
        selection=[
            ("0", "Low"),
            ("1", "Normal"),
            ("2", "High"),
            ("3", "Urgent"),
        ],
        string="Priority",
        default="1",
        tracking=True,
    )
    expected_finish_date = fields.Date(
        string="Expected Finish Date",
        tracking=True,
    )
    date_start = fields.Datetime(
        string="Actual Start",
        tracking=True,
    )
    date_end = fields.Datetime(
        string="Actual End",
        tracking=True,
    )
    approval_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("supervisor_review", "Supervisor Review"),
            ("manager_review", "Manager Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Approval Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    required_approver_group_id = fields.Many2one(
        comodel_name="res.groups",
        string="Required Approver Group",
        copy=False,
        help="Set by the approval rule engine when the Job Order is submitted.",
    )
    manager_approval_required = fields.Boolean(
        string="Manager Approval Required",
        copy=False,
        help="Set when estimated value meets a Manager-level approval rule.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("waiting_approval", "Waiting Approval"),
            ("approved", "Approved"),
            ("assigned", "Assigned"),
            ("in_progress", "In Progress"),
            ("waiting_parts", "Waiting Parts"),
            ("quality_inspection", "Quality Inspection"),
            ("completed", "Completed"),
            ("closed", "Closed"),
        ],
        string="Job Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Workshop Supervisor / Responsible",
        default=lambda self: self.env.user,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        readonly=True,
    )
    work_order_ids = fields.One2many(
        comodel_name="workshop.work.order",
        inverse_name="job_order_id",
        string="Work Dispatches",
    )
    field_visit_ids = fields.One2many(
        comodel_name="workshop.field.visit",
        inverse_name="job_order_id",
        string="Field Visits",
    )
    spare_request_ids = fields.One2many(
        comodel_name="workshop.spare.request",
        inverse_name="job_order_id",
        string="Spare Requests",
    )
    expense_ids = fields.One2many(
        comodel_name="workshop.expense",
        inverse_name="job_order_id",
        string="Field Expenses",
    )
    quality_inspection_ids = fields.One2many(
        comodel_name="workshop.quality.inspection",
        inverse_name="job_order_id",
        string="Quality Inspections",
    )
    warranty_ids = fields.One2many(
        comodel_name="workshop.warranty",
        inverse_name="job_order_id",
        string="Issued Warranties",
    )
    approval_log_ids = fields.One2many(
        comodel_name="workshop.approval.log",
        inverse_name="job_order_id",
        string="Approval History",
    )
    purchase_order_ids = fields.One2many(
        comodel_name="purchase.order",
        inverse_name="job_order_id",
        string="Purchase Orders / Requisitions",
    )
    invoice_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="job_order_id",
        string="Invoices",
        domain=[("move_type", "in", ["out_invoice", "out_refund"])],
    )
    customer_signature = fields.Binary(
        string="Customer Acceptance Signature",
        copy=False,
        attachment=True,
    )
    signed_by = fields.Char(string="Signed By")
    signed_on = fields.Datetime(string="Signed On")
    completion_document_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Archived Completion Form",
        copy=False,
        readonly=True,
    )

    workshop_client_class = fields.Selection(
        related="partner_id.workshop_client_class",
        string="Workshop Client Class",
        store=True,
        readonly=True,
    )
    vehicle_released = fields.Boolean(
        string="Vehicle Released",
        default=False,
        copy=False,
        tracking=True,
        help="True when the equipment/vehicle has left the workshop.",
    )
    vehicle_release_date = fields.Datetime(
        string="Vehicle Release Date",
        copy=False,
        tracking=True,
    )
    vehicle_release_mode = fields.Selection(
        selection=[
            ("paid", "Fully Paid"),
            ("credit", "Credit / Pending Payment"),
            ("no_charge", "No Charge"),
        ],
        string="Release Mode",
        copy=False,
        tracking=True,
    )
    released_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Released By",
        copy=False,
        tracking=True,
    )
    outstanding_invoice_amount = fields.Monetary(
        string="Outstanding Invoice Amount",
        compute="_compute_release_payment",
        store=True,
        help="Residual amount on posted customer invoices for this job.",
    )
    invoices_fully_paid = fields.Boolean(
        string="Invoices Fully Paid",
        compute="_compute_release_payment",
        store=True,
    )
    payment_pending = fields.Boolean(
        string="Payment Pending",
        compute="_compute_release_payment",
        store=True,
        help="Vehicle was released on credit and customer invoices are still unpaid.",
    )
    release_blocked = fields.Boolean(
        string="Release Blocked",
        compute="_compute_release_gate_ui",
    )
    release_block_reason = fields.Text(
        string="Release Block Reason",
        compute="_compute_release_gate_ui",
    )

    # Costing and Hours Rollups
    planned_hours = fields.Float(
        string="Standard Hours",
        compute="_compute_hours_and_costs",
        store=True,
    )
    actual_hours = fields.Float(
        string="Actual Hours",
        compute="_compute_hours_and_costs",
        store=True,
    )
    labor_cost = fields.Monetary(
        string="Labor Cost",
        compute="_compute_hours_and_costs",
        store=True,
        help="Standard Hours × technician hourly rate (or company default). "
             "Timer / actual hours are not used for costing.",
    )
    parts_cost = fields.Monetary(
        string="Parts Cost",
        compute="_compute_hours_and_costs",
        store=True,
    )
    external_service_cost = fields.Monetary(
        string="External Job / Outsourcing (Vendor Bills)",
        compute="_compute_hours_and_costs",
        store=True,
    )
    other_cost = fields.Monetary(
        string="Field & Other Charges",
        compute="_compute_hours_and_costs",
        store=True,
        help="Live field charges from the request estimate. Travel/mileage is replaced by "
             "actual visit travel hours × labor rate once travel is logged.",
    )
    expense_cost = fields.Monetary(
        string="Approved Field Expenses",
        compute="_compute_hours_and_costs",
        store=True,
        help="Out-of-pocket amounts approved by the Foreman. Billing uses cost plus company margin.",
    )
    total_travel_hours = fields.Float(
        string="Total Travel Hours",
        compute="_compute_field_service_kpis",
        store=True,
    )
    total_on_site_hours = fields.Float(
        string="Total On-Site Hours",
        compute="_compute_field_service_kpis",
        store=True,
    )
    avg_dispatch_to_arrival_hours = fields.Float(
        string="Avg Dispatch to Arrival (hrs)",
        compute="_compute_field_service_kpis",
        store=True,
    )
    total_cost = fields.Monetary(
        string="Total Cost",
        compute="_compute_hours_and_costs",
        store=True,
    )
    job_profitability = fields.Monetary(
        string="Realized Profit",
        compute="_compute_hours_and_costs",
        store=True,
        help="Posted customer invoices − total cost. See Expected Profit for quoted − cost.",
    )
    invoiced_amount = fields.Monetary(
        string="Invoiced Amount",
        compute="_compute_hours_and_costs",
        store=True,
        help="Posted customer invoices only. Quotations are not counted as revenue.",
    )
    cost_of_quality = fields.Monetary(
        string="Cost of Quality",
        compute="_compute_hours_and_costs",
        store=True,
        help="Rework labor cost absorbed by the workshop or technician (excludes customer-paid rework).",
    )
    waiting_parts_since = fields.Datetime(
        string="Waiting Parts Since",
        copy=False,
        tracking=True,
    )
    is_overdue = fields.Boolean(
        string="Overdue",
        compute="_compute_is_overdue",
        search="_search_is_overdue",
    )

    work_order_count = fields.Integer(
        string="# Work Dispatches",
        compute="_compute_counts",
    )
    field_visit_count = fields.Integer(
        string="# Field Visits",
        compute="_compute_counts",
    )
    spare_request_count = fields.Integer(
        string="# Spare Requests",
        compute="_compute_counts",
    )
    expense_count = fields.Integer(
        string="# Field Expenses",
        compute="_compute_counts",
    )
    quality_inspection_count = fields.Integer(
        string="# Quality Inspections",
        compute="_compute_counts",
    )
    purchase_order_count = fields.Integer(
        string="# Purchase Orders",
        compute="_compute_counts",
    )
    invoice_count = fields.Integer(
        string="# Invoices",
        compute="_compute_counts",
    )
    warranty_count = fields.Integer(
        string="# Warranties",
        compute="_compute_counts",
    )
    notes = fields.Html(string="Notes & Observations")

    @api.depends(
        "agreement_id",
        "equipment_id",
        "equipment_id.warranty_ids.date_start",
        "equipment_id.warranty_ids.date_end",
        "equipment_id.warranty_ids.is_cancelled",
        "work_order_ids.task_id",
        "work_order_ids.task_id.is_warrantable",
        "work_order_ids.task_id.warranty_kind",
        "request_id.line_ids.task_id",
        "request_id.line_ids.task_id.is_warrantable",
        "request_id.line_ids.task_id.warranty_kind",
        "request_id.date_request",
        "date_end",
    )
    def _compute_billing_flags(self):
        for rec in self:
            rec.is_agreement_job = bool(rec.agreement_id)
            rec.is_warranty_job = rec._has_covered_warranty_work()

    def _warrantable_tasks(self):
        self.ensure_one()
        tasks = self.work_order_ids.task_id | self.request_id.line_ids.task_id
        return tasks.filtered(lambda t: t.is_warrantable and t.warranty_kind)

    def _warranty_as_of_date(self):
        self.ensure_one()
        if self.date_end:
            return fields.Date.to_date(self.date_end)
        if self.request_id.date_request:
            return self.request_id.date_request
        return fields.Date.context_today(self)

    def _has_covered_warranty_work(self):
        self.ensure_one()
        if not self.equipment_id:
            return False
        as_of = self._warranty_as_of_date()
        for task in self._warrantable_tasks():
            if self.equipment_id.find_active_warranty(
                task=task, date=as_of, exclude_job=self
            ):
                return True
        return False

    def _issue_service_warranties(self):
        """Grant Engine Overhaul / Gearbox warranties after a paid (non-comeback) close."""
        self.ensure_one()
        if not self.equipment_id:
            return self.env["workshop.warranty"]
        as_of = self._warranty_as_of_date()
        issued = self.env["workshop.warranty"]
        seen_kinds = set()
        for task in self._warrantable_tasks():
            kind = task.warranty_kind
            if kind in seen_kinds:
                continue
            seen_kinds.add(kind)
            if self.equipment_id.find_active_warranty(
                kind=kind, date=as_of, exclude_job=self
            ):
                continue
            rule = self.env["workshop.warranty.rule"].match_rule(
                kind,
                equipment=self.equipment_id,
                partner=self.partner_id,
                agreement=self.agreement_id,
                company=self.company_id,
            )
            if not rule or rule.duration_months <= 0:
                continue
            issued |= self.env["workshop.warranty"].create({
                "equipment_id": self.equipment_id.id,
                "job_order_id": self.id,
                "task_id": task.id,
                "warranty_kind": kind,
                "rule_id": rule.id,
                "agreement_id": self.agreement_id.id if self.agreement_id else False,
                "date_start": as_of,
                "duration_months": rule.duration_months,
                "company_id": self.company_id.id,
                "notes": _("Issued from Job Order %s using rule %s.") % (
                    self.name, rule.display_name,
                ),
            })
        if issued:
            self.message_post(body=_(
                "Service warranty issued: %s"
            ) % ", ".join(issued.mapped("name")))
        return issued

    def _workshop_posted_customer_invoices(self):
        self.ensure_one()
        return self.invoice_ids.filtered(
            lambda m: m.move_type == "out_invoice" and m.state == "posted"
        )

    def _workshop_unpaid_invoices(self):
        self.ensure_one()
        return self._workshop_posted_customer_invoices().filtered(
            lambda m: m.payment_state not in ("paid", "reversed")
        )

    def _workshop_outstanding_residual(self):
        self.ensure_one()
        return sum(self._workshop_unpaid_invoices().mapped("amount_residual"))

    def _workshop_has_uninvoiced_billable(self):
        self.ensure_one()
        so = self.sale_order_id
        if not so:
            return False
        rounding = so.currency_id.rounding if so.currency_id else 0.01
        for line in so.order_line.filtered(lambda l: not l.display_type):
            coverage = line.workshop_coverage or "billable"
            if coverage not in ("billable", "agreement"):
                continue
            if float_compare(line.discount, 100.0, precision_digits=2) >= 0:
                continue
            open_qty = line.product_uom_qty - line.qty_invoiced
            if float_compare(open_qty, 0.0, precision_rounding=rounding) > 0:
                return True
        return False

    def _workshop_financial_gate_decision(self):
        """Return (allowed, release_mode, block_reason) for vehicle handover.

        Dual rule (when company.workshop_financial_gate is enabled):
        1. Corporate / trusted / credit clients: allow release on credit and
           keep unpaid invoices as payment-pending.
        2. Standard / new clients: block until every invoice is fully paid.
        """
        self.ensure_one()
        unpaid = self._workshop_unpaid_invoices()
        uninvoiced = self._workshop_has_uninvoiced_billable()
        posted = self._workshop_posted_customer_invoices()
        nothing_due = not unpaid and not uninvoiced
        is_credit = self.partner_id.workshop_client_class == "credit"
        gate_on = self.company_id.workshop_financial_gate

        if nothing_due:
            mode = "paid" if posted else "no_charge"
            return True, mode, False

        if not gate_on or is_credit:
            return True, "credit", False

        if uninvoiced:
            reason = _(
                "Standard / new clients cannot take the vehicle until the "
                "invoice is created and fully marked as paid."
            )
        else:
            names = ", ".join(unpaid.mapped("name"))
            reason = _(
                "Standard / new clients cannot take the vehicle until "
                "invoice %s is fully marked as paid."
            ) % names
        return False, False, reason

    @api.depends(
        "vehicle_released",
        "vehicle_release_mode",
        "invoice_ids.state",
        "invoice_ids.move_type",
        "invoice_ids.payment_state",
        "invoice_ids.amount_residual",
        "sale_order_id.order_line.product_uom_qty",
        "sale_order_id.order_line.qty_invoiced",
        "sale_order_id.order_line.discount",
        "sale_order_id.order_line.workshop_coverage",
    )
    def _compute_release_payment(self):
        for rec in self:
            outstanding = rec._workshop_outstanding_residual()
            rec.outstanding_invoice_amount = outstanding
            unpaid = rec._workshop_unpaid_invoices()
            uninvoiced = rec._workshop_has_uninvoiced_billable()
            posted = rec._workshop_posted_customer_invoices()
            rec.invoices_fully_paid = bool(posted) and not unpaid and not uninvoiced
            rec.payment_pending = bool(
                rec.vehicle_released
                and rec.vehicle_release_mode == "credit"
                and (unpaid or uninvoiced or not float_is_zero(
                    outstanding, precision_rounding=rec.currency_id.rounding or 0.01
                ))
            )

    @api.depends(
        "vehicle_released",
        "state",
        "workshop_client_class",
        "company_id.workshop_financial_gate",
        "invoice_ids.state",
        "invoice_ids.move_type",
        "invoice_ids.payment_state",
        "invoice_ids.amount_residual",
        "sale_order_id.order_line.product_uom_qty",
        "sale_order_id.order_line.qty_invoiced",
        "sale_order_id.order_line.discount",
        "sale_order_id.order_line.workshop_coverage",
        "partner_id.workshop_client_class",
    )
    def _compute_release_gate_ui(self):
        for rec in self:
            if rec.vehicle_released or rec.state != "closed":
                rec.release_blocked = False
                rec.release_block_reason = False
                continue
            allowed, _mode, reason = rec._workshop_financial_gate_decision()
            rec.release_blocked = not allowed
            rec.release_block_reason = reason or False

    @api.depends("sale_order_id.amount_total")
    def _compute_estimated_cost(self):
        for rec in self:
            rec.estimated_cost = rec.sale_order_id.amount_total if rec.sale_order_id else 0.0

    @api.depends(
        "work_order_ids",
        "field_visit_ids",
        "spare_request_ids",
        "expense_ids",
        "quality_inspection_ids",
        "purchase_order_ids",
        "invoice_ids",
        "warranty_ids",
    )
    def _compute_counts(self):
        for rec in self:
            rec.work_order_count = len(rec.work_order_ids)
            rec.field_visit_count = len(rec.field_visit_ids)
            rec.spare_request_count = len(rec.spare_request_ids)
            rec.expense_count = len(rec.expense_ids)
            rec.quality_inspection_count = len(rec.quality_inspection_ids)
            rec.purchase_order_count = len(rec.purchase_order_ids)
            rec.invoice_count = len(rec.invoice_ids)
            rec.warranty_count = len(rec.warranty_ids)

    @api.depends(
        "field_visit_ids.travel_hours",
        "field_visit_ids.on_site_hours",
        "field_visit_ids.dispatch_to_arrival_hours",
        "field_visit_ids.state",
    )
    def _compute_field_service_kpis(self):
        for jo in self:
            visits = jo.field_visit_ids.filtered(lambda v: v.state != "cancelled")
            jo.total_travel_hours = sum(visits.mapped("travel_hours"))
            jo.total_on_site_hours = sum(visits.mapped("on_site_hours"))
            dispatch_vals = visits.filtered("dispatch_to_arrival_hours").mapped(
                "dispatch_to_arrival_hours"
            )
            jo.avg_dispatch_to_arrival_hours = (
                sum(dispatch_vals) / len(dispatch_vals) if dispatch_vals else 0.0
            )

    @api.onchange("request_id")
    def _onchange_request_id_service_location(self):
        if self.request_id:
            self.update(self.request_id._get_service_location_copy_vals())

    @api.depends(
        "work_order_ids.planned_hours",
        "work_order_ids.actual_hours",
        "work_order_ids.technician_id.hourly_cost",
        "work_order_ids.request_line_id",
        "work_order_ids.request_line_id.product_id",
        "work_order_ids.task_id",
        "request_id.line_ids.quantity",
        "request_id.line_ids.line_type",
        "request_id.line_ids.task_id",
        "request_id.line_ids.product_id",
        "partner_id.workshop_customer_type_id",
        "company_id.workshop_default_labor_rate",
        "company_id.workshop_labor_rate_rule_ids.labor_rate",
        "company_id.workshop_labor_rate_rule_ids.pricelist_item_id",
        "company_id.workshop_labor_rate_rule_ids.customer_type_id",
        "company_id.workshop_labor_rate_rule_ids.applied_on",
        "spare_request_ids.line_ids.cost_subtotal",
        "spare_request_ids.state",
        "request_id.line_ids.price_subtotal",
        "request_id.line_ids.line_type",
        "request_id.line_ids.is_warranty_covered",
        "field_visit_ids.travel_hours",
        "field_visit_ids.state",
        "purchase_order_ids.invoice_ids.amount_total",
        "purchase_order_ids.invoice_ids.state",
        "invoice_ids.amount_total",
        "invoice_ids.state",
        "work_order_ids.rework_cost",
        "work_order_ids.rework_who_pays",
        "expense_ids.amount",
        "expense_ids.state",
    )
    def _compute_hours_and_costs(self):
        for jo in self:
            jo.planned_hours = sum(jo.work_order_ids.mapped("planned_hours"))
            jo.actual_hours = sum(jo.work_order_ids.mapped("actual_hours"))

            # Labor: Standard Hours × technician hourly_cost (fallback customer-type / company rate)
            default_rate = jo._workshop_default_labor_rate()
            jo.labor_cost = jo._workshop_labor_cost_total()

            # Parts: issued / returned net cost from spare lines
            p_cost = 0.0
            for spr in jo.spare_request_ids.filtered(
                lambda s: s.state in ("store_approved", "issued", "return_flagged", "partially_returned")
            ):
                p_cost += sum(spr.line_ids.mapped("cost_subtotal"))
            jo.parts_cost = p_cost

            # External services: posted vendor bills tagged to this job (via PO or direct)
            ext_cost = 0.0
            vendor_bills = self.env["account.move"].search([
                ("job_order_id", "=", jo.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
            ])
            ext_cost += sum(vendor_bills.mapped("amount_total"))
            for po in jo.purchase_order_ids:
                for bill in po.invoice_ids.filtered(
                    lambda m: m.move_type == "in_invoice" and m.state == "posted" and not m.job_order_id
                ):
                    ext_cost += bill.amount_total
            jo.external_service_cost = ext_cost

            field_lines = jo.request_id.line_ids.filtered(
                lambda l: l.line_type in FIELD_CHARGE_LINE_TYPES and not l._is_service_warranty_covered()
            )
            visits = jo.field_visit_ids.filtered(lambda v: v.state != "cancelled")
            actual_travel_hours = sum(visits.mapped("travel_hours"))
            if actual_travel_hours:
                keep = field_lines.filtered(lambda l: l.line_type not in ("travel", "mileage"))
                jo.other_cost = sum(keep.mapped("price_subtotal")) + (
                    actual_travel_hours * default_rate
                )
            else:
                jo.other_cost = sum(field_lines.mapped("price_subtotal"))

            jo.expense_cost = sum(
                jo.expense_ids.filtered(lambda e: e.state == "approved").mapped("amount")
            )
            jo.total_cost = jo.labor_cost + p_cost + ext_cost + jo.other_cost + jo.expense_cost

            invoiced = 0.0
            for move in jo.invoice_ids.filtered(lambda m: m.state == "posted"):
                if move.move_type == "out_invoice":
                    invoiced += move.amount_total
                elif move.move_type == "out_refund":
                    invoiced -= move.amount_total
            jo.invoiced_amount = invoiced
            jo.job_profitability = invoiced - jo.total_cost
            jo.cost_of_quality = sum(
                wo.rework_cost
                for wo in jo.work_order_ids
                if wo.rework_who_pays != "customer"
            )

    @api.depends("expected_finish_date", "state")
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        open_states = ("completed", "closed")
        for rec in self:
            rec.is_overdue = bool(
                rec.expected_finish_date
                and rec.expected_finish_date < today
                and rec.state not in open_states
            )

    def _search_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        overdue_domain = [
            ("expected_finish_date", "!=", False),
            ("expected_finish_date", "<", today),
            ("state", "not in", ["completed", "closed"]),
        ]
        is_true = (operator == "=" and value) or (operator == "!=" and not value)
        if is_true:
            return overdue_domain
        return expression.NOT(overdue_domain)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.job.order"
                ) or "New"
            if vals.get("request_id") and "service_location_type" not in vals:
                request = self.env["workshop.request"].browse(vals["request_id"])
                vals.update(request._get_service_location_copy_vals())
        records = super().create(vals_list)
        records._sync_equipment_workshop_status()
        return records

    def write(self, vals):
        if vals.get("customer_signature") and not vals.get("signed_on"):
            vals = dict(vals, signed_on=fields.Datetime.now())
            if not vals.get("signed_by"):
                vals["signed_by"] = self.env.user.name
        entering_parts = self.browse()
        if vals.get("state") == "waiting_parts":
            entering_parts = self.filtered(lambda r: r.state != "waiting_parts")
        res = super().write(vals)
        if entering_parts and "waiting_parts_since" not in vals:
            super(WorkshopJobOrder, entering_parts).write({
                "waiting_parts_since": fields.Datetime.now(),
            })
        if any(key in vals for key in ("state", "vehicle_released", "vehicle_release_date", "request_id")):
            self._sync_equipment_workshop_status()
        return res

    def _sync_equipment_workshop_status(self):
        self.mapped("equipment_id")._sync_workshop_status_from_jobs()

    def _get_approval_amount(self):
        """Use SO estimated value when available; otherwise current total cost."""
        self.ensure_one()
        return self.estimated_cost or self.total_cost or 0.0

    def _match_approval_rule(self):
        self.ensure_one()
        amount = self._get_approval_amount()
        return self.env["workshop.approval.rule"].search([
            ("company_id", "=", self.company_id.id),
            ("active", "=", True),
            ("amount_threshold", "<=", amount),
        ], order="amount_threshold desc", limit=1)

    def action_in_progress(self):
        self.write({"state": "in_progress", "date_start": fields.Datetime.now()})

    def action_waiting_parts(self):
        self.write({"state": "waiting_parts"})

    def action_resume_from_parts(self):
        for rec in self:
            pending = rec.spare_request_ids.filtered(
                lambda s: s.state in ("submitted", "store_approved", "waiting_purchase", "return_flagged")
            )
            if pending:
                raise UserError(_(
                    "Cannot resume: spare requests still pending (%s)."
                ) % ", ".join(pending.mapped("name")))
            rec.write({"state": "in_progress"})

    def action_quality_inspection(self):
        self.write({"state": "quality_inspection"})

    def action_complete(self):
        self.write({"state": "completed", "date_end": fields.Datetime.now()})

    def action_close(self):
        """Close only when WOs verified, QI passed, signature on file, costs ready."""
        for rec in self:
            if not rec.work_order_ids:
                raise UserError(_("Cannot close Job Order without Work Dispatches."))

            unverified = rec.work_order_ids.filtered(lambda w: w.state != "verified")
            if unverified:
                raise UserError(_(
                    "Cannot close Job Order: All Work Dispatches must be 'Verified' first (Pending: %s)."
                ) % ", ".join(unverified.mapped("name")))

            if not rec.quality_inspection_ids:
                raise UserError(_(
                    "Cannot close Job Order: At least one Quality Inspection is required."
                ))
            failed_qi = rec.quality_inspection_ids.filtered(lambda q: q.state != "pass")
            if failed_qi:
                raise UserError(_("Cannot close Job Order: All Quality Inspections must be 'Passed'."))

            if not rec.customer_signature:
                raise UserError(_("Cannot close Job Order: Customer Acceptance Signature is required."))

            open_spares = rec.spare_request_ids.filtered(
                lambda s: s.state in ("draft", "submitted", "store_approved", "waiting_purchase", "return_flagged")
            )
            if open_spares:
                raise UserError(_(
                    "Cannot close Job Order: finalize spare requests first (%s)."
                ) % ", ".join(open_spares.mapped("name")))

            pending_exp = rec.expense_ids.filtered(lambda e: e.state == "submitted")
            if pending_exp:
                raise UserError(_(
                    "Cannot close Job Order: Foreman must validate field expenses first (%s)."
                ) % ", ".join(pending_exp.mapped("name")))

            rec._archive_completion_form()
            rec.write({"state": "closed"})
            rec._issue_service_warranties()

    def action_release_vehicle(self):
        """Hand the vehicle back under the two-way financial gate."""
        for rec in self:
            if rec.vehicle_released:
                raise UserError(_("This vehicle has already been released."))
            if rec.state != "closed":
                raise UserError(_(
                    "Close the Job Order before releasing the vehicle."
                ))
            allowed, mode, reason = rec._workshop_financial_gate_decision()
            if not allowed:
                raise UserError(reason)
            rec.write({
                "vehicle_released": True,
                "vehicle_release_date": fields.Datetime.now(),
                "vehicle_release_mode": mode,
                "released_by_id": self.env.user.id,
            })
            if mode == "credit":
                rec._schedule_credit_release_activity()
                rec.message_post(body=_(
                    "Vehicle released on credit. Outstanding amount: %(amount)s. "
                    "Payment remains pending."
                ) % {"amount": rec.outstanding_invoice_amount})
            elif mode == "paid":
                rec.message_post(body=_("Vehicle released after full invoice payment."))
            else:
                rec.message_post(body=_("Vehicle released (no charge outstanding)."))
        return True

    def _schedule_credit_release_activity(self):
        self.ensure_one()
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            summary=_("Collect payment — credit vehicle release %s") % self.name,
            note=_(
                "Vehicle/equipment %s was released to %s on credit. "
                "Track and collect the outstanding invoice."
            ) % (
                self.equipment_id.display_name or _("(no equipment)"),
                self.partner_id.display_name or _("(no customer)"),
            ),
            user_id=self.user_id.id or self.env.user.id,
        )

    def _archive_completion_form(self):
        """Generate completion PDF and archive as attachment on equipment + job."""
        import base64

        self.ensure_one()
        report = self.env.ref(
            "workshop_management.action_report_workshop_completion",
            raise_if_not_found=False,
        )
        if not report:
            return False
        pdf_content, _report_format = self.env["ir.actions.report"]._render_qweb_pdf(
            report.id, res_ids=self.ids
        )
        datas = base64.b64encode(pdf_content)
        attachment = self.env["ir.attachment"].create({
            "name": _("Job Completion Form - %s.pdf") % self.name,
            "type": "binary",
            "datas": datas,
            "res_model": "workshop.job.order",
            "res_id": self.id,
            "mimetype": "application/pdf",
        })
        if self.equipment_id:
            self.env["ir.attachment"].create({
                "name": attachment.name,
                "type": "binary",
                "datas": datas,
                "res_model": "workshop.equipment",
                "res_id": self.equipment_id.id,
                "mimetype": "application/pdf",
            })
        self.completion_document_id = attachment.id
        return attachment

    def action_create_invoice(self):
        """Invoice only billable / agreement SO lines (exclude warranty-covered)."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("No Sales Order linked to this Job Order."))

        so = self.sale_order_id
        self.expense_ids.filtered(lambda e: e.state == "approved")._ensure_sale_line()
        so.action_apply_workshop_billing_rules()

        billable_lines = so.order_line.filtered(
            lambda l: not l.display_type
            and l.workshop_coverage in ("billable", "agreement")
            and l.discount < 100.0
        )
        warranty_lines = so.order_line.filtered(
            lambda l: not l.display_type and l.workshop_coverage == "warranty"
        )

        if not billable_lines:
            raise UserError(_(
                "No billable lines to invoice. All Sales Order lines are warranty-covered "
                "(or have 100%% discount). Adjust Workshop Coverage on the Sales Order if needed."
            ))

        try:
            so._workshop_force_billable_lines_to_invoice()
            invoices = so.with_context(
                workshop_invoice_billable_only=True,
            )._create_invoices()
        except Exception as exc:
            raise UserError(_(
                "Could not create invoice from Sales Order %s: %s"
            ) % (so.name, exc)) from exc

        if not invoices:
            raise UserError(_("Nothing left to invoice on Sales Order %s.") % so.name)

        invoices.write({"job_order_id": self.id})
        note = _(
            "Invoice created for billable/agreement lines only. "
            "Excluded %(n)s warranty-covered line(s)."
        ) % {"n": len(warranty_lines)}
        self.message_post(body=note)
        invoices.message_post(body=note)

        return {
            "type": "ir.actions.act_window",
            "name": _("Invoices"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", invoices.ids)],
            "res_id": invoices[0].id if len(invoices) == 1 else False,
        }

    def action_open_assign_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Assign Technicians / Create Work Pack"),
            "res_model": "workshop.technician.assignment",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_job_order_id": self.id,
                "default_create_field_visit": self.is_field_job,
            },
        }

    def action_create_field_visit(self):
        self.ensure_one()
        if not self.is_field_job:
            raise UserError(_("Field visits are only available for Field Service job orders."))
        visit = self.env["workshop.field.visit"].create({
            "job_order_id": self.id,
            "technician_id": self.work_order_ids[:1].technician_id.id
            if self.work_order_ids
            else False,
            "state": "draft",
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Field Visit"),
            "res_model": "workshop.field.visit",
            "view_mode": "form",
            "res_id": visit.id,
        }

    def action_view_field_visits(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Field Visits"),
            "res_model": "workshop.field.visit",
            "view_mode": "list,form,calendar",
            "domain": [("job_order_id", "=", self.id)],
            "context": {"default_job_order_id": self.id},
        }

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Work Dispatches"),
            "res_model": "workshop.work.order",
            "view_mode": "kanban,calendar,list,form",
            "domain": [("job_order_id", "=", self.id)],
            "context": {"default_job_order_id": self.id},
        }

    def action_view_spare_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Spare Parts Requests"),
            "res_model": "workshop.spare.request",
            "view_mode": "list,form",
            "domain": [("job_order_id", "=", self.id)],
            "context": {"default_job_order_id": self.id},
        }

    def action_view_expenses(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Field Expenses"),
            "res_model": "workshop.expense",
            "view_mode": "list,form",
            "domain": [("job_order_id", "=", self.id)],
            "context": {"default_job_order_id": self.id},
        }

    def action_submit_expense(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Submit Field Expense"),
            "res_model": "workshop.expense",
            "view_mode": "form",
            "target": "current",
            "context": {"default_job_order_id": self.id},
        }

    def action_view_quality_inspections(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Quality Inspections"),
            "res_model": "workshop.quality.inspection",
            "view_mode": "list,form",
            "domain": [("job_order_id", "=", self.id)],
            "context": {"default_job_order_id": self.id},
        }

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Requisitions"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("job_order_id", "=", self.id)],
            "context": {"default_job_order_id": self.id},
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoices"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("job_order_id", "=", self.id)],
        }

    def action_view_warranties(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Service Warranties"),
            "res_model": "workshop.warranty",
            "view_mode": "list,form",
            "domain": [("job_order_id", "=", self.id)],
            "context": {
                "default_job_order_id": self.id,
                "default_equipment_id": self.equipment_id.id,
            },
        }
