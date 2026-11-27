# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    job_order_id = fields.Many2one(
        comodel_name="workshop.job.order",
        string="Workshop Job Order",
        index=True,
        ondelete="set null",
        copy=False,
    )

    @api.depends("approver_ids.status", "approver_ids.required")
    def _compute_request_status(self):
        previous = {request.id: request.request_status for request in self}
        super()._compute_request_status()
        for request in self.filtered("job_order_id"):
            if request.request_status != previous.get(request.id):
                request.job_order_id._apply_odoo_approval_result(request.request_status)


class WorkshopJobOrderApproval(models.Model):
    _inherit = "workshop.job.order"

    approval_request_id = fields.Many2one(
        comodel_name="approval.request",
        string="Approval Request",
        copy=False,
        readonly=True,
    )
    approval_request_count = fields.Integer(
        compute="_compute_approval_request_count",
    )

    @api.depends("approval_request_id")
    def _compute_approval_request_count(self):
        for rec in self:
            rec.approval_request_count = 1 if rec.approval_request_id else 0

    def _get_approval_category(self, rule):
        """Resolve Odoo Approvals category from workshop rule or defaults."""
        self.ensure_one()
        if rule and rule.category_id:
            return rule.category_id
        xmlid = (
            "workshop_management.approval_category_workshop_job_manager"
            if self.manager_approval_required
            else "workshop_management.approval_category_workshop_job_standard"
        )
        category = self.env.ref(xmlid, raise_if_not_found=False)
        if not category:
            raise UserError(_(
                "Workshop approval categories are missing. "
                "Upgrade the Workshop Management module."
            ))
        return category

    def _get_approval_reason_html(self):
        self.ensure_one()
        parts = [
            "<p><strong>%s</strong></p>" % _("Workshop Job Order Approval"),
            "<ul>",
            "<li>%s: %s</li>" % (_("Job Order"), self.name),
            "<li>%s: %s</li>" % (_("Customer"), self.partner_id.display_name if self.partner_id else "-"),
            "<li>%s: %s</li>" % (_("Equipment/Vehicle"), self.equipment_id.display_name if self.equipment_id else "-"),
            "<li>%s: %.2f</li>" % (_("Estimated Amount"), self._get_approval_amount()),
            "</ul>",
        ]
        if self.request_id and self.request_id.complaint:
            parts.append("<p>%s</p>" % self.request_id.complaint)
        return "".join(parts)

    def _prepare_odoo_approval_approvers(self, category, needs_manager):
        """Build approver lines from Workshop Supervisor / Manager groups."""
        supervisor_group = self.env.ref(
            "workshop_management.group_workshop_supervisor",
            raise_if_not_found=False,
        )
        manager_group = self.env.ref(
            "workshop_management.group_workshop_manager",
            raise_if_not_found=False,
        )
        supervisors = supervisor_group.all_user_ids if supervisor_group else self.env["res.users"]
        managers = manager_group.all_user_ids if manager_group else self.env["res.users"]

        if not supervisors:
            raise UserError(_(
                "No Workshop Supervisor users are configured. "
                "Assign users to Workshop / Supervisor before submitting approvals."
            ))

        commands = [fields.Command.clear()]
        if category.approver_sequence and needs_manager:
            if not managers:
                raise UserError(_(
                    "No Workshop Manager users are configured. "
                    "Assign users to Workshop / Manager for high-value job approvals."
                ))
            commands.append(fields.Command.create({
                "user_id": supervisors[0].id,
                "status": "new",
                "required": True,
                "sequence": 10,
            }))
            commands.append(fields.Command.create({
                "user_id": managers[0].id,
                "status": "new",
                "required": True,
                "sequence": 20,
            }))
        else:
            for seq, user in enumerate(supervisors):
                commands.append(fields.Command.create({
                    "user_id": user.id,
                    "status": "new",
                    "required": seq == 0,
                    "sequence": 10 + seq,
                }))
        return commands

    def _log_approval_action(self, action, comments):
        self.ensure_one()
        self.env["workshop.approval.log"].create({
            "job_order_id": self.id,
            "user_id": self.env.uid,
            "action": action,
            "comments": comments,
        })

    def _apply_odoo_approval_result(self, request_status):
        """Sync Job Order state from linked approval.request status."""
        self.ensure_one()
        if request_status == "approved":
            if self.state != "approved":
                self.write({
                    "approval_state": "approved",
                    "state": "approved",
                })
                self._log_approval_action("approve", _("Approved via Approvals app."))
                self.message_post(body=_("Job Order approved via Approvals."))
        elif request_status == "refused":
            if self.state == "waiting_approval":
                self.write({
                    "approval_state": "rejected",
                    "state": "draft",
                })
                self._log_approval_action("reject", _("Refused via Approvals app."))
                self.message_post(body=_("Job Order approval refused."))
        elif request_status == "cancel":
            if self.state == "waiting_approval":
                self.write({
                    "approval_state": "draft",
                    "state": "draft",
                    "approval_request_id": False,
                })
                self.message_post(body=_("Job Order approval request cancelled."))
        elif request_status == "pending":
            manager_group = self.env.ref(
                "workshop_management.group_workshop_manager",
                raise_if_not_found=False,
            )
            manager_users = manager_group.all_user_ids if manager_group else self.env["res.users"]
            pending = self.approval_request_id.approver_ids.filtered(
                lambda a: a.status == "pending"
            )
            approval_state = "supervisor_review"
            if manager_users and pending and pending[0].user_id in manager_users:
                approval_state = "manager_review"
            self.write({
                "approval_state": approval_state,
                "state": "waiting_approval",
            })

    def action_submit_approval(self):
        """Create an Odoo Approvals request and submit it to configured approvers."""
        ApprovalRequest = self.env["approval.request"]
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft Job Orders can be submitted for approval."))
            if rec.approval_request_id and rec.approval_request_id.request_status in (
                "new", "pending"
            ):
                raise UserError(_(
                    "An approval request is already in progress for Job Order %s."
                ) % rec.name)

            rule = rec._match_approval_rule()
            manager_group = self.env.ref(
                "workshop_management.group_workshop_manager",
                raise_if_not_found=False,
            )
            needs_manager = bool(
                rule and manager_group and rule.group_id == manager_group
            )
            category = rec._get_approval_category(rule)

            rec.write({
                "manager_approval_required": needs_manager,
                "required_approver_group_id": (
                    rule.group_id.id if rule else False
                ),
            })

            approval = ApprovalRequest.create({
                "name": _("Job Order %s") % rec.name,
                "category_id": category.id,
                "request_owner_id": rec.env.user.id,
                "reference": rec.name,
                "amount": rec._get_approval_amount(),
                "partner_id": rec.partner_id.id,
                "reason": rec._get_approval_reason_html(),
                "job_order_id": rec.id,
            })
            approval.write({
                "approver_ids": rec._prepare_odoo_approval_approvers(
                    category, needs_manager
                ),
            })
            approval.action_confirm()

            rec.write({
                "approval_request_id": approval.id,
                "approval_state": (
                    "manager_review" if needs_manager and category.approver_sequence
                    else "supervisor_review"
                ),
                "state": "waiting_approval",
            })
            rec._log_approval_action(
                "submit",
                _(
                    "Submitted to Approvals (Amount: %(amount).2f, Category: %(category)s)."
                ) % {
                    "amount": rec._get_approval_amount(),
                    "category": category.name,
                },
            )
            rec.message_post(
                body=_(
                    "Approval request %(name)s submitted. "
                    "Approvers can review it in the Approvals app."
                ) % {"name": approval.name},
            )

    def action_view_approval_request(self):
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError(_("No approval request linked to this Job Order."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Request"),
            "res_model": "approval.request",
            "res_id": self.approval_request_id.id,
            "view_mode": "form",
        }

    def action_open_approval_wizard(self):
        """Legacy entry point — open the linked Approvals request."""
        return self.action_view_approval_request()
