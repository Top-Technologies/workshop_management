/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { getBorderWhite, getColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";
import { Component, onWillStart, useEffect, useRef } from "@odoo/owl";

const colorScheme = () => cookie.get("color_scheme");
const LABEL_COLOR = () => (colorScheme() === "dark" ? "#E4E4E4" : "#374151");
const GRID_COLOR = () => (colorScheme() === "dark" ? "rgba(255,255,255,.12)" : "rgba(0,0,0,.08)");

export class WorkshopChart extends Component {
    static template = "workshop_management.WorkshopChart";
    static props = {
        type: { type: String }, // pie | doughnut | bar
        labels: { type: Array },
        data: { type: Array },
        colors: { type: Array, optional: true },
        dataSecondary: { type: Array, optional: true },
        labelPrimary: { type: String, optional: true },
        labelSecondary: { type: String, optional: true },
        colorsSecondary: { type: Array, optional: true },
        horizontal: { type: Boolean, optional: true },
        height: { type: Number, optional: true },
        onSliceClick: { type: Function, optional: true },
    };

    setup() {
        this.chart = null;
        this.canvasRef = useRef("canvas");

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
        });

        useEffect(
            () => {
                this.renderChart();
                return () => this.destroyChart();
            },
            () => [
                this.props.type,
                this.props.horizontal,
                this.props.height,
                JSON.stringify(this.props.labels),
                JSON.stringify(this.props.data),
                JSON.stringify(this.props.colors),
                JSON.stringify(this.props.dataSecondary || []),
            ]
        );
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    _resolveColors() {
        if (this.props.colors?.length) {
            return this.props.colors;
        }
        return this.props.labels.map((_, index) =>
            getColor(index, colorScheme(), this.props.labels.length)
        );
    }

    renderChart() {
        const canvas = this.canvasRef.el;
        if (!canvas || !window.Chart) {
            return;
        }
        this.destroyChart();

        const colors = this._resolveColors();
        const borderColor = getBorderWhite(colorScheme());
        const secondary = this.props.dataSecondary || [];
        const hasSecondary = secondary.length > 0;
        const hasData =
            this.props.data.some((value) => value > 0) ||
            secondary.some((value) => value > 0);

        if (!hasData) {
            return;
        }

        const isHorizontal = this.props.horizontal && this.props.type === "bar";
        const datasets = [
            {
                label: this.props.labelPrimary || "",
                data: this.props.data,
                backgroundColor: colors,
                borderColor: this.props.type === "bar" ? colors : borderColor,
                borderWidth: this.props.type === "bar" ? 0 : 1,
                borderRadius: this.props.type === "bar" ? 4 : 0,
                hoverOffset: this.props.type === "pie" || this.props.type === "doughnut" ? 6 : 0,
            },
        ];
        if (hasSecondary) {
            const secondaryColors = this.props.colorsSecondary?.length
                ? this.props.colorsSecondary
                : this.props.labels.map(() => "#38bdf8");
            datasets.push({
                label: this.props.labelSecondary || "",
                data: secondary,
                backgroundColor: secondaryColors,
                borderColor: secondaryColors,
                borderWidth: 0,
                borderRadius: 4,
            });
        }
        const config = {
            type: this.props.type === "doughnut" ? "doughnut" : this.props.type,
            data: {
                labels: this.props.labels,
                datasets,
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: isHorizontal ? "y" : "x",
                onClick: (event, elements) => {
                    if (elements.length && this.props.onSliceClick) {
                        this.props.onSliceClick(elements[0].index);
                    }
                },
                plugins: {
                    legend: {
                        display:
                            this.props.type === "pie" ||
                            this.props.type === "doughnut" ||
                            hasSecondary,
                        position: "bottom",
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            color: LABEL_COLOR(),
                            padding: 12,
                            font: { size: 11 },
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = isHorizontal
                                    ? context.parsed.x
                                    : context.parsed.y ?? context.parsed ?? context.raw;
                                const total = this.props.data.reduce((sum, n) => sum + n, 0);
                                const pct = total ? Math.round((value / total) * 100) : 0;
                                return ` ${value} (${pct}%)`;
                            },
                        },
                    },
                },
                scales:
                    this.props.type === "bar"
                        ? {
                              x: {
                                  beginAtZero: true,
                                  grid: { color: GRID_COLOR() },
                                  ticks: { color: LABEL_COLOR(), precision: 0 },
                                  border: { display: false },
                              },
                              y: {
                                  beginAtZero: true,
                                  grid: { color: isHorizontal ? "transparent" : GRID_COLOR() },
                                  ticks: {
                                      color: LABEL_COLOR(),
                                      precision: 0,
                                      autoSkip: false,
                                  },
                                  border: { display: false },
                              },
                          }
                        : {},
            },
        };

        if (this.props.type === "doughnut") {
            config.options.cutout = "62%";
        }

        this.chart = new Chart(canvas, config);
    }
}
