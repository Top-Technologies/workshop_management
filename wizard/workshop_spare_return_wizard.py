from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from ..models.workshop_spare_request import SPARE_RETURN_REASONS


class WorkshopSpareReturnWizard(models.TransientModel):
    """Technician flags unused, non-fitting, or defective issued parts."""

    _name = "workshop.spare.return.wizard"
    _description = "Flag Spare Parts for Return"

    spare_request_id = fields.Many2one(
        comodel_name="workshop.spare.request",
        string="Spare Request",
        required=True,
        ondelete="cascade",
    )
    job_order_id = fields.Many2one(
        related="spare_request_id.job_order_id",
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="workshop.spare.return.wizard.line",
        inverse_name="wizard_id",
        string="Parts to Flag",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request = self.env["workshop.spare.request"].browse(
            res.get("spare_request_id") or self.env.context.get("default_spare_request_id")
        )
        if request:
            res["spare_request_id"] = request.id
            commands = []
            for line in request.line_ids:
                remaining = line._qty_remaining_on_job()
                if float_compare(remaining, 0.0, precision_digits=2) <= 0:
                    continue
                commands.append((0, 0, {
                    "spare_line_id": line.id,
                    "qty_remaining": remaining,
                    "qty": 0.0,
                    "reason": "wrong_fit",
                    "request_replacement": True,
                }))
            res["line_ids"] = commands
        return res

    def action_flag(self):
        self.ensure_one()
        vals_list = []
        for line in self.line_ids:
            if float_compare(line.qty, 0.0, precision_digits=2) <= 0:
                continue
            vals_list.append({
                "spare_line_id": line.spare_line_id.id,
                "qty": line.qty,
                "reason": line.reason,
                "request_replacement": line.request_replacement,
                "notes": line.notes,
            })
        if not vals_list:
            raise UserError(_("Enter a quantity on at least one part to flag."))
        self.spare_request_id.action_flag_returns(vals_list)
        return {"type": "ir.actions.act_window_close"}


class WorkshopSpareReturnWizardLine(models.TransientModel):
    _name = "workshop.spare.return.wizard.line"
    _description = "Flag Spare Parts Line"

    wizard_id = fields.Many2one(
        comodel_name="workshop.spare.return.wizard",
        required=True,
        ondelete="cascade",
    )
    spare_line_id = fields.Many2one(
        comodel_name="workshop.spare.request.line",
        string="Spare Line",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        related="spare_line_id.product_id",
        readonly=True,
    )
    qty_remaining = fields.Float(string="Remaining on Job", readonly=True)
    qty = fields.Float(string="Qty to Flag")
    reason = fields.Selection(
        selection=SPARE_RETURN_REASONS,
        string="Reason",
        required=True,
        default="wrong_fit",
    )
    request_replacement = fields.Boolean(
        string="Request Replacement",
        default=True,
    )
    notes = fields.Char(string="Notes")

    @api.onchange("reason")
    def _onchange_reason(self):
        self.request_replacement = self.reason in ("wrong_fit", "defective")
