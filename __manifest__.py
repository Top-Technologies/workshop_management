{
    "name": "Workshop Management",
    "version": "19.0.1.34.0",
    "category": "Services/Manufacturing",
    "summary": "Full Workshop Lifecycle Management: Sales Order → Job Order → Work Dispatches → Timesheets → Spare Parts → Quality → Invoicing → Close",
    "description": """
Workshop Management System
==========================

Digitalizes Tana Engineering's workshop process across Mechanical, Body, Electrical, Inspection, and Store departments:
- Sales Order integration and auto Job Order creation
- Multi-stage approval workflow via Odoo Approvals app with threshold rule engine
- Departmental Work Dispatch generation & technician assignment
- Timesheet tracking with planned vs actual hours rollup & variance
- Spare Parts Request workflow & store approval to stock.picking
- Purchase requisition on stock shortage + reverse logistics for unused, non-fitting, and defective parts (restock / scrap / vendor return + replacement)
- Quality Inspection checklist gating
- Electronic Customer Acceptance signature
- Job Costing (labor + parts + external services) & profitability analytics
- Agreement / warranty-aware billing (covered lines non-billable; invoice billable only)
- Work Dispatch auto timesheet timer (start / pause with reason / stop → account.analytic.line)
- Enterprise Documents integration (completion forms, equipment history, inspection photos)
- Field Service: In-Shop vs Field jobs, site address, field visits with dispatch/check-in/out
- Field charge types: travel, mileage, per diem, fuel on quotation estimate lines
- Field Service analytics: travel hours, on-site turnaround, dispatch KPIs
- Work Dispatch kanban by department, technician workload calendar, work photos
- Rework cause / who pays / extra hours and cost of quality
- Control dashboard: overdue jobs, parts aging, utilization, profit, quality fail rate
- Posted-invoice profitability, expected profit from quotes, and per-line breakdown
- Labor costing from Standard Hours (not timer hours); spare / labor / task profit rows
- Technician record rules on Job Orders and Requests
- Work pack assignment from quotation labor lines
- Real service agreements: period, coverage, included visits/hours, extra labor rate
- Vehicle intake checklist on Equipment Master (54 English items, trailer header, terms)
- Receptionist role: equipment intake and Customer Requests (no assignment or store)
- Two-way vehicle release financial gate: credit/trusted clients may collect on credit with pending-payment tracking; standard/new clients are blocked until the invoice is fully paid
- Service warranties only for Engine Overhaul and Gearbox; duration varies by service, vehicle type, and client agreement
- Reverse logistics: technicians flag unused, non-fitting, or defective issued parts; store restocks, scraps, or returns to vendor and can issue a replacement
- Field staff personal-money expenses on the Job Order with Foreman (Supervisor) validation; approved cost plus company margin is billed
- Workshop costing labor rates by Customer Type Description, Pricelist Rule, Labour Rate, and Pricelist Rules/Apply On
- Automotive KPI dashboard: job turnaround, first-time fix rate, utilization vs available hours, rework rate, revenue per job type, trucks and punch volume
- Work Dispatch pause timer with required clock-out reason codes (lunch, parts, meeting, machine shop, etc.)
    """,
    "author": "Top Technologies System Solutions PLC",
    "website": "https://www.toptechnologies.com",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "sale_management",
        "stock",
        "purchase",
        "account",
        "hr",
        "hr_timesheet",
        "mail",
        "documents",
        "approvals",
        "base_geolocalize",
    ],
    "data": [
        "security/workshop_security.xml",
        "security/ir.model.access.csv",
        "security/workshop_rules.xml",
        "data/ir_sequence_data.xml",
        "data/workshop_department_data.xml",
        "data/workshop_task_master_data.xml",
        "data/workshop_warranty_data.xml",
        "data/mail_template_data.xml",
        "data/workshop_quality_checklist_data.xml",
        "data/workshop_equipment_intake_data.xml",
        "data/workshop_equipment_catalog_data.xml",
        "data/workshop_approval_category_data.xml",
        "data/workshop_expense_product_data.xml",
        "wizard/workshop_technician_assignment_views.xml",
        "wizard/workshop_rework_wizard_views.xml",
        "wizard/workshop_spare_return_wizard_views.xml",
        "wizard/workshop_timer_pause_wizard_views.xml",
        "views/hr_employee_views.xml",
        "views/res_partner_views.xml",
        "views/workshop_equipment_views.xml",
        "views/workshop_agreement_views.xml",
        "views/workshop_task_master_views.xml",
        "views/workshop_warranty_views.xml",
        "views/workshop_request_views.xml",
        "views/workshop_job_order_views.xml",
        "views/workshop_field_visit_views.xml",
        "views/workshop_work_order_views.xml",
        "views/workshop_spare_request_views.xml",
        "views/workshop_expense_views.xml",
        "views/workshop_quality_inspection_views.xml",
        "views/workshop_approval_rule_views.xml",
        "views/sale_order_views.xml",
        "views/workshop_dashboard_views.xml",
        "views/workshop_labor_rate_views.xml",
        "views/res_config_settings_views.xml",
        "views/workshop_menus.xml",
        "report/workshop_job_order_report.xml",
        "report/workshop_work_order_report.xml",
        "report/workshop_completion_report.xml",
        "report/report_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "workshop_management/static/src/scss/workshop_dashboard.scss",
            "workshop_management/static/src/js/file_input_patch.js",
            "workshop_management/static/src/js/workshop_chart.js",
            "workshop_management/static/src/xml/workshop_chart.xml",
            "workshop_management/static/src/js/workshop_dashboard.js",
            "workshop_management/static/src/xml/workshop_dashboard.xml",
            "workshop_management/static/src/js/workshop_kpi_dashboard.js",
            "workshop_management/static/src/xml/workshop_kpi_dashboard.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
