from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WorkshopTechnicianAssignment(models.TransientModel):
    """Wizard to explode estimate labor lines into a work pack."""

    _name = "workshop.technician.assignment"
    _description = "Workshop Technician Assignment Wizard"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Job Order",
        required=True,
    )
    is_field_job = fields.Boolean(
        related="job_order_id.is_field_job",
        readonly=True,
    )
    default_technician_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Default Technician",
        help="Applied to pack lines that have no technician yet.",
    )
    line_ids = fields.One2many(
        comodel_name="workshop.technician.assignment.line",
        inverse_name="wizard_id",
        string="Work Pack",
    )
    create_field_visit = fields.Boolean(
        string="Schedule Field Visit",
        help="Create a field service visit when assigning a technician to a field job.",
    )
    visit_scheduled_start = fields.Datetime(string="Visit Scheduled Start")
    visit_scheduled_end = fields.Datetime(string="Visit Scheduled End")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        job_id = res.get("job_order_id") or self.env.context.get("default_job_order_id")
        if not job_id:
            return res
        job = self.env["workshop.job.order"].browse(job_id)
        res["job_order_id"] = job.id
        if "create_field_visit" in fields_list or not fields_list:
            res["create_field_visit"] = bool(job.is_field_job)
        lines = []
        labor_lines = job.request_id.line_ids.filtered(lambda l: l.line_type == "labor")
        default_dept = self.env["workshop.department"]._default_department()
        for line in labor_lines:
            task = line.task_id
            dept = task.department if task and task.department else default_dept
            lines.append((0, 0, {
                "request_line_id": line.id,
                "task_id": task.id if task else False,
                "name": line.name
                or (task.name if task else (line.product_id.display_name if line.product_id else "")),
                "department": dept.id if dept else False,
                "planned_hours": line.quantity or (task.standard_hours if task else 1.0),
            }))
        if not lines:
            lines = [(0, 0, {
                "department": default_dept.id if default_dept else False,
                "planned_hours": 1.0,
            })]
        res["line_ids"] = lines
        return res

    @api.onchange("default_technician_id")
    def _onchange_default_technician_id(self):
        if not self.default_technician_id:
            return
        for line in self.line_ids:
            if not line.technician_id:
                line.technician_id = self.default_technician_id

    def action_assign_and_create_work_order(self):
        """Create one Work Order per pack line."""
        self.ensure_one()
        if self.job_order_id.state not in ["approved", "assigned", "in_progress"]:
            raise UserError(_("Work orders can only be assigned after Job Order is approved."))
        if not self.line_ids:
            raise UserError(_("Add at least one work pack line."))

        cursor = fields.Datetime.now()
        created = self.env["workshop.work.order"]
        first_technician = self.env["hr.employee"]
        for line in self.line_ids:
            technician = line.technician_id or self.default_technician_id
            if not technician:
                raise UserError(_("Set a technician on every pack line, or choose a Default Technician."))
            if not technician.user_id:
                raise UserError(_(
                    "Employee %(name)s has no linked User. "
                    "Open the employee form and set Related User so the technician can see their Work Dispatches."
                ) % {"name": technician.display_name})
            start = line.planned_start or cursor
            hours = line.planned_hours or 1.0
            finish = line.planned_finish or (start + timedelta(hours=hours))
            if not line.department:
                raise UserError(_("Set a department on every work pack line."))
            created |= self.env["workshop.work.order"].create({
                "job_order_id": self.job_order_id.id,
                "department": line.department.id,
                "technician_id": technician.id,
                "user_id": technician.user_id.id,
                "task_id": line.task_id.id if line.task_id else False,
                "request_line_id": line.request_line_id.id if line.request_line_id else False,
                "standard_hours": line.task_id.standard_hours if line.task_id else hours,
                "planned_hours": hours,
                "planned_start": start,
                "planned_finish": finish,
                "notes": line.name or False,
                "state": "assigned",
            })
            if not first_technician:
                first_technician = technician
            if not line.planned_start:
                cursor = finish

        if self.job_order_id.state == "approved":
            self.job_order_id.write({"state": "assigned"})

        if self.create_field_visit and self.job_order_id.is_field_job:
            self.env["workshop.field.visit"].create({
                "job_order_id": self.job_order_id.id,
                "technician_id": first_technician.id,
                "scheduled_start": self.visit_scheduled_start,
                "scheduled_end": self.visit_scheduled_end,
                "state": "scheduled" if self.visit_scheduled_start else "draft",
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Work Dispatches"),
            "res_model": "workshop.work.order",
            "view_mode": "kanban,calendar,list,form",
            "domain": [("job_order_id", "=", self.job_order_id.id)],
            "context": {"default_job_order_id": self.job_order_id.id},
            "views": [
                (False, "kanban"),
                (False, "calendar"),
                (False, "list"),
                (False, "form"),
            ],
        }


class WorkshopTechnicianAssignmentLine(models.TransientModel):
    """One work pack line, usually mapped from a labor estimate."""

    _name = "workshop.technician.assignment.line"
    _description = "Workshop Technician Assignment Line"

    wizard_id = fields.Many2one(
        comodel_name="workshop.technician.assignment",
        required=True,
        ondelete="cascade",
    )
    request_line_id = fields.Many2one(
        comodel_name="workshop.request.line",
        string="Estimate Line",
        ondelete="set null",
    )
    name = fields.Char(string="Job Description")
    task_id = fields.Many2one(
        comodel_name="workshop.task.master",
        string="Job Description",
        ondelete="set null",
    )
    department = fields.Many2one(
        comodel_name="workshop.department",
        string="Department",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["workshop.department"]._default_department(),
    )
    technician_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Technician",
    )
    planned_hours = fields.Float(string="Standard Hours", default=1.0, required=True)
    planned_start = fields.Datetime(string="Planned Start")
    planned_finish = fields.Datetime(string="Planned Finish")

    @api.onchange("task_id")
    def _onchange_task_id(self):
        if self.task_id:
            self.department = self.task_id.department
            self.planned_hours = self.task_id.standard_hours
            if not self.name:
                self.name = self.task_id.name
