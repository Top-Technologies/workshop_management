from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .workshop_field_service_mixin import FIELD_CHARGE_LINE_TYPES


class WorkshopRequest(models.Model):
    """Initial customer request + inspection findings; source of quotation."""

    _name = "workshop.request"
    _description = "Customer Request"
    _inherit = ["mail.thread", "mail.activity.mixin", "workshop.field.service.location.mixin"]
    _order = "date_request desc, id desc"

    name = fields.Char(
        string="Request No.",
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
    partner_tax_id = fields.Char(
        string="Tax ID",
        related="partner_id.vat",
        readonly=True,
    )
    equipment_id = fields.Many2one(
        comodel_name="workshop.equipment",
        string="Equipment/Vehicle",
        tracking=True,
        index=True,
        ondelete="restrict",
        domain="[('company_id', 'in', [company_id, False])]",
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
        ondelete="set null",
        tracking=True,
        domain="[('partner_id', '=', partner_id), ('state', '=', 'running'), ('company_id', 'in', [company_id, False])]",
    )
    agreement_remaining_visits = fields.Integer(
        related="agreement_id.remaining_visits",
        string="Remaining Visits",
    )
    agreement_remaining_hours = fields.Float(
        related="agreement_id.remaining_hours",
        string="Remaining Hours",
    )
    date_request = fields.Date(
        string="Request Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    complaint = fields.Text(string="Customer Complaint")
    inspection_notes = fields.Text(string="Inspection Notes")
    inspection_photo_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="workshop_request_attachment_rel",
        column1="request_id",
        column2="attachment_id",
        string="Inspection Photos / Documents",
    )
    line_ids = fields.One2many(
        comodel_name="workshop.request.line",
        inverse_name="request_id",
        string="Quotation Estimate Lines",
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order / Quotation",
        copy=False,
        tracking=True,
        ondelete="set null",
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
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("quoted", "Quoted"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
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
    job_order_ids = fields.One2many(
        comodel_name="workshop.job.order",
        inverse_name="request_id",
        string="Job Orders",
    )
    job_order_count = fields.Integer(
        string="# Job Orders",
        compute="_compute_job_order_count",
    )

    @api.depends("job_order_ids")
    def _compute_job_order_count(self):
        for rec in self:
            rec.job_order_count = len(rec.job_order_ids)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        """Clear equipment that does not belong to the selected customer."""
        if (
            self.equipment_id
            and self.partner_id
            and self.equipment_id.partner_id != self.partner_id
        ):
            self.equipment_id = False
        self._suggest_service_agreement()

    @api.onchange("equipment_id")
    def _onchange_equipment_id(self):
        """Selecting equipment fills the customer automatically."""
        if self.equipment_id:
            self.partner_id = self.equipment_id.partner_id
        self._suggest_service_agreement()

    @api.onchange("date_request")
    def _onchange_date_request_agreement(self):
        self._suggest_service_agreement()

    def _suggest_service_agreement(self):
        if not self.partner_id:
            self.agreement_id = False
            return
        current = self.agreement_id
        if current and current.is_applicable_for(
            self.partner_id, self.equipment_id, self.date_request
        ):
            return
        self.agreement_id = self.env["workshop.agreement"]._find_applicable(
            self.partner_id, self.equipment_id, self.date_request
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.request"
                ) or "New"
        return super().create(vals_list)

    def action_create_agreement(self):
        """Create a Service Agreement prefilled from this Customer Request."""
        self.ensure_one()
        if self.agreement_id:
            raise UserError(_("A Service Agreement is already linked to this Customer Request."))
        if not self.partner_id:
            raise UserError(_("Set a Customer before creating a Service Agreement."))
        if not self.line_ids:
            raise UserError(_("Add estimate lines before creating a Service Agreement."))

        line_cmds = []
        for line in self.line_ids:
            if line._is_service_warranty_covered():
                coverage = "included"
            elif line.price_unit:
                coverage = "fixed_price"
            else:
                coverage = "extra"
            line_cmds.append((0, 0, {
                "product_id": line.product_id.id if line.product_id else False,
                "task_id": line.task_id.id if line.task_id else False,
                "name": line.name
                or (line.task_id.name if line.task_id else False)
                or (line.product_id.display_name if line.product_id else False),
                "line_type": line.line_type,
                "coverage_type": coverage,
                "price_unit": line.price_unit,
            }))

        agreement_vals = {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "date_start": self.date_request or fields.Date.context_today(self),
            "notes": _("Created from Customer Request %s") % self.name,
            "line_ids": line_cmds,
        }
        if self.equipment_id:
            agreement_vals["equipment_ids"] = [(6, 0, [self.equipment_id.id])]

        agreement = self.env["workshop.agreement"].create(agreement_vals)
        self.agreement_id = agreement.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "workshop.agreement",
            "res_id": agreement.id,
            "view_mode": "form",
        }

    def action_create_quotation(self):
        """Create a sale.order quotation with estimate lines from this request."""
        self.ensure_one()
        if self.sale_order_id:
            raise UserError(_("Quotation already exists for this Customer Request."))

        so_vals = {
            "partner_id": self.partner_id.id,
            "workshop_request_id": self.id,
            "origin": self.name,
            "company_id": self.company_id.id,
        }
        so = self.env["sale.order"].create(so_vals)

        agreement = self.agreement_id
        if agreement:
            agreement._expire_if_needed()
            if agreement.state != "running":
                agreement = False

        order_lines = []
        for line in self.line_ids:
            if not line.product_id:
                continue
            price_unit = line.price_unit
            discount = 0.0
            coverage = "billable"

            if line._is_service_warranty_covered():
                coverage = "warranty"
                discount = 100.0
            elif agreement:
                billing = agreement.get_line_billing(
                    line.product_id, line.line_type, line.price_unit
                )
                if billing:
                    coverage = billing["coverage"]
                    price_unit = billing["price_unit"]
                    discount = billing["discount"]

            order_lines.append((0, 0, {
                "product_id": line.product_id.id,
                "name": line.name or line.product_id.display_name,
                "product_uom_qty": line.quantity,
                "price_unit": price_unit,
                "discount": discount,
                "product_uom_id": line.product_id.uom_id.id,
                "workshop_coverage": coverage,
                "workshop_request_line_id": line.id,
            }))
        if order_lines:
            so.write({"order_line": order_lines})
        so.action_apply_workshop_billing_rules()

        self.write({
            "sale_order_id": so.id,
            "state": "quoted",
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": so.id,
            "view_mode": "form",
        }

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_draft(self):
        self.write({"state": "draft"})

    def action_view_job_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Job Orders"),
            "res_model": "workshop.job.order",
            "view_mode": "list,form",
            "domain": [("request_id", "=", self.id)],
            "context": {"default_request_id": self.id},
        }


class WorkshopRequestLine(models.Model):
    """Estimate lines for labor, parts, and other charges on a Customer Request."""

    _name = "workshop.request.line"
    _description = "Customer Request Estimate Line"

    request_id = fields.Many2one(
        comodel_name="workshop.request",
        string="Customer Request",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product / Service",
        required=True,
    )
    name = fields.Char(string="Job Description")
    line_type = fields.Selection(
        selection=[
            ("labor", "Labor"),
            ("parts", "Spare Parts"),
            ("external", "External Job / Outsourcing"),
            ("travel", "Travel / Transport"),
            ("mileage", "Mileage"),
            ("per_diem", "Per Diem"),
            ("fuel", "Fuel"),
            ("other", "Other Charges"),
        ],
        string="Service Type",
        default="labor",
        required=True,
    )
    is_warranty_covered = fields.Boolean(
        string="Warranty Covered",
        default=False,
        help="Covered only when this line is Engine Overhaul or Gearbox and an "
             "active issued warranty of that kind exists on the vehicle.",
    )
    task_id = fields.Many2one(
        comodel_name="workshop.task.master",
        string="Job Description",
    )
    quantity = fields.Float(string="Quantity / Hours", default=1.0, required=True)
    price_unit = fields.Float(string="Unit Price")
    currency_id = fields.Many2one(
        related="request_id.company_id.currency_id",
        readonly=True,
    )
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,
    )

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    def _is_service_warranty_covered(self):
        """True only for Engine Overhaul / Gearbox lines with an active issued warranty."""
        self.ensure_one()
        task = self.task_id
        if not task or not task.is_warrantable or not task.warranty_kind:
            return False
        request = self.request_id
        equipment = request.equipment_id if request else False
        if not equipment:
            return False
        return bool(equipment.find_active_warranty(
            task=task,
            date=request.date_request or fields.Date.context_today(self),
        ))

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.display_name
            self.price_unit = self.product_id.list_price

    @api.onchange("task_id")
    def _onchange_task_id(self):
        if self.task_id:
            self.quantity = self.task_id.standard_hours
            self.name = self.task_id.name
            # Do not overwrite Service Type — user may have set Parts/External/etc. first.
        self._onchange_line_type_warranty_default()

    @api.onchange("line_type", "task_id", "request_id", "request_id.equipment_id")
    def _onchange_line_type_warranty_default(self):
        """Cover labor/parts only when a matching Engine Overhaul / Gearbox warranty is active."""
        if self.line_type in ("external", "other", "travel", "mileage", "per_diem", "fuel"):
            self.is_warranty_covered = False
            return
        self.is_warranty_covered = bool(
            self.request_id and self.task_id and self._is_service_warranty_covered()
        )
