# -*- coding: utf-8 -*-
from datetime import timedelta, datetime, time
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, http

import logging

from odoo.http import request

_logger = logging.getLogger(__name__)


class VetDashboardData(models.Model):
	_name = 'vet.dashboard.data'
	_description = 'Veterinary Dashboard Data'
	_auto = False  # Prevents table creation - this is a data model

	@api.model
	def get_executive_dashboard_data(self):
		"""Get high-level KPIs for executive dashboard"""
		today = fields.Date.today()
		current_month = today.replace(day=1)
		last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
		current_year = today.replace(month=1, day=1)

		# Revenue KPIs
		revenue_data = self._get_revenue_metrics(today, current_month, current_year)

		# Patient KPIs
		patient_data = self._get_patient_metrics(today, current_month, current_year)

		# Service KPIs
		service_data = self._get_service_metrics(today, current_month, current_year)

		# Practitioner KPIs
		practitioner_data = self._get_practitioner_metrics(today, current_month)

		# Payment KPIs
		payment_data = self._get_payment_metrics()

		return {
			'revenue': revenue_data,
			'patients': patient_data,
			'services': service_data,
			'practitioners': practitioner_data,
			'payments': payment_data,
			'currency': {
				'symbol': self.env.company.currency_id.symbol,
				'position': self.env.company.currency_id.position,
				'name': self.env.company.currency_id.name
			},
			'generated_at': fields.Datetime.now().isoformat()
		}

	def _get_revenue_metrics(self, today, current_month, current_year):
		"""Calculate revenue metrics"""

		# Today's revenue
		today_revenue = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '=', today), ('payment_status', '=', 'paid')],
			['sub_total:sum'], []
		)[0]['sub_total'] or 0

		# This month's revenue
		month_revenue = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_month), ('payment_status', '=', 'paid')],
			['sub_total:sum'], []
		)[0]['sub_total'] or 0

		# This year's revenue
		year_revenue = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_year), ('payment_status', '=', 'paid')],
			['sub_total:sum'], []
		)[0]['sub_total'] or 0

		# Pending revenue
		pending_revenue = self.env['vet.encounter.line'].read_group(
			[('payment_status', 'in', ['pending', 'partial', 'posted'])],
			['sub_total:sum'], []
		)[0]['sub_total'] or 0

		# Revenue trend (last 12 months)
		revenue_trend = []
		for i in range(12):
			month_start = (current_month - relativedelta(months=i))
			month_end = month_start + relativedelta(months=1) - timedelta(days=1)

			month_rev = self.env['vet.encounter.line'].read_group(
				[('encounter_id.encounter_date', '>=', month_start),
				 ('encounter_id.encounter_date', '<=', month_end),
				 ('payment_status', '=', 'paid')],
				['sub_total:sum'], []
			)[0]['sub_total'] or 0

			revenue_trend.insert(0, {
				'month': month_start.strftime('%b %Y'),
				'revenue': month_rev
			})

		return {
			'today': today_revenue,
			'month': month_revenue,
			'year': year_revenue,
			'pending': pending_revenue,
			'trend': revenue_trend
		}

	def _get_patient_metrics(self, today, current_month, current_year):
		"""Calculate patient metrics"""

		# Today's patients
		today_patients = len(self.env['vet.encounter.header'].search([
			('encounter_date', '=', today)
		]).mapped('patient_ids'))

		# This month's unique patients
		month_patients = len(self.env['vet.encounter.header'].search([
			('encounter_date', '>=', current_month)
		]).mapped('patient_ids'))

		# Total active patients (had encounter in last 12 months)
		active_patients = len(self.env['vet.encounter.header'].search([
			('encounter_date', '>=', current_year)
		]).mapped('patient_ids'))

		# New patients this month
		new_patients = self.env['res.partner'].search_count([
			('is_pet', '=', True),
			('create_date', '>=', current_month)
		])

		# Species distribution - FIXED for your res.partner.species_id structure
		species_data = self.env['res.partner'].read_group(
			[('is_pet', '=', True), ('species_id', '!=', False)],
			['species_id'], ['species_id']
		)

		species_chart = [{
			'species': item['species_id'][1] if item['species_id'] else 'Unknown',
			'count': item['species_id_count']
		} for item in species_data]

		return {
			'today': today_patients,
			'month': month_patients,
			'active': active_patients,
			'new_month': new_patients,
			'species_distribution': species_chart
		}

	def _get_service_metrics(self, today, current_month, current_year):
		"""Calculate service metrics"""

		# Most popular services this month
		popular_services = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_month)],
			['product_id', 'qty:sum'], ['product_id'],
			orderby='qty desc', limit=10
		)

		services_chart = [{
			'service': item['product_id'][1],
			'count': item['qty']
		} for item in popular_services]

		# Service revenue breakdown
		service_revenue = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_month), ('payment_status', '=', 'paid')],
			['product_id', 'sub_total:sum'], ['product_id'],
			orderby='sub_total desc', limit=10
		)

		revenue_chart = [{
			'service': item['product_id'][1],
			'revenue': item['sub_total']
		} for item in service_revenue]

		return {
			'popular_services': services_chart,
			'revenue_by_service': revenue_chart
		}

	def _get_practitioner_metrics(self, today, current_month):
		"""Calculate practitioner performance metrics"""

		# Practitioner revenue this month
		practitioner_revenue = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_month),
			 ('practitioner_id', '!=', False),
			 ('payment_status', '=', 'paid')],
			['practitioner_id', 'sub_total:sum'], ['practitioner_id'],
			orderby='sub_total desc'
		)

		revenue_chart = [{
			'practitioner': item['practitioner_id'][1] if item['practitioner_id'] else 'Unknown',
			'revenue': item['sub_total']
		} for item in practitioner_revenue]

		# Practitioner patient count this month
		practitioner_patients = self.env['vet.encounter.header'].read_group(
			[('encounter_date', '>=', current_month), ('practitioner_id', '!=', False)],
			['practitioner_id'], ['practitioner_id']
		)

		patient_chart = [{
			'practitioner': item['practitioner_id'][1] if item['practitioner_id'] else 'Unknown',
			'patients': item['practitioner_id_count']
		} for item in practitioner_patients]

		return {
			'revenue_by_practitioner': revenue_chart,
			'patients_by_practitioner': patient_chart
		}

	def _get_department_metrics(self, current_month):
		"""Calculate department performance metrics"""

		# Department revenue this month
		dept_revenue = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_month),
			 ('practitioner_id.ths_department_id', '!=', False),
			 ('payment_status', '=', 'paid')],
			['practitioner_id.ths_department_id', 'sub_total:sum'],
			['practitioner_id.ths_department_id'],
			orderby='sub_total desc'
		)

		dept_chart = [{
			'department': item['practitioner_id.ths_department_id'][1] if item['practitioner_id.ths_department_id'] else 'No Department',
			'revenue': item['sub_total']
		} for item in dept_revenue]

		# Department patient count
		dept_patients = self.env['vet.encounter.header'].read_group(
			[('encounter_date', '>=', current_month),
			 ('practitioner_id.ths_department_id', '!=', False)],
			['practitioner_id.ths_department_id'],
			['practitioner_id.ths_department_id']
		)

		dept_patient_chart = [{
			'department': item['practitioner_id.ths_department_id'][1] if item['practitioner_id.ths_department_id'] else 'No Department',
			'patients': item['practitioner_id.ths_department_id_count']
		} for item in dept_patients]

		return {
			'revenue_by_department': dept_chart,
			'patients_by_department': dept_patient_chart
		}

	def _get_service_analysis(self, current_month):
		"""Enhanced service analysis with department breakdown"""

		# Service performance by department
		service_dept = self.env['vet.encounter.line'].read_group(
			[('encounter_id.encounter_date', '>=', current_month)],
			['product_id', 'practitioner_id.ths_department_id', 'sub_total:sum', 'qty:sum'],
			['product_id', 'practitioner_id.ths_department_id'],
			orderby='sub_total desc', limit=20
		)

		service_analysis = [{
			'service': item['product_id'][1] if item['product_id'] else 'Unknown',
			'department': item['practitioner_id.ths_department_id'][1] if item['practitioner_id.ths_department_id'] else 'No Department',
			'revenue': item['sub_total'],
			'quantity': item['qty']
		} for item in service_dept]

		return {
			'service_department_analysis': service_analysis
		}

	def _get_appointment_analysis(self, current_month):
		"""Comprehensive appointment analysis for BI"""

		# Appointment status distribution
		apt_status = self.env['calendar.event'].read_group(
			[('start', '>=', current_month)],
			['appointment_status'], ['appointment_status']
		)

		status_chart = [{
			'status': item['appointment_status'],
			'count': item['appointment_status_count']
		} for item in apt_status]

		# Appointment types performance
		apt_types = self.env['calendar.event'].read_group(
			[('start', '>=', current_month)],
			['appointment_type_id', 'actual_duration:avg'],
			['appointment_type_id']
		)

		type_chart = [{
			'type': item['appointment_type_id'][1] if item['appointment_type_id'] else 'No Type',
			'count': item['appointment_type_id_count'],
			'avg_duration': item['actual_duration'] or 0
		} for item in apt_types]

		# Department appointment load
		dept_appointments = self.env['calendar.event'].read_group(
			[('start', '>=', current_month),
			 ('practitioner_id.ths_department_id', '!=', False)],
			['practitioner_id.ths_department_id'],
			['practitioner_id.ths_department_id']
		)

		dept_apt_chart = [{
			'department': item['practitioner_id.ths_department_id'][1],
			'appointments': item['practitioner_id.ths_department_id_count']
		} for item in dept_appointments]

		# No-show analysis
		no_shows = self.env['calendar.event'].search_count([
			('start', '>=', current_month),
			('appointment_status', '=', 'no_show')
		])

		total_appointments = self.env['calendar.event'].search_count([
			('start', '>=', current_month)
		])

		no_show_rate = (no_shows / total_appointments * 100) if total_appointments > 0 else 0

		return {
			'status_distribution': status_chart,
			'type_performance': type_chart,
			'department_load': dept_apt_chart,
			'no_show_rate': no_show_rate,
			'total_appointments': total_appointments
		}

	def _get_payment_metrics(self):
		"""Calculate payment status metrics"""

		payment_status = self.env['vet.encounter.line'].read_group(
			[], ['payment_status', 'sub_total:sum'], ['payment_status']
		)

		status_chart = [{
			'status': item['payment_status'].title(),
			'amount': item['sub_total']
		} for item in payment_status]

		return {
			'by_status': status_chart
		}

	@api.model
	def get_operational_dashboard_data(self):
		"""Get detailed operational metrics for managers"""
		today = fields.Date.today()

		# Today's schedule - FIXED for calendar.event structure
		today_appointments = self.env['calendar.event'].search([
			('start', '>=', datetime.combine(today, time.min)),
			('start', '<=', datetime.combine(today, time.max))
		])

		schedule_data = [{
			'time': apt.start.strftime('%H:%M'),
			'patient': ', '.join(apt.patient_ids.mapped('name')) if apt.patient_ids else '',
			'owner': apt.pet_owner_id.name if apt.pet_owner_id else '',
			'practitioner': apt.practitioner_id.name if apt.practitioner_id else '',
			'status': apt.appointment_status,
			'type': apt.appointment_type_id.name if apt.appointment_type_id else ''
		} for apt in today_appointments]

		# Boarding occupancy - FIXED for vet.boarding.cage
		current_boardings = self.env['vet.boarding.stay'].search([
			('state', 'in', ['checked_in', 'scheduled'])  # Active boarding states
		])

		total_cages = self.env['vet.boarding.cage'].search_count([
			('active', '=', True)
		])

		occupancy_rate = (len(current_boardings) / total_cages * 100) if total_cages > 0 else 0

		# Pending tasks
		pending_encounters = self.env['vet.encounter.header'].search_count([
			('state', '=', 'in_progress')
		])

		pending_payments = self.env['vet.encounter.line'].search_count([
			('payment_status', 'in', ['pending', 'partial'])
		])

		# Low stock alerts (if you have stock management)
		low_stock = self.env['product.product'].search_count([
			('type', '=', 'consu'),
			('qty_available', '<=', 5)
		])

		return {
			'schedule': schedule_data,
			'boarding': {
				'occupied': len(current_boardings),
				'total_cages': total_cages,
				'occupancy_rate': occupancy_rate
			},
			'pending_tasks': {
				'encounters': pending_encounters,
				'payments': pending_payments,
				'low_stock': low_stock
			},
			'generated_at': fields.Datetime.now().isoformat()
		}

	@api.model
	def action_dashboard_data_refresh_all(self):
		"""Single method to refresh all dashboard computed fields"""
		# Refresh encounter line computed fields for better dashboard performance
		encounter_lines = self.env['vet.encounter.line'].search([])
		if encounter_lines:
			encounter_lines._compute_encounter_month()
			encounter_lines._compute_encounter_week()
			encounter_lines._compute_revenue_per_patient()
			encounter_lines._compute_payment_amounts()
			encounter_lines._compute_payment_status()

		# Refresh encounter header payment summaries
		encounters = self.env['vet.encounter.header'].search([])
		if encounters:
			encounters._compute_payment_status()
			encounters._compute_total()

		return True


# ========== 2. DASHBOARD CONTROLLER ==========

class VetDashboardController(http.Controller):

	@http.route('/vet/dashboard/executive', type='json', auth='user')
	def executive_dashboard(self):
		"""API endpoint for executive dashboard data"""
		return request.env['vet.dashboard.data'].get_executive_dashboard_data()

	@http.route('/vet/dashboard/operational', type='json', auth='user')
	def operational_dashboard(self):
		"""API endpoint for operational dashboard data"""
		return request.env['vet.dashboard.data'].get_operational_dashboard_data()


# ========== 3. DASHBOARD MODELS FOR VIEWS ==========

class VetExecutiveDashboard(models.TransientModel):
	_name = 'vet.executive.dashboard'
	_description = 'Executive Dashboard'

	name = fields.Char(default='Executive Dashboard', readonly=True)
	date_from = fields.Date(string='From', default=lambda self: fields.Date.today().replace(day=1))
	date_to = fields.Date(string='To', default=fields.Date.today)

	@api.model
	def action_refresh_dashboard(self):
		"""Refresh dashboard data"""
		return {
			'type': 'ir.actions.client',
			'tag': 'vet_executive_dashboard',
			'target': 'current',
		}


class VetOperationalDashboard(models.TransientModel):
	_name = 'vet.operational.dashboard'
	_description = 'Operational Dashboard'

	name = fields.Char(default='Operational Dashboard', readonly=True)
	date_filter = fields.Selection([
		('today', 'Today'),
		('week', 'This Week'),
		('month', 'This Month')
	], default='today')

	@api.model
	def action_refresh_dashboard(self):
		"""Refresh operational dashboard"""
		return {
			'type': 'ir.actions.client',
			'tag': 'vet_operational_dashboard',
			'target': 'current',
		}


# ========== 4. DASHBOARD ACTIONS ==========

class VetDashboardActions(models.Model):
	_name = 'vet.dashboard.actions'
	_description = 'Dashboard Action Handlers'

	@api.model
	def action_executive_dashboard(self):
		"""Open executive dashboard"""
		return {
			'type': 'ir.actions.client',
			'name': 'Executive Dashboard',
			'tag': 'vet_executive_dashboard',
			'target': 'current',
		}

	@api.model
	def action_operational_dashboard(self):
		"""Open operational dashboard"""
		return {
			'type': 'ir.actions.client',
			'name': 'Operational Dashboard',
			'tag': 'vet_operational_dashboard',
			'target': 'current',
		}

	@api.model
	def action_revenue_report(self):
		"""Open detailed revenue analysis"""
		return {
			'type': 'ir.actions.act_window',
			'name': 'Revenue Analysis',
			'res_model': 'vet.encounter.line',
			'view_mode': 'pivot,graph,list',
			'domain': [('payment_status', '=', 'paid')],
			'context': {
				'pivot_measures': ['sub_total'],
				'pivot_row_groupby': ['encounter_id.encounter_date:month'],
				'pivot_column_groupby': ['product_id'],
				'graph_measure': 'sub_total',
				'graph_type': 'line',
				'graph_groupbys': ['encounter_id.encounter_date:month']
			}
		}

	@api.model
	def action_patient_analysis(self):
		"""Open patient analysis report"""
		return {
			'type': 'ir.actions.act_window',
			'name': 'Patient Analysis',
			'res_model': 'res.partner',
			'view_mode': 'pivot,graph,list',
			'domain': [('is_pet', '=', True)],
			'context': {
				'pivot_row_groupby': ['species_id'],
				'pivot_column_groupby': ['pet_owner_id'],
				'graph_type': 'pie',
				'graph_groupbys': ['species_id']
			}
		}