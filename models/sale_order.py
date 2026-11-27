from odoo import api, fields, models, _


class SaleOrder(models.Model):
    """Extend Sale Order with Workshop Request integration and billing rules."""

    _inherit = "sale.order"

    workshop_request_id = fields.Many2one(
        comodel_name="workshop.request",
        string="Customer Request",
        ondelete="set null",
        copy=False,
    )
    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Job Order",
        compute="_compute_job_order_id",
        store=True,
    )
    job_order_ids = fields.One2many(
        comodel_name="workshop.job.order",
        inverse_name="sale_order_id",
        string="Job Orders",
    )
    is_warranty_order = fields.Boolean(
        string="Warranty Order",
        compute="_compute_workshop_billing_flags",
        store=True,
    )
    is_agreement_order = fields.Boolean(
        string="Agreement Order",
        compute="_compute_workshop_billing_flags",
        store=True,
    )

    @api.depends("job_order_ids")
    def _compute_job_order_id(self):
        for order in self:
            order.job_order_id = order.job_order_ids[:1]

    @api.depends(
        "workshop_request_id.warranty_status",
        "workshop_request_id.agreement_id",
        "job_order_ids.is_warranty_job",
        "job_order_ids.is_agreement_job",
    )
    def _compute_workshop_billing_flags(self):
        for order in self:
            req = order.workshop_request_id
            jo = order.job_order_ids[:1]
            under_warranty = False
            has_agreement = False
            if jo:
                under_warranty = jo.is_warranty_job
                has_agreement = jo.is_agreement_job
            elif req:
                under_warranty = bool(
                    req.line_ids.filtered(lambda l: l._is_service_warranty_covered())
                )
                has_agreement = bool(req.agreement_id)
            order.is_warranty_order = under_warranty
            order.is_agreement_order = has_agreement

    def action_confirm(self):
        """Auto-create Workshop Job Order upon SO confirmation when linked to a request."""
        for order in self.filtered("workshop_request_id"):
            order.action_apply_workshop_billing_rules()
        res = super().action_confirm()
        for order in self:
            if order.job_order_ids or not order.workshop_request_id:
                continue
            expected = False
            if hasattr(order, "commitment_date") and order.commitment_date:
                expected = fields.Date.to_date(order.commitment_date)
            elif hasattr(order, "expected_date") and order.expected_date:
                expected = fields.Date.to_date(order.expected_date)
            self.env["workshop.job.order"].create({
                "sale_order_id": order.id,
                "request_id": order.workshop_request_id.id,
                "expected_finish_date": expected,
                "company_id": order.company_id.id,
                "priority": order.workshop_request_id.priority or "1",
                "state": "draft",
                **order.workshop_request_id._get_service_location_copy_vals(),
            })
            order.workshop_request_id.write({"state": "confirmed"})
        return res

    def action_apply_workshop_billing_rules(self):
        """Mark SO lines as warranty/agreement covered and adjust prices/discounts."""
        for order in self:
            req = order.workshop_request_id
            under_warranty = bool(
                order.job_order_ids[:1].is_warranty_job
                or (req and req.line_ids.filtered(lambda l: l._is_service_warranty_covered()))
            )
            agreement = req.agreement_id if req else False
            if not agreement and order.job_order_ids:
                agreement = order.job_order_ids[:1].agreement_id
            if agreement:
                agreement._expire_if_needed()
                if agreement.state != "running":
                    agreement = False

            for line in order.order_line.filtered(lambda l: not l.display_type):
                # Respect explicit coverage already set from request mapping
                coverage = line.workshop_coverage or "billable"

                req_line = False
                if req:
                    req_line = req.line_ids.filtered(
                        lambda l: l.product_id == line.product_id
                    )[:1]
                if req_line and req_line._is_service_warranty_covered():
                    line.write({
                        "workshop_coverage": "warranty",
                        "discount": 100.0,
                    })
                    continue
                if coverage == "warranty":
                    # Brake / other jobs are never warranty-covered.
                    line.write({
                        "workshop_coverage": "billable",
                        "discount": 0.0,
                    })
                    coverage = "billable"

                if agreement:
                    billing = agreement.get_line_billing(
                        line.product_id,
                        req_line.line_type if req_line else False,
                        line.price_unit,
                    )
                    if billing:
                        vals = {
                            "workshop_coverage": billing["coverage"],
                            "discount": billing["discount"],
                        }
                        if billing.get("price_unit") is not None:
                            vals["price_unit"] = billing["price_unit"]
                        line.write(vals)
                        continue

                if coverage == "billable":
                    line.write({"discount": line.discount if line.discount < 100 else 0.0})

            order.message_post(body=_(
                "Workshop billing rules applied "
                "(Warranty: %(w)s, Agreement: %(a)s)."
            ) % {
                "w": _("Yes") if under_warranty else _("No"),
                "a": agreement.display_name if agreement else _("No"),
            })
        return True

    def _workshop_force_billable_lines_to_invoice(self):
        """Prepare billable workshop lines for invoicing on ordered quantities.

        Workshop jobs are invoiced at job close; lines must not depend on stock
        delivery when products use the 'Delivered Quantities' invoicing policy.
        """
        for order in self:
            for line in order.order_line.filtered(
                lambda l: not l.display_type
                and l.state == "sale"
                and l.workshop_coverage in ("billable", "agreement")
                and l.discount < 100.0
            ):
                line.qty_to_invoice = line.product_uom_qty - line.qty_invoiced

    def _get_invoiceable_lines(self, final=False):
        """Exclude warranty-covered (non-billable) lines when workshop context is set."""
        lines = super()._get_invoiceable_lines(final=final)
        if self.env.context.get("workshop_invoice_billable_only"):
            lines = lines.filtered(
                lambda l: l.workshop_coverage in ("billable", "agreement")
                and l.discount < 100.0
            )
        return lines

    def action_view_job_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Job Orders",
            "res_model": "workshop.job.order",
            "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {"default_sale_order_id": self.id},
        }


class SaleOrderLine(models.Model):
    """Workshop coverage flags for warranty / agreement billing."""

    _inherit = "sale.order.line"

    workshop_request_line_id = fields.Many2one(
        comodel_name="workshop.request.line",
        string="Customer Request Line",
        ondelete="set null",
        index=True,
        copy=False,
    )
    workshop_coverage = fields.Selection(
        selection=[
            ("billable", "Billable"),
            ("warranty", "Warranty Covered (Non-billable)"),
            ("agreement", "Agreement Price"),
        ],
        string="Workshop Coverage",
        default="billable",
        copy=True,
        help="Warranty-covered lines are not invoiced. Agreement lines use negotiated price.",
    )
    workshop_expense_id = fields.Many2one(
        comodel_name="workshop.expense",
        string="Workshop Field Expense",
        ondelete="set null",
        copy=False,
        index=True,
    )

    @api.onchange("workshop_coverage")
    def _onchange_workshop_coverage(self):
        if self.workshop_coverage == "warranty":
            self.discount = 100.0
        elif self.workshop_coverage in ("billable", "agreement") and self.discount == 100.0:
            self.discount = 0.0

    def write(self, vals):
        res = super().write(vals)
        if "workshop_coverage" in vals:
            for line in self:
                if line.workshop_coverage == "warranty" and line.discount < 100.0:
                    super(SaleOrderLine, line).write({"discount": 100.0})
                elif line.workshop_coverage in ("billable", "agreement") and line.discount == 100.0:
                    super(SaleOrderLine, line).write({"discount": 0.0})
        return res