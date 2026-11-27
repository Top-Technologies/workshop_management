from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WorkshopFieldVisit(models.Model):
    """Off-site field service visit linked to a Job Order."""

    _name = "workshop.field.visit"
    _description = "Workshop Field Visit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "scheduled_start desc, id desc"

    name = fields.Char(
        string="Visit Reference",
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
        tracking=True,
        index=True,
    )
    request_id = fields.Many2one(
        related="job_order_id.request_id",
        store=True,
        readonly=True,
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
    technician_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Technician",
        tracking=True,
        index=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Technician User",
        related="technician_id.user_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="job_order_id.company_id",
        store=True,
        readonly=True,
    )
    service_street = fields.Char(related="job_order_id.service_street", readonly=True)
    service_city = fields.Char(related="job_order_id.service_city", readonly=True)
    service_state_id = fields.Many2one(
        related="job_order_id.service_state_id",
        readonly=True,
    )
    service_zip = fields.Char(related="job_order_id.service_zip", readonly=True)
    service_country_id = fields.Many2one(
        related="job_order_id.service_country_id",
        readonly=True,
    )
    scheduled_start = fields.Datetime(string="Scheduled Start", tracking=True)
    scheduled_end = fields.Datetime(string="Scheduled End", tracking=True)
    travel_start = fields.Datetime(string="Travel Start", tracking=True, copy=False)
    arrival_time = fields.Datetime(string="Check-In", tracking=True, copy=False)
    departure_time = fields.Datetime(string="Check-Out", tracking=True, copy=False)
    return_time = fields.Datetime(string="Return", tracking=True, copy=False)
    travel_hours = fields.Float(
        string="Travel Hours",
        compute="_compute_field_hours",
        store=True,
    )
    on_site_hours = fields.Float(
        string="On-Site Hours",
        compute="_compute_field_hours",
        store=True,
    )
    dispatch_to_arrival_hours = fields.Float(
        string="Dispatch to Arrival (hrs)",
        compute="_compute_field_hours",
        store=True,
    )
    check_in_latitude = fields.Float(string="Check-In Latitude", digits=(10, 7))
    check_in_longitude = fields.Float(string="Check-In Longitude", digits=(10, 7))
    check_out_latitude = fields.Float(string="Check-Out Latitude", digits=(10, 7))
    check_out_longitude = fields.Float(string="Check-Out Longitude", digits=(10, 7))
    customer_signature = fields.Binary(string="Customer Signature", copy=False, attachment=True)
    signed_by = fields.Char(string="Signed By")
    notes = fields.Html(string="Visit Notes")
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("traveling", "Traveling"),
            ("on_site", "On Site"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    @api.depends(
        "travel_start",
        "arrival_time",
        "departure_time",
        "return_time",
        "scheduled_start",
    )
    def _compute_field_hours(self):
        for visit in self:
            travel = 0.0
            if visit.travel_start and visit.arrival_time:
                travel = (visit.arrival_time - visit.travel_start).total_seconds() / 3600.0
            elif visit.travel_start and visit.return_time and not visit.arrival_time:
                travel = (visit.return_time - visit.travel_start).total_seconds() / 3600.0
            visit.travel_hours = max(travel, 0.0)

            on_site = 0.0
            if visit.arrival_time and visit.departure_time:
                on_site = (visit.departure_time - visit.arrival_time).total_seconds() / 3600.0
            visit.on_site_hours = max(on_site, 0.0)

            dispatch = 0.0
            start_ref = visit.scheduled_start or visit.travel_start
            if start_ref and visit.arrival_time:
                dispatch = (visit.arrival_time - start_ref).total_seconds() / 3600.0
            visit.dispatch_to_arrival_hours = max(dispatch, 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.field.visit"
                ) or "New"
        return super().create(vals_list)

    def action_schedule(self):
        self._ensure_field_job()
        for visit in self.filtered(lambda v: v.state == "draft"):
            if not visit.scheduled_start:
                raise UserError(_("Set a scheduled start before scheduling the visit."))
            if not visit.technician_id:
                raise UserError(_("Assign a technician before scheduling the visit."))
            visit.state = "scheduled"

    def action_start_travel(self):
        self._ensure_field_job()
        now = fields.Datetime.now()
        for visit in self.filtered(lambda v: v.state in ("draft", "scheduled")):
            vals = {"state": "traveling", "travel_start": now}
            if not visit.scheduled_start:
                vals["scheduled_start"] = now
            visit.write(vals)

    def action_check_in(self):
        self._ensure_field_job()
        now = fields.Datetime.now()
        for visit in self.filtered(lambda v: v.state == "traveling"):
            visit.write({"state": "on_site", "arrival_time": now})

    def action_check_out(self):
        self._ensure_field_job()
        now = fields.Datetime.now()
        for visit in self.filtered(lambda v: v.state == "on_site"):
            visit.write({"state": "completed", "departure_time": now, "return_time": now})

    def action_cancel(self):
        self.filtered(lambda v: v.state != "completed").write({"state": "cancelled"})

    def action_reset_draft(self):
        self.filtered(lambda v: v.state == "cancelled").write({"state": "draft"})

    def _ensure_field_job(self):
        for visit in self:
            if not visit.job_order_id.is_field_job:
                raise UserError(_(
                    "Field visits can only be created for Job Orders marked as Field Service."
                ))
