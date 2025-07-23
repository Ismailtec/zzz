/** @odoo-module **/

import {Component, onWillStart, onMounted, useState, useRef} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class EncounterDashboard extends Component {
    static template = "ths_vet_base.vet_encounter_dashboard_template";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            dashboardData: {},
        });

        this.encountersChartRef = useRef("encountersChart");
        this.statusChartRef = useRef("statusChart");

        onWillStart(this.onWillStart);
        onMounted(this.onMounted);
    }

    async onWillStart() {
        await this.loadDashboardData();
    }

    onMounted() {
        this.renderCharts();
    }

    async loadDashboardData() {
        try {
            // Call your model method to get dashboard data
            this.state.dashboardData = await this.orm.call(
                "vet.encounter.header",
                "get_dashboard_data",
                []
            );
        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.dashboardData = {
                daily_encounters: 0,
                daily_revenue: 0,
                daily_patients: 0,
                pending_amount: 0,
                chart_data: [],
                status_data: {}
            };
        }
    }

    renderCharts() {
        // You'll need to include Chart.js for this to work
        if (typeof Chart !== 'undefined') {
            this.renderEncountersChart();
            this.renderStatusChart();
        }
    }

    renderEncountersChart() {
        const canvas = this.encountersChartRef.el;
        if (!canvas) return;

        const chartData = this.state.dashboardData.chart_data || [];

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: chartData.map(item => item.date),
                datasets: [{
                    label: 'Daily Encounters',
                    data: chartData.map(item => item.count),
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    renderStatusChart() {
        const canvas = this.statusChartRef.el;
        if (!canvas) return;

        const statusData = this.state.dashboardData.status_data || {};

        new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: Object.keys(statusData),
                datasets: [{
                    data: Object.values(statusData),
                    backgroundColor: [
                        '#FF6384',
                        '#36A2EB',
                        '#FFCE56',
                        '#4BC0C0'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    async executeAction(actionName) {
        try {
            const action = await this.orm.call(
                "vet.encounter.header",
                "get_dashboard_action",
                [actionName]
            );

            if (action) {
                await this.action.doAction(action);
            }
        } catch (error) {
            console.error("Error executing action:", error);
            this.notification.add("Error executing action", {type: "danger"});
        }
    }

    async refreshDashboard() {
        await this.loadDashboardData();
        this.renderCharts();
        this.notification.add("Dashboard refreshed", {type: "success"});
    }
}

// Register the component
registry.category("actions").add("encounter_dashboard", EncounterDashboard);