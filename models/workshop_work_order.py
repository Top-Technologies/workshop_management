from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

REWORK_CAUSES = [
    ("quality_fail", "Quality Inspection Failed"),
    ("customer_complaint", "Customer Complaint"),
    ("incomplete", "Incomplete Work"),
    ("parts_issue", "Parts / Material Issue"),
    ("other", "Other"),
]
REWORK_WHO_PAYS = [
    ("workshop", "Workshop"),
    ("customer", "Customer"),
    ("warranty", "Warranty"),
    ("technician", "Technician"),
]

# Workshop clock-in/out pause reason codes (Reason ID from workshop feedback).
# -1 On Progress is the running state, not a pause reason.
TIMER_PAUSE_REASONS = [
    ("0", "0 — Work Completed"),
    ("1", "1 — Lunch Break"),
    ("2", "2 — Tea Break"),
    ("3", "3 — End of Day"),
    ("5", "5 — Spare Part Out of Stock"),
    ("6", "6 — Sick"),
    ("7", "7 — Waiting for Approval"),
    ("8", "8 — Sublet"),
    ("9", "9 — Meeting"),
    ("10", "10 — To Assist Another Job"),
    ("11", "11 — To Supply Fuel and Lubricant"),
    ("12", "12 — Specific Work Completed"),
    ("14", "14 — Send to Machine Shop"),
]


class WorkshopWorkOrder(models.Model):
    """Work Order – individual per-department task assigned to a technician."""

    _name = "workshop.work.order"
    _description = "Work Dispatch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="Work Dispatch No.",
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
        tracking=True,
        index=True,
        ondelete="cascade",
    )
    department = fields.Many2one(
        comodel_name="workshop.department",
        string="Department",
        required=True,
        tracking=True,
        index=True,
        ondelete="restrict",
        default=lambda self: self.env["workshop.department"]._default_department(),
    )
    technician_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Assigned Technician",
        tracking=True,
        index=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Technician User",
        tracking=True,
        index=True,
    )
    task_id = fields.Many2one(
        comodel_name="workshop.task.master",
        string="Job Description",
        tracking=True,
        index=True,
        ondelete="restrict",
    )
    request_line_id = fields.Many2one(
        comodel_name="workshop.request.line",
        string="Estimate Labor Line",
        ondelete="set null",
        index=True,
        copy=False,
        help="Customer Request labor line this dispatch was created from.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        related="job_order_id.partner_id",
        store=True,
        readonly=True,
    )
    equipment_id = fields.Many2one(
        comodel_name="workshop.equipment",
        string="Equipment/Vehicle",
        related="job_order_id.equipment_id",
        store=True,
        readonly=True,
    )
    standard_hours = fields.Float(
        string="Catalog Hours",
        related="task_id.standard_hours",
        store=True,
        readonly=False,
    )
    planned_hours = fields.Float(
        string="Standard Hours",
        default=1.0,
        required=True,
        tracking=True,
    )
    actual_hours = fields.Float(
        string="Actual Hours",
        compute="_compute_actual_hours",
        store=True,
    )
    variance_hours = fields.Float(
        string="Variance (Actual - Standard)",
        compute="_compute_actual_hours",
        store=True,
    )
    planned_start = fields.Datetime(
        string="Planned Start",
        tracking=True,
    )
    planned_finish = fields.Datetime(
        string="Planned Finish",
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
    timesheet_ids = fields.One2many(
        comodel_name="account.analytic.line",
        inverse_name="work_order_id",
        string="Timesheets",
    )
    spare_request_ids = fields.One2many(
        comodel_name="workshop.spare.request",
        inverse_name="work_order_id",
        string="Spare Requests",
    )
    quality_inspection_ids = fields.One2many(
        comodel_name="workshop.quality.inspection",
        inverse_name="work_order_id",
        string="Quality Inspections",
    )
    # ---- Auto timesheet timer ----
    timer_start = fields.Datetime(
        string="Timer Started At",
        copy=False,
        readonly=True,
    )
    is_timer_running = fields.Boolean(
        string="Timer Running",
        compute="_compute_is_timer_running",
    )
    timer_elapsed_hours = fields.Float(
        string="Elapsed (Running Timer)",
        compute="_compute_is_timer_running",
    )
    timer_pause_reason = fields.Selection(
        selection=TIMER_PAUSE_REASONS,
        string="Pause Reason",
        copy=False,
        tracking=True,
        help="Why the timesheet timer was last paused.",
    )
    timer_pause_notes = fields.Text(
        string="Pause Notes",
        copy=False,
    )
    is_timer_paused = fields.Boolean(
        string="Timer Paused",
        compute="_compute_is_timer_running",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("assigned", "Assigned"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("rework", "Rework"),
            ("verified", "Verified"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
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
    notes = fields.Html(string="Notes / Instructions")
    photo_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="workshop_work_order_photo_rel",
        column1="work_order_id",
        column2="attachment_id",
        string="Work Photos",
    )
    calendar_start = fields.Datetime(
        string="Calendar Start",
        compute="_compute_calendar_dates",
        store=True,
    )
    calendar_stop = fields.Datetime(
        string="Calendar Stop",
        compute="_compute_calendar_dates",
        store=True,
    )
    labor_cost = fields.Monetary(
        string="Labor Cost",
        compute="_compute_labor_and_rework",
        store=True,
        help="Standard Hours × technician hourly rate (or company default). "
             "Timer / actual hours are not used for costing.",
    )
    rework_count = fields.Integer(string="Rework Count", default=0, copy=False)
    rework_cause = fields.Selection(
        selection=REWORK_CAUSES,
        string="Rework Cause",
        copy=False,
        tracking=True,
    )
    rework_who_pays = fields.Selection(
        selection=REWORK_WHO_PAYS,
        string="Who Pays",
        copy=False,
        tracking=True,
        help="Workshop/technician-paid rework counts as cost of quality.",
    )
    rework_notes = fields.Text(string="Rework Notes", copy=False)
    rework_hours_at_fail = fields.Float(
        string="Hours Before Rework",
        copy=False,
        help="Actual hours logged when the work order was first sent to rework.",
    )
    rework_extra_hours = fields.Float(
        string="Rework Extra Hours",
        compute="_compute_labor_and_rework",
        store=True,
    )
    rework_cost = fields.Monetary(
        string="Rework Cost",
        compute="_compute_labor_and_rework",
        store=True,
        help="Extra hours × technician hourly cost (or company default rate).",
    )

    @api.depends("timesheet_ids.unit_amount")
    def _compute_actual_hours(self):
        for wo in self:
            total = sum(wo.timesheet_ids.mapped("unit_amount"))
            wo.actual_hours = total
            wo.variance_hours = total - wo.planned_hours

    def _workshop_labor_rate(self):
        self.ensure_one()
        if self.technician_id and self.technician_id.hourly_cost > 0:
            return self.technician_id.hourly_cost
        product = self.request_line_id.product_id
        matched = self.env["workshop.labor.rate.rule"]._match_labor_rate(
            partner=self.partner_id,
            product=product,
            company=self.company_id,
        )
        if matched is not None:
            return matched
        return self.company_id.workshop_default_labor_rate or 50.0

    @api.depends(
        "actual_hours",
        "planned_hours",
        "rework_count",
        "rework_hours_at_fail",
        "technician_id.hourly_cost",
        "partner_id.workshop_customer_type_id",
        "request_line_id.product_id",
        "company_id.workshop_default_labor_rate",
        "company_id.workshop_labor_rate_rule_ids.labor_rate",
        "company_id.workshop_labor_rate_rule_ids.pricelist_item_id",
        "company_id.workshop_labor_rate_rule_ids.customer_type_id",
        "company_id.workshop_labor_rate_rule_ids.applied_on",
    )
    def _compute_labor_and_rework(self):
        for wo in self:
            rate = wo._workshop_labor_rate()
            wo.labor_cost = wo.planned_hours * rate
            extra = 0.0
            if wo.rework_count:
                extra = max(wo.actual_hours - wo.rework_hours_at_fail, 0.0)
            wo.rework_extra_hours = extra
            wo.rework_cost = extra * rate

    @api.depends("planned_start", "planned_finish", "date_start", "date_end", "planned_hours")
    def _compute_calendar_dates(self):
        for wo in self:
            start = wo.planned_start or wo.date_start
            stop = wo.planned_finish or wo.date_end
            if start and not stop and wo.planned_hours:
                stop = start + timedelta(hours=wo.planned_hours)
            wo.calendar_start = start
            wo.calendar_stop = stop

    @api.depends("timer_start", "timer_pause_reason")
    def _compute_is_timer_running(self):
        now = fields.Datetime.now()
        for wo in self:
            wo.is_timer_running = bool(wo.timer_start)
            wo.is_timer_paused = bool(wo.timer_pause_reason) and not wo.timer_start
            if wo.timer_start:
                delta = now - wo.timer_start
                wo.timer_elapsed_hours = delta.total_seconds() / 3600.0
            else:
                wo.timer_elapsed_hours = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.work.order"
                ) or "New"
            self._sync_user_from_technician_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        if "technician_id" in vals and "user_id" not in vals:
            self._sync_user_from_technician_vals(vals)
        return super().write(vals)

    @api.model
    def _sync_user_from_technician_vals(self, vals):
        """Keep user_id aligned with the assigned employee's login user."""
        tech_id = vals.get("technician_id")
        if not tech_id:
            return
        employee = self.env["hr.employee"].browse(tech_id)
        if employee.user_id:
            vals["user_id"] = employee.user_id.id

    @api.onchange("technician_id")
    def _onchange_technician_id(self):
        self.user_id = self.technician_id.user_id

    def action_assign(self):
        now = fields.Datetime.now()
        for wo in self:
            vals = {"state": "assigned"}
            if not wo.planned_start:
                vals["planned_start"] = now
            start = vals.get("planned_start") or wo.planned_start
            if not wo.planned_finish and start and wo.planned_hours:
                vals["planned_finish"] = start + timedelta(hours=wo.planned_hours)
            wo.write(vals)

    def action_start(self):
        """Start work and automatically start the timesheet timer."""
        for wo in self:
            vals = {
                "state": "in_progress",
                "date_start": wo.date_start or fields.Datetime.now(),
            }
            wo.write(vals)
            if wo.job_order_id.state in ("approved", "assigned"):
                # Technicians have read-only ACL on Job Orders; escalate this state write.
                wo.job_order_id.sudo().write({
                    "state": "in_progress",
                    "date_start": fields.Datetime.now(),
                })
            if not wo.timer_start:
                wo._timer_start()

    def action_done(self):
        for rec in self:
            if rec.timer_start:
                rec._timer_stop()
            if not rec.quality_inspection_ids:
                rec._create_quality_inspection_from_template()
            rec.write({
                "state": "done",
                "date_end": fields.Datetime.now(),
                "timer_pause_reason": False,
                "timer_pause_notes": False,
            })

    def action_open_rework_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Send to Rework"),
            "res_model": "workshop.rework.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_work_order_id": self.id,
                "default_rework_cause": self.rework_cause or "quality_fail",
                "default_rework_who_pays": self.rework_who_pays or "workshop",
                "default_notes": self.rework_notes or False,
            },
        }

    def action_rework(self, cause="quality_fail", who_pays="workshop", notes=False):
        """Send to rework and capture cost-of-quality fields."""
        for rec in self:
            vals = {
                "state": "rework",
                "rework_count": rec.rework_count + 1,
                "rework_cause": cause or rec.rework_cause or "quality_fail",
                "rework_who_pays": who_pays or rec.rework_who_pays or "workshop",
            }
            if notes:
                vals["rework_notes"] = notes
            if not rec.rework_hours_at_fail:
                vals["rework_hours_at_fail"] = rec.actual_hours
            rec.write(vals)
            rec.message_post(body=_(
                "Sent to rework (%(count)s). Cause: %(cause)s. Who pays: %(pays)s."
            ) % {
                "count": rec.rework_count,
                "cause": dict(REWORK_CAUSES).get(rec.rework_cause) or rec.rework_cause,
                "pays": dict(REWORK_WHO_PAYS).get(rec.rework_who_pays) or rec.rework_who_pays,
            })

    def action_verify(self):
        """Verify only when a passed QI exists and none failed."""
        for rec in self:
            failed_qi = rec.quality_inspection_ids.filtered(lambda q: q.state == "fail")
            if failed_qi:
                raise UserError(_(
                    "Cannot verify Work Dispatch with failed Quality Inspection. Send to rework first."
                ))
            passed_qi = rec.quality_inspection_ids.filtered(lambda q: q.state == "pass")
            if not passed_qi:
                raise UserError(_(
                    "Cannot verify Work Dispatch until Quality Inspection has passed."
                ))
            rec.write({"state": "verified"})

    def action_timer_start(self):
        """Manual Start Timer (also moves WO to in progress if needed)."""
        for wo in self:
            if wo.state in ("draft", "assigned", "rework"):
                wo.action_start()
            elif wo.state == "in_progress":
                wo._timer_start()
            else:
                raise UserError(_(
                    "Timer can only run on assigned / in-progress / rework Work Dispatches."
                ))

    def action_timer_stop(self):
        """Stop timer and create an account.analytic.line timesheet entry."""
        for wo in self:
            wo._timer_stop()

    def action_open_pause_timer_wizard(self):
        """Open the pause-reason wizard. A reason is required to pause."""
        self.ensure_one()
        if not self.timer_start:
            raise UserError(_("Timer is not running on %s.") % self.name)
        return {
            "type": "ir.actions.act_window",
            "name": _("Pause Timer"),
            "res_model": "workshop.timer.pause.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_work_order_id": self.id,
            },
        }

    def action_timer_pause(self, reason, notes=False):
        """Pause the running timer after the technician selects a reason."""
        if not reason:
            raise UserError(_("Select a pause reason before pausing the timer."))
        valid_codes = {code for code, _label in TIMER_PAUSE_REASONS}
        if reason not in valid_codes:
            raise UserError(_("Invalid pause reason."))
        for wo in self:
            if not wo.timer_start:
                raise UserError(_("Timer is not running on %s.") % wo.name)
            wo._timer_stop(pause_reason=reason, notes=notes)

    def _timer_start(self):
        self.ensure_one()
        if self.timer_start:
            raise UserError(_("Timer is already running on %s. Stop it first.") % self.name)
        if not self.technician_id and not self.user_id:
            raise UserError(_("Assign a technician (or user) before starting the timer."))
        previous_reason = dict(TIMER_PAUSE_REASONS).get(self.timer_pause_reason)
        self.write({
            "timer_start": fields.Datetime.now(),
            "timer_pause_reason": False,
            "timer_pause_notes": False,
        })
        if previous_reason:
            self.message_post(body=_(
                "Timesheet timer resumed (was paused: %s)."
            ) % previous_reason)
        else:
            self.message_post(body=_("Timesheet timer started."))

    def _timer_stop(self, pause_reason=False, notes=False):
        self.ensure_one()
        if not self.timer_start:
            return False
        now = fields.Datetime.now()
        hours = (now - self.timer_start).total_seconds() / 3600.0
        # Round to minutes (min 1 minute if any time passed)
        hours = round(hours, 4)
        if hours < (1.0 / 60.0):
            hours = 1.0 / 60.0

        line = self._create_timesheet_line(hours, self.timer_start, now)
        vals = {"timer_start": False}
        if pause_reason:
            vals["timer_pause_reason"] = pause_reason
            vals["timer_pause_notes"] = notes or False
            reason_label = dict(TIMER_PAUSE_REASONS).get(pause_reason) or pause_reason
            self.write(vals)
            message = _(
                "Timesheet timer paused (%(reason)s): %(h).2f hour(s) logged."
            ) % {"reason": reason_label, "h": hours}
            if notes:
                message = "%s<br/>%s" % (message, notes)
            self.message_post(body=message)
        else:
            vals["timer_pause_reason"] = False
            vals["timer_pause_notes"] = False
            self.write(vals)
            self.message_post(body=_(
                "Timesheet timer stopped: %(h).2f hour(s) logged."
            ) % {"h": hours})
        return line

    def _create_timesheet_line(self, hours, start_dt, stop_dt):
        """Create account.analytic.line linked to this Work Order."""
        self.ensure_one()
        employee = self.technician_id
        if not employee and self.user_id:
            employee = self.env["hr.employee"].search([
                ("user_id", "=", self.user_id.id),
                "|",
                ("company_id", "=", self.company_id.id),
                ("company_id", "=", False),
            ], limit=1)
        if not employee:
            raise UserError(_(
                "Cannot log timesheet: no technician/employee linked to Work Dispatch %s."
            ) % self.name)

        task_name = self.task_id.name if self.task_id else self.name
        description = _(
            "%(wo)s — %(task)s (%(start)s → %(stop)s)"
        ) % {
            "wo": self.name,
            "task": task_name,
            "start": fields.Datetime.to_string(start_dt),
            "stop": fields.Datetime.to_string(stop_dt),
        }

        AnalytiLine = self.env["account.analytic.line"]
        vals = {
            "name": description,
            "date": fields.Date.context_today(self),
            "unit_amount": hours,
            "employee_id": employee.id,
            "user_id": (self.user_id or employee.user_id or self.env.user).id,
            "company_id": self.company_id.id,
            "work_order_id": self.id,
        }

        # Odoo versions that still require analytic account on timesheet lines
        if "account_id" in AnalytiLine._fields:
            account = self._get_workshop_analytic_account()
            if account:
                vals["account_id"] = account.id

        return AnalytiLine.create(vals)

    def _get_workshop_analytic_account(self):
        """Get or create a shared analytic account for workshop labor timesheets."""
        self.ensure_one()
        Analytic = self.env["account.analytic.account"]
        account = Analytic.search([
            ("name", "=", "Workshop Labor"),
            ("company_id", "in", [self.company_id.id, False]),
        ], limit=1)
        if account:
            return account
        plan = False
        if "plan_id" in Analytic._fields:
            plan = self.env["account.analytic.plan"].search([], limit=1)
            if not plan:
                plan = self.env["account.analytic.plan"].create({"name": "Workshop"})
        vals = {
            "name": "Workshop Labor",
            "company_id": self.company_id.id,
        }
        if plan:
            vals["plan_id"] = plan.id
        return Analytic.create(vals)

    def _create_quality_inspection_from_template(self):
        self.ensure_one()
        Checklist = self.env["workshop.quality.checklist.item"]
        items = Checklist.search([
            "|",
            ("department", "=", False),
            ("department", "=", self.department.id if self.department else False),
            ("active", "=", True),
        ])
        lines = [(0, 0, {"name": item.name, "passed": False}) for item in items]
        if not lines:
            lines = [(0, 0, {"name": _("General workmanship check"), "passed": False})]
        return self.env["workshop.quality.inspection"].create({
            "job_order_id": self.job_order_id.id,
            "work_order_id": self.id,
            "line_ids": lines,
        })
