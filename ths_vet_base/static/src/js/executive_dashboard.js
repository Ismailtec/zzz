/** @odoo-module **/

import {Component, useState, onMounted, onWillStart} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";
import {loadJS} from "@web/core/assets";

// ========== 1. EXECUTIVE DASHBOARD COMPONENT ==========

class VetExecutiveDashboard extends Component {
    static template = "ths_vet_base.ExecutiveDashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            data: null,
            loading: true,
            error: false,
            lastUpdated: null
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
        });

        onMounted(() => {
            this.loadDashboardData();
            setInterval(() => this.loadDashboardData(), 300000);
        });
    }

    async loadDashboardData() {
        try {
            this.state.loading = true;
            this.state.error = false;

            this.state.data = await this.orm.call('vet.dashboard.data', 'get_executive_dashboard_data', []);
            this.state.lastUpdated = new Date().toLocaleString();

            // Render charts after data is loaded
            setTimeout(() => {
                this.renderCharts();
            }, 100);

        } catch (error) {
            console.error('Dashboard loading error:', error);
            this.state.error = true;
            this.notification.add(_t("Failed to load dashboard data"), {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
        }
    }

    renderCharts() {
        if (!this.state.data) return;

        // Revenue Trend Chart
        this.renderRevenueChart();

        // Species Distribution Chart
        this.renderSpeciesChart();

        // Service Revenue Chart
        this.renderServiceRevenueChart();

        // Payment Status Chart
        this.renderPaymentStatusChart();
    }

    renderRevenueChart() {
        const canvas = document.getElementById('revenueChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const currencySymbol = this.state.data.currency.symbol;

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: this.state.data.revenue.trend.map(item => item.month),
                datasets: [{
                    label: 'Monthly Revenue',
                    data: this.state.data.revenue.trend.map(item => item.revenue),
                    borderColor: '#28a745',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return value.toLocaleString() + ' ' + currencySymbol;
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return 'Revenue: ' + context.raw.toLocaleString() + ' ' + currencySymbol;
                            }
                        }
                    }
                }
            }
        });
    }

    renderSpeciesChart() {
        const canvas = document.getElementById('speciesChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        if (!this.state.data.patients || !this.state.data.patients.species_distribution) return;

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: this.state.data.patients.species_distribution.map(item => item.species),
                datasets: [{
                    data: this.state.data.patients.species_distribution.map(item => item.count),
                    backgroundColor: [
                        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
                        '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    renderServiceRevenueChart() {
        const canvas = document.getElementById('serviceRevenueChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const currencySymbol = this.state.data.currency.symbol;

        if (!this.state.data.services || !this.state.data.services.revenue_by_service) return;

        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: this.state.data.services.revenue_by_service.map(item => item.service),
                datasets: [{
                    label: 'Revenue',
                    data: this.state.data.services.revenue_by_service.map(item => item.revenue),
                    backgroundColor: '#007bff',
                    borderColor: '#0056b3',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return value.toLocaleString() + ' ' + currencySymbol;
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    renderPaymentStatusChart() {
        const canvas = document.getElementById('paymentStatusChart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const currencySymbol = this.state.data.currency.symbol;

        if (!this.state.data.payments || !this.state.data.payments.by_status) return;

        new Chart(ctx, {
            type: 'pie',
            data: {
                labels: this.state.data.payments.by_status.map(item => item.status),
                datasets: [{
                    data: this.state.data.payments.by_status.map(item => item.amount),
                    backgroundColor: ['#28a745', '#ffc107', '#dc3545', '#6c757d', '#17a2b8']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return context.label + ': ' + context.raw.toLocaleString() + ' ' + currencySymbol;
                            }
                        }
                    }
                }
            }
        });
    }

    async refreshDashboard() {
        await this.loadDashboardData();
        this.notification.add(_t("Dashboard refreshed"), {
            type: "success"
        });
    }

    openRevenueAnalysis() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Revenue Analysis',
            res_model: 'vet.encounter.line',
            view_mode: 'pivot,graph,list',
            views: [[false, 'pivot'], [false, 'graph'], [false, 'list']],
            domain: [['payment_status', '=', 'paid']],
            context: {
                pivot_measures: ['sub_total'],
                pivot_row_groupby: ['encounter_month'],
                graph_measure: 'sub_total',
                graph_type: 'line'
            }
        });
    }

    openPatientAnalysis() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Patient Analysis',
            res_model: 'res.partner',
            view_mode: 'pivot,graph,list',
            views: [[false, 'pivot'], [false, 'graph'], [false, 'list']],
            domain: [['is_pet', '=', true]],
            context: {
                pivot_row_groupby: ['species_id'],
                graph_type: 'pie',
                graph_groupbys: ['species_id']
            }
        });
    }
}

// ========== 2. OPERATIONAL DASHBOARD COMPONENT ==========

class VetOperationalDashboard extends Component {
    static template = "ths_vet_base.OperationalDashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            data: null,
            loading: true,
            error: false,
            lastUpdated: null
        });

        onMounted(() => {
            this.loadDashboardData();
            // Auto-refresh every 2 minutes for operational data
            setInterval(() => this.loadDashboardData(), 120000);
        });
    }

    async loadDashboardData() {
        try {
            this.state.loading = true;
            this.state.error = false;

            this.state.data = await this.orm.call('vet.dashboard.data', 'get_operational_dashboard_data', []);
            this.state.lastUpdated = new Date().toLocaleString();

        } catch (error) {
            console.error('Operational dashboard loading error:', error);
            this.state.error = true;
            this.notification.add(_t("Failed to load operational data"), {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
        }
    }

    async refreshDashboard() {
        await this.loadDashboardData();
        this.notification.add(_t("Operational dashboard refreshed"), {
            type: "success"
        });
    }

    openEncounters() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Today\'s Encounters',
            res_model: 'vet.encounter.header',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['encounter_date', '=', new Date().toISOString().split('T')[0]]]
        });
    }

    openPendingPayments() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Pending Payments',
            res_model: 'vet.encounter.line',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['payment_status', 'in', ['pending', 'partial']]]
        });
    }
}

// ========== 3. REGISTER COMPONENTS ==========

registry.category("actions").add("vet_executive_dashboard", VetExecutiveDashboard);
registry.category("actions").add("vet_operational_dashboard", VetOperationalDashboard);