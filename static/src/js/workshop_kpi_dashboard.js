/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { WorkshopChart } from "./workshop_chart";

const emptyKpi = () => ({
    date_from: "",
    date_to: "",
    currency: "",
    turnaround: {
        hours: 0,
        job_count: 0,
        total_hours: 0,
        labels: [],
        by_type: [],
        trend_labels: [],
        trend: [],
        domain: [],
    },
    ftfr: {
        percent: 0,
        jobs_ok: 0,
        jobs_total: 0,
        target: 90,
        on_target: true,
        domain: [],
        domain_all: [],
    },
    utilization: {
        percent: 0,
        productive_hours: 0,
        available_hours: 0,
        labels: [],
        productive: [],
        available: [],
        domain: [],
    },
    rework: {
        percent: 0,
        jobs_rework: 0,
        jobs_total: 0,
        target: 5,
        on_target: true,
        cost: 0,
        labels: [],
        cost_by_type: [],
        domain: [],
    },
    revenue_per_type: {
        labels: [],
        revenue: [],
        per_job: [],
        counts: [],
        overall_per_job: 0,
        domain: [],
    },
    volume: {
        vehicles_received: 0,
        punch_completed: 0,
        trend_labels: [],
        vehicles: [],
        punch: [],
        domain_vehicles: [],
        domain_punch: [],
    },
});

function currentYearMonth() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function monthBounds(yearMonth) {
    const [year, month] = (yearMonth || currentYearMonth()).split("-").map(Number);
    const last = new Date(year, month, 0).getDate();
    const mm = String(month).padStart(2, "0");
    return {
        date_from: `${year}-${mm}-01`,
        date_to: `${year}-${mm}-${String(last).padStart(2, "0")}`,
    };
}

export class WorkshopKpiDashboard extends Component {
    static template = "workshop_management.WorkshopKpiDashboard";
    static components = { WorkshopChart };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            kpiMonth: currentYearMonth(),
            kpi: emptyKpi(),
        });
        onWillStart(async () => {
            await this.loadKpiData();
        });
    }

    get ftfrCardClass() {
        return `o_kanban_record o_kanban_global_click ${this.kpiCardClass(this.state.kpi.ftfr.on_target, true)}`;
    }

    get reworkCardClass() {
        return `o_kanban_record o_kanban_global_click ${this.kpiCardClass(this.state.kpi.rework.on_target, true)}`;
    }

    kpiCardClass(onTarget, invertWarning = false) {
        if (onTarget) {
            return "o_workshop_kpi_card o_workshop_kpi_card--success";
        }
        return invertWarning
            ? "o_workshop_kpi_card o_workshop_kpi_card--danger"
            : "o_workshop_kpi_card o_workshop_kpi_card--warning";
    }

    formatHours(value) {
        return Number(value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
        });
    }

    formatMoney(value) {
        return Number(value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    async loadKpiData() {
        this.state.loading = true;
        try {
            const { date_from, date_to } = monthBounds(this.state.kpiMonth);
            const result = await this.orm.call("workshop.job.order", "get_kpi_framework", [], {
                date_from,
                date_to,
            });
            this.state.kpi = { ...emptyKpi(), ...result };
        } catch (error) {
            console.error("Error loading workshop KPI dashboard:", error);
            this.state.kpi = emptyKpi();
        } finally {
            this.state.loading = false;
        }
    }

    onKpiMonthChange(ev) {
        this.state.kpiMonth = ev.target.value || currentYearMonth();
        this.loadKpiData();
    }

    openAction(resModel, domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: domain || [],
        });
    }

    openKpiTurnaround() {
        this.openAction("workshop.job.order", this.state.kpi.turnaround.domain, "Job Turnaround");
    }

    openKpiFtfr() {
        this.openAction("workshop.job.order", this.state.kpi.ftfr.domain, "First Time Fix Jobs");
    }

    openKpiUtilization() {
        this.openAction("workshop.work.order", this.state.kpi.utilization.domain, "Technician Utilization");
    }

    openKpiReworkJobs() {
        this.openAction("workshop.job.order", this.state.kpi.rework.domain, "Jobs With Rework");
    }

    openKpiRevenue() {
        this.openAction("workshop.job.order", this.state.kpi.revenue_per_type.domain, "Revenue per Job Type");
    }

    openKpiVehicles() {
        this.openAction("workshop.request", this.state.kpi.volume.domain_vehicles, "Vehicles Received");
    }

    openKpiPunch() {
        this.openAction("workshop.job.order", this.state.kpi.volume.domain_punch, "Punch Jobs Completed");
    }
}

registry.category("actions").add("workshop_kpi_dashboard_tags", WorkshopKpiDashboard);
