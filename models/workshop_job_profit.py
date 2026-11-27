from collections import defaultdict

from odoo import api, fields, models

from .workshop_field_service_mixin import FIELD_CHARGE_LINE_TYPES

SPARE_COST_STATES = ("store_approved", "issued", "return_flagged", "partially_returned")
PROFIT_LINE_TYPES = [
    ("labor", "Labor / Task"),
    ("parts", "Spare Part"),
    ("external", "External Job / Outsourcing"),
    ("travel", "Travel / Field"),
    ("other", "Other Charges"),
    ("expense", "Field Expense"),
]


class WorkshopJobProfitLine(models.Model):
    """Per-task / per-spare / per-line profit row on a Job Order (persisted for UI)."""

    _name = "workshop.job.profit.line"
    _description = "Job Order Profit Breakdown Line"
    _order = "sequence, id"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Job Order",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    line_type = fields.Selection(
        selection=PROFIT_LINE_TYPES,
        string="Type",
        required=True,
    )
    name = fields.Char(string="Description", required=True)
    task_id = fields.Many2one(
        comodel_name="workshop.task.master",
        string="Job Description",
        ondelete="set null",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        ondelete="set null",
    )
    hours = fields.Float(string="Standard Hours")
    hourly_rate = fields.Float(string="Hourly Rate")
    quoted_amount = fields.Monetary(string="Quoted")
    cost_amount = fields.Monetary(string="Cost")
    expected_profit = fields.Monetary(string="Expected Profit")
    invoiced_amount = fields.Monetary(string="Invoiced")
    realized_profit = fields.Monetary(string="Realized Profit")
    currency_id = fields.Many2one(
        related="job_order_id.currency_id",
        readonly=True,
    )
    request_line_id = fields.Many2one(
        comodel_name="workshop.request.line",
        string="Estimate Line",
        ondelete="set null",
    )
    work_order_id = fields.Many2one(
        comodel_name="workshop.work.order",
        string="Work Dispatch",
        ondelete="set null",
    )


class WorkshopJobOrder(models.Model):
    _inherit = "workshop.job.order"

    # Persisted (not computed NewId records) — Odoo UI only shows real x2many ids.
    profit_line_ids = fields.One2many(
        comodel_name="workshop.job.profit.line",
        inverse_name="job_order_id",
        string="Profit Breakdown",
        copy=False,
        readonly=True,
    )
    quoted_amount = fields.Monetary(
        string="Quoted Amount",
        compute="_compute_quoted_profit",
        store=True,
        help="Quoted / expected revenue from estimate and sales order lines "
             "(warranty-covered lines are zero).",
    )
    expected_profit = fields.Monetary(
        string="Expected Profit",
        compute="_compute_quoted_profit",
        store=True,
        help="Quoted amount − total cost. Labor cost uses Standard Hours × rate.",
    )

    def _workshop_default_labor_rate(self, product=None):
        self.ensure_one()
        matched = self.env["workshop.labor.rate.rule"]._match_labor_rate(
            partner=self.partner_id,
            product=product,
            company=self.company_id,
        )
        if matched is not None:
            return matched
        return self.company_id.workshop_default_labor_rate or 50.0

    def _workshop_rate_for_technician(self, technician, product=None):
        self.ensure_one()
        if technician and technician.hourly_cost > 0:
            return technician.hourly_cost
        return self._workshop_default_labor_rate(product=product)

    def _workshop_quoted_for_request_line(self, line, sol_map):
        sol = sol_map.get(line.id)
        if sol:
            return sol.price_subtotal
        if line._is_service_warranty_covered():
            return 0.0
        return line.price_subtotal

    def _workshop_sale_line_map(self):
        self.ensure_one()
        lines = self.request_id.line_ids
        if not lines:
            return {}
        sols = self.env["sale.order.line"].search([
            ("workshop_request_line_id", "in", lines.ids),
        ])
        return {sol.workshop_request_line_id.id: sol for sol in sols}

    def _workshop_invoiced_maps(self):
        self.ensure_one()
        by_req = defaultdict(float)
        by_product = defaultdict(float)
        moves = self.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.move_type in ("out_invoice", "out_refund")
        )
        for move in moves:
            sign = -1.0 if move.move_type == "out_refund" else 1.0
            for aml in move.invoice_line_ids:
                if aml.display_type and aml.display_type != "product":
                    continue
                amount = sign * aml.price_subtotal
                req = aml.sale_line_ids.mapped("workshop_request_line_id")[:1]
                if req:
                    by_req[req.id] += amount
                elif aml.product_id:
                    by_product[aml.product_id.id] += amount
        return by_req, by_product

    def _workshop_match_labor_bundles(self):
        """Pair estimate labor lines with work dispatches (Standard Hours)."""
        self.ensure_one()
        remaining = self.work_order_ids
        bundles = []
        labor_lines = self.request_id.line_ids.filtered(lambda l: l.line_type == "labor")
        for line in labor_lines:
            matched = remaining.filtered(lambda w: w.request_line_id == line)
            if not matched and line.task_id:
                matched = remaining.filtered(
                    lambda w: not w.request_line_id and w.task_id == line.task_id
                )
            remaining -= matched
            bundles.append({"request_line": line, "work_orders": matched})
        for wo in remaining:
            bundles.append({"request_line": self.env["workshop.request.line"], "work_orders": wo})
        return bundles

    def _workshop_labor_bundle_product(self, line, work_orders):
        if line and line.product_id:
            return line.product_id
        if work_orders:
            return work_orders[:1].request_line_id.product_id
        return self.env["product.product"]

    def _workshop_labor_cost_total(self):
        self.ensure_one()
        total = 0.0
        for bundle in self._workshop_match_labor_bundles():
            wos = bundle["work_orders"]
            line = bundle["request_line"]
            product = self._workshop_labor_bundle_product(line, wos)
            if wos:
                for wo in wos:
                    wo_product = wo.request_line_id.product_id or product
                    total += wo.planned_hours * self._workshop_rate_for_technician(
                        wo.technician_id, product=wo_product
                    )
            elif line:
                total += (line.quantity or 0.0) * self._workshop_default_labor_rate(
                    product=product
                )
        return total

    def _prepare_profit_line_vals(self):
        self.ensure_one()
        sol_map = self._workshop_sale_line_map()
        invoiced_req, invoiced_product = self._workshop_invoiced_maps()
        used_invoiced_req = set()
        used_invoiced_product = set()
        vals_list = []
        sequence = 10

        def _take_invoiced(request_line=None, product=None):
            if request_line and request_line.id and request_line.id not in used_invoiced_req:
                used_invoiced_req.add(request_line.id)
                return invoiced_req.get(request_line.id, 0.0)
            if product and product.id and product.id not in used_invoiced_product:
                used_invoiced_product.add(product.id)
                return invoiced_product.get(product.id, 0.0)
            return 0.0

        def _append(vals):
            nonlocal sequence
            quoted = vals.get("quoted_amount") or 0.0
            cost = vals.get("cost_amount") or 0.0
            invoiced = vals.get("invoiced_amount") or 0.0
            vals.update({
                "sequence": sequence,
                "expected_profit": quoted - cost,
                "realized_profit": invoiced - cost if invoiced else 0.0,
            })
            vals_list.append(vals)
            sequence += 10

        for bundle in self._workshop_match_labor_bundles():
            line = bundle["request_line"]
            wos = bundle["work_orders"]
            wo = wos[:1]
            product = self._workshop_labor_bundle_product(line, wos)
            if wos:
                hours = sum(wos.mapped("planned_hours"))
                rate = self._workshop_rate_for_technician(
                    wo.technician_id, product=wo.request_line_id.product_id or product
                )
                cost = sum(
                    w.planned_hours * self._workshop_rate_for_technician(
                        w.technician_id,
                        product=w.request_line_id.product_id or product,
                    )
                    for w in wos
                )
            else:
                hours = line.quantity or 0.0
                rate = self._workshop_default_labor_rate(product=product)
                cost = hours * rate
            quoted = self._workshop_quoted_for_request_line(line, sol_map) if line else 0.0
            name = (
                (line.task_id.name if line and line.task_id else False)
                or (line.name if line else False)
                or (wo.task_id.name if wo and wo.task_id else False)
                or (wo.display_name if wo else "Labor")
            )
            _append({
                "line_type": "labor",
                "name": name,
                "task_id": (line.task_id.id if line and line.task_id else False)
                or (wo.task_id.id if wo else False),
                "product_id": line.product_id.id if line and line.product_id else False,
                "hours": hours,
                "hourly_rate": rate,
                "quoted_amount": quoted,
                "cost_amount": cost,
                "invoiced_amount": _take_invoiced(request_line=line, product=line.product_id if line else False),
                "request_line_id": line.id if line else False,
                "work_order_id": wo.id if wo else False,
            })

        spare_records = []
        qty_by_product = defaultdict(float)
        for spr in self.spare_request_ids.filtered(lambda s: s.state in SPARE_COST_STATES):
            for spare in spr.line_ids:
                net_qty = max(spare.qty_issued - spare.qty_returned, 0.0)
                if spr.state in ("store_approved",):
                    display_qty = spare.qty_requested
                else:
                    display_qty = net_qty or spare.qty_requested
                pid = spare.product_id.id if spare.product_id else False
                qty_by_product[pid] += display_qty or 0.0
                spare_records.append((spare, spr, display_qty, pid))

        est_quoted_by_product = defaultdict(float)
        est_line_by_product = {}
        for line in self.request_id.line_ids.filtered(lambda l: l.line_type == "parts"):
            pid = line.product_id.id if line.product_id else False
            est_quoted_by_product[pid] += self._workshop_quoted_for_request_line(line, sol_map)
            est_line_by_product.setdefault(pid, line)

        spare_products = self.env["product.product"]
        for spare, spr, display_qty, pid in spare_records:
            estimate = est_line_by_product.get(pid)
            total_qty = qty_by_product.get(pid) or 0.0
            if estimate and total_qty:
                quoted = est_quoted_by_product[pid] * ((display_qty or 0.0) / total_qty)
            elif estimate:
                quoted = 0.0
            else:
                quoted = (spare.unit_price or 0.0) * (display_qty or 0.0)
            if estimate:
                invoiced = _take_invoiced(request_line=estimate, product=spare.product_id)
            else:
                invoiced = _take_invoiced(product=spare.product_id)
            if spare.product_id:
                spare_products |= spare.product_id
            _append({
                "line_type": "parts",
                "name": spare.product_id.display_name if spare.product_id else spr.display_name,
                "product_id": pid,
                "quoted_amount": quoted,
                "cost_amount": spare.cost_subtotal,
                "invoiced_amount": invoiced,
                "request_line_id": estimate.id if estimate else False,
            })

        for line in self.request_id.line_ids.filtered(lambda l: l.line_type == "parts"):
            if line.product_id and line.product_id in spare_products:
                continue
            _append({
                "line_type": "parts",
                "name": line.name or (line.product_id.display_name if line.product_id else "Spare Part"),
                "product_id": line.product_id.id if line.product_id else False,
                "quoted_amount": self._workshop_quoted_for_request_line(line, sol_map),
                "cost_amount": 0.0,
                "invoiced_amount": _take_invoiced(request_line=line, product=line.product_id),
                "request_line_id": line.id,
            })

        ext_lines = self.request_id.line_ids.filtered(lambda l: l.line_type == "external")
        ext_cost = self.external_service_cost
        if ext_lines:
            quoted_total = sum(
                self._workshop_quoted_for_request_line(line, sol_map) for line in ext_lines
            )
            remaining_cost = ext_cost
            for index, line in enumerate(ext_lines):
                quoted = self._workshop_quoted_for_request_line(line, sol_map)
                if index == len(ext_lines) - 1:
                    share = remaining_cost
                elif quoted_total:
                    share = ext_cost * (quoted / quoted_total)
                    remaining_cost -= share
                else:
                    share = ext_cost / len(ext_lines)
                    remaining_cost -= share
                _append({
                    "line_type": "external",
                    "name": line.name or (
                        line.product_id.display_name if line.product_id else "External Job"
                    ),
                    "product_id": line.product_id.id if line.product_id else False,
                    "quoted_amount": quoted,
                    "cost_amount": share,
                    "invoiced_amount": _take_invoiced(request_line=line, product=line.product_id),
                    "request_line_id": line.id,
                })
        elif ext_cost:
            _append({
                "line_type": "external",
                "name": "Vendor Bills / Outsourcing",
                "quoted_amount": 0.0,
                "cost_amount": ext_cost,
                "invoiced_amount": 0.0,
            })

        field_lines = self.request_id.line_ids.filtered(
            lambda l: l.line_type in FIELD_CHARGE_LINE_TYPES
        )
        visits = self.field_visit_ids.filtered(lambda v: v.state != "cancelled")
        actual_travel_hours = sum(visits.mapped("travel_hours"))
        travel_cost_left = actual_travel_hours * default_rate if actual_travel_hours else None
        for line in field_lines:
            quoted = self._workshop_quoted_for_request_line(line, sol_map)
            skip_cost = line._is_service_warranty_covered()
            if skip_cost:
                cost = 0.0
            elif line.line_type in ("travel", "mileage") and travel_cost_left is not None:
                cost = travel_cost_left
                travel_cost_left = 0.0
            else:
                cost = line.price_subtotal
            line_type = "travel" if line.line_type in ("travel", "mileage") else "other"
            _append({
                "line_type": line_type,
                "name": line.name or (
                    line.product_id.display_name if line.product_id else line.line_type
                ),
                "product_id": line.product_id.id if line.product_id else False,
                "hours": actual_travel_hours if (
                    line.line_type in ("travel", "mileage") and actual_travel_hours
                ) else 0.0,
                "hourly_rate": default_rate if (
                    line.line_type in ("travel", "mileage") and actual_travel_hours
                ) else 0.0,
                "quoted_amount": quoted,
                "cost_amount": cost,
                "invoiced_amount": _take_invoiced(request_line=line, product=line.product_id),
                "request_line_id": line.id,
            })

        for exp in self.expense_ids.filtered(lambda e: e.state == "approved"):
            _append({
                "line_type": "expense",
                "name": exp.description or exp.name,
                "quoted_amount": exp.billable_amount,
                "cost_amount": exp.amount,
                "invoiced_amount": (
                    exp.sale_line_id.qty_invoiced * exp.sale_line_id.price_unit
                    if exp.sale_line_id else 0.0
                ),
            })

        return vals_list

    def _sync_profit_breakdown(self):
        """Rebuild stored profit lines so the form list can display them."""
        if self.env.context.get("workshop_skip_profit_sync"):
            return
        ProfitLine = self.env["workshop.job.profit.line"].sudo()
        for jo in self:
            if not jo.id or not isinstance(jo.id, int):
                continue
            ProfitLine.search([("job_order_id", "=", jo.id)]).unlink()
            create_vals = []
            for vals in jo._prepare_profit_line_vals():
                create_vals.append({
                    **vals,
                    "job_order_id": jo.id,
                })
            if create_vals:
                ProfitLine.create(create_vals)

    @api.model
    def _workshop_precommit_sync_profit(self):
        data = self.env.cr.precommit.data.pop("workshop_sync_profit_job_ids", None)
        if not data:
            return
        jobs = self.browse(list(data)).exists()
        if jobs:
            jobs._sync_profit_breakdown()

    def web_read(self, specification):
        # Refresh breakdown whenever the form asks for profit lines / totals.
        if specification and any(
            key in specification
            for key in ("profit_line_ids", "quoted_amount", "expected_profit")
        ):
            self._sync_profit_breakdown()
        return super().web_read(specification)

    @api.depends(
        "request_id.line_ids.price_subtotal",
        "request_id.line_ids.line_type",
        "request_id.line_ids.quantity",
        "request_id.line_ids.is_warranty_covered",
        "request_id.line_ids.task_id",
        "request_id.line_ids.product_id",
        "request_id.line_ids.name",
        "request_id.warranty_status",
        "work_order_ids.planned_hours",
        "work_order_ids.technician_id.hourly_cost",
        "work_order_ids.request_line_id",
        "work_order_ids.request_line_id.product_id",
        "work_order_ids.task_id",
        "partner_id.workshop_customer_type_id",
        "company_id.workshop_default_labor_rate",
        "company_id.workshop_labor_rate_rule_ids.labor_rate",
        "company_id.workshop_labor_rate_rule_ids.pricelist_item_id",
        "company_id.workshop_labor_rate_rule_ids.customer_type_id",
        "company_id.workshop_labor_rate_rule_ids.applied_on",
        "spare_request_ids.line_ids.cost_subtotal",
        "spare_request_ids.line_ids.unit_price",
        "spare_request_ids.line_ids.qty_issued",
        "spare_request_ids.line_ids.qty_returned",
        "spare_request_ids.line_ids.product_id",
        "spare_request_ids.state",
        "external_service_cost",
        "total_cost",
        "invoice_ids.state",
        "invoice_ids.invoice_line_ids.price_subtotal",
        "invoice_ids.invoice_line_ids.sale_line_ids.workshop_request_line_id",
        "invoice_ids.move_type",
        "sale_order_id.order_line.price_subtotal",
        "sale_order_id.order_line.workshop_request_line_id",
        "field_visit_ids.travel_hours",
        "field_visit_ids.state",
        "expense_ids.amount",
        "expense_ids.billable_amount",
        "expense_ids.state",
        "currency_id",
    )
    def _compute_quoted_profit(self):
        for jo in self:
            vals_list = jo._prepare_profit_line_vals()
            quoted = sum(v.get("quoted_amount") or 0.0 for v in vals_list)
            jo.quoted_amount = quoted
            jo.expected_profit = quoted - (jo.total_cost or 0.0)
            if jo.id and isinstance(jo.id, int) and not self.env.context.get("workshop_skip_profit_sync"):
                data = self.env.cr.precommit.data.setdefault("workshop_sync_profit_job_ids", set())
                if not data:
                    self.env.cr.precommit.add(self._workshop_precommit_sync_profit)
                data.add(jo.id)
