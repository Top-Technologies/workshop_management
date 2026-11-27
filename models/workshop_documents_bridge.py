from odoo import api, models, _


class WorkshopJobOrderDocuments(models.Model):
    """File Job Order attachments into Documents (Enterprise)."""

    _name = "workshop.job.order"
    _inherit = ["workshop.job.order", "documents.mixin"]

    def _get_document_folder(self):
        self.ensure_one()
        company = self.company_id
        if not company.documents_workshop_settings:
            return False
        helper = self.env["workshop.documents.helper"]
        folders = helper.ensure_workshop_folders(company)
        return folders["completion"]

    def _check_create_documents(self):
        return bool(
            self.company_id.documents_workshop_settings
            and self._get_document_folder()
        )

    def action_open_documents(self):
        """Open Documents filtered to this Job Order's attachments."""
        self.ensure_one()
        domain = [
            ("res_model", "=", "workshop.job.order"),
            ("res_id", "=", self.id),
        ]
        if self.equipment_id:
            domain = [
                "|",
                "&", ("res_model", "=", "workshop.job.order"), ("res_id", "=", self.id),
                "&", ("res_model", "=", "workshop.equipment"), ("res_id", "=", self.equipment_id.id),
            ]
        attachments = self.env["ir.attachment"].search(domain)
        docs = self.env["documents.document"].search([
            ("attachment_id", "in", attachments.ids),
        ])
        folder = self._get_document_folder()
        return {
            "type": "ir.actions.act_window",
            "name": _("Documents"),
            "res_model": "documents.document",
            "view_mode": "kanban,list,form",
            "domain": [("id", "in", docs.ids)] if docs else [("id", "=", False)],
            "context": {
                "default_folder_id": folder.id if folder else False,
                "searchpanel_default_folder_id": folder.id if folder else False,
            },
        }

    def _archive_completion_form(self):
        """Generate PDF attachment, then ensure it appears in Documents."""
        attachment = super()._archive_completion_form()
        if not attachment:
            return attachment
        company = self.company_id
        if not company.documents_workshop_settings:
            return attachment
        helper = self.env["workshop.documents.helper"]
        folders = helper.ensure_workshop_folders(company)
        doc = helper.create_document_from_attachment(
            attachment,
            folders["completion"],
            partner=self.partner_id,
        )
        if self.equipment_id:
            equip_att = self.env["ir.attachment"].search([
                ("res_model", "=", "workshop.equipment"),
                ("res_id", "=", self.equipment_id.id),
                ("name", "=", attachment.name),
            ], limit=1)
            if equip_att:
                helper.create_document_from_attachment(
                    equip_att,
                    folders["equipment"],
                    partner=self.partner_id,
                )
        if doc:
            self.message_post(body=_(
                "Completion form archived in Documents: %s"
            ) % doc.display_name)
        return attachment


class WorkshopEquipmentDocuments(models.Model):
    """File Equipment attachments into Documents (Enterprise)."""

    _name = "workshop.equipment"
    _inherit = ["workshop.equipment", "documents.mixin"]

    def _get_document_folder(self):
        self.ensure_one()
        company = self.company_id
        if not company.documents_workshop_settings:
            return False
        helper = self.env["workshop.documents.helper"]
        folders = helper.ensure_workshop_folders(company)
        return folders["equipment"]

    def _check_create_documents(self):
        return bool(
            self.company_id.documents_workshop_settings
            and self._get_document_folder()
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_intake_attachments_to_documents()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "intake_attachment_ids" in vals:
            self._sync_intake_attachments_to_documents()
        return res

    def _sync_intake_attachments_to_documents(self):
        helper = self.env["workshop.documents.helper"]
        for rec in self:
            if not rec.id or not rec.company_id.documents_workshop_settings:
                continue
            folders = helper.ensure_workshop_folders(rec.company_id)
            for att in rec.intake_attachment_ids:
                if not att.res_model:
                    att.with_context(skip_document_sync=True).write({
                        "res_model": "workshop.equipment",
                        "res_id": rec.id,
                    })
                helper.create_document_from_attachment(
                    att,
                    folders["equipment"],
                    partner=rec.partner_id,
                )


class WorkshopRequestDocuments(models.Model):
    """File Workshop Request inspection photos into Documents (Enterprise)."""

    _name = "workshop.request"
    _inherit = ["workshop.request", "documents.mixin"]

    def _get_document_folder(self):
        self.ensure_one()
        company = self.company_id
        if not company.documents_workshop_settings:
            return False
        helper = self.env["workshop.documents.helper"]
        folders = helper.ensure_workshop_folders(company)
        return folders["inspection"]

    def _check_create_documents(self):
        return bool(
            self.company_id.documents_workshop_settings
            and self._get_document_folder()
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_inspection_photos_to_documents()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "inspection_photo_ids" in vals:
            self._sync_inspection_photos_to_documents()
        return res

    def _sync_inspection_photos_to_documents(self):
        helper = self.env["workshop.documents.helper"]
        for rec in self:
            if not rec.id or not rec.company_id.documents_workshop_settings:
                continue
            folders = helper.ensure_workshop_folders(rec.company_id)
            for att in rec.inspection_photo_ids:
                # Avoid writing attachments mid-upload (causes FileInput remount crash)
                if not att.res_model:
                    att.with_context(skip_document_sync=True).write({
                        "res_model": "workshop.request",
                        "res_id": rec.id,
                    })
                helper.create_document_from_attachment(
                    att,
                    folders["inspection"],
                    partner=rec.partner_id,
                )


class WorkshopQualityInspectionDocuments(models.Model):
    """File Quality Inspection photos into Documents (Enterprise)."""

    _name = "workshop.quality.inspection"
    _inherit = ["workshop.quality.inspection", "documents.mixin"]

    def _get_document_folder(self):
        self.ensure_one()
        company = self.company_id
        if not company.documents_workshop_settings:
            return False
        helper = self.env["workshop.documents.helper"]
        folders = helper.ensure_workshop_folders(company)
        return folders["inspection"]

    def _check_create_documents(self):
        return bool(
            self.company_id.documents_workshop_settings
            and self._get_document_folder()
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_qi_attachments_to_documents()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "attachment_ids" in vals:
            self._sync_qi_attachments_to_documents()
        return res

    def _sync_qi_attachments_to_documents(self):
        helper = self.env["workshop.documents.helper"]
        for rec in self:
            if not rec.id or not rec.company_id.documents_workshop_settings:
                continue
            folders = helper.ensure_workshop_folders(rec.company_id)
            partner = rec.job_order_id.partner_id
            for att in rec.attachment_ids:
                if not att.res_model:
                    att.with_context(skip_document_sync=True).write({
                        "res_model": "workshop.quality.inspection",
                        "res_id": rec.id,
                    })
                helper.create_document_from_attachment(
                    att,
                    folders["inspection"],
                    partner=partner,
                )
