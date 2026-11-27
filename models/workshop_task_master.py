from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


WARRANTY_KINDS = [
    ("engine_overhaul", "Engine Overhaul"),
    ("gearbox", "Gearbox"),
]


class WorkshopTaskMaster(models.Model):
    """Standard repair task catalogue."""

    _name = "workshop.task.master"
    _description = "Workshop Task Master"
    _order = "code, name"

    code = fields.Char(
        string="Code",
        required=True,
        index=True,
    )
    name = fields.Char(
        string="Job Description",
        required=True,
        translate=True,
    )
    description = fields.Text(string="Job Details")
    department_id = fields.Many2one(
        comodel_name="hr.department",
        string="HR Department",
        ondelete="set null",
        index=True,
    )
    department = fields.Many2one(
        comodel_name="workshop.department",
        string="Department",
        required=True,
        ondelete="restrict",
        index=True,
        default=lambda self: self.env["workshop.department"]._default_department(),
    )
    standard_hours = fields.Float(
        string="Standard Hours",
        default=1.0,
        required=True,
        help="Predefined expected labor time per task.",
    )
    estimated_hours = fields.Float(
        string="Estimated Hours",
        related="standard_hours",
        readonly=False,
    )
    is_warrantable = fields.Boolean(
        string="Warrantable Service",
        default=False,
        help="Only Engine Overhaul and Gearbox grant a workmanship warranty.",
    )
    warranty_kind = fields.Selection(
        selection=WARRANTY_KINDS,
        string="Warranty Service",
        help="Engine Overhaul or Gearbox. Other jobs never start or consume warranty.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Task code must be unique.",
    )

    @api.constrains("is_warrantable", "warranty_kind")
    def _check_warrantable_kind(self):
        for rec in self:
            if rec.is_warrantable and not rec.warranty_kind:
                raise ValidationError(_(
                    "Warrantable jobs must be Engine Overhaul or Gearbox."
                ))
