from odoo import api, fields, models


class WorkshopDepartment(models.Model):
    """Workshop department used on work packs, dispatches, tasks, and QI."""

    _name = "workshop.department"
    _description = "Workshop Department"
    _order = "sequence, name"

    name = fields.Char(string="Department", required=True, translate=True)
    code = fields.Char(string="Code", index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        help="Leave empty to share this department across all companies.",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Department code must be unique.",
    )

    @api.model
    def _default_department(self):
        return self.env.ref(
            "workshop_management.workshop_department_mechanical",
            raise_if_not_found=False,
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") and vals.get("name"):
                base = "".join(
                    ch if ch.isalnum() else "_"
                    for ch in (vals["name"] or "").strip().lower()
                ).strip("_") or "dept"
                code = base[:32]
                n = 1
                while self.search_count([("code", "=", code)]):
                    n += 1
                    code = ("%s_%s" % (base[:28], n))[:32]
                vals["code"] = code
        return super().create(vals_list)
