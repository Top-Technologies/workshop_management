from odoo import fields, models, _


class WorkshopApprovalWizard(models.TransientModel):
    """Wizard for approving or rejecting a Workshop Job Order with comments."""

    _name = "workshop.approval.wizard"
    _description = "Workshop Approval / Rejection Wizard"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Job Order",
        required=True,
    )
    action_type = fields.Selection(
        selection=[
            ("approve", "Approve"),
            ("reject", "Reject"),
        ],
        string="Action",
        required=True,
        default="approve",
    )
    comments = fields.Text(
        string="Comments / Reason",
        required=True,
    )

    def action_confirm_decision(self):
        self.ensure_one()
        jo = self.job_order_id
        if self.action_type == "approve":
            jo.action_approve()
            # Enrich last log with wizard comments
            last_log = jo.approval_log_ids[:1]
            if last_log and self.comments:
                last_log.write({
                    "comments": "%s — %s" % (last_log.comments or "", self.comments),
                })
        else:
            jo.action_reject()
            last_log = jo.approval_log_ids[:1]
            if last_log and self.comments:
                last_log.write({"comments": self.comments})
        return {"type": "ir.actions.act_window_close"}
