from odoo import api, fields, models, _


INTAKE_CONDITIONS = [
    ("good", "Good"),
    ("fair", "Fair"),
    ("damaged", "Damaged"),
    ("missing", "Missing"),
    ("na", "N/A"),
]

INTAKE_TERMS_HTML = """
<ol>
    <li>Tana is not responsible for any valuables left in the vehicle/machine.</li>
    <li>For vehicles not collected within 2 weeks after completion of work, a parking fee of Birr 25 per day will be charged.</li>
    <li>Tana bears no responsibility for replaced parts not collected upon delivery of the vehicle/machine.</li>
</ol>
"""


class WorkshopEquipmentType(models.Model):
    """User-maintainable Equipment/Vehicle type (Vehicle, Generator, etc.)."""

    _name = "workshop.equipment.type"
    _description = "Equipment/Vehicle Type"
    _order = "sequence, name"

    name = fields.Char(string="Type", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        help="Leave empty to share this type across all companies.",
    )


class WorkshopWorkType(models.Model):
    """User-maintainable Type of Work (Repair, Inspection, etc.)."""

    _name = "workshop.work.type"
    _description = "Type of Work"
    _order = "sequence, name"

    name = fields.Char(string="Type of Work", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        help="Leave empty to share this type across all companies.",
    )


class WorkshopEquipmentIntakeItem(models.Model):
    """Reusable English template for the vehicle/trailer intake checklist."""

    _name = "workshop.equipment.intake.item"
    _description = "Vehicle Intake Checklist Template Item"
    _order = "sequence, id"

    name = fields.Char(string="Item Description", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        help="Leave empty to share this item across all companies.",
    )


class WorkshopEquipmentIntakeLine(models.Model):
    """Filled intake checklist line on an equipment record."""

    _name = "workshop.equipment.intake.line"
    _description = "Vehicle Intake Checklist Line"
    _order = "sequence, id"

    equipment_id = fields.Many2one(
        comodel_name="workshop.equipment",
        string="Equipment/Vehicle",
        required=True,
        ondelete="cascade",
        index=True,
    )
    template_item_id = fields.Many2one(
        comodel_name="workshop.equipment.intake.item",
        string="Template Item",
        ondelete="set null",
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Item Description", required=True)
    quantity = fields.Float(string="Quantity", default=1.0)
    condition = fields.Selection(
        selection=INTAKE_CONDITIONS,
        string="Condition",
    )
    remarks = fields.Char(string="Remarks")
    company_id = fields.Many2one(
        related="equipment_id.company_id",
        store=True,
        readonly=True,
    )


class WorkshopEquipment(models.Model):
    """Customer vehicle/machine/equipment master – anchor for service history."""

    _name = "workshop.equipment"
    _description = "Workshop Equipment/Vehicle"
    _order = "name"
    _rec_names_search = ["name", "serial_number", "plate_number", "chassis_number", "make", "model"]

    name = fields.Char(
        string="Equipment/Vehicle Name",
        required=True,
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Owner / Customer",
        required=True,
        index=True,
        ondelete="restrict",
    )
    equipment_type = fields.Many2one(
        comodel_name="workshop.equipment.type",
        string="Equipment/Vehicle Type",
        required=True,
        ondelete="restrict",
        index=True,
        default=lambda self: self.env.ref(
            "workshop_management.equipment_type_vehicle",
            raise_if_not_found=False,
        ),
    )
    make = fields.Char(string="Make / Brand")
    model = fields.Char(string="Model")
    serial_number = fields.Char(
        string="Serial / Identification Number",
        copy=False,
        index=True,
    )
    plate_number = fields.Char(string="Plate Number (Vehicles)")
    chassis_number = fields.Char(
        string="Chassis No.",
        copy=False,
        index=True,
    )
    intake_work_order_no = fields.Char(
        string="Work Order No.",
        copy=False,
        help="Work order / job card number recorded at vehicle intake.",
    )
    intake_line_ids = fields.One2many(
        comodel_name="workshop.equipment.intake.line",
        inverse_name="equipment_id",
        string="Vehicle Intake Checklist",
        copy=False,
    )
    intake_terms = fields.Html(
        string="Intake Terms",
        default=INTAKE_TERMS_HTML,
    )
    intake_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="workshop_equipment_intake_attachment_rel",
        column1="equipment_id",
        column2="attachment_id",
        string="Intake Photos / Documents",
        copy=False,
    )
    mileage_on_arrival = fields.Float(string="Mileage (on Arrival)")
    arrival_date = fields.Date(string="Arrival Date")
    workshop_status = fields.Selection(
        selection=[
            ("available", "Available"),
            ("in_workshop", "In Workshop"),
            ("released", "Released"),
        ],
        string="Workshop Status",
        default="available",
        required=True,
        copy=False,
        help="Set to In Workshop on intake / job creation. "
             "Set to Released when the financial gate allows vehicle handover.",
    )
    release_date = fields.Datetime(
        string="Last Release Date",
        copy=False,
    )
    town = fields.Char(string="Town")
    work_type = fields.Many2one(
        comodel_name="workshop.work.type",
        string="Type of Work",
        ondelete="set null",
        index=True,
    )
    phone = fields.Char(string="Tel")
    inspected_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Inspected By",
        default=lambda self: self.env.user,
        index=True,
    )
    warranty_end_date = fields.Date(
        string="Warranty End Date",
        readonly=True,
        help="Latest active Engine Overhaul / Gearbox warranty end date on this vehicle.",
    )
    warranty_status = fields.Selection(
        selection=[
            ("none", "No Warranty"),
            ("under_warranty", "Under Warranty"),
            ("expired", "Expired"),
        ],
        string="Warranty Status",
        compute="_compute_warranty_status",
        store=True,
    )
    warranty_ids = fields.One2many(
        comodel_name="workshop.warranty",
        inverse_name="equipment_id",
        string="Service Warranties",
    )
    job_order_ids = fields.One2many(
        comodel_name="workshop.job.order",
        inverse_name="equipment_id",
        string="Service History (Job Orders)",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    notes = fields.Html(string="Internal Notes")
    active = fields.Boolean(default=True)

    @api.depends("name", "serial_number", "plate_number")
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.name or ""]
            if rec.serial_number:
                parts.append(f"[{rec.serial_number}]")
            if rec.plate_number:
                parts.append(f"({rec.plate_number})")
            rec.display_name = " ".join(p for p in parts if p).strip() or rec.name or _("Equipment/Vehicle")

    @api.onchange("partner_id")
    def _onchange_partner_phone(self):
        if self.partner_id and not self.phone:
            self.phone = self.partner_id.phone

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("arrival_date") and not vals.get("workshop_status"):
                vals["workshop_status"] = "in_workshop"
        records = super().create(vals_list)
        records.filtered(lambda e: not e.intake_line_ids)._load_intake_checklist()
        return records

    def write(self, vals):
        if vals.get("arrival_date") and "workshop_status" not in vals:
            arriving = self.filtered(lambda e: e.workshop_status == "available")
            res = super().write(vals)
            if arriving:
                super(WorkshopEquipment, arriving).write({
                    "workshop_status": "in_workshop",
                })
            return res
        return super().write(vals)

    def _sync_workshop_status_from_jobs(self):
        """Keep equipment in-workshop until every linked job has released it."""
        Job = self.env["workshop.job.order"]
        for rec in self:
            jobs = Job.search([("equipment_id", "=", rec.id)])
            unreleased = jobs.filtered(lambda j: not j.vehicle_released)
            if unreleased:
                rec.workshop_status = "in_workshop"
                continue
            released = jobs.filtered("vehicle_released").sorted(
                "vehicle_release_date", reverse=True
            )
            if released:
                rec.workshop_status = "released"
                rec.release_date = released[0].vehicle_release_date
            elif rec.arrival_date:
                rec.workshop_status = "in_workshop"

    def action_load_intake_checklist(self):
        self._load_intake_checklist()
        return True

    def _load_intake_checklist(self, replace=False):
        items = self.env["workshop.equipment.intake.item"].search([
            ("active", "=", True),
        ])
        for rec in self:
            if replace:
                rec.intake_line_ids.unlink()
            existing_item_ids = set(rec.intake_line_ids.template_item_id.ids)
            existing_names = set(rec.intake_line_ids.mapped("name"))
            commands = []
            for item in items:
                if item.id in existing_item_ids or item.name in existing_names:
                    continue
                commands.append((0, 0, {
                    "template_item_id": item.id,
                    "sequence": item.sequence,
                    "name": item.name,
                    "quantity": 1.0,
                }))
            if commands:
                rec.write({"intake_line_ids": commands})

    @api.depends(
        "warranty_end_date",
        "warranty_ids.date_end",
        "warranty_ids.is_cancelled",
        "warranty_ids.state",
    )
    def _compute_warranty_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            warranties = rec.warranty_ids.filtered(lambda w: not w.is_cancelled)
            active = warranties.filtered(lambda w: w.date_end and w.date_end >= today)
            if active:
                rec.warranty_status = "under_warranty"
            elif warranties:
                rec.warranty_status = "expired"
            else:
                rec.warranty_status = "none"

    def find_active_warranty(self, task=None, kind=None, date=None, exclude_job=None):
        """Return the active Engine Overhaul / Gearbox warranty covering this visit."""
        self.ensure_one()
        date = fields.Date.to_date(date or fields.Date.context_today(self))
        if task:
            if not task.is_warrantable or not task.warranty_kind:
                return self.env["workshop.warranty"]
            kind = task.warranty_kind
        if not kind:
            return self.env["workshop.warranty"]
        warranties = self.warranty_ids.filtered(
            lambda w: not w.is_cancelled
            and w.warranty_kind == kind
            and w.date_start
            and w.date_end
            and w.date_start <= date <= w.date_end
            and (not exclude_job or w.job_order_id != exclude_job)
        )
        return warranties[:1]

    def _sync_warranty_end_date(self):
        today = fields.Date.context_today(self)
        for rec in self:
            active = rec.warranty_ids.filtered(
                lambda w: not w.is_cancelled and w.date_end and w.date_end >= today
            )
            rec.warranty_end_date = max(active.mapped("date_end")) if active else False

    def action_view_warranties(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Service Warranties"),
            "res_model": "workshop.warranty",
            "view_mode": "list,form",
            "domain": [("equipment_id", "=", self.id)],
            "context": {"default_equipment_id": self.id, "default_partner_id": self.partner_id.id},
        }
