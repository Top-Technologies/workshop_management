from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    documents_workshop_settings = fields.Boolean(
        string="Workshop Documents",
        default=True,
        help="Automatically file workshop attachments into the Documents app.",
    )
    documents_workshop_folder_id = fields.Many2one(
        comodel_name="documents.document",
        string="Workshop Workspace",
        domain="[('type', '=', 'folder')]",
        help="Root Documents folder/workspace for Workshop Management.",
    )
    documents_workshop_completion_folder_id = fields.Many2one(
        comodel_name="documents.document",
        string="Job Completions Folder",
        domain="[('type', '=', 'folder')]",
    )
    documents_workshop_equipment_folder_id = fields.Many2one(
        comodel_name="documents.document",
        string="Equipment History Folder",
        domain="[('type', '=', 'folder')]",
    )
    documents_workshop_inspection_folder_id = fields.Many2one(
        comodel_name="documents.document",
        string="Inspection Photos Folder",
        domain="[('type', '=', 'folder')]",
    )
    workshop_default_labor_rate = fields.Float(
        string="Default Labor Rate",
        default=50.0,
        help="Fallback hourly labor rate when no customer-type / pricelist "
             "rule matches and the technician has no Workshop Hourly Cost.",
    )
    workshop_labor_rate_rule_ids = fields.One2many(
        comodel_name="workshop.labor.rate.rule",
        inverse_name="company_id",
        string="Labor Rate Rules",
    )
    workshop_financial_gate = fields.Boolean(
        string="Vehicle Release Financial Gate",
        default=True,
        help="Two-way vehicle-release financial gate:\n"
             "1. Corporate / trusted / credit clients: allow vehicle release "
             "on credit with pending-payment tracking (urgent turnaround).\n"
             "2. New / standard clients: block vehicle release until every "
             "customer invoice is fully marked as paid.",
    )
    workshop_expense_margin_percent = fields.Float(
        string="Field Expense Profit Margin (%)",
        default=20.0,
        help="Target company margin on Foreman-approved field-staff expenses. "
             "20% means a 100 out-of-pocket cost is billed to the customer at 125.",
    )
    workshop_expense_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Field Expense Recovery Product",
        domain="[('sale_ok', '=', True)]",
        help="Service product added to the Sales Order when a field expense is approved.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    documents_workshop_settings = fields.Boolean(
        related="company_id.documents_workshop_settings",
        readonly=False,
    )
    documents_workshop_folder_id = fields.Many2one(
        related="company_id.documents_workshop_folder_id",
        readonly=False,
    )
    documents_workshop_completion_folder_id = fields.Many2one(
        related="company_id.documents_workshop_completion_folder_id",
        readonly=False,
    )
    documents_workshop_equipment_folder_id = fields.Many2one(
        related="company_id.documents_workshop_equipment_folder_id",
        readonly=False,
    )
    documents_workshop_inspection_folder_id = fields.Many2one(
        related="company_id.documents_workshop_inspection_folder_id",
        readonly=False,
    )
    workshop_default_labor_rate = fields.Float(
        related="company_id.workshop_default_labor_rate",
        readonly=False,
    )
    workshop_financial_gate = fields.Boolean(
        related="company_id.workshop_financial_gate",
        readonly=False,
    )
    workshop_expense_margin_percent = fields.Float(
        related="company_id.workshop_expense_margin_percent",
        readonly=False,
    )
    workshop_expense_product_id = fields.Many2one(
        related="company_id.workshop_expense_product_id",
        readonly=False,
    )


class DocumentsWorkshopFolderHelper(models.AbstractModel):
    """Helpers to create / resolve Workshop folders in Documents (Odoo 18+/19)."""

    _name = "workshop.documents.helper"
    _description = "Workshop Documents Helper"

    @api.model
    def _folder_model(self):
        """Return the model used for Documents folders."""
        # Odoo 18+/19: folders are documents.document with type='folder'
        # Older enterprise builds used documents.folder
        if "documents.folder" in self.env and "documents.document" not in self.env:
            return self.env["documents.folder"]
        return self.env["documents.document"]

    @api.model
    def _create_folder(self, name, parent=False, company=False):
        Folder = self._folder_model()
        company = company or self.env.company
        domain = [("name", "=", name)]
        if parent:
            parent_field = "folder_id" if "folder_id" in Folder._fields else "parent_folder_id"
            domain.append((parent_field, "=", parent.id))
        else:
            parent_field = "folder_id" if "folder_id" in Folder._fields else "parent_folder_id"
            if parent_field in Folder._fields:
                domain.append((parent_field, "=", False))
        if "company_id" in Folder._fields:
            domain.append(("company_id", "in", [company.id, False]))
        existing = Folder.search(domain, limit=1)
        if existing:
            return existing

        vals = {"name": name}
        if "type" in Folder._fields:
            vals["type"] = "folder"
        if parent:
            parent_field = "folder_id" if "folder_id" in Folder._fields else "parent_folder_id"
            vals[parent_field] = parent.id
        if "company_id" in Folder._fields:
            vals["company_id"] = company.id
        if "access_internal" in Folder._fields:
            vals["access_internal"] = "view"
        return Folder.create(vals)

    @api.model
    def ensure_workshop_folders(self, company=None):
        """Create Workshop workspace + subfolders and link them on the company."""
        company = company or self.env.company
        root = company.documents_workshop_folder_id
        if not root:
            root = self._create_folder(_("Workshop"), company=company)
            company.documents_workshop_folder_id = root.id

        completion = company.documents_workshop_completion_folder_id
        if not completion:
            completion = self._create_folder(
                _("Job Completions"), parent=root, company=company
            )
            company.documents_workshop_completion_folder_id = completion.id

        equipment = company.documents_workshop_equipment_folder_id
        if not equipment:
            equipment = self._create_folder(
                _("Equipment History"), parent=root, company=company
            )
            company.documents_workshop_equipment_folder_id = equipment.id

        inspection = company.documents_workshop_inspection_folder_id
        if not inspection:
            inspection = self._create_folder(
                _("Inspection Photos"), parent=root, company=company
            )
            company.documents_workshop_inspection_folder_id = inspection.id

        return {
            "root": root,
            "completion": completion,
            "equipment": equipment,
            "inspection": inspection,
        }

    @api.model
    def create_document_from_attachment(self, attachment, folder, partner=False, tag_ids=None):
        """Create a documents.document linked to an existing ir.attachment."""
        if not attachment or "documents.document" not in self.env:
            return self.env["documents.document"] if "documents.document" in self.env else False

        Document = self.env["documents.document"]
        existing = Document.search([("attachment_id", "=", attachment.id)], limit=1)
        if existing:
            vals_update = {}
            if folder and existing.folder_id != folder:
                vals_update["folder_id"] = folder.id
            if partner and not existing.partner_id:
                vals_update["partner_id"] = partner.id
            if vals_update:
                existing.write(vals_update)
            return existing

        vals = {
            "name": attachment.name,
            "attachment_id": attachment.id,
            "folder_id": folder.id if folder else False,
        }
        if partner and "partner_id" in Document._fields:
            vals["partner_id"] = partner.id
        if "owner_id" in Document._fields:
            vals["owner_id"] = self.env.user.id
        if tag_ids and "tag_ids" in Document._fields:
            vals["tag_ids"] = [(6, 0, tag_ids)]
        # Avoid infinite loops when mixin also reacts to attachment create
        return Document.with_context(no_document=True).create(vals)
