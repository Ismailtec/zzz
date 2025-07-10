# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, _, Command
# from odoo.exceptions import UserError
# from datetime import datetime, date

import logging

from odoo.tools import format_date

_logger = logging.getLogger(__name__)


class ThsMedicalEncounter(models.Model):
	""" Represents a single clinical encounter/visit. """
	_name = 'ths.medical.base.encounter'
	_description = 'Medical Encounter'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_order = 'encounter_date desc, name desc'

	name = fields.Char(
		string='Encounter ID',
		required=True,
		copy=False,
		readonly=True,
		index=True,
		default=lambda self: _('New')
	)

	encounter_date = fields.Date(
		string='Encounter Date',
		required=True,
		default=fields.Date.context_today,
		index=True,
		help="Date for this encounter - one encounter per partner per date"
	)

	# For medical: partner_id = patient (same person receiving care and paying)
	partner_id = fields.Many2one(
		'res.partner',
		string='Patient (Billing)',  # In medical, patient is the customer
		store=True,
		index=True,
		help="Billing customer."
	)

	# For medical: patient_ids = [patient]
	patient_ids = fields.Many2many(
		'res.partner',
		'medical_encounter_patient_rel',
		'encounter_id',
		'patient_id',
		string='Patients',
		domain="[('partner_type_id.is_patient', '=', True)]",
		store=True,
		index=True,
		help="Patients participating in this encounter. In human medical practice, these are the same people as in partner_id."
	)

	# TODO: Add computed fields for primary patient info for backward compatibility
	patient_mobile = fields.Char(string="Partner Mobile", related='partner_id.mobile', store=False, readonly=True)

	practitioner_id = fields.Many2one(
		'appointment.resource',
		string='Service Provider',
		domain="[('resource_category', '=', 'practitioner')]",
		store=True,
		index=True,
	)
	room_id = fields.Many2one(
		'appointment.resource',
		string='Room',
		domain="[('resource_category', '=', 'location')]",
		store=True,
		index=True,
	)
	room_id_domain = fields.Char(
		compute='_compute_room_id_domain',
		store=False,
		help="Domain for selecting the room based on the practitioner."
	)

	state = fields.Selection([
		('in_progress', 'In Progress'),
		('done', 'Done')
	], string='Status', default='in_progress', index=True, tracking=True, copy=False)

	appointment_ids = fields.One2many(
		'calendar.event',
		'encounter_id',
		string='Appointments',
		help="All appointments linked to this encounter"
	)

	# New computed field to derive the default appointment type from the practitioner's department
	default_appointment_type_id = fields.Many2one(
		'appointment.type',
		string="Default Appointment Type (from Practitioner Dept.)",
		compute='_compute_default_appointment_type',
		store=False,
		readonly=True,
		help="Computes a default appointment type based on the selected practitioner's department."
	)

	appointment_status = fields.Selection(
		related='appointment_ids.appointment_status',
		string='Appointment Status',
		store=True,
		readonly=True,
		help="Status of the related appointment"
	)

	pending_pos_items = fields.One2many(
		'ths.pending.pos.item',
		'encounter_id',
		string='POS Pending Items',
		copy=False
	)

	# Payment tracking
	pending_amount = fields.Float(
		string='Pending Amount',
		compute='_compute_payment_status',
		store=True,
		help="Amount of unpaid Services/Items lines"
	)
	paid_amount = fields.Float(
		string='Paid Amount',
		compute='_compute_payment_status',
		store=True,
		help="Total amount of Services/Items lines"
	)
	pending_payments = fields.Boolean(
		string='ending Payments',
		compute='_compute_payment_status',
		store=True,
		help="True if there are unpaid Services/Items lines"
	)

	notes = fields.Text(string="Internal Notes")

	# === EMR Fields (Base Text Fields) ===
	chief_complaint = fields.Text(string="Chief Complaint")
	history_illness = fields.Text(string="History of Present Illness")
	vitals = fields.Text(string="Vital Signs",
						 help="Record key vitals like Temp, HR, RR, BP etc.")

	# === SOAP Fields ===
	ths_subjective = fields.Text(string="Subjective", help="Patient's reported symptoms and history.")
	ths_objective = fields.Text(string="Objective", help="Practitioner's observations, exam findings, vitals.")
	ths_assessment = fields.Text(string="Assessment", help="Diagnosis or differential diagnosis.")
	ths_plan = fields.Text(string="Plan", help="Treatment plan, tests ordered, prescriptions, follow-up.")

	# === Other Clinical Details (as Text) ===
	ths_diagnosis_text = fields.Text(string="Diagnoses Summary", help="Summary of diagnoses made during encounter.")
	ths_procedures_text = fields.Text(string="Procedures Summary", help="Summary of procedures performed.")
	ths_prescriptions_text = fields.Text(string="Prescriptions Summary", help="Summary of medications prescribed.")
	ths_lab_orders_text = fields.Text(string="Lab Orders Summary", help="Summary of laboratory tests ordered.")
	ths_radiology_orders_text = fields.Text(string="Radiology Orders Summary",
											help="Summary of radiology exams ordered.")

	@api.depends('practitioner_id')
	def _compute_room_id_domain(self):
		""" Compute domain for room_id based on practitioner_id """
		for record in self:
			if record.practitioner_id and record.practitioner_id.ths_department_id:
				record.room_id_domain = str([
					('resource_category', '=', 'location'),
					('ths_department_id', '=', record.practitioner_id.ths_department_id.id)
				])
			else:
				record.room_id_domain = str([('resource_category', '=', 'location')])

	@api.depends('practitioner_id.ths_department_id')
	def _compute_default_appointment_type(self):
		"""  Computes the default appointment type ID based on the practitioner's associated department.
			 It searches for an appointment type that has this department linked to it.  """
		for rec in self:
			rec.default_appointment_type_id = False

			if rec.practitioner_id and rec.practitioner_id.ths_department_id:
				appointment_type = self.env['appointment.type'].search([
					('department_ids', 'in', rec.practitioner_id.ths_department_id.id)
				], limit=1)

				rec.default_appointment_type_id = appointment_type.id if appointment_type else False

	@api.model
	def _get_encounter_domain_by_context(self):
		domain = []
		date_filter = self.env.context.get('search_encounter_date_range')
		today = fields.Date.context_today(self)

		if date_filter == 'this_week':
			start_week = today - timedelta(days=today.weekday())
			end_week = start_week + timedelta(days=6)
			domain += [('encounter_date', '>=', start_week), ('encounter_date', '<=', end_week)]

		elif date_filter == 'last_week':
			start_last_week = today - timedelta(days=today.weekday() + 7)
			end_last_week = start_last_week + timedelta(days=6)
			domain += [('encounter_date', '>=', start_last_week), ('encounter_date', '<=', end_last_week)]

		return domain

	@api.depends('pending_pos_items.qty', 'pending_pos_items.discount', 'pending_pos_items.product_id.lst_price')
	def _compute_payment_status(self):
		for encounter in self:
			pending_lines = encounter.pending_pos_items.filtered(lambda o: o.state == 'pending')
			encounter.pending_amount = sum(
				line.qty * line.product_id.lst_price * (1 - line.discount / 100) for line in pending_lines)
			paid_lines = encounter.pending_pos_items.filtered(lambda o: o.state == 'processed')
			encounter.paid_amount = sum(paid_lines.mapped('sub_total'))
			encounter.pending_payments = encounter.pending_amount > 0
			if encounter.pending_payments:
				encounter.state = 'in_progress'
			else:
				encounter.state = 'done'

	@api.model
	def _find_or_create_daily_encounter(
			self, partner_id, patient_ids=None, encounter_date=None, practitioner_id=None, room_id=None):
		"""Find existing encounter for partner+date or create new one"""
		domain = [
			('partner_id', '=', partner_id),
			('encounter_date', '=', encounter_date),
		]
		encounter = self.search(domain, limit=1)

		if not encounter:
			vals = {
				'partner_id': partner_id,
				'encounter_date': encounter_date,
				'patient_ids': [Command.set(patient_ids)],  # Set initial patients
				'practitioner_id': practitioner_id.id if practitioner_id else False,
				'room_id': room_id.id if room_id else False,
			}
			encounter = self.create(vals)
		else:
			update_vals = {}

			if practitioner_id and (
					not encounter.practitioner_id or encounter.practitioner_id.id != practitioner_id.id):
				update_vals['practitioner_id'] = practitioner_id.id

			if room_id and (not encounter.room_id or encounter.room_id.id != room_id.id):
				update_vals['room_id'] = room_id.id

			current_encounter_patient_ids = encounter.patient_ids.ids
			all_unique_patient_ids = list(set(current_encounter_patient_ids + patient_ids))

			if set(all_unique_patient_ids) != set(current_encounter_patient_ids):
				update_vals['patient_ids'] = [Command.set(all_unique_patient_ids)]

			if update_vals:
				encounter.write(update_vals)
		return encounter

	@api.depends('name', 'encounter_date', 'partner_id.name')
	def name_get(self):
		"""  Formats the display as: "Encounter Name, Date - Partner Name"  """
		result = []
		for encounter in self:
			encounter_name = encounter.name or _('New Encounter')

			encounter_date_str = ""
			if encounter.encounter_date:
				encounter_date_str = format_date(self.env, encounter.encounter_date)

			partner_name = encounter.partner_id.name or _('No Partner')

			display_name = f"{encounter_name} ({encounter_date_str}) - {partner_name}"

			result.append((encounter.id, display_name))
		return result

	# TODO: Add similar helper methods for practitioner_id and room_id formatting
	# TODO: Consider caching formatted data for performance
	def _get_formatted_patient_ids_with_names(self):
		"""
		Helper method to format patient_ids as [[id, name], [id, name]] for frontend consumption
		Replaces raw IDs with proper [id, name] format
		"""
		self.ensure_one()
		if not self.patient_ids:
			return []

		formatted_patients = []
		for patient in self.patient_ids:
			formatted_patients.append([patient.id, patient.name])

		return formatted_patients

	@api.model
	def get_formatted_patients_for_encounter_list(self, encounter_ids):
		"""
		Batch method to format patient_ids for multiple encounters
		Used in POS data loading to avoid N+1 queries
		"""
		encounters = self.browse(encounter_ids)
		result = {}

		for encounter in encounters:
			result[encounter.id] = encounter._get_formatted_patient_ids_with_names()

		return result

	# --- Overrides ---
	@api.model_create_multi
	def create(self, vals_list):
		""" Assign sequence on creation. """
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('medical.encounter') or _('New')

			# Ensure encounter_date is set
			if not vals.get('encounter_date'):
				vals['encounter_date'] = fields.Date.context_today(self)

		return super(ThsMedicalEncounter, self).create(vals_list)

	_sql_constraints = [
		('unique_partner_date', 'unique(partner_id, encounter_date)',
		 'Only one encounter per partner per date is allowed!'),
	]

	# --- Actions ---
	def action_view_appointments(self):
		"""View all appointments for this encounter"""
		self.ensure_one()
		return {
			'name': _('Appointments'),
			'type': 'ir.actions.act_window',
			'res_model': 'calendar.event',
			'view_mode': 'list,form',
			'domain': [('encounter_id', '=', self.id)],
			'context': {'create': False}
		}

	def action_view_pos_orders(self):
		"""View all POS orders for this encounter"""
		self.ensure_one()
		return {
			'name': _('POS Orders'),
			'type': 'ir.actions.act_window',
			'res_model': 'pos.order',
			'view_mode': 'list,form',
			'domain': [('encounter_id', '=', self.id)],
			'context': {'create': False}
		}

	def add_service_to_encounter(self, service_model, service_id):
		"""Generic method to link any service to this encounter"""
		self.ensure_one()
		service = self.env[service_model].browse(service_id)
		if hasattr(service, 'encounter_id'):
			service.encounter_id = self.id
		return True

# TODO: Add encounter analytics dashboard for daily metrics
# TODO: Implement encounter merge functionality for same-day duplicates
# TODO: Add encounter templates for common service combinations
# TODO: Implement encounter archiving for old records after 1 year
# TODO: Add encounter automatic closure after 7 days of inactivity
# TODO: Implement encounter follow-up scheduling system
# TODO: Add encounter insurance integration for claims
# TODO: Implement encounter inventory tracking for consumed items
# TODO: Create encounter performance metrics per practitioner
# TODO: Add encounter timezone handling for multi-location clinics