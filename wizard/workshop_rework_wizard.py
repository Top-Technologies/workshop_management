from odoo import api, fields, models

from ..models.workshop_work_order import REWORK_CAUSES, REWORK_WHO_PAYS


class WorkshopReworkWizard(models.TransientModel):
    """Capture rework cause, who pays, and notes before sending a Work Order back."""

    _name = "workshop.rework.wizard"
    _description = "Workshop Rework Wizard"

    work_order_id = fields.Many2one(
        comodel_name="workshop.work.order",
        string="Work Dispatch",
        required=True,
        ondelete="cascade",
    )
    job_order_id = fields.Many2one(
        related="work_order_id.job_order_id",
        readonly=True,
    )
    actual_hours = fields.Float(
        related="work_order_id.actual_hours",
        readonly=True,
    )
    rework_hours_at_fail = fields.Float(
        related="work_order_id.rework_hours_at_fail",
        readonly=True,
    )
    extra_hours_so_far = fields.Float(
        string="Extra Hours So Far",
        compute="_compute_extra_hours_so_far",
    )
    rework_cause = fields.Selection(
        selection=REWORK_CAUSES,
        string="Cause",
        required=True,
        default="quality_fail",
    )
    rework_who_pays = fields.Selection(
        selection=REWORK_WHO_PAYS,
        string="Who Pays",
        required=True,
        default="workshop",
    )
    notes = fields.Text(string="Notes")

    @api.depends("actual_hours", "rework_hours_at_fail")
    def _compute_extra_hours_so_far(self):
        for wiz in self:
            baseline = wiz.rework_hours_at_fail or wiz.actual_hours
            wiz.extra_hours_so_far = max(wiz.actual_hours - baseline, 0.0)

    def action_confirm(self):
        self.ensure_one()
        self.work_order_id.action_rework(
            cause=self.rework_cause,
            who_pays=self.rework_who_pays,
            notes=self.notes,
        )
        return {"type": "ir.actions.act_window_close"}
