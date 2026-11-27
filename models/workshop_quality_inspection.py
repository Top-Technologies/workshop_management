from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WorkshopQualityChecklistItem(models.Model):
    """Reusable quality checklist template lines by department."""

    _name = "workshop.quality.checklist.item"
    _description = "Workshop Quality Checklist Template Item"
    _order = "sequence, name"

    name = fields.Char(string="Checklist Item", required=True)
    department = fields.Many2one(
        comodel_name="workshop.department",
        string="Department",
        ondelete="set null",
        help="Leave empty to apply to all departments.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )


class WorkshopQualityInspection(models.Model):
    """Quality inspection checklist for Job Orders & Work Orders."""

    _name = "workshop.quality.inspection"
    _description = "Workshop Quality Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="Inspection Ref",
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
        ondelete="cascade",
        index=True,
    )
    inspector_id = fields.Many2one(
        comodel_name="res.users",
        string="Inspector",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    date_inspection = fields.Datetime(
        string="Inspection Date",
        default=fields.Datetime.now,
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name="workshop.quality.inspection.line",
        inverse_name="inspection_id",
        string="Checklist Items",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("pass", "Passed"),
            ("fail", "Failed"),
        ],
        string="Inspection Result",
        default="draft",
        required=True,
        tracking=True,
    )
    notes = fields.Text(string="Inspection Remarks")
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="workshop_quality_inspection_attachment_rel",
        column1="inspection_id",
        column2="attachment_id",
        string="Inspection Photos / Documents",
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "workshop.quality.inspection"
                ) or "QI-0001"
        return super().create(vals_list)

    def action_load_checklist(self):
        for rec in self:
            department = rec.work_order_id.department.id if rec.work_order_id.department else False
            items = self.env["workshop.quality.checklist.item"].search([
                "|",
                ("department", "=", department),
                ("department", "=", False),
                ("active", "=", True),
            ])
            if not items:
                raise UserError(_("No checklist template items found. Configure them under Configuration."))
            rec.line_ids.unlink()
            rec.write({
                "line_ids": [(0, 0, {"name": item.name, "passed": False}) for item in items],
            })

    def action_pass(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add checklist items (or load template) before passing."))
            failed_lines = rec.line_ids.filtered(lambda l: not l.passed)
            if failed_lines:
                raise UserError(_(
                    "Cannot pass inspection: unchecked items remain (%s)."
                ) % ", ".join(failed_lines.mapped("name")))
            rec.write({"state": "pass"})

    def action_fail(self):
        for rec in self:
            rec.write({"state": "fail"})
            if rec.work_order_id and rec.work_order_id.state in ("done", "verified"):
                rec.work_order_id.action_rework()


class WorkshopQualityInspectionLine(models.Model):
    """Checklist item for quality inspection."""

    _name = "workshop.quality.inspection.line"
    _description = "Workshop Quality Inspection Line"

    inspection_id = fields.Many2one(
        comodel_name="workshop.quality.inspection",
        string="Quality Inspection",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(
        string="Checklist Item",
        required=True,
    )
    passed = fields.Boolean(
        string="Pass",
        default=False,
    )
    notes = fields.Char(string="Remarks / Defect Details")
