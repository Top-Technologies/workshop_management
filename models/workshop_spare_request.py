from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


SPARE_RETURN_REASONS = [
    ("unused", "Unused / leftover"),
    ("wrong_fit", "Does not fit"),
    ("defective", "Defective / damaged"),
]
SPARE_RETURN_DISPOSITIONS = [
    ("restock", "Restock to inventory"),
    ("scrap", "Scrap (do not restock)"),
    ("vendor_return", "Return to vendor"),
]


class WorkshopSpareRequest(models.Model):
    """Spare parts request for workshop execution."""

    _name = "workshop.spare.request"
    _description = "Workshop Spare Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="Request No.",
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
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    work_order_id = fields.Many2one(
        comodel_name="workshop.work.order",
        string="Work Dispatch",
        domain="[('job_order_id', '=', job_order_id)]",
        ondelete="set null",
        index=True,
    )
    line_ids = fields.One2many(
        comodel_name="workshop.spare.request.line",
        inverse_name="spare_request_id",
        string="Requested Spare Parts",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("waiting_purchase", "Waiting Purchase"),
            ("store_approved", "Store Approved"),
            ("issued", "Issued"),
            ("return_flagged", "Return Flagged"),
            ("partially_returned", "Partially Returned"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Inventory Issue / Picking",
        readonly=True,
        copy=False,
    )
    return_picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Return Picking",
        readonly=True,
        copy=False,
    )
    purchase_order_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Purchase Requisition / RFQ",
        readonly=True,
        copy=False,
    )
    has_shortage = fields.Boolean(
        string="Has Stock Shortage",
        compute="_compute_has_shortage",
        store=True,
    )
    requested_by = fields.Many2one(
        comodel_name="res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    notes = fields.Text(string="Notes")
    origin_request_id = fields.Many2one(
        comodel_name="workshop.spare.request",
        string="Replaces Request",
        ondelete="set null",
        copy=False,
        help="Set when this request was created to replace non-fitting or defective parts.",
    )
    replacement_request_ids = fields.One2many(
        comodel_name="workshop.spare.request",
        inverse_name="origin_request_id",
        string="Replacement Requests",
    )
    return_ids = fields.One2many(
        comodel_name="workshop.spare.return",
        inverse_name="spare_request_id",
        string="Reverse Logistics",
        copy=False,
    )
    flagged_return_count = fields.Integer(
        compute="_compute_flagged_return_count",
    )

    @api.depends("line_ids.qty_available", "line_ids.qty_requested")
    def _compute_has_shortage(self):
        for rec in self:
            rec.has_shortage = any(
                float_compare(line.qty_available, line.qty_requested, precision_digits=2) < 0
                for line in rec.line_ids
            )

    @api.depends("return_ids.state")
    def _compute_flagged_return_count(self):
        for rec in self:
            rec.flagged_return_count = len(rec.return_ids.filtered(lambda r: r.state == "flagged"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.spare.part.request"
                ) or "New"
        return super().create(vals_list)

    def _workshop_store_notify_users(self):
        """Users who should be alerted when a spare request is submitted."""
        store_group = self.env.ref(
            "workshop_management.group_workshop_store", raise_if_not_found=False
        )
        users = store_group.all_user_ids if store_group else self.env["res.users"]
        if not users:
            stock_group = self.env.ref("stock.group_stock_user", raise_if_not_found=False)
            if stock_group:
                users = stock_group.all_user_ids
        return users.filtered(lambda u: u.active and not u.share)

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Please add at least one spare part line."))
            rec.write({"state": "submitted"})
            # Put Job Order into Waiting Parts
            if rec.job_order_id.state in ("approved", "assigned", "in_progress"):
                rec.job_order_id.write({"state": "waiting_parts"})

            notify_users = rec._workshop_store_notify_users()[:20]
            job_name = rec.job_order_id.display_name
            summary = _("Approve spare request %s") % rec.name
            body = _(
                "Spare part request <b>%(req)s</b> was submitted for Job Order "
                "<b>%(job)s</b>. Please review and approve in Store."
            ) % {"req": rec.name, "job": job_name}

            partner_ids = []
            for user in notify_users:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary=summary,
                    note=body,
                )
                if user.partner_id:
                    partner_ids.append(user.partner_id.id)

            if partner_ids:
                rec.message_post(
                    body=body,
                    partner_ids=partner_ids,
                    subtype_xmlid="mail.mt_comment",
                    message_type="notification",
                )
            else:
                rec.message_post(
                    body=_(
                        "Spare part request submitted, but no Store / Inventory users "
                        "are configured to receive the alert. Assign users to the "
                        "Workshop Store / Inventory group."
                    ),
                )

    def action_store_approve(self):
        """Store approves: create picking, or purchase RFQ if shortage."""
        for rec in self:
            rec.line_ids._refresh_availability()
            if rec.has_shortage:
                po = rec._create_purchase_requisition()
                rec.write({
                    "state": "waiting_purchase",
                    "purchase_order_id": po.id if po else False,
                })
                rec.message_post(body=_(
                    "Stock shortage detected. Purchase RFQ %s created."
                ) % (po.name if po else _("(failed)")))
            else:
                rec.write({"state": "store_approved"})
                rec._create_stock_picking()
            rec.activity_ids.action_feedback(feedback=_("Processed by store"))

    def action_confirm_after_purchase(self):
        """After PO receipt, approve and create issue picking for available qty."""
        for rec in self:
            if rec.state != "waiting_purchase":
                continue
            rec.line_ids._refresh_availability()
            still_short = rec.line_ids.filtered(
                lambda l: float_compare(l.qty_available, l.qty_requested, precision_digits=2) < 0
            )
            if still_short:
                raise UserError(_(
                    "Stock still insufficient for: %s"
                ) % ", ".join(still_short.mapped("product_id.display_name")))
            rec.write({"state": "store_approved"})
            rec._create_stock_picking()

    def action_issue(self):
        """Validate picking and mark parts as issued."""
        for rec in self:
            if not rec.picking_id:
                raise UserError(_("No stock picking linked to this request."))
            rec._workshop_validate_picking(rec.picking_id)
            for line in rec.line_ids:
                line.qty_issued = line.qty_requested
            rec.write({"state": "issued"})
            rec._maybe_resume_job_order()

    def action_open_flag_return_wizard(self):
        """Technician flags unused, non-fitting, or defective issued parts."""
        self.ensure_one()
        if self.state not in ("issued", "return_flagged", "partially_returned"):
            raise UserError(_("Parts must be issued before they can be flagged for return."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Flag Parts for Return"),
            "res_model": "workshop.spare.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_spare_request_id": self.id},
        }

    def action_flag_returns(self, line_vals_list):
        """Create flagged reverse-logistics lines from technician input."""
        self.ensure_one()
        created = self.env["workshop.spare.return"]
        for vals in line_vals_list:
            qty = vals.get("qty") or 0.0
            spare_line = self.env["workshop.spare.request.line"].browse(vals["spare_line_id"])
            if spare_line.spare_request_id != self:
                raise UserError(_("Return line does not belong to this spare request."))
            remaining = spare_line._qty_remaining_on_job()
            if float_compare(qty, 0.0, precision_digits=2) <= 0:
                continue
            if float_compare(qty, remaining, precision_digits=2) > 0:
                raise UserError(_(
                    "Cannot flag %.2f of %s: only %.2f remain on the job."
                ) % (qty, spare_line.product_id.display_name, remaining))
            reason = vals.get("reason") or "unused"
            created |= self.env["workshop.spare.return"].create({
                "spare_request_id": self.id,
                "spare_line_id": spare_line.id,
                "qty": qty,
                "reason": reason,
                "disposition": vals.get("disposition") or self.env["workshop.spare.return"]._default_disposition(reason),
                "request_replacement": vals.get("request_replacement", reason in ("wrong_fit", "defective")),
                "notes": vals.get("notes") or False,
                "flagged_by_id": self.env.user.id,
            })
        if not created:
            raise UserError(_("Enter a quantity to return on at least one line."))
        self.write({"state": "return_flagged"})
        self._notify_store_returns(created)
        return created

    def action_return_unused(self):
        """Store shortcut: restock leftover issued qty as unused."""
        for rec in self:
            if rec.state not in ("issued", "return_flagged", "partially_returned"):
                raise UserError(_("Returns are only allowed after parts have been issued."))
            vals_list = []
            for line in rec.line_ids:
                remaining = line._qty_remaining_on_job()
                if float_compare(remaining, 0.0, precision_digits=2) <= 0:
                    continue
                vals_list.append({
                    "spare_line_id": line.id,
                    "qty": remaining,
                    "reason": "unused",
                    "disposition": "restock",
                    "request_replacement": False,
                    "notes": _("Unused leftover returned by store."),
                })
            if not vals_list:
                raise UserError(_("No remaining quantity available to return."))
            rec.action_flag_returns(vals_list)
            rec.action_process_flagged_returns()

    def action_process_flagged_returns(self):
        """Store processes flagged lines: restock, scrap, vendor return, replacement."""
        for rec in self:
            pending = rec.return_ids.filtered(lambda r: r.state == "flagged")
            if not pending:
                raise UserError(_("No flagged returns waiting for store processing."))
            rec._process_returns(pending.filtered(lambda r: r.disposition == "restock"), "restock")
            rec._process_returns(pending.filtered(lambda r: r.disposition == "scrap"), "scrap")
            rec._process_returns(pending.filtered(lambda r: r.disposition == "vendor_return"), "vendor_return")
            rec._create_replacement_request(pending.filtered(
                lambda r: r.state == "done" and r.request_replacement
            ))
            rec.activity_ids.filtered(
                lambda a: a.summary and "return" in (a.summary or "").lower()
            ).action_feedback(feedback=_("Returns processed"))
            rec._sync_state_after_returns()

    def _process_returns(self, returns, disposition):
        self.ensure_one()
        if not returns:
            return self.env["stock.picking"]
        dest = self._disposition_location(disposition)
        picking = self.env["stock.picking"]
        if dest and self.picking_id:
            picking = self._create_disposition_picking(returns, dest, disposition)
            self._workshop_validate_picking(picking)
            if disposition == "restock" and not self.return_picking_id:
                self.return_picking_id = picking.id
        for ret in returns:
            ret.spare_line_id.qty_returned += ret.qty
            vals = {
                "state": "done",
                "processed_by_id": self.env.user.id,
                "disposition": disposition,
            }
            if picking:
                vals["picking_id"] = picking.id
            ret.write(vals)
        return picking

    def _create_replacement_request(self, returns):
        self.ensure_one()
        if not returns:
            return self.env["workshop.spare.request"]
        products = {}
        for ret in returns:
            products.setdefault(ret.spare_line_id.product_id.id, {
                "product_id": ret.spare_line_id.product_id.id,
                "qty_requested": 0.0,
                "unit_price": ret.spare_line_id.unit_price,
                "unit_cost": ret.spare_line_id.unit_cost,
            })
            products[ret.spare_line_id.product_id.id]["qty_requested"] += ret.qty
        replacement = self.create({
            "job_order_id": self.job_order_id.id,
            "work_order_id": self.work_order_id.id if self.work_order_id else False,
            "origin_request_id": self.id,
            "notes": _("Replacement for %s (%s).") % (
                self.name,
                ", ".join(sorted(set(returns.mapped("reason")))),
            ),
            "line_ids": [(0, 0, vals) for vals in products.values()],
        })
        returns.write({"replacement_request_id": replacement.id})
        replacement.action_submit()
        self.message_post(body=_(
            "Replacement spare request %s created for non-fitting / defective parts."
        ) % replacement.name)
        return replacement

    def _notify_store_returns(self, returns):
        self.ensure_one()
        notify_users = self._workshop_store_notify_users()[:20]
        summary = _("Process part returns %s") % self.name
        reasons = ", ".join(sorted({
            dict(SPARE_RETURN_REASONS).get(r.reason, r.reason) for r in returns
        }))
        body = _(
            "Technician <b>%(user)s</b> flagged parts on <b>%(req)s</b> "
            "(%(reasons)s). Please inspect and process restock / scrap / vendor return."
        ) % {
            "user": self.env.user.display_name,
            "req": self.name,
            "reasons": reasons,
        }
        for user in notify_users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=summary,
                note=body,
            )
        self.message_post(body=body)

    def _sync_state_after_returns(self):
        self.ensure_one()
        if self.return_ids.filtered(lambda r: r.state == "flagged"):
            self.state = "return_flagged"
            return
        if any(
            float_compare(line.qty_returned, 0.0, precision_digits=2) > 0
            for line in self.line_ids
        ):
            self.state = "partially_returned"
        else:
            self.state = "issued"

    def _disposition_location(self, disposition):
        self.ensure_one()
        Location = self.env["stock.location"]
        company_domain = [("company_id", "in", [self.company_id.id, False])]
        if disposition == "restock":
            if self.picking_id:
                return self.picking_id.location_id
            return Location.search(
                [("usage", "=", "internal")] + company_domain, limit=1
            )
        if disposition == "scrap":
            return Location.search(
                [("usage", "=", "inventory")] + company_domain, limit=1
            )
        if disposition == "vendor_return":
            loc = Location.search(
                [("usage", "=", "supplier")] + company_domain, limit=1
            )
            return loc or Location.search(
                [("usage", "=", "inventory")] + company_domain, limit=1
            )
        return Location.browse()

    def _create_disposition_picking(self, returns, dest, disposition):
        self.ensure_one()
        src = self.picking_id.location_dest_id
        picking_type = self._get_issue_picking_type()
        if not picking_type or not src or not dest:
            return self.env["stock.picking"]
        origin_label = {
            "restock": _("Restock %s"),
            "scrap": _("Scrap %s"),
            "vendor_return": _("Vendor return %s"),
        }.get(disposition, _("Return %s"))
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "origin": origin_label % self.name,
            "job_order_id": self.job_order_id.id,
            "company_id": self.company_id.id,
        })
        for ret in returns:
            self.env["stock.move"].create({
                "product_id": ret.spare_line_id.product_id.id,
                "product_uom_qty": ret.qty,
                "product_uom": ret.spare_line_id.product_uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "picking_id": picking.id,
                "company_id": self.company_id.id,
            })
        return picking

    def _workshop_validate_picking(self, picking):
        if not picking:
            return picking
        if picking.state == "draft":
            picking.action_confirm()
        if picking.state == "confirmed":
            picking.action_assign()
        if picking.state not in ("done", "cancel"):
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            result = picking.button_validate()
            if isinstance(result, dict) and result.get("res_model"):
                wizard = self.env[result["res_model"]].with_context(
                    **result.get("context", {})
                ).create({})
                if hasattr(wizard, "process"):
                    wizard.process()
                elif hasattr(wizard, "button_validate"):
                    wizard.button_validate()
        if picking.state != "done":
            raise UserError(_(
                "Could not validate picking %s. Check stock quantities and try again."
            ) % picking.name)
        return picking

    def action_reject(self):
        self.write({"state": "rejected"})
        for rec in self:
            rec._maybe_resume_job_order()

    def _maybe_resume_job_order(self):
        for rec in self:
            jo = rec.job_order_id
            if jo.state != "waiting_parts":
                continue
            pending = jo.spare_request_ids.filtered(
                lambda s: s.state in (
                    "submitted", "store_approved", "waiting_purchase", "return_flagged"
                )
            )
            if not pending:
                jo.write({"state": "in_progress"})

    def _get_issue_picking_type(self):
        self.ensure_one()
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search([
                ("code", "=", "outgoing"),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
        return picking_type

    def _create_stock_picking(self):
        """Create stock picking to issue spare parts to the job."""
        self.ensure_one()
        if self.picking_id:
            return self.picking_id

        picking_type = self._get_issue_picking_type()
        if not picking_type:
            raise UserError(_("No internal/outgoing picking type configured for this company."))

        location_src = picking_type.default_location_src_id
        location_dest = picking_type.default_location_dest_id
        if not location_src:
            location_src = self.env["stock.location"].search([
                ("usage", "=", "internal"),
                ("company_id", "in", [self.company_id.id, False]),
            ], limit=1)
        if not location_dest:
            location_dest = self.env["stock.location"].search([
                ("usage", "=", "production"),
                ("company_id", "in", [self.company_id.id, False]),
            ], limit=1) or location_src

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "origin": f"{self.name} ({self.job_order_id.name})",
            "job_order_id": self.job_order_id.id,
            "company_id": self.company_id.id,
        })

        for line in self.line_ids:
            cost = line.product_id.standard_price or line.unit_price
            self.env["stock.move"].create({
                "product_id": line.product_id.id,
                "product_uom_qty": line.qty_requested,
                "product_uom": line.product_uom_id.id,
                "location_id": location_src.id,
                "location_dest_id": location_dest.id,
                "picking_id": picking.id,
                "price_unit": cost,
                "company_id": self.company_id.id,
            })
            line.unit_cost = cost

        self.picking_id = picking.id
        return picking

    def _create_return_picking(self, lines):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("No original issue picking to return against."))
        src = self.picking_id.location_dest_id
        dest = self.picking_id.location_id
        picking_type = self._get_issue_picking_type()
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "origin": _("Return %s") % self.name,
            "job_order_id": self.job_order_id.id,
            "company_id": self.company_id.id,
        })
        for line in lines:
            qty = line.qty_issued - line.qty_returned
            if qty <= 0:
                continue
            self.env["stock.move"].create({
                "product_id": line.product_id.id,
                "product_uom_qty": qty,
                "product_uom": line.product_uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "picking_id": picking.id,
                "company_id": self.company_id.id,
            })
        return picking

    def _create_purchase_requisition(self):
        """Create RFQ for shortage quantities."""
        self.ensure_one()
        short_lines = self.line_ids.filtered(
            lambda l: float_compare(l.qty_available, l.qty_requested, precision_digits=2) < 0
        )
        if not short_lines:
            return False

        # Prefer product seller; otherwise placeholder vendor
        partner = False
        for line in short_lines:
            seller = line.product_id.seller_ids[:1]
            if seller:
                partner = seller.partner_id
                break
        if not partner:
            partner = self.env["res.partner"].search([("supplier_rank", ">", 0)], limit=1)
        if not partner:
            partner = self.env["res.partner"].create({
                "name": _("Workshop Parts Supplier"),
                "supplier_rank": 1,
            })

        po = self.env["purchase.order"].create({
            "partner_id": partner.id,
            "origin": f"{self.name} / {self.job_order_id.name}",
            "job_order_id": self.job_order_id.id,
            "company_id": self.company_id.id,
        })
        for line in short_lines:
            qty = line.qty_requested - max(line.qty_available, 0.0)
            if qty <= 0:
                continue
            self.env["purchase.order.line"].create({
                "order_id": po.id,
                "product_id": line.product_id.id,
                "name": line.product_id.display_name,
                "product_qty": qty,
                "product_uom_id": line.product_uom_id.id,
                "price_unit": line.product_id.standard_price or line.unit_price,
                "date_planned": fields.Datetime.now(),
            })
        return po


class WorkshopSpareRequestLine(models.Model):
    """Individual product line in a spare request."""

    _name = "workshop.spare.request.line"
    _description = "Workshop Spare Request Line"

    spare_request_id = fields.Many2one(
        comodel_name="workshop.spare.request",
        string="Spare Request",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product / Spare Part",
        required=True,
        domain="[('type', '=', 'consu')]",
    )
    qty_requested = fields.Float(
        string="Requested Qty",
        default=1.0,
        required=True,
    )
    qty_issued = fields.Float(
        string="Issued Qty",
        default=0.0,
    )
    qty_returned = fields.Float(
        string="Returned Qty",
        default=0.0,
    )
    return_ids = fields.One2many(
        comodel_name="workshop.spare.return",
        inverse_name="spare_line_id",
        string="Returns",
    )
    qty_flagged = fields.Float(
        string="Flagged Qty",
        compute="_compute_return_qtys",
    )
    qty_remaining = fields.Float(
        string="Remaining on Job",
        compute="_compute_return_qtys",
    )
    qty_available = fields.Float(
        string="Available Qty",
        compute="_compute_qty_available",
        store=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
        related="product_id.uom_id",
        readonly=True,
    )
    unit_price = fields.Float(
        string="Sales Price",
        related="product_id.list_price",
        readonly=False,
        store=True,
    )
    unit_cost = fields.Float(
        string="Unit Cost",
        help="Cost used for job costing (defaults to product standard price).",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="spare_request_id.company_id.currency_id",
        readonly=True,
    )
    total_price = fields.Monetary(
        string="Sales Subtotal",
        compute="_compute_totals",
        store=True,
    )
    cost_subtotal = fields.Monetary(
        string="Cost Subtotal (Issued − Returned)",
        compute="_compute_totals",
        store=True,
    )

    @api.depends("product_id", "spare_request_id.company_id")
    def _compute_qty_available(self):
        for line in self:
            if line.product_id:
                line.qty_available = line.product_id.with_company(
                    line.spare_request_id.company_id
                ).qty_available
            else:
                line.qty_available = 0.0

    def _refresh_availability(self):
        for line in self:
            if line.product_id:
                line.qty_available = line.product_id.with_company(
                    line.spare_request_id.company_id
                ).qty_available

    @api.depends("qty_issued", "qty_returned", "return_ids.qty", "return_ids.state")
    def _compute_return_qtys(self):
        for line in self:
            flagged = sum(
                line.return_ids.filtered(lambda r: r.state == "flagged").mapped("qty")
            )
            line.qty_flagged = flagged
            line.qty_remaining = max(line.qty_issued - line.qty_returned - flagged, 0.0)

    def _qty_remaining_on_job(self):
        self.ensure_one()
        flagged = sum(
            self.return_ids.filtered(lambda r: r.state == "flagged").mapped("qty")
        )
        return max(self.qty_issued - self.qty_returned - flagged, 0.0)

    @api.depends("qty_requested", "unit_price", "qty_issued", "qty_returned", "unit_cost", "product_id")
    def _compute_totals(self):
        for line in self:
            line.total_price = line.qty_requested * line.unit_price
            cost = line.unit_cost or (line.product_id.standard_price if line.product_id else 0.0)
            net_qty = max(line.qty_issued - line.qty_returned, 0.0)
            # Before issue, estimate on requested qty for approval thresholds
            if line.spare_request_id.state in ("draft", "submitted", "waiting_purchase", "store_approved"):
                net_qty = line.qty_requested
            line.cost_subtotal = net_qty * cost

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_cost = self.product_id.standard_price
            self.unit_price = self.product_id.list_price


class WorkshopSpareReturn(models.Model):
    """Technician-flagged reverse logistics line for issued spare parts."""

    _name = "workshop.spare.return"
    _description = "Workshop Spare Part Return"
    _order = "id desc"

    spare_request_id = fields.Many2one(
        comodel_name="workshop.spare.request",
        string="Spare Request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    spare_line_id = fields.Many2one(
        comodel_name="workshop.spare.request.line",
        string="Spare Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        related="spare_line_id.product_id",
        store=True,
        readonly=True,
    )
    qty = fields.Float(string="Quantity", required=True)
    reason = fields.Selection(
        selection=SPARE_RETURN_REASONS,
        string="Reason",
        required=True,
        default="unused",
        index=True,
    )
    disposition = fields.Selection(
        selection=SPARE_RETURN_DISPOSITIONS,
        string="Store Action",
        required=True,
        default="restock",
        help="Restock unused or mis-picked parts; scrap defective; send vendor returns to the supplier location.",
    )
    request_replacement = fields.Boolean(
        string="Request Replacement",
        help="Create a new spare request for the same quantity after store processes this return.",
    )
    notes = fields.Text(string="Notes")
    state = fields.Selection(
        selection=[
            ("flagged", "Flagged"),
            ("done", "Processed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="flagged",
        required=True,
        copy=False,
        index=True,
    )
    flagged_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Flagged By",
        default=lambda self: self.env.user,
    )
    processed_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Processed By",
        copy=False,
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Reverse Picking",
        copy=False,
        readonly=True,
    )
    replacement_request_id = fields.Many2one(
        comodel_name="workshop.spare.request",
        string="Replacement Request",
        copy=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="spare_request_id.company_id",
        store=True,
        readonly=True,
    )

    @api.model
    def _default_disposition(self, reason):
        if reason == "defective":
            return "scrap"
        return "restock"

    @api.onchange("reason")
    def _onchange_reason(self):
        self.disposition = self._default_disposition(self.reason)
        self.request_replacement = self.reason in ("wrong_fit", "defective")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            reason = vals.get("reason") or "unused"
            if not vals.get("disposition"):
                vals["disposition"] = self._default_disposition(reason)
            if "request_replacement" not in vals:
                vals["request_replacement"] = reason in ("wrong_fit", "defective")
        return super().create(vals_list)

    def action_cancel(self):
        flagged = self.filtered(lambda r: r.state == "flagged")
        flagged.write({"state": "cancelled"})
        flagged.mapped("spare_request_id")._sync_state_after_returns()
        return True
