from odoo import api, fields, models

SERVICE_LOCATION_TYPES = [
    ("in_shop", "In-Shop"),
    ("field", "Field Service"),
]

FIELD_CHARGE_LINE_TYPES = ("travel", "mileage", "per_diem", "fuel", "other")


class WorkshopFieldServiceLocationMixin(models.AbstractModel):
    """Shared service location fields for workshop request and job order."""

    _name = "workshop.field.service.location.mixin"
    _description = "Workshop Field Service Location Mixin"

    service_location_type = fields.Selection(
        selection=SERVICE_LOCATION_TYPES,
        string="Service Location",
        default="in_shop",
        required=True,
        tracking=True,
        index=True,
    )
    is_field_job = fields.Boolean(
        string="Field Service Job",
        compute="_compute_is_field_job",
        store=True,
        index=True,
    )
    service_site_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Service Site Contact",
        tracking=True,
        ondelete="restrict",
    )
    service_street = fields.Char(string="Site Street")
    service_street2 = fields.Char(string="Site Street 2")
    service_city = fields.Char(string="Site City")
    service_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Site State",
    )
    service_zip = fields.Char(string="Site ZIP")
    service_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Site Country",
    )
    service_latitude = fields.Float(string="Latitude", digits=(10, 7))
    service_longitude = fields.Float(string="Longitude", digits=(10, 7))

    @api.depends("service_location_type")
    def _compute_is_field_job(self):
        for rec in self:
            rec.is_field_job = rec.service_location_type == "field"

    def _apply_service_site_from_partner(self, partner):
        partner = partner or self.env["res.partner"]
        if not partner:
            return
        self.service_site_partner_id = partner
        self.service_street = partner.street
        self.service_street2 = partner.street2
        self.service_city = partner.city
        self.service_state_id = partner.state_id
        self.service_zip = partner.zip
        self.service_country_id = partner.country_id
        if partner.partner_latitude:
            self.service_latitude = partner.partner_latitude
        if partner.partner_longitude:
            self.service_longitude = partner.partner_longitude

    @api.onchange("service_location_type", "partner_id")
    def _onchange_service_location_partner(self):
        if self.service_location_type == "field" and self.partner_id:
            delivery_partner_id = self.partner_id.address_get(["delivery"])["delivery"]
            delivery_partner = self.env["res.partner"].browse(delivery_partner_id)
            self._apply_service_site_from_partner(delivery_partner)

    @api.onchange("service_site_partner_id")
    def _onchange_service_site_partner_id(self):
        if self.service_site_partner_id:
            self._apply_service_site_from_partner(self.service_site_partner_id)

    def _get_service_location_copy_vals(self):
        self.ensure_one()
        return {
            "service_location_type": self.service_location_type,
            "service_site_partner_id": self.service_site_partner_id.id
            if self.service_site_partner_id
            else False,
            "service_street": self.service_street,
            "service_street2": self.service_street2,
            "service_city": self.service_city,
            "service_state_id": self.service_state_id.id if self.service_state_id else False,
            "service_zip": self.service_zip,
            "service_country_id": self.service_country_id.id if self.service_country_id else False,
            "service_latitude": self.service_latitude,
            "service_longitude": self.service_longitude,
        }
