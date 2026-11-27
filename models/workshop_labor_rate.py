from odoo import api, fields, models


class WorkshopCustomerType(models.Model):
    """Named customer class used by labor-rate rules (Customer Type Description)."""

    _name = "workshop.customer.type"
    _description = "Workshop Customer Type"
    _order = "name"

    name = fields.Char(
        string="Customer Type Description",
        required=True,
        translate=True,
        index=True,
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
        help="Leave empty to share this type across all companies.",
    )


class WorkshopLaborRateRule(models.Model):
    """Default labor rate by customer type and Odoo pricelist rule."""

    _name = "workshop.labor.rate.rule"
    _description = "Workshop Labor Rate Rule"
    _order = "customer_type_id, applied_on, id"

    customer_type_id = fields.Many2one(
        comodel_name="workshop.customer.type",
        string="Customer Type Description",
        required=True,
        ondelete="restrict",
        index=True,
    )
    pricelist_item_id = fields.Many2one(
        comodel_name="product.pricelist.item",
        string="Pricelist Rule",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    labor_rate = fields.Float(
        string="Labour Rate",
        required=True,
        digits="Product Price",
        help="Hourly labor rate used for job costing when the technician has "
             "no Workshop Hourly Cost.",
    )
    applied_on = fields.Selection(
        related="pricelist_item_id.applied_on",
        string="Pricelist Rules/Apply On",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
    )

    _uniq_type_pricelist_item = models.Constraint(
        "UNIQUE(customer_type_id, pricelist_item_id, company_id)",
        "A labour rate is already set for this customer type and pricelist rule.",
    )

    @api.model
    def _match_labor_rate(self, partner=None, product=None, company=None):
        """Return the labour rate for this customer type and product, or None."""
        company = company or self.env.company
        customer_type = partner.workshop_customer_type_id if partner else False
        if not customer_type:
            return None
        rules = self.sudo().search([
            ("customer_type_id", "=", customer_type.id),
            ("company_id", "in", [company.id, False]),
        ])
        if not rules:
            return None
        ranked = rules.sorted(lambda r: (r.applied_on or "3_global", r.id))
        for rule in ranked:
            item = rule.pricelist_item_id
            if not item:
                continue
            if not product:
                if item.applied_on == "3_global":
                    return rule.labor_rate
                continue
            if item._is_applicable_for(product, 1.0):
                return rule.labor_rate
        return None
