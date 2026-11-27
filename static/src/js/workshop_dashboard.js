/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { getColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";
import { WorkshopChart } from "./workshop_chart";

const PIPELINE_CONFIG = {
    requests: {
        model: "workshop.request",
        title: "Customer Requests",
        subtitle: "Customer intake to confirmation",
        icon: "fa-inbox",
        stages: [
            { key: "draft", label: "Draft", color: "#94a3b8" },
            { key: "quoted", label: "Quoted", color: "#60a5fa" },
            { key: "confirmed", label: "Confirmed", color: "#22c55e" },
            { key: "cancelled", label: "Cancelled", color: "#ef4444" },
        ],
    },
    jobOrders: {
        model: "workshop.job.order",
        title: "Job Orders",
        subtitle: "Approval through close",
        icon: "fa-cogs",
        stages: [
            { key: "draft", label: "Draft", color: "#94a3b8" },
            { key: "waiting_approval", label: "Waiting Approval", color: "#f59e0b" },
            { key: "approved", label: "Approved", color: "#38bdf8" },
            { key: "assigned", label: "Assigned", color: "#818cf8" },
            { key: "in_progress", label: "In Progress", color: "#3b82f6" },
            { key: "waiting_parts", label: "Waiting Parts", color: "#f97316" },
            { key: "quality_inspection", label: "Quality Check", color: "#a855f7" },
            { key: "completed", label: "Completed", color: "#22c55e" },
            { key: "closed", label: "Closed", color: "#64748b" },
        ],
    },
    workOrders: {
        model: "workshop.work.order",
        title: "Work Dispatches",
        subtitle: "Technician execution pipeline",
        icon: "fa-wrench",
        stages: [
            { key: "draft", label: "Draft", color: "#94a3b8" },
            { key: "assigned", label: "Assigned", color: "#38bdf8" },
            { key: "in_progress", label: "In Progress", color: "#3b82f6" },
            { key: "done", label: "Done", color: "#22c55e" },
            { key: "rework", label: "Rework", color: "#f97316" },
            { key: "verified", label: "Verified", color: "#10b981" },
        ],
    },
    spareRequests: {
        model: "workshop.spare.request",
        title: "Spare Parts Requests",
        subtitle: "Store issue workflow",
        icon: "fa-cubes",
        stages: [
            { key: "draft", label: "Draft", color: "#94a3b8" },
            { key: "submitted", label: "Submitted", color: "#60a5fa" },
            { key: "waiting_purchase", label: "Waiting Purchase", color: "#f59e0b" },
            { key: "store_approved", label: "Store Approved", color: "#38bdf8" },
            { key: "issued", label: "Issued", color: "#22c55e" },
            { key: "return_flagged", label: "Return Flagged", color: "#fb923c" },
            { key: "partially_returned", label: "Partial Return", color: "#a78bfa" },
            { key: "rejected", label: "Rejected", color: "#ef4444" },
        ],
    },
};

const OVERVIEW_KEYS = ["requests", "jobOrders", "workOrders", "spareRequests"];

const emptyControl = () => ({
    overdue: 0,
    waitingParts: 0,
    utilizationPct: 0,
    profit: 0,
    invoiced: 0,
    cost: 0,
    costOfQuality: 0,
    qiFail: 0,
    qiPass: 0,
    qiTotal: 0,
    qiFailRate: 0,
    reworkOpen: 0,
    reworkHistory: 0,
    workOrderTotal: 0,
    reworkRate: 0,
    creditPending: 0,
    partsAging: {
        labels: ["0–2 days", "3–7 days", "8+ days"],
        data: [0, 0, 0],
        colors: ["#22c55e", "#f59e0b", "#ef4444"],
    },
    utilization: {
        labels: [],
        planned: [],
        actual: [],
        colors: [],
    },
    quality: {
        labels: ["Passed", "Failed", "Draft"],
        data: [0, 0, 0],
        colors: ["#22c55e", "#ef4444", "#94a3b8"],
    },
});

function localISODate() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${now.getFullYear()}-${month}-${day}`;
}

function daysBetween(isoDatetime) {
    if (!isoDatetime) {
        return 0;
    }
    const then = new Date(isoDatetime);
    return Math.max(0, (Date.now() - then.getTime()) / 86400000);
}

function aggregateValue(group, fieldName) {
    if (!group) {
        return 0;
    }
    return group[fieldName] ?? group[`${fieldName}:sum`] ?? 0;
}

export class WorkshopDashboard extends Component {
    static template = "workshop_management.WorkshopDashboard";
    static components = { WorkshopChart };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.pipelineKeys = Object.keys(PIPELINE_CONFIG);

        this.state = useState({
            loading: true,
            pipelines: Object.fromEntries(
                Object.keys(PIPELINE_CONFIG).map((key) => [
                    key,
                    {
                        ...PIPELINE_CONFIG[key],
                        key,
                        total: 0,
                        stages: [],
                        activeStages: [],
                        emptyStages: [],
                        chartLabels: [],
                        chartData: [],
                        chartColors: [],
                        chartStageKeys: [],
                        barLabels: [],
                        barData: [],
                        barColors: [],
                    },
                ])
            ),
            totals: {
                requests: 0,
                jobOrders: 0,
                workOrders: 0,
                spareRequests: 0,
            },
            overview: {
                labels: [],
                data: [],
                colors: [],
            },
            control: emptyControl(),
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    get overviewTotal() {
        return OVERVIEW_KEYS.reduce((sum, key) => sum + this.state.totals[key], 0);
    }

    _groupCount(group) {
        return group.__count ?? 0;
    }

    _getGroupKey(group, fieldName = "state") {
        const value = group[fieldName];
        if (Array.isArray(value)) {
            return value[0];
        }
        return value;
    }

    async _readStageGroups(model, fieldName = "state") {
        return this.orm.formattedReadGroup(model, [], [fieldName], ["__count"]);
    }

    _buildPipeline(configKey, groups) {
        const config = PIPELINE_CONFIG[configKey];
        const countByState = {};
        let total = 0;
        for (const group of groups) {
            const state = this._getGroupKey(group, "state");
            const count = this._groupCount(group);
            if (!state) {
                continue;
            }
            countByState[state] = count;
            total += count;
        }
        const maxCount = Math.max(
            ...config.stages.map((stage) => countByState[stage.key] || 0),
            1
        );
        const stages = config.stages.map((stage) => {
            const count = countByState[stage.key] || 0;
            return {
                ...stage,
                count,
                percent: total ? Math.round((count / total) * 100) : 0,
                barWidth: Math.round((count / maxCount) * 100),
            };
        });
        const activeStages = stages.filter((stage) => stage.count > 0);
        const emptyStages = stages.filter((stage) => stage.count === 0);
        return {
            ...config,
            key: configKey,
            total,
            stages,
            activeStages,
            emptyStages,
            chartLabels: activeStages.map((stage) => stage.label),
            chartData: activeStages.map((stage) => stage.count),
            chartColors: activeStages.map((stage) => stage.color),
            chartStageKeys: activeStages.map((stage) => stage.key),
            barLabels: stages.map((stage) => stage.label),
            barData: stages.map((stage) => stage.count),
            barColors: stages.map((stage) => stage.color),
        };
    }

    _buildOverview() {
        const colorScheme = cookie.get("color_scheme");
        return {
            labels: OVERVIEW_KEYS.map((key) => PIPELINE_CONFIG[key].title),
            data: OVERVIEW_KEYS.map((key) => this.state.totals[key]),
            colors: OVERVIEW_KEYS.map((_, index) => getColor(index, colorScheme, OVERVIEW_KEYS.length)),
        };
    }

    _groupDisplayName(group, fieldName) {
        const value = group[fieldName];
        if (Array.isArray(value)) {
            return value[1] || String(value[0]);
        }
        return value || "";
    }

    async _loadControlMetrics() {
        try {
            return await this._fetchControlMetrics();
        } catch (error) {
            console.error("Error loading workshop control metrics:", error);
            return emptyControl();
        }
    }

    async _fetchControlMetrics() {
        const today = localISODate();
        const overdueDomain = [
            ["expected_finish_date", "!=", false],
            ["expected_finish_date", "<", today],
            ["state", "not in", ["completed", "closed"]],
        ];
        const colorScheme = cookie.get("color_scheme");

        const [
            overdue,
            waitingParts,
            waitingJobs,
            profitGroups,
            qiGroups,
            reworkOpen,
            reworkHistory,
            workOrderTotal,
            techGroups,
            creditPending,
        ] = await Promise.all([
            this.orm.searchCount("workshop.job.order", overdueDomain),
            this.orm.searchCount("workshop.job.order", [["state", "=", "waiting_parts"]]),
            this.orm.searchRead(
                "workshop.job.order",
                [["state", "=", "waiting_parts"]],
                ["waiting_parts_since"]
            ),
            this.orm.formattedReadGroup(
                "workshop.job.order",
                [],
                [],
                ["job_profitability:sum", "invoiced_amount:sum", "total_cost:sum", "cost_of_quality:sum"]
            ),
            this.orm.formattedReadGroup("workshop.quality.inspection", [], ["state"], ["__count"]),
            this.orm.searchCount("workshop.work.order", [["state", "=", "rework"]]),
            this.orm.searchCount("workshop.work.order", [["rework_count", ">", 0]]),
            this.orm.searchCount("workshop.work.order", []),
            this.orm.formattedReadGroup(
                "workshop.work.order",
                [
                    ["technician_id", "!=", false],
                    ["state", "not in", ["draft"]],
                ],
                ["technician_id"],
                ["planned_hours:sum", "actual_hours:sum"]
            ),
            this.orm.searchCount("workshop.job.order", [["payment_pending", "=", true]]),
        ]);

        const aging = [0, 0, 0];
        for (const job of waitingJobs) {
            if (!job.waiting_parts_since) {
                aging[2] += 1;
                continue;
            }
            const days = daysBetween(job.waiting_parts_since);
            if (days <= 2) {
                aging[0] += 1;
            } else if (days <= 7) {
                aging[1] += 1;
            } else {
                aging[2] += 1;
            }
        }

        const profitRow = profitGroups[0] || {};
        const profit = aggregateValue(profitRow, "job_profitability");
        const invoiced = aggregateValue(profitRow, "invoiced_amount");
        const cost = aggregateValue(profitRow, "total_cost");
        const costOfQuality = aggregateValue(profitRow, "cost_of_quality");

        let qiPass = 0;
        let qiFail = 0;
        let qiDraft = 0;
        for (const group of qiGroups) {
            const state = this._getGroupKey(group, "state");
            const count = this._groupCount(group);
            if (state === "pass") {
                qiPass = count;
            } else if (state === "fail") {
                qiFail = count;
            } else {
                qiDraft += count;
            }
        }
        const qiDecided = qiPass + qiFail;
        const qiFailRate = qiDecided ? Math.round((qiFail / qiDecided) * 100) : 0;
        const reworkRate = workOrderTotal ? Math.round((reworkHistory / workOrderTotal) * 100) : 0;

        const utilLabels = [];
        const utilPlanned = [];
        const utilActual = [];
        const utilColors = [];
        let plannedTotal = 0;
        let actualTotal = 0;
        techGroups.forEach((group, index) => {
            const planned = aggregateValue(group, "planned_hours");
            const actual = aggregateValue(group, "actual_hours");
            plannedTotal += planned;
            actualTotal += actual;
            utilLabels.push(this._groupDisplayName(group, "technician_id"));
            utilPlanned.push(planned);
            utilActual.push(actual);
            utilColors.push(getColor(index, colorScheme, Math.max(techGroups.length, 1)));
        });
        const utilizationPct = plannedTotal ? Math.round((actualTotal / plannedTotal) * 100) : 0;

        return {
            overdue,
            waitingParts,
            utilizationPct,
            profit,
            invoiced,
            cost,
            costOfQuality,
            qiFail,
            qiPass,
            qiTotal: qiPass + qiFail + qiDraft,
            qiFailRate,
            reworkOpen,
            reworkHistory,
            workOrderTotal,
            reworkRate,
            creditPending,
            partsAging: {
                labels: ["0–2 days", "3–7 days", "8+ days"],
                data: aging,
                colors: ["#22c55e", "#f59e0b", "#ef4444"],
            },
            utilization: {
                labels: utilLabels,
                planned: utilPlanned,
                actual: utilActual,
                colors: utilColors,
            },
            quality: {
                labels: ["Passed", "Failed", "Draft"],
                data: [qiPass, qiFail, qiDraft],
                colors: ["#22c55e", "#ef4444", "#94a3b8"],
            },
        };
    }

    formatMoney(value) {
        return Number(value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            const [requestGroups, jobGroups, workGroups, spareGroups, control] = await Promise.all([
                this._readStageGroups("workshop.request"),
                this._readStageGroups("workshop.job.order"),
                this._readStageGroups("workshop.work.order"),
                this._readStageGroups("workshop.spare.request"),
                this._loadControlMetrics(),
            ]);

            this.state.pipelines = {
                requests: this._buildPipeline("requests", requestGroups),
                jobOrders: this._buildPipeline("jobOrders", jobGroups),
                workOrders: this._buildPipeline("workOrders", workGroups),
                spareRequests: this._buildPipeline("spareRequests", spareGroups),
            };
            this.state.totals = {
                requests: this.state.pipelines.requests.total,
                jobOrders: this.state.pipelines.jobOrders.total,
                workOrders: this.state.pipelines.workOrders.total,
                spareRequests: this.state.pipelines.spareRequests.total,
            };
            this.state.overview = this._buildOverview();
            this.state.control = control;
        } catch (error) {
            console.error("Error loading workshop dashboard:", error);
        } finally {
            this.state.loading = false;
        }
    }

    openAction(resModel, viewMode, domain = [], name = "View") {
        const views =
            viewMode === "kanban"
                ? [
                      [false, "kanban"],
                      [false, "list"],
                      [false, "form"],
                  ]
                : viewMode === "calendar"
                  ? [
                        [false, "calendar"],
                        [false, "list"],
                        [false, "form"],
                    ]
                  : [
                        [false, "list"],
                        [false, "form"],
                    ];
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            views,
            domain,
        });
    }

    openOverdue() {
        this.openAction(
            "workshop.job.order",
            "list",
            [
                ["expected_finish_date", "!=", false],
                ["expected_finish_date", "<", localISODate()],
                ["state", "not in", ["completed", "closed"]],
            ],
            "Overdue Job Orders"
        );
    }

    openWaitingParts() {
        this.openAction(
            "workshop.job.order",
            "list",
            [["state", "=", "waiting_parts"]],
            "Jobs Waiting on Parts"
        );
    }

    openUtilization() {
        this.openAction("workshop.work.order", "calendar", [["technician_id", "!=", false]], "Technician Workload");
    }

    openProfit() {
        this.openAction("workshop.job.order", "list", [], "Job Profitability");
    }

    openQuality() {
        this.openAction("workshop.quality.inspection", "list", [["state", "=", "fail"]], "Failed Quality Inspections");
    }

    openRework() {
        this.openAction("workshop.work.order", "kanban", [["rework_count", ">", 0]], "Rework Work Dispatches");
    }

    openCreditReleases() {
        this.openAction(
            "workshop.job.order",
            "list",
            [["payment_pending", "=", true]],
            "Credit Releases (Payment Pending)"
        );
    }

    openPipeline(pipeline) {
        this.openAction(pipeline.model, "list", [], pipeline.title);
    }

    openStage(pipeline, stage) {
        this.openAction(
            pipeline.model,
            "list",
            [["state", "=", stage.key]],
            `${pipeline.title} — ${stage.label}`
        );
    }

    onChartSliceClick(pipeline, index) {
        const stageKey = pipeline.chartStageKeys[index];
        const stage = pipeline.stages.find((item) => item.key === stageKey);
        if (stage) {
            this.openStage(pipeline, stage);
        }
    }

    onBarSliceClick(pipeline, index) {
        const stage = pipeline.stages[index];
        if (stage) {
            this.openStage(pipeline, stage);
        }
    }
}

registry.category("actions").add("workshop_dashboard_tags", WorkshopDashboard);
