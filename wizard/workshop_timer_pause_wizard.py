from odoo import fields, models, _
from odoo.exceptions import UserError

from ..models.workshop_work_order import TIMER_PAUSE_REASONS


class WorkshopTimerPauseWizard(models.TransientModel):
    """Require a clock-out reason before pausing the Work Dispatch timer."""

    _name = "workshop.timer.pause.wizard"
    _description = "Pause Timer Reason"

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
    timer_elapsed_hours = fields.Float(
        related="work_order_id.timer_elapsed_hours",
        readonly=True,
    )
    pause_reason = fields.Selection(
        selection=TIMER_PAUSE_REASONS,
        string="Pause Reason",
        required=True,
    )
    notes = fields.Text(string="Notes")

    def action_confirm(self):
        self.ensure_one()
        if not self.pause_reason:
            raise UserError(_("Select a pause reason before pausing the timer."))
        self.work_order_id.action_timer_pause(
            reason=self.pause_reason,
            notes=self.notes,
        )
        return {"type": "ir.actions.act_window_close"}
