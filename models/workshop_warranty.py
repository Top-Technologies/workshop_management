from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

from .workshop_task_master import WARRANTY_KINDS


class WorkshopWarrantyRule(models.Model):
    """Duration lookup: service kind × vehicle type × customer / agreement."""

    _name = "workshop.warranty.rule"
    _description = "Workshop Warranty Period Rule"
    _order = "sequence, id"

    name = fields.Char(string="Rule Name", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    warranty_kind = fields.Selection(
        selection=WARRANTY_KINDS,
        string="Warranty Service",
        required=True,
        index=True,
    )
    duration_months = fields.Integer(
        string="Duration (Months)",
        required=True,
        default=6,
        help="Warranty length granted when this rule matches.",
    )
    equipment_type_id = fields.Many2one(
        comodel_name="workshop.equipment.type",
        string="Vehicle / Equipment Type",
        ondelete="cascade",
        help="Leave empty to apply to every vehicle type.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        ondelete="cascade",
        help="Leave empty to apply to every customer.",
    )
    agreement_id = fields.Many2one(
        comodel_name="workshop.agreement",
        string="Service Agreement",
        ondelete="cascade",
        index=True,
        help="Most specific match. Leave empty for a general rule.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )
    notes = fields.Text(string="Notes")

    _duration_positive = models.Constraint(
        "CHECK(duration_months > 0)",
        "Warranty duration must be greater than zero.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("agreement_id") and not vals.get("partner_id"):
                agreement = self.env["workshop.agreement"].browse(vals["agreement_id"])
                vals["partner_id"] = agreement.partner_id.id
        return super().create(vals_list)

    @api.onchange("agreement_id")
    def _onchange_agreement_id(self):
        if self.agreement_id:
            self.partner_id = self.agreement_id.partner_id

    @api.model
    def match_rule(self, kind, equipment=None, partner=None, agreement=None, company=None):
        """Return the most specific active rule for this service / vehicle / client."""
        if not kind:
            return self.browse()
        company = company or self.env.company
        equipment = equipment or self.env["workshop.equipment"]
        partner = partner or (equipment.partner_id if equipment else self.env["res.partner"])
        agreement = agreement or self.env["workshop.agreement"]
        rules = self.search([
            ("warranty_kind", "=", kind),
            ("active", "=", True),
            ("company_id", "in", [company.id, False]),
        ])
        best = self.browse()
        best_score = -1
        for rule in rules:
            if rule.agreement_id and rule.agreement_id != agreement:
                continue
            if rule.partner_id and rule.partner_id != partner:
                continue
            if rule.equipment_type_id and (
                not equipment or rule.equipment_type_id != equipment.equipment_type
            ):
                continue
            score = 0
            if rule.agreement_id:
                score += 8
            if rule.partner_id:
                score += 4
            if rule.equipment_type_id:
                score += 2
            if score > best_score:
                best = rule
                best_score = score
        return best


class WorkshopWarranty(models.Model):
    """Issued workmanship warranty for engine overhaul or gearbox on one vehicle."""

    _name = "workshop.warranty"
    _description = "Workshop Service Warranty"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end desc, id desc"

    name = fields.Char(
        string="Warranty No.",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index=True,
    )
    equipment_id = fields.Many2one(
        comodel_name="workshop.equipment",
        string="Equipment/Vehicle",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        related="equipment_id.partner_id",
        store=True,
        readonly=True,
    )
    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Origin Job Order",
        index=True,
        ondelete="set null",
        tracking=True,
    )
    task_id = fields.Many2one(
        comodel_name="workshop.task.master",
        string="Warranted Job",
        ondelete="restrict",
    )
    warranty_kind = fields.Selection(
        selection=WARRANTY_KINDS,
        string="Warranty Service",
        required=True,
        index=True,
        tracking=True,
    )
    rule_id = fields.Many2one(
        comodel_name="workshop.warranty.rule",
        string="Period Rule",
        ondelete="set null",
    )
    agreement_id = fields.Many2one(
        comodel_name="workshop.agreement",
        string="Service Agreement",
        ondelete="set null",
    )
    date_start = fields.Date(
        string="Start Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    duration_months = fields.Integer(string="Duration (Months)", required=True)
    date_end = fields.Date(
        string="End Date",
        required=True,
        index=True,
        tracking=True,
    )
    is_cancelled = fields.Boolean(copy=False)
    state = fields.Selection(
        selection=[
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        compute="_compute_state",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    notes = fields.Text(string="Notes")

    _duration_positive = models.Constraint(
        "CHECK(duration_months > 0)",
        "Warranty duration must be greater than zero.",
    )

    @api.depends("date_end", "is_cancelled")
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.is_cancelled:
                rec.state = "cancelled"
            elif rec.date_end and rec.date_end < today:
                rec.state = "expired"
            else:
                rec.state = "active"

    @api.onchange("date_start", "duration_months")
    def _onchange_duration(self):
        if self.date_start and self.duration_months:
            self.date_end = self.date_start + relativedelta(months=self.duration_months)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.warranty"
                ) or "New"
            if vals.get("date_start") and vals.get("duration_months") and not vals.get("date_end"):
                start = fields.Date.to_date(vals["date_start"])
                vals["date_end"] = start + relativedelta(months=int(vals["duration_months"]))
        records = super().create(vals_list)
        records.mapped("equipment_id")._sync_warranty_end_date()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("date_end", "is_cancelled", "equipment_id")):
            self.mapped("equipment_id")._sync_warranty_end_date()
        return res

    def action_cancel(self):
        self.write({"is_cancelled": True})
        self.mapped("equipment_id")._sync_warranty_end_date()

    def action_reset_active(self):
        self.write({"is_cancelled": False})
        self.mapped("equipment_id")._sync_warranty_end_date()

    @api.model
    def _cron_expire_warranties(self):
        today = fields.Date.context_today(self)
        expired = self.search([
            ("is_cancelled", "=", False),
            ("state", "=", "active"),
            ("date_end", "<", today),
        ])
        if expired:
            expired._compute_state()
            expired.mapped("equipment_id")._sync_warranty_end_date()
            expired.mapped("equipment_id")._compute_warranty_status()
