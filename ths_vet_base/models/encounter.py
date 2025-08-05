# -*- coding: utf-8 -*-
import uuid
from datetime import timedelta, datetime, time
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, Command, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import format_date
import logging

_logger = logging.getLogger(__name__)


# --------- Encounter Mixin ---------
class EncounterMixin(models.AbstractModel):
	_name = 'vet.encounter.mixin'
	_description = 'Veterinary Encounter Mixin'
	_inherit = ['mail.thread', 'mail.activity.mixin']

	# --------- Core fields for encounters and related models ---------
	partner_id = fields.Many2one('res.partner', string='Pet Owner (Billing)', context={'default_is_pet': False, 'default_is_pet_owner': True}, required=True, index=True,
								 tracking=True, domain="[('is_pet_owner', '=', True)]", help="Pet owner responsible for billing this encounter or service.")
	pet_owner_id = fields.Many2one('res.partner', string='Pet Owner', compute='_compute_pet_owner_id', store=True, readonly=True, index=True,
								   context={'default_is_pet': False, 'default_is_pet_owner': True}, help="Computed pet owner, synchronized with partner_id.")
	patient_ids = fields.Many2many('res.partner', 'vet_encounter_mixin_patient_rel', 'encounter_id', 'patient_id', string='Pets',
								   context={'default_is_pet_owner': False, 'default_is_pet': True}, store=True, readonly=False, index=True, tracking=True,
								   domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]", help="Pets receiving veterinary care in this encounter or service.")
	practitioner_id = fields.Many2one('appointment.resource', string='Practitioner', index=True, tracking=True, copy=False, domain="[('resource_category', '=', 'practitioner')]",
									  help="Veterinarian responsible for this encounter or service.")
	room_id = fields.Many2one('appointment.resource', string='Room', index=True, tracking=True, domain="[('resource_category', '=', 'location')]",
							  help="Room where the encounter or service takes place.")
	partner_mobile = fields.Char(string="Partner Mobile", related='partner_id.mobile', store=False, readonly=True)
	is_pet = fields.Boolean(string='Is Pet', compute='_compute_partner_flags', store=False, help="Computed field for view compatibility - indicates if partner is a pet")
	is_pet_owner = fields.Boolean(string='Is Pet Owner', compute='_compute_partner_flags', store=False, help="Computed field - indicates if partner is a pet owner")
	documents_count_model = fields.Integer(string="Documents count", compute='_compute_documents_count_model')
	company_currency = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id, required=True, readonly=True)
	partner_balance = fields.Monetary('res.partner', related='partner_id.available_credit', currency_field='company_currency', readonly=True, store=False,
									  help="Available Balance for this partner")
	partner_balance_converted = fields.Monetary(string='Pet Owner Balance', compute='_compute_partner_balance', currency_field='company_currency', readonly=True, store=False,
												help="Available Balance for this partner")
	# --------- Domains ---------
	patient_ids_domain = fields.Char(compute='_compute_patient_ids_domain', store=False, help="Dynamic domain for pets based on pet owner.")
	room_id_domain = fields.Char(compute='_compute_room_id_domain', store=False, help="Domain for selecting the room based on the practitioner.")

	# --------- Default Context ---------
	default_patient_ids = fields.Many2many('res.partner', string="Default Patients from Encounter", compute='_compute_default_patient_ids', store=False, readonly=True,
										   help="Provides list of current encounter patients for O2M fields.")
	default_appointment_type_id = fields.Many2one('appointment.type', string="Default Appointment Type", compute='_compute_default_appointment_type', store=False, readonly=True,
												  help="Computes a default appointment type based on the selected practitioner's department.")

	# --------- Computes & Depends Methods ---------
	@api.depends('partner_id')
	def _compute_pet_owner_id(self):
		"""Synchronize pet_owner_id with partner_id"""
		for rec in self:
			rec.pet_owner_id = rec.partner_id if rec.partner_id and rec.partner_id.is_pet_owner else False

	@api.depends('partner_id.is_pet', 'partner_id.is_pet_owner')
	def _compute_partner_flags(self):
		"""Compute partner type flags for view compatibility"""
		for rec in self:
			rec.is_pet = rec.partner_id.is_pet if rec.partner_id else False
			rec.is_pet_owner = rec.partner_id.is_pet_owner if rec.partner_id else False

	@api.depends('partner_balance')
	def _compute_partner_balance(self):
		for partner in self:
			partner.partner_balance_converted = partner.partner_balance * -1
		else:
			self.partner_balance_converted = self.partner_balance

	@api.depends('partner_id')
	def _compute_patient_ids_domain(self):
		"""Compute dynamic domain for pets based on selected owner"""
		for rec in self:
			if rec.partner_id:
				rec.patient_ids_domain = str([
					('pet_owner_id', '=', rec.partner_id.id),
					('is_pet', '=', True)
				])
			else:
				rec.patient_ids_domain = str([('is_pet', '=', True)])

	@api.depends('practitioner_id.ths_department_id')
	def _compute_room_id_domain(self):
		""" Compute domain for room_id based on practitioner's department """
		for record in self:
			if record.practitioner_id.ths_department_id:
				record.room_id_domain = str([
					('resource_category', '=', 'location'),
					('ths_department_id', '=', record.practitioner_id.ths_department_id.id)
				])
			else:
				record.room_id_domain = str([('resource_category', '=', 'location')])

	@api.depends('patient_ids')
	def _compute_default_patient_ids(self):
		"""Compute default patient IDs for O2M fields"""
		for rec in self:
			rec.default_patient_ids = [Command.set(rec.patient_ids.ids)]

	@api.depends('practitioner_id.ths_department_id')
	def _compute_default_appointment_type(self):
		""" Computes the default appointment type ID based on the practitioner's or room's associated department. """
		for rec in self:
			rec.default_appointment_type_id = False

			if rec.practitioner_id and rec.practitioner_id.ths_department_id:
				appointment_type = self.env['appointment.type'].search([
					('department_ids', 'in', rec.practitioner_id.ths_department_id.id)
				], limit=1)
				rec.default_appointment_type_id = appointment_type.id if appointment_type else False
			elif rec.room_id and rec.room_id.ths_department_id:
				appointment_type = self.env['appointment.type'].search([
					('department_ids', 'in', rec.room_id.ths_department_id.id)
				], limit=1)
				rec.default_appointment_type_id = appointment_type.id if appointment_type else False

	# --------- Onchange Methods ---------
	@api.onchange('practitioner_id')
	def _onchange_practitioner_filter_rooms(self):
		"""Filter available rooms when practitioner changes"""
		if self.practitioner_id and self.practitioner_id.ths_department_id:
			# Clear room if it doesn't match the new practitioner's department
			if self.room_id and self.room_id.ths_department_id != self.practitioner_id.ths_department_id:
				self.room_id = False

			return {
				'domain': {
					'room_id': [
						('resource_category', '=', 'location'),
						('ths_department_id', '=', self.practitioner_id.ths_department_id.id)
					]
				}
			}
		else:
			return {'domain': {'room_id': [('resource_category', '=', 'location')]}}

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		"""Update pet owner and handle pet selection logic"""
		if self.partner_id:
			self.pet_owner_id = self.partner_id

			# Only do auto-selection if NO pets are selected
			if not self.patient_ids:
				# No pets selected - check if owner has exactly 1 pet and auto-select it
				owner_pets = self.env['res.partner'].search([
					('pet_owner_id', '=', self.partner_id.id),
					('is_pet', '=', True)
				])
				if len(owner_pets) == 1:
					self.patient_ids = [(6, 0, owner_pets.ids)]

			# If pets are already selected, clear them only if they don't belong to new owner
			elif any(p.pet_owner_id != self.partner_id for p in self.patient_ids):
				self.patient_ids = [Command.clear()]

		# If pets DO belong to this owner, do nothing (keep the selection)

		else:
			self.pet_owner_id = False
			self.patient_ids = [Command.clear()]

	@api.onchange('patient_ids')
	def _onchange_patient_ids_set_owner(self):
		"""Auto-set owner when pet is selected"""
		if self.patient_ids and not self.partner_id:
			# Set owner from first pet
			self.partner_id = self.patient_ids[0].pet_owner_id

	# --------- Constrains ---------
	@api.constrains('partner_id', 'patient_ids')
	def _check_owner_consistency(self):
		"""Validate that pets belong to the selected owner"""
		for rec in self:
			if rec.patient_ids and rec.partner_id:
				invalid_pets = rec.patient_ids.filtered(lambda p: p.pet_owner_id != rec.partner_id)
				if invalid_pets:
					raise ValidationError(
						_("Pets %s do not belong to owner %s.") %
						(", ".join(invalid_pets.mapped('name')), rec.partner_id.name)
					)

	# --------- Action Methods ---------
	def action_view_documents_model(self, folder_xmlid, title_prefix, tag_xmlid):
		""" Generic method to view documents for service models
			:param folder_xmlid: External ID of the folder
			:param title_prefix: Prefix for the window title
			:param tag_xmlid: External ID of the default tag """
		self.ensure_one()

		folder = self.env.ref(folder_xmlid, raise_if_not_found=False)
		tag = self.env.ref(tag_xmlid, raise_if_not_found=False)

		partner_id = self.patient_ids[0].id if self.patient_ids else (
			self.pet_owner_id[0].id if hasattr(self, 'pet_owner_id') and self.pet_owner_id else False
		)

		if not partner_id:
			return {}

		folder_main = self.env.ref('ths_vet_base.documents_pet_folder', raise_if_not_found=False)
		domain = [
			'|',
			'&', ('type', '=', 'folder'), ('folder_id', '=', folder_main.id if folder_main else False),
			'&', ('res_model', '=', 'res.partner'), ('res_id', '=', partner_id)
		]

		context = {
			'default_res_model': 'res.partner',
			'default_res_id': partner_id,
			'default_partner_id': partner_id,
			'default_folder_id': folder.id if folder else False,
			'default_tag_ids': [(6, 0, [tag.id])] if tag else False,
			'searchpanel_default_folder_id': folder.id if folder else False,
			'res_model': 'res.partner',
			'partner_id': partner_id,
		}

		return {
			'name': _('%s Photos/Documents') % title_prefix,
			'type': 'ir.actions.act_window',
			'res_model': 'documents.document',
			'view_mode': 'kanban,list,form',
			'target': 'current',
			'domain': domain,
			'context': context
		}

	# --------- Computes for Documents ---------
	@api.depends('patient_ids')
	def _compute_documents_count_model(self):
		"""Compute number of attached documents for this service record"""
		for record in self:
			if record.patient_ids:
				domain = [
					('res_model', '=', 'res.partner'),
					('res_id', '=', record.patient_ids[0].id)
				]
				record.documents_count_model = self.env['documents.document'].search_count(domain)
			else:
				record.documents_count_model = 0

	# --------- Helper Methods ---------
	def _get_formatted_patient_ids_with_names(self):
		""" Helper method to format patient_ids as [[id, name], [id, name]] for frontend consumption
			Replaces raw IDs with proper [id, name] format """
		self.ensure_one()
		if not self.patient_ids:
			return []

		formatted_patients = []
		for patient in self.patient_ids:
			formatted_patients.append([patient.id, patient.name])

		return formatted_patients

	def _get_formatted_practitioner_with_room(self):
		"""Helper method to format practitioner with room info for frontend"""
		self.ensure_one()
		if not self.practitioner_id:
			return False

		result = {
			'id': self.practitioner_id.id,
			'name': self.practitioner_id.name,
			'room_id': self.room_id.id if self.room_id else False,
			'room_name': self.room_id.name if self.room_id else '',
			'department': self.practitioner_id.ths_department_id.name if self.practitioner_id.ths_department_id else '',
		}
		return result


# --------- TODO Comments ---------
# TODO: Consider caching formatted data for performance
# TODO: Optimize domain caching for performance in large datasets
# --------- End of Encounter Mixin ---------


class VetEncounterHeader(models.Model):
	_name = 'vet.encounter.header'
	_description = 'Vet Encounter Header'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'encounter_date desc, id desc'

	# Inherit core fields from encounter_mixin (partner_id, patient_ids, practitioner_id, room_id)

	# -------- Header Main Fields --------
	name = fields.Char(string='Encounter ID', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
	encounter_line_ids = fields.One2many('vet.encounter.line', 'encounter_id', string='Encounter Lines',
										 context={'default_partner_id': 'partner_id', 'default_practitioner_id': 'practitioner_id', 'default_room_id': 'room_id',
												  'default_pet_owner_id': 'pet_owner_id'})
	encounter_date = fields.Date(string='Encounter Date', required=True, default=fields.Date.context_today, index=True,
								 help="Date for this encounter - one encounter per partner per date")
	state = fields.Selection([('in_progress', 'In Progress'), ('done', 'Done')], string='Status', default='in_progress', index=True, tracking=True, copy=False)
	notes = fields.Text(string="Internal Notes")
	encounter_priority = fields.Selection([('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('urgent', 'Urgent')], string='Priority', default='normal',
										  help="Encounter priority level")
	estimated_duration = fields.Float(string='Estimated Duration (hours)', help="Estimated total duration for all services")
	actual_duration = fields.Float(string='Actual Duration (hours)', help="Actual time spent on encounter")
	auto_state = fields.Selection([('in_progress', 'In Progress'), ('done', 'Done')], string='Auto State', compute='_compute_auto_state_from_payments', store=False,
								  help="Automatically computed state based on payment status")
	documents_count = fields.Integer(string="Photos/Documents", compute='_compute_documents_count')

	# -------- Links to Service Models --------
	appointment_ids = fields.One2many('calendar.event', 'encounter_id', string='Appointments', help="Daily encounter container for all services",
									  context={'default_partner_id': 'partner_id', 'default_appointment_type_id': 'default_appointment_type_id', 'default_room_id': 'room_id',
											   'default_pet_owner_id': 'partner_id', 'default_practitioner_id': 'practitioner_id'})
	boarding_stay_ids = fields.One2many('vet.boarding.stay', 'encounter_id', string='Boarding Stays', help="Boarding stays for this encounter",
										context={'default_partner_id': 'partner_id', 'default_pet_owner_id': 'partner_id'})
	park_checkin_ids = fields.One2many('vet.park.checkin', 'encounter_id', string='Park Check-ins', help="Park visits for this encounter",
									   context={'default_partner_id': 'partner_id', 'default_pet_owner_id': 'partner_id'})
	vaccination_ids = fields.One2many('vet.vaccination', 'encounter_id', string='Vaccinations', help="Vaccinations for this encounter",
									  context={'default_partner_id': 'partner_id', 'default_pet_owner_id': 'partner_id', 'default_practitioner_id': 'practitioner_id'})
	pet_membership_ids = fields.One2many('vet.pet.membership', 'encounter_id', string='Pet Memberships',
										 context={'default_partner_id': 'partner_id', 'default_pet_owner_id': 'partner_id'})

	# -------- Pet Supplementary Info --------
	total_pets_count = fields.Integer(string='Total Pets', compute='_compute_pets_summary', store=False, readonly=True, help="Total number of pets in encounter")
	pets_summary = fields.Char(string='Pets Summary', compute='_compute_pets_summary', store=False, readonly=True, help="Summary of all pets in this encounter")
	all_pets_species = fields.Char(string='All Species', compute='_compute_pets_summary', store=False, readonly=True, help="All species in this encounter")
	pet_badge_data = fields.Json(string="Pet Badge Data", compute="_compute_pet_badge_data", store=True)

	# -------- Payment Tracking --------
	pending_amount = fields.Monetary(string='Pending Amount', compute='_compute_payment_status', currency_field='company_currency', store=True,
									 help="Unpaid Amount on lines")
	paid_amount = fields.Monetary(string='Paid Amount', compute='_compute_payment_status', currency_field='company_currency', store=True,
								  help="Total amount paid on lines")
	pending_payments = fields.Boolean(string='Pending Payments', compute='_compute_payment_status', store=True, help="Pending Amounts")
	total_amount = fields.Monetary(string='Total Amount', compute='_compute_total', currency_field='company_currency', required=False, readonly=True)
	returned_amount = fields.Monetary(string='Returned Amount', currency_field='company_currency', required=False, readonly=True)
	sale_order_ids = fields.One2many('sale.order', 'encounter_id', string='Sale Orders', readonly=True, copy=False,
									 context={'default_partner_id': 'partner_id', 'default_pet_owner_id': 'pet_owner_id', 'default_practitioner_id': 'practitioner_id',
											  'default_room_id': 'room_id', })
	direct_invoice_ids = fields.One2many('account.move', 'encounter_id', string='Invoices', copy=False, domain="[('move_type', '=', 'out_invoice')]")
	credit_note_ids = fields.One2many('account.move', 'encounter_id', string='Credit Notes', domain="[('move_type', '=', 'out_refund')]", copy=False)
	credit_note_count = fields.Integer(compute='_compute_payment_document_counts', store=False)
	invoice_count = fields.Integer(compute='_compute_payment_document_counts', store=False)
	sale_order_count = fields.Integer(compute='_compute_payment_document_counts', store=False)
	kanban_payment_method_id = fields.Many2one('account.journal', string='Payment Method', domain="[('end_user_payment_method', '=', True), ('type', 'in', ['bank', 'cash'])]",
											   help="Payment method for POS UI processing")
	partner_available_credit = fields.Monetary(string='Partner Available Credit', related='partner_id.available_credit', currency_field='company_currency')
	partner_credit_count = fields.Integer(string='Partner Credit Payments', related='partner_id.available_credit_count')
	payment_ids = fields.One2many('account.payment', 'partner_id', related='partner_id.payment_ids', string='Partner Payments')

	# -------- EMR Fields (Base Text Fields) --------
	chief_complaint = fields.Text(string="Chief Complaint")
	history_illness = fields.Text(string="History of Present Illness")
	vitals_log_ids = fields.One2many('vet.vitals.log', 'encounter_id', string='Vitals Logs',
									 context={'default_patient_id': 'patient_ids[0].id if len(patient_ids) == 1 else False'})
	treatment_plan_ids = fields.One2many('vet.treatment.plan', 'encounter_id', string='Treatment Plan', copy=False)
	treatment_plan_count = fields.Integer(compute='_compute_payment_document_counts', store=False)

	# -------- SOAP Fields --------
	soap_subjective = fields.Text(string="Subjective", help="Patient's reported symptoms and history.")
	soap_objective = fields.Text(string="Objective", help="Practitioner's observations, exam findings, vitals.")
	soap_assessment = fields.Text(string="Assessment", help="Diagnosis or differential diagnosis.")
	soap_plan = fields.Text(string="Plan", help="Treatment plan, tests ordered, prescriptions, follow-up.")

	# -------- Other Clinical Details (as Text) --------
	diagnosis_text = fields.Text(string="Diagnoses Summary", help="Summary of diagnoses made during encounter.")
	procedures_text = fields.Text(string="Procedures Summary", help="Summary of procedures performed.")
	prescriptions_text = fields.Text(string="Prescriptions Summary", help="Summary of medications prescribed.")
	lab_orders_text = fields.Text(string="Lab Orders Summary", help="Summary of laboratory tests ordered.")
	radiology_orders_text = fields.Text(string="Radiology Orders Summary", help="Summary of radiology exams ordered.")

	# -------- Dashboard Fields --------
	daily_encounters = fields.Integer(compute='_compute_daily_metrics', string='Daily Encounters')
	daily_revenue = fields.Monetary(compute='_compute_daily_metrics', currency_field='company_currency', string='Daily Revenue')
	daily_patients = fields.Integer(compute='_compute_daily_metrics', string='Daily Patients')
	practitioner_revenue = fields.Monetary(string='Practitioner Revenue', currency_field='company_currency', compute='_compute_practitioner_metrics')
	practitioner_patients = fields.Integer(string='Patients Handled', compute='_compute_practitioner_metrics')

	# -------- Computes & Depends Methods --------
	@api.depends('patient_ids', 'patient_ids.name', 'patient_ids.species_id', 'patient_ids.species_id.name')
	def _compute_pets_summary(self):
		"""Compute pets summary and species"""
		for encounter in self:
			pets = encounter.patient_ids
			encounter.total_pets_count = len(pets)
			if not pets:
				encounter.pets_summary = "No pets"
				encounter.all_pets_species = ""
			elif len(pets) == 1:
				encounter.pets_summary = pets[0].name or ''
				encounter.all_pets_species = pets[0].species_id.name if pets[0].species_id else ''  # Simplified hasattr check
			else:
				names = pets[:3].mapped('name')
				encounter.pets_summary = f"{', '.join(names)} and {len(pets) - 3} more" if len(pets) > 3 else ', '.join(
					names)
				species = [s.name for s in pets.mapped('species_id') if s]
				encounter.all_pets_species = ', '.join(set(species)) if species else ''

	@api.depends('patient_ids')
	def _compute_pet_badge_data(self):
		"""Compute badge data for encounter pets"""
		for rec in self:
			badge_data = []
			for pet in rec.patient_ids:
				if pet:
					badge_data.append({
						'name': pet.name or 'Unknown Pet',
						'species': pet.species_id.name if pet.species_id else 'Unknown Species',
						'color': pet.species_id.color if pet.species_id and pet.species_id.color else 0,
						'pet_id': pet.id,
					})
				rec.pet_badge_data = badge_data

	@api.depends('partner_id')
	def _compute_documents_count(self):
		"""Compute number of documents for all pets under this encounter's partner"""
		for encounter in self:
			if encounter.partner_id:
				pet_ids = self.env['res.partner'].search([
					('pet_owner_id', '=', encounter.partner_id.id),
					('is_pet', '=', True)
				]).ids

				if pet_ids:
					domain = [
						('res_model', '=', 'res.partner'),
						('res_id', 'in', pet_ids)
					]
					encounter.documents_count = self.env['documents.document'].search_count(domain)
				else:
					encounter.documents_count = 0
			else:
				encounter.documents_count = 0

	@api.depends('encounter_line_ids.payment_status', 'encounter_line_ids.sub_total', 'encounter_line_ids.paid_amount', 'encounter_line_ids.remaining_qty',
				 'encounter_line_ids.unit_price', 'encounter_line_ids.discount')
	def _compute_payment_status(self):
		for encounter in self:
			lines = encounter.encounter_line_ids
			if not lines:
				encounter.update({
					'pending_amount': 0.0,
					'paid_amount': 0.0,
					'total_amount': 0.0,
					'pending_payments': False
				})
				continue

			# Calculate totals using sub_total (which includes discounts)
			total_amount = sum(lines.mapped('sub_total'))

			# Sum ALL lines' paid amounts
			paid_amount = sum(lines.mapped('paid_amount'))

			# Calculate pending based on remaining quantities WITH discount applied
			pending_amount = 0.0
			for line in lines:
				if line.remaining_qty > 0:
					# Apply discount to remaining amount
					line_subtotal_per_qty = line.sub_total / line.qty if line.qty > 0 else line.unit_price
					pending_amount += line.remaining_qty * line_subtotal_per_qty

			encounter.update({
				'total_amount': total_amount,
				'paid_amount': paid_amount,
				'pending_amount': pending_amount,
				'pending_payments': abs(pending_amount) > 0.01
			})

	@api.depends('encounter_line_ids.payment_status', 'encounter_line_ids.sub_total', 'encounter_line_ids.paid_amount')
	def _compute_auto_state_from_payments(self):
		"""Auto-change encounter state to 'done' when all lines are paid"""
		for encounter in self:
			lines_with_amount = encounter.encounter_line_ids.filtered(lambda l: l.sub_total > 0)

			if lines_with_amount:
				all_paid = all(line.payment_status == 'paid' for line in lines_with_amount)

				# Auto-change to done if all lines are paid and still in progress
				if all_paid and encounter.state == 'in_progress':
					encounter.state = 'done'
				# Maybe revert to in_progress if some become unpaid (edge case)
				elif not all_paid and encounter.state == 'done':
					# Only revert if there are pending payments
					has_pending = any(line.payment_status in ['pending', 'partial', 'posted'] for line in lines_with_amount)
					if has_pending:
						encounter.state = 'in_progress'

	@api.depends('encounter_line_ids.sub_total')
	def _compute_total(self):
		for encounter in self:
			encounter.total_amount = sum(encounter.encounter_line_ids.mapped('sub_total'))

	@api.depends('direct_invoice_ids.move_type', 'credit_note_ids.move_type', 'encounter_line_ids.invoice_ids.move_type', 'encounter_line_ids.sale_order_ids', 'treatment_plan_ids')
	def _compute_payment_document_counts(self):
		for header in self:
			# INVOICES ONLY (out_invoice) - use sets to avoid duplicates
			invoice_ids = set()

			# From direct invoices (should already be filtered by domain)
			direct_invoices = header.direct_invoice_ids.filtered(lambda i: i.move_type == 'out_invoice')
			invoice_ids.update(direct_invoices.ids)

			# From encounter line invoices (filter for out_invoice only)
			line_invoices = header.encounter_line_ids.mapped('invoice_ids').filtered(lambda i: i.move_type == 'out_invoice')
			invoice_ids.update(line_invoices.ids)

			header.invoice_count = len(invoice_ids)

			# CREDIT NOTES ONLY (out_refund)
			credit_note_ids = set()

			# From direct credit notes (should already be filtered by domain)
			direct_credits = header.credit_note_ids.filtered(lambda i: i.move_type == 'out_refund')
			credit_note_ids.update(direct_credits.ids)

			# From encounter line credit notes
			line_credits = header.encounter_line_ids.mapped('invoice_ids').filtered(lambda i: i.move_type == 'out_refund')
			credit_note_ids.update(line_credits.ids)

			header.credit_note_count = len(credit_note_ids)

			# SALE ORDERS
			so_ids = set(header.encounter_line_ids.mapped('sale_order_ids').ids)
			header.sale_order_count = len(so_ids)

			# TREATMENT PLANS
			header.treatment_plan_count = len(header.treatment_plan_ids)

	@api.model
	def _find_or_create_daily_encounter(self, partner_id, patient_ids=None, encounter_date=None, practitioner_id=None, room_id=None):
		"""Find existing encounter for partner+date or create new one"""
		# Normalize encounter_date to ensure consistent date handling
		if encounter_date:
			if isinstance(encounter_date, str):
				encounter_date = fields.Date.from_string(encounter_date)
			elif hasattr(encounter_date, 'date'):  # datetime object
				encounter_date = encounter_date.date()
		# if already date object, keep as is
		else:
			encounter_date = fields.Date.today()

		domain = [
			('partner_id', '=', partner_id),
			('encounter_date', '=', encounter_date),
		]
		encounter = self.search(domain, limit=1)

		if not encounter:
			vals = {
				'partner_id': partner_id,
				'pet_owner_id': partner_id,
				'encounter_date': encounter_date,
				'patient_ids': [Command.set(patient_ids or [])],
				'practitioner_id': getattr(practitioner_id, 'id', practitioner_id) if practitioner_id else False,
				'room_id': getattr(room_id, 'id', room_id) if room_id else False,
			}
			with self.env.cr.savepoint():
				encounter = self.search(domain, limit=1) or self.create(vals)
		else:
			if patient_ids:
				current_encounter_patient_ids = encounter.patient_ids.ids
				all_unique_patient_ids = list(set(current_encounter_patient_ids + patient_ids))
				if set(all_unique_patient_ids) != set(current_encounter_patient_ids):
					encounter.write({'patient_ids': [Command.set(all_unique_patient_ids)]})
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

	@api.model_create_multi
	def create(self, vals_list):
		""" Assign sequence on creation. """
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('medical.encounter') or _('New')  # Updated sequence code to match model

			# Ensure encounter_date is set
			if not vals.get('encounter_date'):
				vals['encounter_date'] = fields.Date.context_today(self)

		return super(VetEncounterHeader, self).create(vals_list)

	_sql_constraints = [('unique_partner_date', 'unique(partner_id, encounter_date)', 'Only one encounter per partner per date is allowed!'), ]

	def write(self, vals):
		"""Allow manual state changes but sync with payment status"""
		result = super().write(vals)

		if 'state' not in vals:
			# Only auto-update if state wasn't manually changed
			self._compute_auto_state_from_payments()

		return result

	def unlink(self):
		"""Prevent deletion of encounters with paid lines"""
		paid_encounters = self.filtered(lambda e: e.encounter_line_ids.filtered(lambda l: l.payment_status == 'paid'))
		if paid_encounters:
			raise UserError(_("Cannot delete encounters with paid lines. Cancel them instead."))
		return super().unlink()

	@api.model
	def get_products_by_category(self):
		"""Get products grouped by sub_type for POS UI"""
		products = self.env['product.product'].search([
			('sale_ok', '=', True), ('active', '=', True)
		])
		result = {}
		all_products = []

		for product in products:
			category = product.product_sub_type_id.name or 'Other'
			if category not in result:
				result[category] = []

			price = product.lst_price or 0.0

			product_data = {
				'id': product.id,
				'name': product.name,
				'default_code': product.default_code or '',
				'price': price,
				'lst_price': price,
				'barcode': product.barcode or '',
				'image_128': product.image_128,
			}

			result[category].append(product_data)
			all_products.append(product_data)

		# Add "All" category at the beginning
		result = {'All': all_products, **result}
		return result

	def process_payment_kanban_ui(self, payment_method_id, selected_line_ids=None, payment_amount=None, credit_used=0):
		"""Process payment through POS UI with proper validation at each step"""
		self.ensure_one()

		try:
			self = self.with_context(processing_payment=True)

			if not selected_line_ids:
				selected_line_ids = self.encounter_line_ids.filtered(lambda l: l.payment_status in ['pending', 'partial'] and l.remaining_qty > 0).ids

			if not selected_line_ids:
				raise UserError("No lines available for payment processing.")

			lines_to_process = self.encounter_line_ids.filtered(lambda l: l.id in selected_line_ids)
			lines_to_process.write({'source_model': 'manual_pos'})

			if payment_amount is None:
				payment_amount = sum(line.remaining_qty * line.unit_price for line in lines_to_process)

			has_recurring_products = any(line.product_id.recurring_invoice for line in lines_to_process)

			# STEP 1: Create/Update Sale Order
			try:
				# Look for existing sale orders in draft or sale state
				existing_so = self.env['sale.order'].search([
					('encounter_id', '=', self.id),
					('state', 'in', ('draft', 'sent', 'sale'))  # Include 'sale' state
				], limit=1)

				if existing_so:
					sale_order = existing_so
					# If SO is in 'sale' state but not invoiced, we'll use it
					if sale_order.state == 'sale' and sale_order.invoice_status == 'to invoice':
						# Perfect - we'll create invoice from this SO
						pass
					elif has_recurring_products and not sale_order.plan_id:
						subscription_plan = self._get_or_create_subscription_plan(lines_to_process)
						if not subscription_plan:
							raise UserError("Could not determine subscription plan for recurring products.")
						sale_order.write({
							'plan_id': subscription_plan.id,
							'is_subscription': True,
							'subscription_state': '1_draft',
							'start_date': fields.Date.today(),
						})
				else:
					# Create new SO
					so_vals = {
						'partner_id': self.partner_id.id,
						'partner_type_id': self.partner_id.partner_type_id.id,
						'encounter_id': self.id,
						'state': 'draft',
						'patient_ids': self.patient_ids.ids if self.patient_ids else False,
						'practitioner_id': self.practitioner_id.id if self.practitioner_id else False,
						'room_id': self.room_id.id if self.room_id else False,
					}

					if has_recurring_products:
						subscription_plan = self._get_or_create_subscription_plan(lines_to_process)
						if not subscription_plan:
							raise UserError("Could not determine subscription plan for recurring products.")
						so_vals.update({
							'plan_id': subscription_plan.id,
							'is_subscription': True,
							'subscription_state': '1_draft',
							'start_date': fields.Date.today(),
						})

					sale_order = self.env['sale.order'].create(so_vals)
			except Exception as e:
				raise UserError(f"Failed to create/update Sale Order: {str(e)}")

			# STEP 2: Create Sale Order Lines (only if needed)
			try:
				for encounter_line in lines_to_process:
					# CHECK: Look for existing SO line for this encounter line
					existing_sol = self.env['sale.order.line'].search([
						('encounter_line_id', '=', encounter_line.id),
						('order_id', '=', sale_order.id)
					], limit=1)

					if not existing_sol:
						# CHECK: Also ensure encounter line isn't already fully processed
						if encounter_line.remaining_qty > 0:
							sol_vals = {
								'order_id': sale_order.id,
								'product_id': encounter_line.product_id.id,
								'product_uom_qty': encounter_line.remaining_qty,
								'product_uom': encounter_line.product_uom.id,
								'price_unit': encounter_line.unit_price,
								'discount': encounter_line.discount * 100 if encounter_line.discount else 0.0,
								'encounter_line_id': encounter_line.id,
								'order_partner_id': self.partner_id.id,
								'patient_ids': encounter_line.patient_ids.ids if encounter_line.patient_ids else False,
								'practitioner_id': encounter_line.practitioner_id.id if encounter_line.practitioner_id else False,
								'room_id': encounter_line.room_id.id if encounter_line.room_id else False,
							}
							self.env['sale.order.line'].create(sol_vals)
			except Exception as e:
				raise UserError(f"Failed to create Sale Order Lines: {str(e)}")

			# STEP 3: Confirm Sale Order (if not already confirmed)
			try:
				if sale_order.state in ('draft', 'sent'):
					sale_order.action_confirm()

				# VALIDATE: SO should now be in 'sale' state
				if sale_order.state != 'sale':
					raise UserError(f"Sale Order confirmation failed. Current state: {sale_order.state}")

				# Update encounter lines to 'posted' after SO confirmation
				for encounter_line in lines_to_process:
					encounter_line.write({
						'payment_status': 'posted',
						'source_model': 'manual_pos',
						'sale_order_id': sale_order.id,
						'source_payment': f"SO-{sale_order.name}",
					})

			except Exception as e:
				raise UserError(f"Failed to confirm Sale Order: {str(e)}")

			# STEP 4: Create Invoice
			try:
				existing_invoice = sale_order.invoice_ids.filtered(lambda inv: inv.state == 'draft')

				if existing_invoice:
					invoice = existing_invoice[0]
				else:
					if sale_order.is_subscription:
						invoiceable_lines = sale_order._get_invoiceable_lines()
						if not invoiceable_lines:
							raise UserError("No invoiceable lines found for subscription.")
						invoices = sale_order._create_invoices()
					else:
						invoices = sale_order._create_invoices()

					if not invoices:
						raise UserError("Failed to create invoice.")
					invoice = invoices[0]

				# Update invoice header
				invoice_vals = {
					'encounter_id': self.id,
					'partner_type_id': self.partner_id.partner_type_id.id,
					'partner_id': self.partner_id.id,
				}
				if self.patient_ids:
					invoice_vals['patient_ids'] = self.patient_ids.ids
				if self.practitioner_id:
					invoice_vals['practitioner_id'] = self.practitioner_id.id
				if self.room_id:
					invoice_vals['room_id'] = self.room_id.id

				invoice.write(invoice_vals)

				# Update invoice lines with encounter line data
				for encounter_line in lines_to_process:
					sale_line = sale_order.order_line.filtered(lambda l: l.encounter_line_id.id == encounter_line.id)
					if sale_line:
						invoice_lines = sale_line.invoice_lines
						for inv_line in invoice_lines:
							inv_line_vals = {}
							if encounter_line.patient_ids:
								inv_line_vals['patient_ids'] = encounter_line.patient_ids.ids
							if encounter_line.practitioner_id:
								inv_line_vals['practitioner_id'] = encounter_line.practitioner_id.id
							if encounter_line.room_id:
								inv_line_vals['room_id'] = encounter_line.room_id.id
							if encounter_line.id:
								inv_line_vals['encounter_line_id'] = encounter_line.id

							if inv_line_vals:
								inv_line.write(inv_line_vals)

			except Exception as e:
				raise UserError(f"Failed to create/update invoice: {str(e)}")

			# STEP 5: Post Invoice
			try:
				if invoice.state == 'draft':
					invoice.action_post()

				# VALIDATE: Invoice should now be posted
				if invoice.state != 'posted':
					raise UserError(f"Invoice posting failed. Current state: {invoice.state}")

				# Update encounter lines after invoice posting
				for encounter_line in lines_to_process:
					encounter_line.write({
						'payment_status': 'posted',
						'source_model': 'manual_pos',
						'invoice_id': invoice.id,
						'source_payment': f"INV-{invoice.name}",
					})
					# Link to invoice
					encounter_line.invoice_ids = [(4, invoice.id)]

			except Exception as e:
				raise UserError(f"Failed to post invoice: {str(e)}")

			# STEP 6: Create and Process Payment
			try:

				payment_journal = self.env['account.journal'].browse(payment_method_id)
				if not payment_journal.exists():
					raise UserError("Invalid payment method selected.")

				# Initialize variables
				created_payments = self.env['account.payment']
				applied_credit_payments = []
				payments_to_process = []

				# Get invoice receivable lines
				invoice_receivable_lines = invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable' and not line.reconciled)

				if not invoice_receivable_lines:
					raise UserError("No receivable lines found on invoice.")

				# Handle credit application
				if credit_used > 0:
					credit_payments = self.env['account.payment'].search(
						[('partner_id', '=', self.partner_id.id), ('amount_remaining', '>', 0), ('state', '=', 'paid'), ('payment_type', '=', 'inbound')], order='date asc, id asc')

					if not credit_payments:
						raise UserError("No credit payments available for this customer.")

					remaining_credit_to_apply = credit_used

					for credit_payment in credit_payments:
						if remaining_credit_to_apply <= 0:
							break

						amount_to_use = min(credit_payment.amount_remaining, remaining_credit_to_apply)

						if amount_to_use > 0:
							payment_vals = {
								'date': fields.Date.today(),
								'amount': amount_to_use,
								'payment_type': 'inbound',
								'partner_type': 'customer',
								'partner_id': self.partner_id.id,
								'partner_type_id': self.partner_id.partner_type_id.id if self.partner_id.partner_type_id else False,
								'journal_id': credit_payment.journal_id.id,
								'payment_method_line_id': credit_payment.payment_method_line_id.id,
								'memo': f"Credit application from {credit_payment.name}",
								'destination_account_id': invoice_receivable_lines[0].account_id.id,
							}

							payments_to_process.append({
								'create_vals': payment_vals,
								'to_reconcile': invoice_receivable_lines,
								'credit_payment_id': credit_payment.id,
								'amount_applied': amount_to_use,
							})

							remaining_credit_to_apply -= amount_to_use

					if remaining_credit_to_apply > 0:
						raise UserError(f"Insufficient credit balance. Required: {credit_used}, Available: {credit_used - remaining_credit_to_apply}")

				# Create new payment for remaining amount
				if payment_amount > 0:
					payment_vals = {
						'date': fields.Date.today(),
						'amount': payment_amount,
						'payment_type': 'inbound',
						'partner_type': 'customer',
						'partner_id': self.partner_id.id,
						'partner_type_id': self.partner_id.partner_type_id.id if self.partner_id.partner_type_id else False,
						'journal_id': payment_journal.id,
						'memo': f"Payment for {invoice.name}",
						'destination_account_id': invoice_receivable_lines[0].account_id.id,
					}

					payment_method_line = payment_journal.inbound_payment_method_line_ids[:1]
					if payment_method_line:
						payment_vals['payment_method_line_id'] = payment_method_line.id

					payments_to_process.append({
						'create_vals': payment_vals,
						'to_reconcile': invoice_receivable_lines,
					})

				# Create payments using standard method
				if payments_to_process:
					created_payments = self.env['account.payment'].with_context(skip_invoice_sync=True).create([p['create_vals'] for p in payments_to_process])

					# Post payments
					created_payments.action_post()

					# Update credit payment remaining amounts
					for i, payment_data in enumerate(payments_to_process):
						if 'credit_payment_id' in payment_data:
							credit_payment = self.env['account.payment'].browse(payment_data['credit_payment_id'])
							credit_payment.write({'amount_remaining': credit_payment.amount_remaining - payment_data['amount_applied']})
							applied_credit_payments.append(created_payments[i])

			except Exception as e:
				raise UserError(f"Failed to create/process payment: {str(e)}")

			# STEP 7: Reconcile Payments with Invoice
			try:
				if created_payments and invoice.state == 'posted':
					# Use standard reconciliation domain from wizard
					domain = [('parent_state', '=', 'posted'), ('account_type', 'in', self.env['account.payment']._get_valid_payment_account_types()), ('reconciled', '=', False)]

					for i, payment_data in enumerate(payments_to_process):
						payment = created_payments[i]
						payment_lines = payment.move_id.line_ids.filtered_domain(domain)
						lines_to_reconcile = payment_data['to_reconcile']

						# Reconcile by account (following wizard pattern)
						for account in payment_lines.account_id:
							reconcile_lines = (payment_lines + lines_to_reconcile).filtered_domain(
								[('account_id', '=', account.id), ('reconciled', '=', False), ('parent_state', '=', 'posted')])
							if reconcile_lines:
								reconcile_lines.reconcile()

						# Add payment to matched payments
						lines_to_reconcile.move_id.matched_payment_ids += payment

					# Force invoice recomputation
					invoice._compute_amount()

					# Update encounter lines based on invoice payment state
					payment_source_text = []
					regular_payments = [p for i, p in enumerate(created_payments) if 'credit_payment_id' not in payments_to_process[i]]
					if regular_payments:
						payment_source_text.extend([f"PAY-{p.name}" for p in regular_payments])
					if applied_credit_payments:
						payment_source_text.extend([f"CREDIT-{p.name}" for p in applied_credit_payments])

					source_payment = ", ".join(payment_source_text) if payment_source_text else "PROCESSED"

					if invoice.payment_state == 'paid':
						for encounter_line in lines_to_process:
							encounter_line.write({'payment_status': 'paid', 'source_model': 'manual_pos', 'source_payment': source_payment})
					elif invoice.payment_state == 'partial':
						for encounter_line in lines_to_process:
							encounter_line.write({'payment_status': 'partial', 'source_model': 'manual_pos', 'source_payment': source_payment})

					# Force recomputation
					for encounter_line in lines_to_process:
						encounter_line._compute_payment_amounts()
						encounter_line._compute_remaining_qty()

			except Exception as e:
				raise UserError(f"Failed to reconcile payment: {str(e)}")

			# STEP 8: Handle Deliveries (only for non-subscription products)
			try:
				for picking in sale_order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel']):
					# Confirm the picking
					if picking.state == 'draft':
						picking.action_confirm()

					# Assign whatever is available
					if picking.state == 'confirmed':
						picking.action_assign()

					# Process each move - just set quantities and go
					for move in picking.move_ids:
						# Set quantity done = quantity ordered (regardless of stock)
						move.quantity = move.product_uom_qty

						# Handle lot/serial if needed (create dummy ones)
						if move.product_id.tracking == 'lot':
							# Create lot if needed
							lot = self.env['stock.lot'].create({
								'name': f"LOT-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}",
								'product_id': move.product_id.id,
								'company_id': move.company_id.id,
							})

							if not move.move_line_ids:
								self.env['stock.move.line'].create({
									'move_id': move.id,
									'product_id': move.product_id.id,
									'lot_id': lot.id,
									'quantity': move.product_uom_qty,
									'location_id': move.location_id.id,
									'location_dest_id': move.location_dest_id.id,
									'product_uom_id': move.product_uom.id,
								})
						elif move.product_id.tracking == 'serial':
							# Create serial numbers
							for i in range(int(move.product_uom_qty)):
								serial = self.env['stock.lot'].create({
									'name': f"SN-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{i + 1:03d}",
									'product_id': move.product_id.id,
									'company_id': move.company_id.id,
								})
								self.env['stock.move.line'].create({
									'move_id': move.id,
									'product_id': move.product_id.id,
									'lot_id': serial.id,
									'quantity': 1.0,
									'location_id': move.location_id.id,
									'location_dest_id': move.location_dest_id.id,
									'product_uom_id': move.product_uom.id,
								})
						else:
							# No tracking - create simple move line if needed
							if not move.move_line_ids:
								self.env['stock.move.line'].create({
									'move_id': move.id,
									'product_id': move.product_id.id,
									'quantity': move.product_uom_qty,
									'location_id': move.location_id.id,
									'location_dest_id': move.location_dest_id.id,
									'product_uom_id': move.product_uom.id,
								})
							else:
								# Set quantity on existing move lines
								for ml in move.move_line_ids:
									ml.quantity = move.product_uom_qty

					# Force validate the picking
					picking.with_context(skip_backorder=True).button_validate()

			except Exception as e:
				_logger.error(f"Delivery error: {str(e)}")

			# STEP 9: Update Subscription (if applicable)
			try:
				if sale_order.is_subscription and sale_order.subscription_state == '3_progress':
					sale_order._update_next_invoice_date()
			except Exception as e:
				# Log but don't fail the entire process for subscription updates
				_logger.warning(f"Failed to update subscription dates: {str(e)}")

			# FINAL VALIDATION: Ensure everything is properly paid
			invoice._compute_amount()
			if invoice.payment_state not in ('paid', 'partial', 'in_payment'):
				if not (payment_amount == 0 and credit_used > 0):
					raise UserError(f"Process completed but invoice payment state is unexpected: {invoice.payment_state}")

			return {
				'success': True,
				'sale_order_id': sale_order.id,
				'invoice_id': invoice.id,
				'payment_id': created_payments[0].id if created_payments else None,
				'message': f'Payment processed successfully. Invoice status: {invoice.payment_state}',
				'print_invoice': True,
				'clear_cart': True,
			}

		except Exception as e:
			return {'success': False, 'error': str(e), 'message': f'Payment processing failed: {str(e)}', 'print_invoice': False, 'clear_cart': False}

	def _get_or_create_subscription_plan(self, lines_to_process):
		"""Find or create subscription plan based on product's ths_membership_duration"""

		# Get duration from the first recurring product
		duration_months = None
		for line in lines_to_process:
			if (line.product_id.recurring_invoice and
					hasattr(line.product_id, 'ths_membership_duration') and
					line.product_id.ths_membership_duration):
				duration_months = line.product_id.ths_membership_duration
				break

		if not duration_months:
			return None

		# First, try to find existing plans that match the duration
		# Check for yearly plans first (more common for longer durations)
		if duration_months >= 12 and duration_months % 12 == 0:
			years = duration_months // 12
			yearly_plan = self.env['sale.subscription.plan'].search([
				('billing_period_value', '=', years),
				('billing_period_unit', '=', 'year'),
				('company_id', 'in', [self.env.company.id, False])
			], limit=1)
			if yearly_plan:
				return yearly_plan

		# Check for monthly plans
		monthly_plan = self.env['sale.subscription.plan'].search([
			('billing_period_value', '=', duration_months),
			('billing_period_unit', '=', 'month'),
			('company_id', 'in', [self.env.company.id, False])
		], limit=1)
		if monthly_plan:
			return monthly_plan

		# If no existing plan found, create one
		if duration_months >= 12 and duration_months % 12 == 0:
			# Create yearly plan for multiples of 12 months
			years = duration_months // 12
			plan_name = f"{years} Year{'s' if years > 1 else ''} Subscription Plan"
			return self.env['sale.subscription.plan'].create({
				'name': plan_name,
				'billing_period_value': years,
				'billing_period_unit': 'year',
				'company_id': self.env.company.id,
			})
		else:
			# Create monthly plan
			plan_name = f"{duration_months} Month{'s' if duration_months > 1 else ''} Subscription Plan"
			return self.env['sale.subscription.plan'].create({
				'name': plan_name,
				'billing_period_value': duration_months,
				'billing_period_unit': 'month',
				'company_id': self.env.company.id,
			})

	def add_product_to_encounter_kanban(self, product_id, qty, unit_price, patient_ids=None, discount=0.0, practitioner_id=None, room_id=None, line_id=None):
		""" Add or update product in encounter - return encounter_line_id """
		if line_id:
			# Update existing line
			line = self.env['vet.encounter.line'].browse(line_id)
			line.write({
				'qty': qty,
				'unit_price': unit_price,
				'discount': discount,
				'partner_id': self.partner_id.id,
				'patient_ids': [(6, 0, patient_ids)] if patient_ids else [(5, 0, 0)],
				'practitioner_id': practitioner_id,
				'room_id': room_id,
			})
			return {'encounter_line_id': line.id}
		else:
			# Create new line
			line_vals = {
				'encounter_id': self.id,
				'product_id': product_id,
				'qty': qty,
				'unit_price': unit_price,
				'discount': discount,
				'partner_id': self.partner_id.id,
				'patient_ids': [(6, 0, patient_ids)] if patient_ids else [(5, 0, 0)],
				'practitioner_id': practitioner_id,
				'room_id': room_id,
				'source_model': 'manual_pos',
			}

			line = self.env['vet.encounter.line'].create(line_vals)
			return {'encounter_line_id': line.id}

	@api.model
	def get_payment_methods_kanban(self):
		"""Get payment methods for kanban UI including credit"""
		journals = self.env['account.journal'].search([
			('end_user_payment_method', '=', True),
			('type', 'in', ['bank', 'cash'])
		])

		methods = [{
			'id': j.id,
			'name': j.name,
			'type': j.type,
			'code': j.code,
			'is_credit': False,
		} for j in journals]

		# Add credit as a special payment method
		methods.append({
			'id': 'credit',
			'name': 'Available Credit',
			'type': 'credit',
			'code': 'CREDIT',
			'is_credit': True,
		})

		return methods

	def action_process_payment(self):
		"""Open POS-style payment interface"""
		return {
			'type': 'ir.actions.client',
			'name': _('Payment Interface'),
			'tag': 'vet_pos_interface_action',
			'target': 'new',
			'context': {
				'encounter_id': self.id,
				'dialog_size': 'extra-large',
			}
		}

	def action_create_invoice_from_pending_lines(self):
		self.ensure_one()

		available_lines = self.encounter_line_ids.filtered(
			lambda l: l.payment_status in ['pending', 'partial'] and l.remaining_qty
		)

		if not available_lines:
			raise UserError(_("No lines available for invoicing."))

		all_patient_ids = available_lines.mapped('patient_ids').ids
		pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)

		# Prepare invoice values
		invoice_vals = {
			'partner_id': self.partner_id.id,
			'patient_ids': [(6, 0, all_patient_ids)],
			'partner_type_id': pet_owner_type.id if pet_owner_type else False,
			'move_type': 'out_invoice',
			'encounter_id': self.id,
			'practitioner_id': self.practitioner_id.id,
			'room_id': self.room_id.id,
			'invoice_origin': self.name,
			'invoice_date': fields.Date.today(),
			'invoice_line_ids': []
		}

		# Create invoice lines
		for line in available_lines:
			remaining = line.remaining_qty * line.unit_price
			if line.payment_status == 'pending':
				# Full line - use original quantity and discount
				quantity = line.qty
				discount = line.discount
			else:
				# Partial line - calculate quantity for remaining amount, no discount
				quantity = remaining / line.unit_price if line.unit_price > 0 else 1.0
				discount = 0.0

			invoice_line_vals = {
				'product_id': line.product_id.id,
				'name': line.product_description or line.product_id.name,
				'quantity': quantity,
				'price_unit': line.unit_price,
				'encounter_line_id': line.id,
				'partner_id': line.partner_id.id,
				'patient_ids': [(6, 0, line.patient_ids.ids)],
				'practitioner_id': line.practitioner_id.id,
				'room_id': line.room_id.id,
				'invoice_origin': self.name,
				'discount': discount * 100 if discount else 0.0,
			}
			invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))

		# Create invoice
		invoice = self.env['account.move'].create(invoice_vals)

		# Link invoice to encounter lines
		for line in available_lines:
			line.invoice_ids = [(4, invoice.id)]
			line.invoice_id = invoice.id
			line._update_payment_history('invoice', invoice.id, invoice.name, 'posted')

		return {
			'type': 'ir.actions.act_window',
			'res_model': 'account.move',
			'res_id': invoice.id,
			'view_mode': 'form',
			'target': 'current'
		}

	def action_create_sale_order_from_pending_lines(self):
		self.ensure_one()

		available_lines = self.encounter_line_ids.filtered(
			lambda l: l.payment_status in ['pending', 'partial'] and l.remaining_qty > 0
		)

		if not available_lines:
			raise UserError(_("No lines available for sale order."))

		all_patient_ids = available_lines.mapped('patient_ids').ids

		# Create sale order
		so_vals = {
			'partner_id': self.partner_id.id,
			'partner_type_id': self.partner_id.partner_type_id.id,
			'patient_ids': [(6, 0, all_patient_ids)],
			'practitioner_id': self.practitioner_id.id,
			'room_id': self.room_id.id,
			'encounter_id': self.id,
			'origin': self.name,
			'order_line': []
		}

		for line in available_lines:
			remaining = line.remaining_qty * line.unit_price
			if line.payment_status == 'pending':
				# Full line - use original quantity and discount
				quantity = line.qty
				discount = line.discount
			else:
				# Partial line - calculate quantity for remaining amount, no discount
				quantity = remaining / line.unit_price if line.unit_price > 0 else 1.0
				discount = 0.0

			so_line_vals = {
				'product_id': line.product_id.id,
				'name': line.product_description or line.product_id.name,
				'product_uom_qty': quantity,
				'price_unit': line.unit_price,
				'patient_ids': line.patient_ids,
				'practitioner_id': line.practitioner_id.id,
				'room_id': line.room_id.id,
				'encounter_line_id': line.id,
				'discount': discount * 100,
			}
			so_vals['order_line'].append((0, 0, so_line_vals))

		sale_order = self.env['sale.order'].create(so_vals)

		# Link to encounter lines
		for line in available_lines:
			line.sale_order_ids = [(4, sale_order.id)]
			line.sale_order_id = sale_order.id  # Legacy field
			line._update_payment_history('sale_order', sale_order.id, sale_order.name, 'posted')

		return {
			'type': 'ir.actions.act_window',
			'res_model': 'sale.order',
			'res_id': sale_order.id,
			'view_mode': 'form',
			'target': 'current',
			'context': {'default_partner_id': self.partner_id.id,
						'default_partner_type_id': self.partner_id.partner_type_id.id if self.partner_id.partner_type_id else 'Pet Owner',
						'default_encounter_id': self.id, }
		}

	# Centralized default context for encounter lines
	@api.model
	def _get_default_context(self):
		"""Provide default context for encounter lines."""
		return {
			'default_encounter_id': self.id,
			'default_source_model': self._context.get('source_model', False),
		}

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

	def action_auto_close_empty_encounters(self):
		"""Close encounters that have no active content"""
		self.ensure_one()

		# Check encounter content
		billable_lines = self.encounter_line_ids.filtered(lambda l: l.sub_total > 0)
		active_boardings = self.boarding_stay_ids.filtered(lambda b: b.state not in ['draft', 'cancelled', 'checked_out'])
		pending_appointments = self.appointment_ids.filtered(lambda a: a.appointment_status in ['request', 'booked', 'attended'])
		active_checkins = self.park_checkin_ids.filtered(lambda p: p.state in ['checked_in', 'overdue'])

		if not billable_lines and not active_boardings and not pending_appointments and not active_checkins:
			self.state = 'done'

			# Return window reload action
			return {
				'type': 'ir.actions.act_window_close'
			}
		else:
			# Show info without navigation
			return {
				'type': 'ir.actions.client',
				'tag': 'display_notification',
				'params': {
					'message': f"Cannot close: encounter has active content.",
					'type': 'warning',
				}
			}

	@api.model
	def action_close_all_empty_encounters(self):
		"""Close all encounters that should be closed"""
		empty_encounters = self.search([
			('state', '=', 'in_progress'),
			('encounter_line_ids.sub_total', '=', 0),  # No billable lines
		])

		closed_count = 0
		for encounter in empty_encounters:
			# Double-check it's truly empty
			active_boardings = encounter.boarding_stay_ids.filtered(lambda b: b.state not in ['draft', 'cancelled', 'checked_out'])
			pending_appointments = encounter.appointment_ids.filtered(lambda a: a.appointment_status in ['request', 'booked', 'attended'])

			if not active_boardings and not pending_appointments:
				encounter.state = 'done'
				closed_count += 1

		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'message': f'Closed {closed_count} empty encounters.',
				'type': 'success',
			}
		}

	@api.model
	def _cron_vaccination_reminders(self):
		"""Cron to check for expiring vaccinations in encounters"""
		today = fields.Date.today()
		expiring_vaccs = self.env['vet.vaccination'].search([
			('encounter_id.state', '=', 'in_progress'),
			('expiry_date', '<', today + relativedelta(months=1)),
			('expiry_date', '>', today)
		])
		for vacc in expiring_vaccs:
			vacc.encounter_id.activity_schedule(
				'mail.mail_activity_data_todo',
				date_deadline=vacc.expiry_date - relativedelta(days=30),
				summary=_('Vaccination Expiry in Encounter'),
				note=_('Vaccination %s for %s expires soon.') % (vacc.vaccine_type_id.name, vacc.patient_ids.name)
			)

	@api.model
	def _compute_daily_metrics(self):
		"""Compute dashboard metrics for today"""
		today = fields.Date.today()
		encounters = self.search([('encounter_date', '=', today)])
		self.daily_encounters = len(encounters)
		self.daily_revenue = sum(encounters.mapped('total_amount'))
		self.daily_patients = len(encounters.mapped('patient_ids'))

	@api.depends('encounter_line_ids.practitioner_id', 'encounter_line_ids.sub_total', 'encounter_line_ids.patient_ids')
	def _compute_practitioner_metrics(self):
		for header in self:
			lines = header.encounter_line_ids.filtered(lambda l: l.practitioner_id == header.practitioner_id)
			header.practitioner_revenue = sum(lines.mapped('sub_total'))
			header.practitioner_patients = len(set(lines.mapped('patient_ids.id')))

	@api.model
	def _cron_close_inactive_encounters(self):
		"""Close encounters inactive for 1 month"""
		inactive_date = fields.Date.today() - relativedelta(months=1)
		inactive = self.search([
			('state', '=', 'in_progress'),
			('write_date', '<', inactive_date)
		])
		inactive.write({'state': 'done'})
		for enc in inactive:
			enc.message_post(body=_("Automatically closed due to inactivity."))

	def get_encounter_dashboard_data(self):
		"""Get dashboard data for encounter analytics"""
		today = fields.Date.today()
		domain_today = [('encounter_date', '=', today)]
		domain_week = [
			('encounter_date', '>=', today - timedelta(days=today.weekday())),
			('encounter_date', '<=', today + timedelta(days=6 - today.weekday()))
		]
		domain_month = [
			('encounter_date', '>=', today.replace(day=1)),
			('encounter_date', '<=', today + relativedelta(day=31))
		]

		encounters_today = self.env['vet.encounter.header'].search(domain_today)
		encounters_week = self.env['vet.encounter.header'].search(domain_week)
		encounters_month = self.env['vet.encounter.header'].search(domain_month)

		return {
			'today': {
				'encounters': len(encounters_today),
				'revenue': sum(encounters_today.mapped('total_amount')),
				'patients': len(encounters_today.mapped('patient_ids')),
				'pending_amount': sum(encounters_today.mapped('pending_amount')),
			},
			'week': {
				'encounters': len(encounters_week),
				'revenue': sum(encounters_week.mapped('total_amount')),
				'patients': len(encounters_week.mapped('patient_ids')),
			},
			'month': {
				'encounters': len(encounters_month),
				'revenue': sum(encounters_month.mapped('total_amount')),
				'patients': len(encounters_month.mapped('patient_ids')),
			}
		}

	@api.model
	def batch_close_encounters(self, encounter_ids):
		"""Batch close multiple encounters"""
		encounters = self.browse(encounter_ids)
		encounters = encounters.filtered(lambda e: e.state == 'in_progress')

		if not encounters:
			return {'warning': {'title': _('Warning'), 'message': _('No encounters to close.')}}

		encounters.write({'state': 'done'})

		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'message': _('%d encounters closed successfully.') % len(encounters),
				'type': 'success',
			}
		}

	@api.model
	def batch_generate_invoices(self, encounter_ids):
		"""Generate consolidated invoices for multiple encounters per partner"""
		encounters = self.browse(encounter_ids)
		encounters = encounters.filtered(lambda e: e.pending_amount > 0)

		if not encounters:
			return {'warning': {'title': _('Warning'), 'message': _('No encounters with pending amounts.')}}

		# Group encounters by partner
		partner_encounters = {}
		for encounter in encounters:
			partner_id = encounter.partner_id.id
			if partner_id not in partner_encounters:
				partner_encounters[partner_id] = self.env['vet.encounter.header']
			partner_encounters[partner_id] |= encounter

		invoices_created = []
		pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)

		for partner_id, partner_encounters_group in partner_encounters.items():
			# Get all pending lines from all encounters for this partner
			all_pending_lines = partner_encounters_group.mapped('encounter_line_ids').filtered(
				lambda l: l.payment_status in ['pending', 'partial'] and l.remaining_qty > 0
			)

			if not all_pending_lines:
				continue

			all_patient_ids = all_pending_lines.mapped('patient_ids').ids
			primary_practitioner = all_pending_lines.mapped('practitioner_id')[:1]
			primary_room = all_pending_lines.mapped('room_id')[:1]

			encounter_names = partner_encounters_group.mapped('name')
			invoice_origin = f"Consolidated: {', '.join(encounter_names)}"

			invoice_vals = {
				'partner_id': partner_id,
				'patient_ids': [(6, 0, all_patient_ids)],
				'partner_type_id': pet_owner_type.id if pet_owner_type else False,
				'practitioner_id': primary_practitioner.id if primary_practitioner else False,
				'room_id': primary_room.id if primary_room else False,
				'move_type': 'out_invoice',
				'invoice_origin': invoice_origin,
				'invoice_date': fields.Date.today(),
				'invoice_line_ids': []
			}

			# Create invoice lines grouped by encounter
			for encounter in partner_encounters_group:
				encounter_lines = encounter.encounter_line_ids.filtered(
					lambda l: l.payment_status in ['pending', 'partial'] and l.remaining_qty > 0
				)

				for line in encounter_lines:
					remaining = line.remaining_qty * line.unit_price
					if line.payment_status == 'pending':
						quantity = line.qty
						discount = line.discount
					else:
						quantity = remaining / line.unit_price if line.unit_price > 0 else 1.0
						discount = 0.0

					invoice_line_vals = {
						'product_id': line.product_id.id,
						'name': f"[{encounter.name}] {line.product_id.name}",
						'quantity': quantity,
						'price_unit': line.unit_price,
						'encounter_line_id': line.id,
						'discount': discount * 100,
						'partner_id': line.partner_id.id,
						'patient_ids': [(6, 0, line.patient_ids.ids)],
						'practitioner_id': line.practitioner_id.id,
						'room_id': line.room_id.id,
					}
					invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))

			if invoice_vals['invoice_line_ids']:
				invoice = self.env['account.move'].create(invoice_vals)
				invoices_created.append(invoice.id)

				# Link invoice to all encounter lines
				for line in all_pending_lines:
					line.invoice_ids = [(4, invoice.id)]
					line.invoice_id = invoice.id
					line._update_payment_history('invoice', invoice.id, invoice.name, 'posted')

		if invoices_created:
			return {
				'name': _('Consolidated Invoices Created'),
				'type': 'ir.actions.act_window',
				'res_model': 'account.move',
				'view_mode': 'list,form',
				'domain': [('id', 'in', invoices_created)],
			}
		else:
			return {'warning': {'title': _('Warning'), 'message': _('No invoices were created.')}}

	# ------- ACTIONS -------
	def action_view_partner_credit_payments(self):
		"""View partner's credit payments"""
		return self.partner_id.action_view_credit_payments()

	def action_view_pet_medical_histories(self):
		"""View medical histories for all pets"""
		self.ensure_one()
		if not self.patient_ids:
			return {}
		return {
			'name': _('Pet Medical Histories'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', self.patient_ids.ids)],
			'context': {'search_default_groupby_patients': 1, 'create': False}
		}

	def action_view_documents(self):
		"""View photos/documents"""
		self.ensure_one()

		folder_main = self.env.ref('ths_vet_base.documents_pet_folder', raise_if_not_found=False)
		domain = [
			'|',
			'&', ('type', '=', 'folder'), ('folder_id', '=', folder_main.id if folder_main else False),
			('partner_id.pet_owner_id.id', '=', self.partner_id.id)
		]
		context = {
			'default_res_model': 'res.partner',
			'default_res_id': self.partner_id.id,
			'default_partner_id': self.partner_id.id,
			'searchpanel_default_folder_id': folder_main.id if folder_main else False,
			'res_model': 'res.partner',
			'partner_id': self.partner_id.id,
			'searchpanel_folder_id': folder_main.id if folder_main else False,
			'folder_id': folder_main.id if folder_main else False,
		}

		return {
			'name': _('Photos/Documents'),
			'type': 'ir.actions.act_window',
			'res_model': 'documents.document',
			'res_id': self.env.ref('documents.document_action').id,
			'view_mode': 'kanban,list,form',
			'target': 'current',
			'domain': domain,
			'context': context
		}

	def action_view_boarding_stays(self):
		"""View boarding stays"""
		self.ensure_one()
		return {
			'name': _('Boarding Stays'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.boarding.stay',
			'view_mode': 'list,form',
			'domain': [('encounter_id', '=', self.id)],
			'context': {'create': False}
		}

	def action_view_vaccinations(self):
		"""View vaccinations"""
		self.ensure_one()
		return {
			'name': _('Vaccinations'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.vaccination',
			'view_mode': 'list,form',
			'domain': [('encounter_id', '=', self.id)],
			'context': {'create': False}
		}

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

	def action_view_invoices(self):
		"""View ONLY invoices (out_invoice) related to this encounter"""
		self.ensure_one()

		# Collect all invoice IDs (out_invoice only)
		invoice_ids = set()

		# From direct invoices
		direct_invoices = self.direct_invoice_ids.filtered(lambda i: i.move_type == 'out_invoice')
		invoice_ids.update(direct_invoices.ids)

		# From encounter lines
		line_invoices = self.encounter_line_ids.mapped('invoice_ids').filtered(lambda i: i.move_type == 'out_invoice')
		invoice_ids.update(line_invoices.ids)

		return {
			'type': 'ir.actions.act_window',
			'name': _('Related Invoices'),
			'res_model': 'account.move',
			'view_mode': 'list,form',
			'domain': [('id', 'in', list(invoice_ids)), ('move_type', '=', 'out_invoice')],
			'context': {
				'create': False,
				'default_partner_id': self.partner_id.id,
				'default_encounter_id': self.id,
			}
		}

	def action_view_credit_notes(self):
		"""View ONLY credit notes (out_refund) related to this encounter"""
		self.ensure_one()

		# Collect all credit note IDs (out_refund only)
		credit_note_ids = set()

		# From direct credit notes
		direct_credits = self.credit_note_ids.filtered(lambda i: i.move_type == 'out_refund')
		credit_note_ids.update(direct_credits.ids)

		# From encounter lines
		line_credits = self.encounter_line_ids.mapped('invoice_ids').filtered(lambda i: i.move_type == 'out_refund')
		credit_note_ids.update(line_credits.ids)

		return {
			'type': 'ir.actions.act_window',
			'name': _('Credit Notes'),
			'res_model': 'account.move',
			'view_mode': 'list,form',
			'domain': [('id', 'in', list(credit_note_ids)), ('move_type', '=', 'out_refund')],
			'context': {
				'create': False,
				'default_partner_id': self.partner_id.id,
				'default_move_type': 'out_refund',
				'default_encounter_id': self.id,
			}
		}

	def action_view_sale_orders(self):
		so_ids = self.encounter_line_ids.mapped('sale_order_ids').ids
		return {
			'type': 'ir.actions.act_window',
			'name': _('Related Sale Orders'),
			'res_model': 'sale.order',
			'view_mode': 'list,form',
			'domain': [('id', 'in', so_ids)],
			'context': {'create': False,
						'default_partner_id': self.partner_id.id,
						'default_partner_type_id': self.partner_id.partner_type_id.id,
						'default_encounter_id': self.id, }
		}

	def action_refresh_all_payment_status(self):
		"""Refresh payment status for all encounter lines"""
		self.encounter_line_ids.action_refresh_payment_status()
		return True

	def action_refresh_payment_status(self):
		"""Manual method to refresh payment status - for testing"""
		for encounter in self:
			# Force recomputation of all related fields in proper order
			encounter.encounter_line_ids._compute_remaining_qty()
			encounter.encounter_line_ids._compute_payment_amounts()
			encounter.encounter_line_ids._compute_payment_status()
			encounter._compute_payment_status()
			encounter._compute_auto_state_from_payments()
			encounter._compute_payment_document_counts()

		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'message': 'Payment status refreshed successfully!',
				'type': 'success',
			}
		}

	def add_service_to_encounter(self, service_model, service_id):
		"""Generic method to link any service to this encounter"""
		self.ensure_one()
		service = self.env[service_model].browse(service_id)
		if hasattr(service, 'encounter_id'):
			service.encounter_id = self.id
		return True

	def action_schedule_follow_up_for_pets(self):
		"""Schedule follow-up appointments for pets in this encounter"""
		self.ensure_one()
		if not self.patient_ids:
			raise UserError(_("No pets found in this encounter to schedule follow-up."))

		# Get default follow-up days based on service types
		follow_up_days = 7  # Default 1 week follow-up

		# Check if encounter has specific services that need different follow-up periods
		if self.vaccination_ids:
			follow_up_days = 14  # 2 weeks for vaccination follow-up
		elif self.boarding_stay_ids:
			follow_up_days = 3  # 3 days for boarding follow-up

		follow_up_date = fields.Date.today() + timedelta(days=follow_up_days)

		# Create follow-up appointment for each pet
		appointments_created = []
		for pet in self.patient_ids:
			# Use datetime.combine instead of fields.Datetime.combine
			start_datetime = datetime.combine(follow_up_date, time(9, 0))  # 9 AM default
			stop_datetime = datetime.combine(follow_up_date, time(9, 30))  # 30 mins default

			appointment_vals = {
				'name': _('Follow-up for %s') % pet.name,
				'appointment_type_id': self.default_appointment_type_id.id if self.default_appointment_type_id else False,
				'partner_id': self.partner_id.id,
				'pet_owner_id': self.partner_id.id,
				'patient_ids': [(6, 0, [pet.id])],
				'practitioner_id': self.practitioner_id.id if self.practitioner_id else False,
				'room_id': self.room_id.id if self.room_id else False,
				'start': start_datetime,
				'stop': stop_datetime,
				'appointment_status': 'request',
				# 'reason_for_visit': _('Follow-up visit for encounter %s') % self.name,
				'encounter_id': False,  # Will be set when new encounter is created
			}
			appointment = self.env['calendar.event'].create(appointment_vals)
			appointments_created.append(appointment)

		# Show created appointments
		if len(appointments_created) == 1:
			return {
				'name': _('Follow-up Appointment Created'),
				'type': 'ir.actions.act_window',
				'res_model': 'calendar.event',
				'view_mode': 'form',
				'res_id': appointments_created[0].id,
				'target': 'new',
			}
		else:
			return {
				'name': _('Follow-up Appointments Created'),
				'type': 'ir.actions.act_window',
				'res_model': 'calendar.event',
				'view_mode': 'list,form',
				'domain': [('id', 'in', [a.id for a in appointments_created])],
			}

	def action_create_treatment_plan(self):
		"""Create treatment plan for pets based on encounter findings"""
		self.ensure_one()
		if not self.patient_ids:
			raise UserError(_("No pets found in this encounter to create treatment plan."))

		# Prepare treatment plan context with encounter data
		context = {
			'default_encounter_id': self.id,
			'default_partner_id': self.partner_id.id,
			'default_patient_ids': [(6, 0, self.patient_ids.ids)],
			'default_practitioner_id': self.practitioner_id.id if self.practitioner_id else False,
			'default_treatment_date': fields.Date.today(),
			'default_notes': self._prepare_treatment_plan_notes(),
		}

		return {
			'name': _('Create Treatment Plan'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.treatment.plan',
			'view_mode': 'form',
			'target': 'new',
			'context': context,
		}

	def _prepare_treatment_plan_notes(self):
		"""Prepare initial notes for treatment plan based on encounter data"""
		notes = ["=== ENCOUNTER SUMMARY ===", f"Encounter ID: {self.name}", f"Date: {self.encounter_date}", f"Pet Owner: {self.partner_id.name}"]

		# === BASIC ENCOUNTER INFORMATION ===

		# Pet Information
		if self.patient_ids:
			notes.append(f"Patients: {', '.join(self.patient_ids.mapped('name'))}")
			for pet in self.patient_ids:
				if pet.species_id:
					notes.append(f"  - {pet.name}: {pet.species_id.name}")
				if hasattr(pet, 'breed_id') and pet.breed_id:
					notes.append(f"    Breed: {pet.breed_id.name}")
				if hasattr(pet, 'ths_dob') and pet.ths_dob:
					age = (fields.Date.today() - pet.ths_dob).days // 365
					notes.append(f"    Age: {age} years")
				if hasattr(pet, 'gender') and pet.gender:
					notes.append(f"    Gender: {pet.gender}")
				if hasattr(pet, 'is_neutered_spayed') and pet.is_neutered_spayed:
					notes.append(f"    Neutered/Spayed: Yes")

		if self.practitioner_id:
			notes.append(f"Attending Practitioner: {self.practitioner_id.name}")

		if self.room_id:
			notes.append(f"Treatment Room: {self.room_id.name}")

		notes.append("")  # Empty line

		# === CLINICAL FINDINGS ===
		notes.append("=== CLINICAL FINDINGS ===")

		if self.chief_complaint:
			notes.append("Chief Complaint:")
			notes.append(f"  {self.chief_complaint}")
			notes.append("")

		if self.history_illness:
			notes.append("History of Present Illness:")
			notes.append(f"  {self.history_illness}")
			notes.append("")

		# === VITALS ===
		if self.vitals_log_ids:
			notes.append("=== VITAL SIGNS ===")
			for vital in self.vitals_log_ids:
				notes.append(f"Patient: {vital.patient_id.name} - {vital.log_date}")
				if vital.weight:
					notes.append(f"  Weight: {vital.weight} kg")
				if vital.temperature:
					notes.append(f"  Temperature: {vital.temperature}°C")
				if vital.heart_rate:
					notes.append(f"  Heart Rate: {vital.heart_rate} bpm")
				if vital.respiratory_rate:
					notes.append(f"  Respiratory Rate: {vital.respiratory_rate} rpm")
				if vital.notes:
					notes.append(f"  Notes: {vital.notes}")
				notes.append("")

		# === SOAP NOTES ===
		if any([self.soap_subjective, self.soap_objective, self.soap_assessment, self.soap_plan]):
			notes.append("=== SOAP NOTES ===")

			if self.soap_subjective:
				notes.append("Subjective:")
				notes.append(f"  {self.soap_subjective}")
				notes.append("")

			if self.soap_objective:
				notes.append("Objective:")
				notes.append(f"  {self.soap_objective}")
				notes.append("")

			if self.soap_assessment:
				notes.append("Assessment:")
				notes.append(f"  {self.soap_assessment}")
				notes.append("")

			if self.soap_plan:
				notes.append("Plan:")
				notes.append(f"  {self.soap_plan}")
				notes.append("")

		# === SERVICES PROVIDED ===
		if self.encounter_line_ids:
			notes.append("=== SERVICES PROVIDED ===")
			for line in self.encounter_line_ids:
				service_note = f"- {line.product_id.name}"
				if line.qty != 1:
					service_note += f" (Qty: {line.qty})"
				if line.practitioner_id:
					service_note += f" - {line.practitioner_id.name}"
				notes.append(service_note)
				if line.notes:
					notes.append(f"    Notes: {line.notes}")
			notes.append("")

		# === VACCINATIONS ===
		if self.vaccination_ids:
			notes.append("=== VACCINATIONS ADMINISTERED ===")
			for vaccination in self.vaccination_ids:
				vacc_note = f"- {vaccination.vaccine_type_id.name}"
				if vaccination.date:
					vacc_note += f" on {vaccination.date}"
				if vaccination.expiry_date:
					vacc_note += f" (expires {vaccination.expiry_date})"
				notes.append(vacc_note)
				if vaccination.batch_number:
					notes.append(f"    Batch: {vaccination.batch_number}")
				if vaccination.notes:
					notes.append(f"    Notes: {vaccination.notes}")
			notes.append("")

		# === BOARDING INFORMATION ===
		if self.boarding_stay_ids:
			notes.append("=== BOARDING INFORMATION ===")
			for boarding in self.boarding_stay_ids:
				notes.append(f"- Boarding Stay: {boarding.name}")
				if boarding.cage_id:
					notes.append(f"    Cage: {boarding.cage_id.name}")
				notes.append(f"    Check-in: {boarding.check_in_datetime}")
				notes.append(f"    Expected Check-out: {boarding.expected_check_out_datetime}")
				if boarding.medical_conditions:
					notes.append(f"    Medical Conditions: {boarding.medical_conditions}")
				if boarding.routines_preferences_quirks:
					notes.append(f"    Special Requirements: {boarding.routines_preferences_quirks}")
			notes.append("")

		# === CLINICAL SUMMARIES ===
		if any([self.diagnosis_text, self.procedures_text, self.prescriptions_text,
				self.lab_orders_text, self.radiology_orders_text]):
			notes.append("=== CLINICAL SUMMARIES ===")

			if self.diagnosis_text:
				notes.append("Diagnoses:")
				notes.append(f"  {self.diagnosis_text}")
				notes.append("")

			if self.procedures_text:
				notes.append("Procedures Performed:")
				notes.append(f"  {self.procedures_text}")
				notes.append("")

			if self.prescriptions_text:
				notes.append("Prescriptions:")
				notes.append(f"  {self.prescriptions_text}")
				notes.append("")

			if self.lab_orders_text:
				notes.append("Laboratory Orders:")
				notes.append(f"  {self.lab_orders_text}")
				notes.append("")

			if self.radiology_orders_text:
				notes.append("Radiology Orders:")
				notes.append(f"  {self.radiology_orders_text}")
				notes.append("")

		# === RECOMMENDATIONS ===
		notes.append("=== TREATMENT RECOMMENDATIONS ===")
		notes.append("[ ] Monitor patient response to treatment")
		notes.append("[ ] Follow medication schedule as prescribed")
		notes.append("[ ] Watch for adverse reactions or complications")
		notes.append("[ ] Schedule follow-up examination")
		notes.append("[ ] Owner education on home care")
		notes.append("")

		# === BILLING INFORMATION ===
		if self.total_amount:
			notes.append("=== BILLING SUMMARY ===")
			notes.append(f"Total Amount: {self.total_amount} {self.company_currency.symbol}")
			if self.paid_amount:
				notes.append(f"Paid Amount: {self.paid_amount} {self.company_currency.symbol}")
			if self.pending_amount:
				notes.append(f"Pending Amount: {self.pending_amount} {self.company_currency.symbol}")
			notes.append("")

		# === CONTACT INFORMATION ===
		notes.append("=== EMERGENCY CONTACT ===")
		notes.append(f"Owner: {self.partner_id.name}")
		if self.partner_mobile:
			notes.append(f"Mobile: {self.partner_mobile}")
		if self.partner_id.phone:
			notes.append(f"Phone: {self.partner_id.phone}")
		if self.partner_id.email:
			notes.append(f"Email: {self.partner_id.email}")

		return "\n".join(notes)

	@api.model
	def _cron_encounter_daily_summary_email(self):
		"""Send daily encounter summary to managers"""
		today = fields.Date.today()
		encounters = self.search([('encounter_date', '=', today)])

		if not encounters:
			return

		# Get manager users
		manager_group = self.env.ref('ths_vet_base.group_vet_manager', raise_if_not_found=False)
		if not manager_group:
			return

		managers = manager_group.users

		# Prepare summary data
		summary_data = {
			'date': today,
			'total_encounters': len(encounters),
			'total_revenue': sum(encounters.mapped('total_amount')),
			'pending_amount': sum(encounters.mapped('pending_amount')),
			'total_patients': len(encounters.mapped('patient_ids')),
		}

		# Send email to each manager
		template = self.env.ref('ths_vet_base.email_template_daily_encounter_summary', raise_if_not_found=False)
		if template:
			for manager in managers:
				template.with_context(summary_data=summary_data).send_mail(
					manager.partner_id.id,
					force_send=True
				)

	@api.model
	def get_dashboard_data(self):
		"""Get data for the dashboard"""
		today = fields.Date.today()

		# Today's encounters
		daily_encounters = self.search_count([
			('encounter_date', '=', today),
		])

		# Today's revenue (you'll need to adjust this based on your fields)
		encounters_today = self.search([('encounter_date', '=', today)])
		daily_revenue = sum(encounters_today.mapped('total_amount'))

		# Today's unique patients
		daily_patients = len(encounters_today.mapped('patient_ids'))

		# Pending amount (encounters not fully paid)
		pending_encounters = self.search([
			('pending_payments', '=', True),
			# Add your pending payment condition here
		])
		pending_amount = sum(pending_encounters.mapped('total_amount'))  # Adjust as needed

		# Chart data - last 7 days
		chart_data = []
		for i in range(7):
			date = today - timedelta(days=i)
			count = self.search_count([('encounter_date', '=', date)])
			chart_data.append({
				'date': date.strftime('%m/%d'),
				'count': count
			})
		chart_data.reverse()  # Show oldest to newest

		# Status distribution
		status_data = {}
		all_encounters = self.search([])
		for encounter in all_encounters:
			state = encounter.state
			status_data[state] = status_data.get(state, 0) + 1

		return {
			'daily_encounters': daily_encounters,
			'daily_revenue': daily_revenue,
			'daily_patients': daily_patients,
			'pending_amount': pending_amount,
			'chart_data': chart_data,
			'status_data': status_data,
		}

	@api.model
	def get_dashboard_action(self, action_name):
		"""Get action configuration for dashboard buttons"""
		actions = {
			'action_medical_encounter_vet': {
				'name': 'All Encounters',
				'type': 'ir.actions.act_window',
				'res_model': 'vet.encounter.header',
				'view_mode': 'list,form',
				'target': 'current',
			},
			'action_vet_encounter_line_item': {
				'name': 'Billing Items',
				'type': 'ir.actions.act_window',
				'res_model': 'vet.encounter.line',
				'view_mode': 'list,form',
				'target': 'current',
			},
			'action_encounter_analytics_wizard': {
				'name': 'Analytics',
				'type': 'ir.actions.act_window',
				'res_model': 'encounter.analytics.wizard',
				'view_mode': 'form',
				'target': 'new',
			}
		}

		return actions.get(action_name, False)


# TODO: Add breed-specific service recommendations
# TODO: Implement multi-pet family discount calculations
# TODO: Implement species-specific treatment protocols
# TODO: Add pet photo capture integration
# TODO: Implement vaccination reminder system
# TODO: Add pet behavioral notes tracking
# TODO: Implement cross-pet medical history analysis
# TODO: Add encounter templates for common service combinations
# TODO: Add encounter insurance integration for claims
# TODO: Create encounter performance metrics per practitioner


class VetEncounterLine(models.Model):
	_name = 'vet.encounter.line'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'create_date desc'
	_description = 'Vet Encounter Line'

	name = fields.Char(compute='_compute_name', store=True, readonly=True)
	# Link to encounter header
	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter Header', required=True, index=True, ondelete='cascade')
	partner_id = fields.Many2one(related='encounter_id.partner_id', string='Pet Owner', store=True, copy=False, index=True, )
	patient_ids = fields.Many2many('res.partner', 'vet_encounter_line_patient_rel', 'line_id', 'patient_id', string='Pets',
								   context={'is_pet': True, 'default_is_pet': True}, store=True, readonly=False, index=True, tracking=True,
								   domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]", help="Pets receiving veterinary care in this encounter or service.")
	notes = fields.Text(string="Internal Notes")
	product_id = fields.Many2one('product.product', string='Product/Service', required=True, help="Service or product provided in this line item.")
	product_description = fields.Text(string='Description', help="Optional override for the product description on the product line.")
	qty = fields.Float(string='Quantity', required=True, digits='Product Unit of Measure', default=1.0)
	product_uom = fields.Many2one(string="UoM", related='product_id.uom_id', store=True, help="Unit of Measure of the product.")
	discount = fields.Float(string='Discount (%)', default=0.0, help="Discount percentage applied to this line.")
	unit_price = fields.Float(string='Unit Price', store=True, readonly=False, default=0.0)
	sub_total = fields.Monetary(string='Subtotal', compute='_compute_sub_total', currency_field='company_currency', store=True, tracking=True,
								help="Subtotal based on altered prices.")
	payment_status = fields.Selection(
		[('pending', 'Pending'), ('partial', 'Partially Paid'), ('posted', 'Posted'), ('paid', 'Paid'), ('refunded', 'Refunded'), ('cancelled', 'Cancelled')],
		string='Payment Status', default='pending', required=True, index=True, copy=False, tracking=True)
	source_model = fields.Selection(
		[('calendar.event', 'Appointment'), ('vet.boarding.stay', 'Boarding Stay'), ('vet.park.checkin', 'Park Check-in'), ('vet.vaccination', 'Vaccination'),
		 ('vet.pet.membership', 'Pet Membership'), ('sale.order', 'Sale Order'), ('account.move', 'Invoice'), ('manual_encounter', 'Encounter Entry'), ('manual_pos', 'POS Entry')],
		string='Source', help='Service type that generated this billing line')

	# Payment Tracking
	paid_amount = fields.Monetary(string='Paid Amount', compute='_compute_payment_amounts', store=True, help="Total amount paid across all payment methods", copy=False,
								  currency_field='company_currency', readonly=True, tracking=True, index=True)
	posted_amount = fields.Monetary(string='Posted Amount', compute='_compute_payment_amounts', store=True, help="Amount in posted documents but not yet paid", copy=False,
									currency_field='company_currency', readonly=True)
	remaining_qty = fields.Float(string='Unpaid Qty', compute='_compute_remaining_qty', store=True, help="Qty still unpaid", copy=False, readonly=True, tracking=True)
	payment_history = fields.Json(string='Payment History', default=list, copy=False, readonly=True, help="JSON array of all payment transactions")
	multiple_payment_sources = fields.Char(string='Payments', compute='_compute_payment_sources', store=True, help="Comma-separated list of payment document names",
										   copy=False, readonly=True)
	source_payment = fields.Char(string='Source Payment', help='Payment method, e.g., SO, Invoice, POS', copy=False, default='Manual', tracking=True)
	processed_date = fields.Datetime(string='Processed Date', readonly=True, copy=False, index=True)
	processed_by = fields.Many2one('res.users', string='Processed By', readonly=True, copy=False, ondelete='set null')
	sale_order_id = fields.Many2one('sale.order', string='Main Sale Order', ondelete='set null', copy=False, readonly=True, index=True)
	invoice_id = fields.Many2one('account.move', string='Main Invoice', ondelete='set null', copy=False, readonly=True, index=True)
	invoice_ids = fields.Many2many('account.move', 'encounter_line_invoice_rel', 'line_id', 'invoice_id', string='All Invoices', help="All invoices that include this line",
								   copy=False, readonly=True, tracking=True)
	sale_order_ids = fields.Many2many('sale.order', 'encounter_line_sale_rel', 'line_id', 'sale_order_id', string='All Sale Orders', help="All sale orders that include this line",
									  copy=False, readonly=True, tracking=True)
	payment_trigger = fields.Boolean(compute='_compute_payment_trigger', store=False)
	fields_readonly = fields.Boolean(compute='_compute_readonly_fields', store=False)

	# Refund tracking
	is_refunded = fields.Boolean(string='Has Refunds', default=False, copy=False, readonly=True, tracking=True, help="True if this line has any refunds")
	refunded_amount = fields.Monetary(string='Total Refunded', default=0.0, copy=False, tracking=True, currency_field='company_currency', help="Total amount refunded/line")
	refund_history = fields.Json(string='Refund History', default=list, copy=False, readonly=True, help="JSON array of refund transactions")
	tracking_reference = fields.Char(string='Tracking Reference', copy=False, readonly=True, index=True)
	original_line_id = fields.Many2one('vet.encounter.line', string='Original Line (for refunds)', copy=False, readonly=True)
	refund_line_ids = fields.One2many('vet.encounter.line', 'original_line_id', string='Refund Lines', readonly=True)

	# Dashboard fields
	encounter_month = fields.Char(string='Encounter Month', compute='_compute_encounter_month', store=True)
	encounter_week = fields.Char(string='Encounter Week', compute='_compute_encounter_week', store=True)
	revenue_per_patient = fields.Monetary(string='Revenue per Patient', currency_field='company_currency', compute='_compute_revenue_per_patient', store=True)

	@api.depends('product_id', 'encounter_id', 'patient_ids')
	def _compute_name(self):
		for item in self:
			name = item.product_id.name or _("Pending Line")
			if item.patient_ids:
				patient_names = ", ".join(item.patient_ids.mapped('name'))
				name += f" - {patient_names}"
			if item.encounter_id:
				name += f" ({item.encounter_id.name})"
			item.name = name

	@api.onchange('product_id')
	def _onchange_product_id(self):
		if self.product_id:
			self.unit_price = self.product_id.lst_price

	@api.depends('invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.amount_residual', 'invoice_ids.amount_total', 'qty', 'refunded_amount', 'unit_price', 'discount')
	def _compute_remaining_qty(self):
		for line in self:
			if not line.invoice_ids:
				line.remaining_qty = line.qty
				continue

			posted_invoices = line.invoice_ids.filtered(lambda inv: inv.state == 'posted')
			if not posted_invoices:
				line.remaining_qty = line.qty
				continue

			total_paid_qty = 0.0

			for invoice in posted_invoices:
				invoice_lines = invoice.invoice_line_ids.filtered(lambda il: il.encounter_line_id.id == line.id)

				if invoice.payment_state == 'paid':
					total_paid_qty += sum(invoice_lines.mapped('quantity'))
				elif invoice.payment_state == 'partial':
					if invoice.amount_total > 0:
						payment_ratio = (invoice.amount_total - invoice.amount_residual) / invoice.amount_total
						total_paid_qty += sum(invoice_lines.mapped('quantity')) * payment_ratio

			if line.refunded_amount > 0 and line.unit_price > 0:
				refunded_qty = line.refunded_amount / line.unit_price
				total_paid_qty = max(0, total_paid_qty - refunded_qty)

			line.remaining_qty = max(0, line.qty - total_paid_qty)

	@api.depends('qty', 'discount', 'unit_price')
	def _compute_sub_total(self):
		for item in self:
			if item.unit_price and item.qty:
				discount_factor = 1 - (item.discount or 0.0)
				item.sub_total = item.unit_price * item.qty * discount_factor
			else:
				item.sub_total = 0.0

	@api.depends('invoice_ids.payment_state', 'invoice_ids.state', 'invoice_ids.amount_residual', 'invoice_ids.amount_total', 'sale_order_ids.invoice_status',
				 'sale_order_ids.state', 'refunded_amount', 'sub_total', 'remaining_qty')
	def _compute_payment_amounts(self):
		for line in self:
			line.paid_amount = float(line._calculate_paid_amount())
			line.posted_amount = float(line._calculate_posted_amount())

	@api.depends('paid_amount', 'posted_amount', 'refunded_amount', 'sub_total', 'is_refunded', 'invoice_ids.payment_state', 'invoice_ids.state', 'invoice_ids.amount_residual',
				 'remaining_qty', 'qty')
	def _compute_payment_status(self):
		for line in self:
			total = line.sub_total or 0.0
			posted = line.posted_amount or 0.0
			refunded = line.refunded_amount or 0.0

			# Use remaining_qty logic first (most accurate)
			if line.remaining_qty == 0 and not line.is_refunded:
				line.payment_status = 'paid'
			elif line.is_refunded and refunded >= total:
				line.payment_status = 'refunded'
			elif line.qty > line.remaining_qty > 0:
				line.payment_status = 'partial'
			elif line.invoice_ids.filtered(lambda inv: inv.state == 'posted'):
				has_paid_invoice = any(inv.payment_state == 'paid' for inv in line.invoice_ids if inv.state == 'posted')
				has_partial_invoice = any(inv.payment_state == 'partial' for inv in line.invoice_ids if inv.state == 'posted')

				if has_paid_invoice:
					line.payment_status = 'paid'
				elif has_partial_invoice:
					line.payment_status = 'partial'
				else:
					line.payment_status = 'posted'
			elif posted > 0:
				line.payment_status = 'partial'
			else:
				line.payment_status = 'pending'

	def _trigger_payment_recomputation(self):
		"""Force recomputation of payment-related fields"""
		self._compute_payment_amounts()
		self._compute_remaining_qty()
		self._compute_payment_status()

	@api.depends('invoice_ids.payment_state', 'invoice_ids.amount_residual')
	def _compute_payment_trigger(self):
		"""Dummy computed field to trigger other computations when invoice payment changes"""
		for line in self:
			line._trigger_payment_recomputation()

	@api.depends('invoice_ids.name', 'invoice_ids.payment_state', 'sale_order_ids.name')
	def _compute_payment_sources(self):
		for line in self:
			sources = []
			for invoice in line.invoice_ids:
				status = f" ({invoice.payment_state})" if invoice.payment_state else ""
				if invoice.name and invoice.name != '/':
					sources.append(f"Invoice {invoice.name}{status}")
				else:
					sources.append(f"Invoice #{invoice.id}{status}")
			for so in line.sale_order_ids:
				if so.name and so.name != '/':
					sources.append(f"Sale {so.name}")
				else:
					sources.append(f"Sale #{so.id}")

			line.multiple_payment_sources = ", ".join(sources)

	def _calculate_paid_amount(self):
		"""Calculate total paid amount from all sources based on quantities"""
		self.ensure_one()
		paid_amount = 0.0

		# From fully paid invoices (payment_state = 'paid')
		for invoice in self.invoice_ids.filtered(lambda i: i.payment_state in ('paid', 'in_payment')):
			invoice_lines = invoice.invoice_line_ids.filtered(lambda l: l.encounter_line_id == self)
			for inv_line in invoice_lines:
				# Calculate proportional amount based on quantity
				qty_ratio = inv_line.quantity / self.qty if self.qty > 0 else 0
				paid_amount += inv_line.price_subtotal * qty_ratio

		# From invoiced and paid sale orders
		for so in self.sale_order_ids:
			so_lines = so.order_line.filtered(lambda l: l.encounter_line_id == self)
			for so_line in so_lines:
				invoice_lines = so_line.invoice_lines.filtered(lambda l: l.move_id.payment_state == 'paid')
				for inv_line in invoice_lines:
					qty_ratio = inv_line.quantity / self.qty if self.qty > 0 else 0
					paid_amount += inv_line.price_subtotal * qty_ratio

		return paid_amount - self.refunded_amount

	def _calculate_posted_amount(self):
		"""Calculate posted but unpaid amount based on quantities"""
		self.ensure_one()
		posted_amount = 0.0

		# From posted but unpaid invoices
		for invoice in self.invoice_ids.filtered(lambda i: i.state == 'posted' and i.payment_state not in ['paid', 'in_payment']):
			invoice_lines = invoice.invoice_line_ids.filtered(lambda l: l.encounter_line_id == self)
			for inv_line in invoice_lines:
				qty_ratio = inv_line.quantity / self.qty if self.qty > 0 else 0
				posted_amount += inv_line.price_subtotal * qty_ratio

		# From confirmed but not invoiced sale orders
		for so in self.sale_order_ids.filtered(lambda s: s.state == 'sale' and s.invoice_status == 'to invoice'):
			so_lines = so.order_line.filtered(lambda l: l.encounter_line_id == self)
			for so_line in so_lines:
				qty_ratio = so_line.product_uom_qty / self.qty if self.qty > 0 else 0
				posted_amount += so_line.price_subtotal * qty_ratio

		return posted_amount

	def _calculate_total_committed_amount(self):
		self.ensure_one()
		committed = 0.0

		# From invoices (posted or paid)
		for invoice in self.invoice_ids.filtered(lambda i: i.state in ['posted']):
			invoice_lines = invoice.invoice_line_ids.filtered(lambda l: l.encounter_line_id == self)
			committed += sum(invoice_lines.mapped('price_subtotal'))

		# From confirmed sale orders
		for so in self.sale_order_ids.filtered(lambda s: s.state == 'sale'):
			so_lines = so.order_line.filtered(lambda l: l.encounter_line_id == self)
			committed += sum(so_lines.mapped('price_subtotal'))

		return committed

	def action_create_refund(self):
		"""Create proper refund for this encounter line"""
		self.ensure_one()

		if self.payment_status != 'paid' or self.remaining_qty > 0:
			raise UserError(_("Cannot refund unpaid or partially unpaid line"))

		# Find the main invoice for this line
		invoice = self.invoice_id or self.invoice_ids[:1]
		if not invoice:
			raise UserError(_("No invoice found to refund"))

		# Create credit note through proper Odoo mechanism
		credit_note_wizard = self.env['account.move.reversal'].with_context(
			active_model='account.move',
			active_ids=invoice.ids
		).create({
			'reason': f'Refund for encounter line: {self.product_id.name}',
			'move_type': 'out_refund',
			'date': fields.Date.today(),
		})

		result = credit_note_wizard.reverse_moves()
		credit_note = self.env['account.move'].browse(result['res_id'])

		# Update line status and tracking - refund affects remaining_qty
		self.write({
			'payment_status': 'refunded',
			'refunded_amount': self.sub_total,
			'is_refunded': True,
		})
		# Trigger remaining_qty recomputation
		self._compute_remaining_qty()

		# Add to refund history
		self._update_refund_history('invoice', credit_note.id, credit_note.name, self.sub_total)

		return {
			'type': 'ir.actions.act_window',
			'name': 'Credit Note Created',
			'res_model': 'account.move',
			'res_id': credit_note.id,
			'view_mode': 'form',
			'target': 'current'
		}

	def _update_refund_history(self, source_type, source_id, source_name, amount):
		"""Update refund history tracking"""
		refund_entry = {
			'date': fields.Datetime.now().isoformat(),
			'source_type': source_type,
			'source_id': source_id,
			'source_name': source_name,
			'amount': amount,
			'user_id': self.env.user.id,
			'user_name': self.env.user.name
		}

		current_history = self.refund_history or []
		current_history.append(refund_entry)
		self.refund_history = current_history

	def _update_payment_history(self, payment_type, document_id, document_name, state):
		self.ensure_one()

		payment_entry = {
			'date': fields.Datetime.now().isoformat(),
			'amount': self.sub_total if state == 'posted' else self.paid_amount,
			'type': payment_type,
			'document_id': document_id,
			'document_name': document_name,
			'state': state,
			'user_id': self.env.user.id,
			'user_name': self.env.user.name
		}

		current_history = self.payment_history or []
		current_history.append(payment_entry)
		self.payment_history = current_history

	def process_refund(self, refund_qty, refund_source, reason="", document_id=None):
		"""Process refund based on quantity"""
		self.ensure_one()

		if refund_qty <= 0:
			raise ValueError("Refund quantity must be positive")

		if refund_qty > (self.qty - self.remaining_qty):
			raise ValidationError(f"Refund quantity ({refund_qty}) cannot exceed paid quantity ({self.qty - self.remaining_qty})")

		refund_amount = refund_qty * self.unit_price

		# Update refund tracking
		self.refunded_amount += refund_amount
		self.is_refunded = True

		# Add to refund history
		refund_entry = {
			'date': fields.Datetime.now().isoformat(),
			'quantity': refund_qty,
			'amount': refund_amount,
			'source': refund_source,
			'document_id': document_id,
			'reason': reason,
			'user_id': self.env.user.id,
			'user_name': self.env.user.name
		}

		current_history = self.refund_history or []
		current_history.append(refund_entry)
		self.refund_history = current_history

		# Trigger recomputation
		self._compute_remaining_qty()
		self._compute_payment_amounts()

		return True

	@api.depends('payment_status')
	def _compute_readonly_fields(self):
		"""Make fields readonly when paid/posted"""
		for line in self:
			line.fields_readonly = line.payment_status in ['paid', 'posted', 'refunded']

	@api.depends('encounter_id.encounter_date')
	def _compute_encounter_month(self):
		for line in self:
			if line.encounter_id.encounter_date:
				line.encounter_month = line.encounter_id.encounter_date.strftime('%Y-%m')
			else:
				line.encounter_month = ''

	@api.depends('encounter_id.encounter_date')
	def _compute_encounter_week(self):
		for line in self:
			if line.encounter_id.encounter_date:
				year, week, _ = line.encounter_id.encounter_date.isocalendar()
				line.encounter_week = f"{year}-W{week:02d}"
			else:
				line.encounter_week = ''

	@api.depends('sub_total', 'patient_ids')
	def _compute_revenue_per_patient(self):
		for line in self:
			patient_count = len(line.patient_ids) or 1
			line.revenue_per_patient = line.sub_total / patient_count

	@api.constrains('encounter_id')
	def _check_encounter_saved(self):
		for line in self:
			if not line.encounter_id.id:
				raise ValidationError(_("Encounter must be saved before adding lines."))

	@api.constrains('invoice_ids', 'sale_order_ids')
	def _check_payment_overlap(self):
		for line in self:
			total_committed = line._calculate_total_committed_amount()
			if total_committed > line.sub_total + 0.01:  # Small tolerance for rounding
				raise ValidationError(
					f"Line {line.name}: Total committed amount ({total_committed:.2f}) exceeds line amount ({line.sub_total:.2f})"
				)

	def _check_available_amount(self, requested_amount):
		self.ensure_one()
		available = self.remaining_qty * self.unit_price

		if requested_amount > available + 0.01:  # Small tolerance for rounding
			raise ValidationError(
				f"Requested amount ({requested_amount:.2f}) exceeds available amount ({available:.2f}) for line {self.name}"
			)

		# Check for existing documents in draft state
		draft_invoices = self.invoice_ids.filtered(lambda i: i.state == 'draft')
		draft_sos = self.sale_order_ids.filtered(lambda s: s.state in ['draft', 'sent'])

		if draft_invoices or draft_sos:
			message = "Existing draft documents found for this line:\n"
			for inv in draft_invoices:
				message += f"- Draft Invoice: {inv.name}\n"
			for so in draft_sos:
				message += f"- Draft Sale Order: {so.name}\n"
			message += "\nPlease process or cancel these documents before creating new ones."
			raise ValidationError(message)

	@api.onchange('product_id')
	def _onchange_product_id(self):
		"""Update unit price when product changes"""
		if self.product_id:
			self.unit_price = self.product_id.lst_price
			if not self.product_description:
				self.product_description = self.product_id.description_sale

	@api.onchange('practitioner_id')
	def _onchange_practitioner_id_filter_rooms(self):
		"""Filter available rooms when practitioner changes"""
		if self.practitioner_id and self.practitioner_id.ths_department_id:
			# Clear room if it doesn't match the new practitioner's department
			if self.room_id and self.room_id.ths_department_id != self.practitioner_id.ths_department_id:
				self.room_id = False

			return {
				'domain': {
					'room_id': [
						('resource_category', '=', 'location'),
						('ths_department_id', '=', self.practitioner_id.ths_department_id.id)
					]
				}
			}
		else:
			return {'domain': {'room_id': [('resource_category', '=', 'location')]}}

	@api.constrains('discount', 'product_id')
	def _check_discount_validity(self):
		"""Validate discount range and restrictions based on product sub-type"""
		for line in self:
			if line.discount < 0 or line.discount > 100:
				raise ValidationError(_("Discount must be between 0% and 100%."))

	# Prevent duplicate payments
	@api.constrains('payment_status', 'source_payment')
	def _check_payment_uniqueness(self):
		"""Ensure a line is not paid multiple times."""
		for line in self:
			if line.payment_status == 'paid' and line.source_payment:
				duplicate_payments = self.search([
					('id', '=', line.id),
					('source_payment', '!=', False),
					('payment_status', '=', 'paid')
				])

				if len(duplicate_payments.mapped('source_payment')) > 1:
					raise ValidationError(f"Line {line.id} has multiple payment sources: {duplicate_payments.mapped('source_payment')}")

	@api.constrains('qty')
	def _check_quantity_positive(self):
		"""Ensure quantity is positive"""
		for line in self:
			if line.qty <= 0:
				raise ValidationError(_("Quantity must be greater than zero."))

	@api.model
	def merge_pending_duplicates(self):
		"""Merge duplicate pending lines in same encounter with same source_model"""
		for line in self.filtered(lambda l: l.payment_status == 'pending'):
			duplicates = self.search([
				('encounter_id', '=', line.encounter_id.id),
				('product_id', '=', line.product_id.id),
				('source_model', '=', line.source_model),
				('payment_status', '=', 'pending'),
				('id', '!=', line.id)
			])
			if duplicates:
				total_qty = line.qty + sum(duplicates.mapped('qty'))
				line.write({'qty': total_qty})
				duplicates.unlink()
				line.message_post(body=_("Merged %d duplicate pending lines from %s.") % (len(duplicates), line.source_model))

	@api.constrains('source_model')
	def _check_source_model(self):
		allowed = ['calendar.event', 'vet.boarding.stay', 'vet.park.checkin', 'vet.vaccination', 'vet.pet.membership', 'vet.encounter.header', 'sale.order', 'account.move',
				   'manual_encounter', 'manual_pos']
		for record in self:
			if record.source_model and record.source_model not in allowed:
				selection_dict = dict(record._fields['source_model'].selection)
				source_display = selection_dict.get(record.source_model, record.source_model)
				raise ValidationError(_("Invalid source model: %s") % source_display)

	@api.model
	def default_get(self, fields_list):
		"""Set default values from encounter context"""
		res = super().default_get(fields_list)

		encounter_id = self.env.context.get('default_encounter_id')
		if encounter_id:
			encounter = self.env['vet.encounter.header'].browse(encounter_id)
			if encounter.exists():
				res['encounter_id'] = encounter.id
				res['partner_id'] = encounter.partner_id.id
				res['patient_ids'] = [(6, 0, encounter.patient_ids.ids)]
				res['practitioner_id'] = encounter.practitioner_id.id
				res['room_id'] = encounter.room_id.id

		if 'source_model' not in res:
			res['source_model'] = 'manual_encounter'

		return res

	@api.model_create_multi
	def create(self, vals_list):
		# Handle both single dict and list of dicts
		if not isinstance(vals_list, list):
			vals_list = [vals_list]

		processed_vals_list = []
		for vals in vals_list:
			if not vals.get('encounter_id'):
				partner_id = vals.get('partner_id')
				patient_ids = []
				if 'patient_ids' in vals:
					patient_ids_data = vals['patient_ids']
					if patient_ids_data and isinstance(patient_ids_data, list):
						for command in patient_ids_data:
							if command[0] == 6 and command[2]:
								patient_ids = command[2]
							elif command[0] == 4:
								patient_ids.append(command[1])
					if patient_ids and not partner_id:
						patient_record = self.env['res.partner'].browse(patient_ids[0])
						if patient_record.exists() and patient_record.pet_owner_id:
							vals['partner_id'] = patient_record.pet_owner_id.id
							partner_id = vals['partner_id']
				encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
					partner_id,
					patient_ids,
					fields.Date.context_today(self),
					vals.get('practitioner_id'),
					vals.get('room_id'),
				)
				vals['encounter_id'] = encounter.id

			if 'source_model' not in vals:
				vals['source_model'] = 'manual_encounter'

			# Default source_payment to Manual if not set
			if 'source_payment' not in vals:
				vals['source_payment'] = 'Manual'

			if not vals.get('tracking_reference'):
				vals['tracking_reference'] = self.env['ir.sequence'].next_by_code('encounter.line.tracking') or str(uuid.uuid4())

			processed_vals_list.append(vals)

		return super().create(processed_vals_list)

	def write(self, vals):
		res = super().write(vals)

		for item in self:
			if item.encounter_id:
				encounter = item.encounter_id

				updated_patient_ids = item.patient_ids.ids
				current_encounter_patient_ids = encounter.patient_ids.ids

				patients_to_add = [patient_id for patient_id in updated_patient_ids if
								   patient_id not in current_encounter_patient_ids]
				if patients_to_add:
					all_unique_patient_ids = list(set(current_encounter_patient_ids + patients_to_add))
					encounter.patient_ids = [Command.set(all_unique_patient_ids)]

				if item.practitioner_id and not encounter.practitioner_id:
					encounter.practitioner_id = item.practitioner_id.id

				if item.room_id and not encounter.room_id:
					encounter.room_id = item.room_id.id

				if 'product_id' in vals or 'qty' in vals:
					self.merge_pending_duplicates()

		return res

	def action_cancel(self):
		"""Cancel lines with proper document cleanup"""
		# Check for constraints
		posted_invoices = self.mapped('invoice_ids').filtered(lambda inv: inv.state == 'posted')
		if posted_invoices:
			raise UserError(_("Cannot cancel lines that are in posted invoices: %s") % posted_invoices.mapped('name'))

		paid_items = self.filtered(lambda i: i.payment_status == 'paid')
		if paid_items:
			raise UserError(_("Cannot cancel already paid items: %s") % paid_items.mapped('name'))

		# Remove from draft documents
		draft_invoices = self.mapped('invoice_ids').filtered(lambda inv: inv.state == 'draft')
		draft_so = self.mapped('sale_order_ids').filtered(lambda so: so.state in ['draft', 'sent'])

		for line in self:
			# Remove from draft invoice lines
			draft_inv_lines = draft_invoices.mapped('invoice_line_ids').filtered(lambda il: il.encounter_line_id == line)
			draft_inv_lines.unlink()

			# Remove from draft SO lines
			draft_so_lines = draft_so.mapped('order_line').filtered(lambda ol: ol.encounter_line_id == line)
			draft_so_lines.unlink()

			# Clear references
			line.write({
				'payment_status': 'cancelled',
				'invoice_ids': [(5, 0, 0)],
				'sale_order_ids': [(5, 0, 0)],
				'invoice_id': False,
				'sale_order_id': False,
			})

		return True

	def action_reset_to_pending(self):
		"""Reset to pending with validation"""
		invalid_items = self.filtered(lambda i: i.payment_status in ['paid', 'posted'])
		if invalid_items:
			raise UserError(_("Cannot reset items that are paid or posted: %s") % invalid_items.mapped('name'))

		items_to_reset = self.filtered(lambda i: i.payment_status == 'cancelled')
		if items_to_reset:
			items_to_reset.write({'payment_status': 'pending'})
		return True

	def action_refunded_from_pos(self):
		_logger.info("Action 'Refunded from POS' called for items: %s", self.ids)
		items_to_reset = self.filtered(lambda i: i.payment_status == 'paid')
		if not items_to_reset:
			_logger.warning("No items found in 'paid' state to refund from POS refund for ids: %s", self.ids)
			return False

		vals_to_write = {
			'payment_status': 'refunded'
		}
		items_to_reset.write(vals_to_write)
		_logger.info("Changed items %s state to 'refunded' due to refund.", items_to_reset.ids)

		for item in items_to_reset:
			item.message_post(body=_("Item status changed to 'Refunded' due to linked POS Order Line refund."))

		return True

	def _get_billing_summary(self):
		"""Generate billing summary for the line"""
		self.ensure_one()
		return {
			'pet_owner': self.partner_id.name or 'No Owner',
			'pet_name': self.patient_ids.name or 'No Pet',
			'service': self.product_id.name or 'No Service',
			'amount': self.sub_total,
			'practitioner': self.practitioner_id.name or 'No Practitioner',
			'room': self.room_id.name or 'No Room',
		}

	def action_refresh_payment_status(self):
		"""Manual method to refresh payment status"""
		for line in self:
			line._compute_payment_amounts()
			line._compute_payment_status()
			line._compute_payment_sources()
		return True

	def _get_vet_service_summary(self):
		self.ensure_one()
		return {
			'service_type': 'Veterinary Service',
			'pet_info': f"{self.patient_ids.name}" if self.patient_ids else 'Unknown Pet',
			'owner_info': self.partner_id.name if self.partner_id else 'Unknown Owner',
			'practitioner_info': self.practitioner_id.name if self.practitioner_id else 'Unknown Practitioner',
			'room_info': self.room_id.name if self.room_id else 'Unknown Room',
			'billing_amount': self.sub_total,
			'discount_amount': self.qty * self.discount if self.product_id else 0.0,
		}

	def action_view_encounter(self):
		self.ensure_one()
		if not self.encounter_id:
			return {}

		return {
			'name': _('Daily Encounter'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
			'view_mode': 'form',
			'res_id': self.encounter_id.id,
			'target': 'current'
		}

	def action_view_owner_billing_history(self):
		self.ensure_one()
		if not self.partner_id:
			return {}
		return {
			'name': _('Billing History: %s') % self.partner_id.name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.line',
			'view_mode': 'list,form',
			'domain': [('partner_id', '=', self.partner_id.id)],
			'context': {'search_default_groupby_state': 1, 'create': False},
		}

	def action_create_follow_up_service(self):
		"""Create follow-up service"""
		self.ensure_one()
		if not self.patient_ids or not self.partner_id:
			raise UserError(_("Pet and Pet Owner must be set to create follow-up service."))
		return {
			'name': _('Create Follow-up Service'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.line',
			'view_mode': 'form',
			'target': 'new',
			'context': {
				'default_encounter_id': self.encounter_id.id,
				'default_partner_id': self.partner_id.id,
				'default_patient_ids': [Command.set(self.patient_ids.ids)],
				'default_practitioner_id': self.practitioner_id.id,
				'default_room_id': self.room_id.id,
				'default_notes': f"Follow-up for: {self.product_id.name or 'Previous Service'}"
			}
		}

	def action_view_pet_medical_history(self):
		self.ensure_one()
		if not self.patient_ids:
			return {}
		return {
			'name': _('Medical History: %s') % self.patient_ids.name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', [self.patient_ids.id])],
			'context': {'search_default_groupby_date': 1, 'create': False},
		}


class EncounterAnalyticsWizard(models.TransientModel):
	_name = 'encounter.analytics.wizard'
	_description = 'Encounter Analytics Wizard'

	date_filter = fields.Selection([('today', 'Today'), ('yesterday', 'Yesterday'), ('last_week', 'Last Week'), ('last_month', 'Last Month'), ('custom', 'Custom')],
								   string='Date Filter', default='today')
	date_from = fields.Date(string='From')
	date_to = fields.Date(string='To')
	analytics_data = fields.Json(string='Analytics Data', readonly=True)

	def generate_analytics(self):
		domain = []
		today = fields.Date.today()
		period_name = ""

		if self.date_filter == 'today':
			domain = [('encounter_date', '=', today)]
			period_name = f"Today ({today.strftime('%Y-%m-%d')})"
		elif self.date_filter == 'yesterday':
			yesterday = today - timedelta(days=1)
			domain = [('encounter_date', '=', yesterday)]
			period_name = f"Yesterday ({yesterday.strftime('%Y-%m-%d')})"
		elif self.date_filter == 'last_week':
			start = today - timedelta(days=today.weekday() + 7)
			end = start + timedelta(days=6)
			domain = [('encounter_date', '>=', start), ('encounter_date', '<=', end)]
			period_name = f"Last Week ({start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')})"
		elif self.date_filter == 'last_month':
			start = today - relativedelta(months=1)
			domain = [('encounter_date', '>=', start), ('encounter_date', '<=', today)]
			period_name = f"Last Month ({start.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')})"
		elif self.date_filter == 'custom':
			if not self.date_from or not self.date_to:
				raise UserError(_("Please specify both From and To dates for custom period."))
			domain = [('encounter_date', '>=', self.date_from), ('encounter_date', '<=', self.date_to)]
			period_name = f"Custom Period ({self.date_from.strftime('%Y-%m-%d')} to {self.date_to.strftime('%Y-%m-%d')})"

		encounters = self.env['vet.encounter.header'].search(domain)

		# Store analytics data in the wizard record itself
		# This way the template can access it reliably
		self.analytics_data = {
			'period_name': period_name,
			'date_filter': self.date_filter,
			'date_from': self.date_from.strftime('%Y-%m-%d') if self.date_from else '',
			'date_to': self.date_to.strftime('%Y-%m-%d') if self.date_to else '',
			'total_encounters': len(encounters),
			'total_revenue': sum(encounters.mapped('total_amount')) or 0.0,
			'pending_amount': sum(encounters.mapped('pending_amount')) or 0.0,
			'paid_amount': sum(encounters.mapped('paid_amount')) or 0.0,
			'returned_amount': sum(encounters.mapped('returned_amount')) or 0.0,
			'total_patients': len(encounters.mapped('patient_ids')),
			'total_boardings': sum(len(e.boarding_stay_ids) for e in encounters),
			'total_services': sum(len(e.encounter_line_ids) for e in encounters),
			'total_vaccinations': sum(len(e.vaccination_ids) for e in encounters),
			'total_memberships': sum(len(e.pet_membership_ids) for e in encounters),
			'total_appointments': sum(len(e.appointment_ids) for e in encounters),
			'total_park_visits': sum(len(e.park_checkin_ids) for e in encounters),
		}

		# Use the standard report action approach
		return self.env.ref('ths_vet_base.action_encounter_analytics_report').report_action(self)


# TODO: Implement pending item priority system
# TODO: Add pending item expiration warnings
# TODO: Implement pending item bulk processing
# TODO: Add pending item approval workflow for high-value items


class AccountMove(models.Model):
	_inherit = 'account.move'

	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', copy=False, index=True, ondelete='set null', help="Encounter this Invoice belongs to")
	encounter_line_ids = fields.One2many('vet.encounter.line', 'invoice_id', string='Encounter Lines', copy=False, readonly=True)
	patient_ids = fields.Many2many('res.partner', 'account_move_patient_rel', 'move_id', 'patient_id', string='Pets', store=True, copy=False, index=True, ondelete='cascade',
								   domain="[('is_pet', '=', True),('pet_owner_id', '=?', partner_id)]", help="Pets this invoice belongs to")
	practitioner_id = fields.Many2one('appointment.resource', string='Primary Practitioner', domain="[('resource_category', '=', 'practitioner')]",
									  help="Primary practitioner for this invoice")
	room_id = fields.Many2one('appointment.resource', string='Primary Room', domain="[('resource_category', '=', 'location')]", help="Primary room for this invoice")
	encounter_line_count = fields.Integer(compute='_compute_encounter_counts', store=False)
	reversed_entry_id = fields.Many2one('account.move', string='Reversal of', help="Original invoice this credit note reverses")
	reversal_entry_ids = fields.One2many('account.move', 'reversed_entry_id', string='Credit Notes')

	@api.depends('encounter_line_ids')
	def _compute_encounter_counts(self):
		for move in self:
			move.encounter_line_count = len(move.encounter_line_ids)

	@api.onchange('move_type')
	def _onchange_move_type_partner_type(self):
		"""Set default partner type based on move type"""
		if self.move_type in ['out_invoice', 'out_refund']:
			# Try xmlid first, fallback to name search
			try:
				pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner')
				self.partner_type_id = pet_owner_type.id
			except ValueError:
				# Fallback to name search
				pet_owner_type = self.env['ths.partner.type'].search([
					('name', 'ilike', 'pet owner')
				], limit=1)
				if pet_owner_type:
					self.partner_type_id = pet_owner_type.id

		elif self.move_type in ['in_invoice', 'in_refund']:
			# Try xmlid first, fallback to name search
			try:
				vendor_type = self.env.ref('ths_base.partner_type_vendor')
				self.partner_type_id = vendor_type.id
			except ValueError:
				# Fallback to name search
				vendor_type = self.env['ths.partner.type'].search([
					('name', 'ilike', 'vendor')
				], limit=1)
				if vendor_type:
					self.partner_type_id = vendor_type.id

	def action_post(self):
		result = super().action_post()

		# Update related encounter lines
		encounter_lines = self.invoice_line_ids.mapped('encounter_line_id')
		for line in encounter_lines:
			line._update_payment_history('invoice', self.id, self.name, 'posted')
			line._compute_payment_amounts()

		return result

	def _post(self, soft=True):
		"""Override _post to monitor when invoice becomes posted"""
		result = super()._post(soft)

		# Update encounter lines when posted
		for move in self.filtered(lambda m: m.state == 'posted'):
			encounter_lines = move.invoice_line_ids.mapped('encounter_line_id').filtered(lambda x: x)
			for line in encounter_lines:
				line._update_payment_history('invoice', move.id, move.name, 'posted')
				line._compute_payment_amounts()

		return result

	@api.model
	def default_get(self, fields_list):
		defaults = super(AccountMove, self).default_get(fields_list)

		source_model = self.env.context.get('active_model')
		source_id = self.env.context.get('active_id')

		if 'partner_type_id' in fields_list:
			move_type = self.env.context.get('default_move_type')
			if move_type in ['out_invoice', 'out_refund']:
				try:
					pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=True)
					defaults['partner_type_id'] = pet_owner_type.id
				except ValueError:
					# Fallback to name search if xmlid is not found
					pet_owner_type = self.env['ths.partner.type'].search([('name', 'ilike', 'pet owner')], limit=1)
					if pet_owner_type:
						defaults['partner_type_id'] = pet_owner_type.id

		if source_model == 'sale.order' and source_id:
			so = self.env['sale.order'].browse(source_id)

			if 'encounter_id' in fields_list:
				defaults['encounter_id'] = so.encounter_id.id

			if 'patient_ids' in fields_list:
				defaults['patient_ids'] = so.mapped('patient_ids').ids

			if 'practitioner_id' in fields_list:
				defaults['practitioner_id'] = so.practitioner_id.id

			if 'room_id' in fields_list:
				defaults['room_id'] = so.room_id.id

		return defaults

	def write(self, vals):
		"""Monitor payment_state changes more aggressively"""
		result = super().write(vals)

		# Monitor payment_state changes specifically
		if 'payment_state' in vals:
			for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
				encounter_lines = move.invoice_line_ids.mapped('encounter_line_id').filtered(lambda x: x)
				if encounter_lines:
					# Force recomputation of payment amounts and status
					encounter_lines._compute_payment_amounts()
					encounter_lines._compute_payment_status()
					encounter_lines._compute_payment_sources()

					# Update payment history
					for line in encounter_lines:
						if move.payment_state in ('paid', 'in_payment'):
							line._update_payment_history('invoice', move.id, move.name, 'paid')
							line.write({
								'processed_date': fields.Datetime.now(),
								'processed_by': self.env.user.id,
								'source_payment': 'Invoice'
							})

		# Handle credit note posting
		if 'state' in vals and vals['state'] == 'posted':
			for move in self.filtered(lambda m: m.move_type == 'out_refund'):
				if move.reversed_entry_id:
					# Set encounter_id from original invoice if not set
					if not move.encounter_id and move.reversed_entry_id.encounter_id:
						move.encounter_id = move.reversed_entry_id.encounter_id.id

					original_lines = move.reversed_entry_id.invoice_line_ids.mapped('encounter_line_id')
					for line in original_lines.filtered(lambda x: x):
						refund_lines = move.invoice_line_ids.filtered(lambda l: l.encounter_line_id == line)
						refund_amount = sum(refund_lines.mapped('price_subtotal'))

						line.write({
							'refunded_amount': line.refunded_amount + refund_amount,
							'is_refunded': True,
							'payment_status': 'refunded',
						})
						line._update_refund_history('credit_note', move.id, move.name, refund_amount)
						line._compute_payment_amounts()

		# Link credit note to encounter
		# if line.encounter_id:
		# 	move.encounter_id = line.encounter_id.id

		return result

	def _reverse_moves(self, default_values_list=None, cancel=False):
		result = super()._reverse_moves(default_values_list, cancel)

		for move in self:
			encounter_lines = move.invoice_line_ids.mapped('encounter_line_id')
			for line in encounter_lines:
				refund_amount = sum(
					move.invoice_line_ids.filtered(lambda l: l.encounter_line_id == line).mapped('price_subtotal')
				)
				line.process_refund(refund_amount, 'invoice', f"Invoice {move.name} refunded", move.id)

		return result

	def action_view_encounter(self):
		"""View the related encounter"""
		self.ensure_one()
		if not self.encounter_id:
			return {}

		return {
			'name': _('Related Encounter'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
			'view_mode': 'form',
			'res_id': self.encounter_id.id,
			'target': 'current'
		}

	def action_view_credit_notes(self):
		"""View all credit notes for this invoice"""
		return {
			'type': 'ir.actions.act_window',
			'name': 'Credit Notes',
			'res_model': 'account.move',
			'view_mode': 'list,form',
			'domain': [('id', 'in', self.reversal_entry_ids.ids)],
			'context': {'default_partner_id': self.partner_id.id}
		}

	def action_view_original_invoice(self):
		"""View original invoice this credit note reverses"""
		return {
			'type': 'ir.actions.act_window',
			'name': 'Original Invoice',
			'res_model': 'account.move',
			'res_id': self.reversed_entry_id.id,
			'view_mode': 'form',
			'target': 'current'
		}

	def action_view_encounter_lines(self):
		return {
			'type': 'ir.actions.act_window',
			'name': _('Related Encounter Lines'),
			'res_model': 'vet.encounter.line',
			'view_mode': 'list,form',
			'domain': [('invoice_ids', 'in', [self.id])],
			'context': {'create': False}
		}

	def action_select_encounter_lines(self):
		return {
			'type': 'ir.actions.act_window',
			'name': _('Select Encounter Lines'),
			'res_model': 'encounter.payment.wizard',
			'view_mode': 'form',
			'target': 'new',
			'context': {
				'default_payment_type': 'invoice',
				'default_partner_id': self.partner_id.id,
				'active_invoice_id': self.id
			}
		}


class AccountMoveLine(models.Model):
	_inherit = 'account.move.line'

	encounter_line_id = fields.Many2one('vet.encounter.line', string='Encounter Line', help="Encounter line this invoice line represents", index=True, ondelete='set null',
										copy=False, readonly=True)
	patient_ids = fields.Many2many('res.partner', 'account_move_line_patient_rel', 'move_id', 'patient_id', string='Pets', store=True, copy=False, index=True, ondelete='cascade',
								   domain="[('is_pet', '=', True),('pet_owner_id', '=?', partner_id)]", help="Pets this invoice belongs to")
	practitioner_id = fields.Many2one('appointment.resource', string='Practitioner', domain="[('resource_category', '=', 'practitioner')]")
	room_id = fields.Many2one('appointment.resource', string='Room', domain="[('resource_category', '=', 'location')]")

	@api.model
	def default_get(self, fields_list):
		defaults = super().default_get(fields_list)

		active_model = self.env.context.get('active_model')
		active_id = self.env.context.get('active_id')

		if active_model == 'account.move' and active_id:
			move = self.env['account.move'].browse(active_id)

			if 'practitioner_id' in fields_list and move.practitioner_id:
				defaults['practitioner_id'] = move.practitioner_id.id

			if 'room_id' in fields_list and move.room_id:
				defaults['room_id'] = move.room_id.id

			if 'patient_ids' in fields_list and move.patient_ids:
				defaults['patient_ids'] = move.patient_ids.ids

		return defaults


class AccountPartialReconcile(models.Model):
	_inherit = 'account.partial.reconcile'

	@api.model_create_multi
	def create(self, vals_list):
		"""Monitor reconciliation to detect payments"""
		result = super().create(vals_list)

		for reconcile in result:
			# Find invoices that became fully paid after this reconciliation
			credit_move = reconcile.credit_move_id.move_id
			debit_move = reconcile.debit_move_id.move_id

			for move in [credit_move, debit_move]:
				if move.move_type == 'out_invoice' and move.payment_state == 'paid':
					encounter_lines = move.invoice_line_ids.mapped('encounter_line_id').filtered(lambda x: x)
					for line in encounter_lines:
						line._update_payment_history('invoice', move.id, move.name, 'paid')
						line._compute_payment_amounts()

		return result


class SaleOrder(models.Model):
	_inherit = 'sale.order'

	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', copy=False, index=True, ondelete='set null', help="Encounter this sales order belongs to")
	encounter_line_ids = fields.One2many('vet.encounter.line', 'sale_order_id', string='Encounter Lines', copy=False, readonly=True)
	patient_ids = fields.Many2many('res.partner', 'sale_order_patient_rel', 'order_id', 'patient_id', string='Pets', store=True, copy=False, index=True, ondelete='cascade',
								   domain="[('is_pet', '=', True),('pet_owner_id', '=?', partner_id)]", help="Pets this Sale Order belongs to")
	practitioner_id = fields.Many2one('appointment.resource', string='Practitioner', domain="[('resource_category', '=', 'practitioner')]")
	room_id = fields.Many2one('appointment.resource', string='Room', domain="[('resource_category', '=', 'location')]")
	encounter_line_count = fields.Integer(compute='_compute_encounter_counts', store=False)

	@api.depends('encounter_line_ids')
	def _compute_encounter_counts(self):
		for order in self:
			order.encounter_line_count = len(order.encounter_line_ids)

	def action_view_encounter_lines(self):
		return {
			'type': 'ir.actions.act_window',
			'name': _('Related Encounter Lines'),
			'res_model': 'vet.encounter.line',
			'view_mode': 'list,form',
			'domain': [('sale_order_ids', 'in', [self.id])],
			'context': {'create': False}
		}

	def action_select_encounter_lines(self):
		return {
			'type': 'ir.actions.act_window',
			'name': _('Select Encounter Lines'),
			'res_model': 'encounter.payment.wizard',
			'view_mode': 'form',
			'target': 'new',
			'context': {
				'default_payment_type': 'sale_order',
				'default_partner_id': self.partner_id.id,
				'default_order_partner_id': self.partner_id.id,
				'active_sale_order_id': self.id
			}
		}

	def action_confirm(self):
		result = super().action_confirm()

		encounter_lines = self.order_line.mapped('encounter_line_id')
		for line in encounter_lines:
			line._update_payment_history('sale_order', self.id, self.name, 'posted')
			line._compute_payment_amounts()

		return result


class SaleOrderLine(models.Model):
	_inherit = 'sale.order.line'

	encounter_line_id = fields.Many2one('vet.encounter.line', string='Encounter Line', index=True, ondelete='set null', copy=False, readonly=True)
	# partner_id = fields.Many2one('res.partner', string='Pet Owner', context={'default_is_pet': False, 'default_is_pet_owner': True}, required=True, index=True,
	# 							 domain="[('is_pet_owner', '=', True)]", help="Pet owner.")
	patient_ids = fields.Many2many('res.partner', 'sale_order_line_patient_rel', 'order_line_id', 'patient_id', string='Pets', store=True, copy=False, index=True,
								   ondelete='cascade', domain="[('is_pet', '=', True),('pet_owner_id', '=?', order_partner_id)]", help="Pets this sale order line belongs to")
	practitioner_id = fields.Many2one('appointment.resource', string='Practitioner', domain="[('resource_category', '=', 'practitioner')]")
	room_id = fields.Many2one('appointment.resource', string='Room', domain="[('resource_category', '=', 'location')]")

	def _prepare_invoice_line(self, **optional_values):
		"""Override to pass encounter_line_id to invoice line if order has encounter"""
		vals = super()._prepare_invoice_line(**optional_values)
		if self.order_id.encounter_id:
			vals['encounter_line_id'] = self.encounter_line_id.id
		return vals


class EncounterPaymentWizard(models.TransientModel):
	_name = 'encounter.payment.wizard'
	_description = 'Select Encounters for Payment'

	partner_id = fields.Many2one('res.partner', string='Customer', required=True, domain="[('is_pet_owner', '=', True)]", index=True)
	date_from = fields.Date(string='From Date', required=True, default=lambda self: fields.Date.today() - timedelta(days=30))
	date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)
	encounter_ids = fields.Many2many('vet.encounter.header', 'wizard_encounter_rel', 'wizard_id', 'encounter_id', string='Available Encounters', readonly=True)
	line_ids = fields.Many2many('vet.encounter.line', 'wizard_line_rel', 'wizard_id', 'line_id', string='Selected Lines',
								domain="[('encounter_id', 'in', encounter_ids), ('payment_status', 'in', ['pending', 'partial'])]")
	total_amount = fields.Monetary(compute='_compute_total', currency_field='company_currency', store=False)
	company_currency = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id, required=True)
	payment_type = fields.Selection([('invoice', 'Create Invoice'), ('sale_order', 'Create Sale Order')], required=True, default='invoice')

	@api.depends('line_ids')
	def _compute_total(self):
		for wizard in self:
			wizard.total_amount = sum(wizard.line_ids.mapped('sub_total'))

	@api.onchange('partner_id', 'date_from', 'date_to')
	def _onchange_search_criteria(self):
		if self.partner_id:
			domain = [
				('partner_id', '=', self.partner_id.id),
				('encounter_date', '>=', self.date_from),
				('encounter_date', '<=', self.date_to),
				('encounter_line_ids.payment_status', 'in', ['pending', 'partial'])
			]
			encounters = self.env['vet.encounter.header'].search(domain)
			self.encounter_ids = [(6, 0, encounters.ids)]

			# Auto-select all pending lines
			pending_lines = encounters.mapped('encounter_line_ids').filtered(
				lambda l: l.payment_status in ['pending', 'partial'] and l.paid_amount < 0
			)
			self.line_ids = [(6, 0, pending_lines.ids)]

	def action_create_payment_document(self):
		if not self.line_ids:
			raise UserError(_("No lines selected for payment."))

		if self.payment_type == 'invoice':
			return self._create_invoice()
		elif self.payment_type == 'sale_order':
			return self._create_sale_order()
		else:
			raise UserError(_("Invalid payment type selected."))

	def _create_invoice(self):
		all_patient_ids = self.line_ids.mapped('patient_ids').ids

		encounters = self.line_ids.mapped('encounter_id')
		if len(encounters) == 1:
			encounter_origin = encounters.name
			encounter_id = encounters.id
		else:
			encounter_origin = f"Multiple Encounters: {', '.join(encounters.mapped('name'))}"
			encounter_id = False

		pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)

		primary_practitioner = self.line_ids.mapped('practitioner_id')[:1]
		primary_room = self.line_ids.mapped('room_id')[:1]

		invoice_vals = {
			'partner_id': self.partner_id.id,
			'patient_ids': [(6, 0, all_patient_ids)],
			'partner_type_id': pet_owner_type.id if pet_owner_type else False,
			'practitioner_id': primary_practitioner.id if primary_practitioner else False,
			'room_id': primary_room.id if primary_room else False,
			'move_type': 'out_invoice',
			'encounter_id': encounter_id,
			'invoice_origin': encounter_origin,
			'invoice_date': fields.Date.today(),
			'invoice_line_ids': []
		}

		# Group lines by encounter for organization
		encounters = self.line_ids.mapped('encounter_id')
		if len(encounters) == 1:
			invoice_vals['encounter_id'] = encounters.id

		for line in self.line_ids:
			remaining = line.remaining_qty * line.unit_price
			if line.payment_status == 'pending':
				# Full line
				quantity = line.qty
				discount = line.discount
			else:
				# Partial line
				quantity = remaining / line.unit_price if line.unit_price > 0 else 1.0
				discount = 0.0

			invoice_line_vals = {
				'product_id': line.product_id.id,
				'name': f"[{line.encounter_id.name}] {line.product_id.name}",
				'quantity': quantity,
				'price_unit': line.unit_price,
				'encounter_line_id': line.id,
				'discount': discount * 100,
				'partner_id': line.partner_id.id,
				'patient_ids': [(6, 0, line.patient_ids.ids)],
				'practitioner_id': line.practitioner_id.id,
				'room_id': line.room_id.id,
			}
			invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))

		invoice = self.env['account.move'].create(invoice_vals)

		# Link to encounter lines
		for line in self.line_ids:
			line.invoice_ids = [(4, invoice.id)]
			line.invoice_id = invoice.id
			line._update_payment_history('invoice', invoice.id, invoice.name, 'posted')

		return {
			'type': 'ir.actions.act_window',
			'res_model': 'account.move',
			'res_id': invoice.id,
			'view_mode': 'form',
			'target': 'current'
		}

	def _create_sale_order(self):
		all_patient_ids = self.line_ids.mapped('patient_ids').ids

		encounters = self.line_ids.mapped('encounter_id')
		if len(encounters) == 1:
			encounter_origin = encounters.name
			encounter_id = encounters.id
		else:
			encounter_origin = f"Multiple Encounters: {', '.join(encounters.mapped('name'))}"
			encounter_id = False

		so_vals = {
			'partner_id': self.partner_id.id,
			'encounter_id': encounter_id,
			'origin': encounter_origin,
			'patient_ids': [(6, 0, all_patient_ids)],
			'order_line': []
		}

		encounters = self.line_ids.mapped('encounter_id')
		if len(encounters) == 1:
			so_vals['encounter_id'] = encounters.id

		for line in self.line_ids:
			remaining = line.remaining_qty * line.unit_price
			if line.payment_status == 'pending':
				# Full line
				quantity = line.qty
				discount = line.discount
			else:
				# Partial line
				quantity = remaining / line.unit_price if line.unit_price > 0 else 1.0
				discount = 0.0

			so_line_vals = {
				'product_id': line.product_id.id,
				'name': f"[{line.encounter_id.name}] {line.product_id.name}",
				'product_uom_qty': quantity,
				'price_unit': line.unit_price,
				'encounter_line_id': line.id,
				'discount': discount,
			}
			so_vals['order_line'].append((0, 0, so_line_vals))

		sale_order = self.env['sale.order'].create(so_vals)

		# Link to encounter lines
		for line in self.line_ids:
			line.sale_order_ids = [(4, sale_order.id)]
			line.sale_order_id = sale_order.id
			line._update_payment_history('sale_order', sale_order.id, sale_order.name, 'posted')

		return {
			'type': 'ir.actions.act_window',
			'res_model': 'sale.order',
			'res_id': sale_order.id,
			'view_mode': 'form',
			'target': 'current'
		}


class VetVitalsLog(models.Model):
	_name = 'vet.vitals.log'
	_description = 'Vitals Log'

	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', required=True, ondelete='cascade')
	patient_id = fields.Many2one('res.partner', string='Pet', domain="[('is_pet', '=', True), ('pet_owner_id', '=?', pet_owner_id)]", required=True)
	pet_owner_id = fields.Many2one('res.partner', string='Pet Owner', store=True, index=True, context={'default_is_pet': False, 'default_is_pet_owner': True})
	log_date = fields.Datetime(string='Log Date', default=fields.Datetime.now)
	weight = fields.Float(string='Weight (kg)')
	height = fields.Float(string='Height (cm)')
	temperature = fields.Float(string='Temperature (°C)')
	heart_rate = fields.Integer(string='Heart Rate (bpm)')
	respiratory_rate = fields.Integer(string='Respiratory Rate (rpm)')
	notes = fields.Text(string='Notes')