from collections import defaultdict
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


DONE_STATES = ("completed", "closed")
FTFR_TARGET = 90.0
REWORK_TARGET = 5.0
PUNCH_NAME_KEYS = ("punch", "injection")


class WorkshopEquipmentType(models.Model):
    _inherit = "workshop.equipment.type"

    is_vehicle = fields.Boolean(
        string="Count as Vehicle / Truck",
        default=False,
        help="Intake of this type is counted on the Trucks & Punch Volume KPI.",
    )


class WorkshopWorkType(models.Model):
    _inherit = "workshop.work.type"

    is_punch = fields.Boolean(
        string="Punch Job",
        default=False,
        help="Completed jobs of this type are counted as punch volume.",
    )


class WorkshopTaskMaster(models.Model):
    _inherit = "workshop.task.master"

    is_punch = fields.Boolean(
        string="Punch Job",
        default=False,
        help="Jobs using this description are counted as punch volume.",
    )


class WorkshopJobOrder(models.Model):
    _inherit = "workshop.job.order"

    equipment_type_id = fields.Many2one(
        related="equipment_id.equipment_type",
        store=True,
        string="Equipment/Vehicle Type",
    )
    work_type_id = fields.Many2one(
        related="equipment_id.work_type",
        store=True,
        string="Type of Work",
    )
    has_rework = fields.Boolean(
        string="Had Rework",
        compute="_compute_kpi_metrics",
        store=True,
        help="True when any work dispatch on this job was sent to rework.",
    )
    turnaround_hours = fields.Float(
        string="Turnaround Hours",
        compute="_compute_kpi_metrics",
        store=True,
        help="Actual End − Actual Start (hours). Used for Job Turnaround Time.",
    )

    @api.depends("work_order_ids.rework_count", "date_start", "date_end", "create_date")
    def _compute_kpi_metrics(self):
        for jo in self:
            jo.has_rework = any(wo.rework_count > 0 for wo in jo.work_order_ids)
            start = jo.date_start or jo.create_date
            end = jo.date_end
            if start and end and end > start:
                jo.turnaround_hours = (end - start).total_seconds() / 3600.0
            else:
                jo.turnaround_hours = 0.0

    def _kpi_is_punch(self):
        self.ensure_one()
        wt = self.work_type_id
        if wt and (wt.is_punch or self._kpi_name_is_punch(wt.name)):
            return True
        tasks = self.work_order_ids.mapped("task_id") | self.request_id.line_ids.mapped("task_id")
        for task in tasks:
            if task.is_punch or self._kpi_name_is_punch(task.name):
                return True
        return False

    @api.model
    def _kpi_name_is_punch(self, name):
        text = (name or "").lower()
        return any(key in text for key in PUNCH_NAME_KEYS)

    @api.model
    def _kpi_period(self, date_from=None, date_to=None):
        today = fields.Date.context_today(self)
        if date_to:
            date_to = fields.Date.to_date(date_to)
        else:
            date_to = today
        if date_from:
            date_from = fields.Date.to_date(date_from)
        else:
            date_from = date_to.replace(day=1)
        return date_from, date_to

    @api.model
    def _kpi_bounds(self, date_from, date_to):
        start_dt = datetime.combine(date_from, time.min)
        end_dt = datetime.combine(date_to, time.max)
        return start_dt, end_dt

    @api.model
    def _kpi_done_jobs(self, date_from, date_to):
        start_dt, end_dt = self._kpi_bounds(date_from, date_to)
        jobs = self.search([
            ("state", "in", DONE_STATES),
            ("date_end", ">=", start_dt),
            ("date_end", "<=", end_dt),
        ])
        jobs |= self.search([
            ("state", "in", DONE_STATES),
            ("date_end", "=", False),
            ("create_date", ">=", start_dt),
            ("create_date", "<=", end_dt),
        ])
        return jobs

    @api.model
    def _kpi_vehicle_types(self):
        types = self.env["workshop.equipment.type"].search([("is_vehicle", "=", True)])
        if types:
            return types
        fallback = self.env.ref(
            "workshop_management.equipment_type_vehicle",
            raise_if_not_found=False,
        )
        return fallback or types

    @api.model
    def _kpi_available_hours(self, employees, date_from, date_to):
        start_dt, end_dt = self._kpi_bounds(date_from, date_to)
        total = 0.0
        for employee in employees:
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            if calendar:
                total += calendar.get_work_hours_count(start_dt, end_dt)
            else:
                days = 0
                cursor = date_from
                while cursor <= date_to:
                    if cursor.weekday() < 5:
                        days += 1
                    cursor += timedelta(days=1)
                total += days * 8.0
        return total

    @api.model
    def _kpi_month_windows(self, date_to, months=6):
        windows = []
        cursor = date_to.replace(day=1)
        for _ in range(months):
            nxt = cursor + relativedelta(months=1)
            windows.append((cursor, nxt - timedelta(days=1), cursor.strftime("%b %Y")))
            cursor = cursor - relativedelta(months=1)
        windows.reverse()
        return windows

    @api.model
    def get_kpi_framework(self, date_from=None, date_to=None):
        """Automotive KPI pack for the Workshop Dashboard."""
        date_from, date_to = self._kpi_period(date_from, date_to)
        start_dt, end_dt = self._kpi_bounds(date_from, date_to)
        jobs = self._kpi_done_jobs(date_from, date_to)
        job_count = len(jobs)
        jobs_rework = jobs.filtered("has_rework")
        jobs_ok = jobs - jobs_rework

        turnaround_jobs = jobs.filtered(lambda j: j.turnaround_hours > 0)
        total_hours = sum(turnaround_jobs.mapped("turnaround_hours"))
        avg_hours = (total_hours / len(turnaround_jobs)) if turnaround_jobs else 0.0

        by_type_hours = defaultdict(lambda: {"hours": 0.0, "count": 0})
        by_type_rev = defaultdict(lambda: {"revenue": 0.0, "count": 0, "cost": 0.0})
        for job in jobs:
            label = job.work_type_id.name or "Untyped"
            if job.turnaround_hours > 0:
                by_type_hours[label]["hours"] += job.turnaround_hours
                by_type_hours[label]["count"] += 1
            by_type_rev[label]["revenue"] += job.invoiced_amount or 0.0
            by_type_rev[label]["count"] += 1
            by_type_rev[label]["cost"] += job.cost_of_quality or 0.0

        type_labels = sorted(set(by_type_hours) | set(by_type_rev)) or ["Untyped"]
        turnaround_by_type = [
            round(by_type_hours[label]["hours"] / by_type_hours[label]["count"], 1)
            if by_type_hours[label]["count"]
            else 0.0
            for label in type_labels
        ]
        revenue_totals = [round(by_type_rev[label]["revenue"], 2) for label in type_labels]
        revenue_per_job = [
            round(by_type_rev[label]["revenue"] / by_type_rev[label]["count"], 2)
            if by_type_rev[label]["count"]
            else 0.0
            for label in type_labels
        ]
        rework_cost_by_type = [round(by_type_rev[label]["cost"], 2) for label in type_labels]

        wos = self.env["workshop.work.order"].search([
            ("technician_id", "!=", False),
            ("state", "!=", "draft"),
            "|",
            "&", ("date_start", ">=", start_dt), ("date_start", "<=", end_dt),
            "&", ("date_start", "=", False),
            "&", ("create_date", ">=", start_dt), ("create_date", "<=", end_dt),
        ])
        productive = sum(wos.mapped("actual_hours"))
        employees = wos.mapped("technician_id")
        available = self._kpi_available_hours(employees, date_from, date_to)
        util_pct = round((productive / available) * 100.0, 1) if available else 0.0
        tech_labels = []
        tech_productive = []
        tech_available = []
        for employee in employees:
            tech_wos = wos.filtered(lambda w, emp=employee: w.technician_id == emp)
            tech_labels.append(employee.name)
            tech_productive.append(round(sum(tech_wos.mapped("actual_hours")), 1))
            tech_available.append(round(self._kpi_available_hours(employee, date_from, date_to), 1))

        ftfr = round((len(jobs_ok) / job_count) * 100.0, 1) if job_count else 0.0
        rework_pct = round((len(jobs_rework) / job_count) * 100.0, 1) if job_count else 0.0

        vehicle_types = self._kpi_vehicle_types()
        vehicle_domain = [
            ("create_date", ">=", start_dt),
            ("create_date", "<=", end_dt),
        ]
        if vehicle_types:
            vehicle_domain.append(("equipment_id.equipment_type", "in", vehicle_types.ids))
        vehicles = self.env["workshop.request"].search(vehicle_domain)
        punch_jobs = jobs.filtered(lambda j: j._kpi_is_punch())

        trend_labels = []
        trend_vehicles = []
        trend_punch = []
        trend_turnaround = []
        for month_start, month_end, label in self._kpi_month_windows(date_to):
            trend_labels.append(label)
            m_start, m_end = self._kpi_bounds(month_start, month_end)
            v_dom = [
                ("create_date", ">=", m_start),
                ("create_date", "<=", m_end),
            ]
            if vehicle_types:
                v_dom.append(("equipment_id.equipment_type", "in", vehicle_types.ids))
            trend_vehicles.append(self.env["workshop.request"].search_count(v_dom))
            month_jobs = self._kpi_done_jobs(month_start, month_end)
            trend_punch.append(len(month_jobs.filtered(lambda j: j._kpi_is_punch())))
            timed = month_jobs.filtered(lambda j: j.turnaround_hours > 0)
            trend_turnaround.append(
                round(sum(timed.mapped("turnaround_hours")) / len(timed), 1) if timed else 0.0
            )

        done_domain = [
            ("state", "in", list(DONE_STATES)),
            "|",
            "&", ("date_end", ">=", start_dt), ("date_end", "<=", end_dt),
            "&", ("date_end", "=", False),
            "&", ("create_date", ">=", start_dt), ("create_date", "<=", end_dt),
        ]
        return {
            "date_from": fields.Date.to_string(date_from),
            "date_to": fields.Date.to_string(date_to),
            "currency": self.env.company.currency_id.symbol or "",
            "turnaround": {
                "hours": round(avg_hours, 1),
                "job_count": len(turnaround_jobs),
                "total_hours": round(total_hours, 1),
                "labels": type_labels,
                "by_type": turnaround_by_type,
                "trend_labels": trend_labels,
                "trend": trend_turnaround,
                "domain": done_domain + [("turnaround_hours", ">", 0)],
            },
            "ftfr": {
                "percent": ftfr,
                "jobs_ok": len(jobs_ok),
                "jobs_total": job_count,
                "target": FTFR_TARGET,
                "on_target": ftfr >= FTFR_TARGET if job_count else True,
                "domain": done_domain + [("has_rework", "=", False)],
                "domain_all": done_domain,
            },
            "utilization": {
                "percent": util_pct,
                "productive_hours": round(productive, 1),
                "available_hours": round(available, 1),
                "labels": tech_labels,
                "productive": tech_productive,
                "available": tech_available,
                "domain": [
                    ("technician_id", "!=", False),
                    ("state", "!=", "draft"),
                ],
            },
            "rework": {
                "percent": rework_pct,
                "jobs_rework": len(jobs_rework),
                "jobs_total": job_count,
                "target": REWORK_TARGET,
                "on_target": rework_pct <= REWORK_TARGET if job_count else True,
                "cost": round(sum(jobs_rework.mapped("cost_of_quality")), 2),
                "labels": type_labels,
                "cost_by_type": rework_cost_by_type,
                "domain": done_domain + [("has_rework", "=", True)],
            },
            "revenue_per_type": {
                "labels": type_labels,
                "revenue": revenue_totals,
                "per_job": revenue_per_job,
                "counts": [by_type_rev[label]["count"] for label in type_labels],
                "overall_per_job": round(
                    (sum(job.invoiced_amount or 0.0 for job in jobs) / job_count) if job_count else 0.0,
                    2,
                ),
                "domain": done_domain,
            },
            "volume": {
                "vehicles_received": len(vehicles),
                "punch_completed": len(punch_jobs),
                "trend_labels": trend_labels,
                "vehicles": trend_vehicles,
                "punch": trend_punch,
                "domain_vehicles": vehicle_domain,
                "domain_punch": [("id", "in", punch_jobs.ids)] if punch_jobs else [("id", "=", False)],
            },
        }
