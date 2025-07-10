# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class VetBoardingStay(models.Model):
	_name = 'vet.boarding.stay'
	_description = 'Veterinary Boarding Stay'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_order = 'check_in_datetime desc, name'
	_rec_name = 'name'

	name = fields.Char(
		string='Boarding Reference',
		required=True,
		copy=False,
		readonly=True,
		index=True,
		default=lambda self: _('New')
	)
	owner_id = fields.Many2one(
		'res.partner',
		string='Pet Owner',
		context={'is_pet': False},
		required=True,
		index=True,
		domain="[('partner_type_id.name', '=', 'Pet Owner')]",
		tracking=True,
	)
	pet_id = fields.Many2one(
		'res.partner',
		string='Pet',
		context={'is_pet': True},
		required=True,
		index=True,
		domain="[('partner_type_id.name', '=', 'Pet')]",
		tracking=True,
	)

	@api.depends('pet_id.species_id')
	def _compute_cage_domain(self):
		"""
		Dynamically computes the domain for the 'cage_id' field.
		Filters available cages by state and, if a pet's species is selected,
		by allowed species.
		"""
		for record in self:
			domain = [('state', '=', 'available')]
			if record.pet_id and record.pet_id.species_id:
				# If a pet is selected AND it has a species,
				# add the species filter to the domain.
				domain.append(('allowed_species_ids', 'in', record.pet_id.species_id.id))
			record.cage_domain = str(domain)  # Convert the list domain to a string

	cage_domain = fields.Char(
		string='Cage Domain',
		compute='_compute_cage_domain',
		store=False,
		readonly=True,
		help="Dynamic domain for cage selection based on pet's species."
	)
	cage_id = fields.Many2one(
		'vet.boarding.cage',
		string='Assigned Cage',
		domain="cage_domain",
		required=True,
		index=True,
		# domain="[('state', '=', 'available')]",
		tracking=True,
	)

	check_in_datetime = fields.Datetime(
		string='Check-in',
		default=fields.Datetime.now,
		tracking=True,
	)
	expected_check_out_datetime = fields.Datetime(
		string='Expected Check-out',
		required=True,
		tracking=True,
	)
	actual_check_out_datetime = fields.Datetime(
		string='Actual Check-out',
		readonly=True,
		copy=False,
		tracking=True,
	)
	duration_days = fields.Integer(
		string="Duration (Days)",
		compute='_compute_duration_days',
		store=True,
		help="Calculated duration in days based on check-in and check-out.",
	)
	state = fields.Selection([
		('draft', 'Draft'),
		('scheduled', 'Scheduled'),
		('checked_in', 'Checked In'),
		('checked_out', 'Checked Out'),
		('invoiced', 'Invoiced/Paid'),
		('cancelled', 'Cancelled')
	], string='Status', default='draft', index=True, required=True, tracking=True, copy=False)

	encounter_id = fields.Many2one(
		'ths.medical.base.encounter',
		string='Daily Encounter',
		readonly=True,
		copy=False,
		index=True,
		ondelete='set null',
		help="Daily encounter this boarding stay belongs to"
	)

	# Computed domain string for pets based on selected owner
	pet_id_domain = fields.Char(
		compute='_compute_pet_domain',
		store=False
	)

	# Boarding Information
	vaccination_proof_received = fields.Boolean(string='Vaccination Proof Received?', tracking=True)
	medical_conditions = fields.Text(string='Medical Conditions / Allergies')
	routines_preferences_quirks = fields.Text(string='Routines & Preferences')

	owner_brought_food = fields.Boolean(string='Own Food Provided?', default=False)
	food_instructions = fields.Text(string='Feeding Instructions')

	owner_brought_medication = fields.Boolean(string='Own Medication Provided?', default=False)
	medication_instructions = fields.Text(string='Medication Instructions')

	consent_form_signed = fields.Boolean(string='Consent Form Signed?', default=False, tracking=True)

	# Billing
	boarding_product_id = fields.Many2one(
		'product.product',
		string='Boarding Product',
		domain="[('product_sub_type_id.code', '=', 'SERV')]",
		help="Product used for billing this boarding stay"
	)
	daily_rate = fields.Float(
		string='Daily Rate',
		compute='_compute_daily_rate',
		store=True,
		readonly=False
	)
	total_amount = fields.Float(
		string='Total Amount',
		compute='_compute_total_amount',
		store=True
	)
	pending_pos_item_ids = fields.One2many(
		'ths.pending.pos.item',
		'boarding_stay_id',
		string='Pending POS Items',
		readonly=True
	)

	notes = fields.Text(string='Internal Boarding Notes')
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

	# TODO: Add relation to vet.boarding.log (One2many) later
	# TODO: Add relation to checklist lines (One2many) later
	# TODO: Add relation to billing (e.g., related product, link to pending items/invoice) later

	#--- Compute / Onchange ---
	# @api.depends('pet_id')
	# def _compute_owner_id(self):
	# 	""" Default owner from pet """
	# 	for stay in self:
	# 		if stay.pet_id and stay.pet_id.pet_owner_id:
	# 			# Set only if owner is not already set or differs from pet's default owner
	# 			if not stay.owner_id or stay.owner_id != stay.pet_id.pet_owner_id:
	# 				stay.owner_id = stay.pet_id.pet_owner_id

	@api.depends('owner_id')
	def _compute_pet_domain(self):
		"""Compute domain for pets based on selected owner"""
		for rec in self:
			if rec.owner_id:
				# Filter pets by selected owner
				rec.pet_id_domain = str([
					('pet_owner_id', '=', rec.owner_id.id),
					('partner_type_id.name', '=', 'Pet')
				])
			else:
				# Show all pets when no owner selected
				rec.pet_id_domain = str([('partner_type_id.name', '=', 'Pet')])

	@api.depends('check_in_datetime', 'expected_check_out_datetime')
	def _compute_duration_days(self):
		""" Calculate stay duration. Needs careful handling of partial days. """
		for stay in self:
			if stay.check_in_datetime and stay.expected_check_out_datetime:
				# Simple difference in days, rounds down. Add 1 maybe? Depends on pricing policy.
				delta = stay.expected_check_out_datetime.date() - stay.check_in_datetime.date()
				stay.duration_days = delta.days + 1  # Example: Check-in Mon, Check-out Tue = 2 days charged?
			else:
				stay.duration_days = 0

	@api.depends('boarding_product_id', 'boarding_product_id.list_price')
	def _compute_daily_rate(self):
		"""Compute daily rate from product or manual entry"""
		for stay in self:
			if stay.boarding_product_id and not stay.daily_rate:
				stay.daily_rate = stay.boarding_product_id.list_price

	@api.depends('daily_rate', 'duration_days')
	def _compute_total_amount(self):
		"""Calculate total boarding cost"""
		for stay in self:
			stay.total_amount = stay.daily_rate * stay.duration_days

	@api.constrains('check_in_datetime', 'expected_check_out_datetime')
	def _check_dates(self):
		for stay in self:
			if stay.check_in_datetime and stay.expected_check_out_datetime and \
					stay.expected_check_out_datetime < stay.check_in_datetime:
				raise ValidationError(_("Expected Check-out date cannot be before Check-in date."))
			if stay.actual_check_out_datetime and stay.check_in_datetime and \
					stay.actual_check_out_datetime < stay.check_in_datetime:
				raise ValidationError(_("Actual Check-out date cannot be before Check-in date."))

	@api.constrains('cage_id', 'state', 'check_in_datetime', 'expected_check_out_datetime')
	def _check_cage_availability_overlap(self):
		"""Ensure no overlapping stays in the same cage"""
		for stay in self.filtered(lambda s: s.state in ('scheduled', 'checked_in')):
			if not stay.cage_id:
				continue

			# Check for overlapping stays
			domain = [
				('cage_id', '=', stay.cage_id.id),
				('state', 'in', ['scheduled', 'checked_in']),
				('id', '!=', stay.id),
			]

			# Add date overlap conditions
			if stay.check_in_datetime and stay.expected_check_out_datetime:
				domain.extend([
					'|',
					'&', ('check_in_datetime', '<=', stay.check_in_datetime),
					('expected_check_out_datetime', '>', stay.check_in_datetime),
					'&', ('check_in_datetime', '<', stay.expected_check_out_datetime),
					('expected_check_out_datetime', '>=', stay.expected_check_out_datetime),
				])

			overlapping = self.search_count(domain)
			if overlapping:
				raise ValidationError(
					_("Cage %s is already booked during this period.", stay.cage_id.name)
				)

	# CRUD methods
	@api.model_create_multi
	def create(self, vals_list):
		"""Assign sequence on creation"""
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('vet.boarding.stay') or _('New')

			# Validate cage availability
			if vals.get('state') == 'checked_in' and vals.get('cage_id'):
				cage = self.env['vet.boarding.cage'].browse(vals['cage_id'])
				if cage.state != 'available':
					raise UserError(
						_("Cannot create a checked-in stay for cage '%s' as it is currently '%s'.",
						  cage.name, cage.state))

		stays = super(VetBoardingStay, self).create(vals_list)

		# Update cage state after creation
		for stay in stays:
			if stay.state == 'checked_in':
				stay.cage_id.sudo().write({'state': 'occupied'})

		return stays

	def write(self, vals):
		"""Handle cage state updates on status changes"""
		# Store old states/cages for comparison
		old_data = {
			stay.id: {
				'cage_id': stay.cage_id,
				'state': stay.state
			} for stay in self
		}

		res = super(VetBoardingStay, self).write(vals)

		# Handle state/cage changes
		for stay in self:
			old_cage = old_data[stay.id]['cage_id']
			old_state = old_data[stay.id]['state']

			# State changed TO checked_in
			if stay.state == 'checked_in' and old_state != 'checked_in':
				if not stay.cage_id:
					raise UserError(_("Cannot check in without assigning a cage."))
				if stay.cage_id.state != 'available':
					raise UserError(
						_("Cannot check in to cage '%s' - it is %s.",
						  stay.cage_id.name, stay.cage_id.state))
				stay.cage_id.sudo().write({'state': 'occupied'})

				# Free old cage if changed
				if old_cage and old_cage != stay.cage_id:
					old_cage.sudo().write({'state': 'available'})

			# State changed FROM checked_in
			elif old_state == 'checked_in' and stay.state != 'checked_in':
				cage_to_free = old_cage or stay.cage_id
				if cage_to_free:
					# Check no other stays are using this cage
					other_stays = self.search_count([
						('cage_id', '=', cage_to_free.id),
						('state', '=', 'checked_in'),
						('id', '!=', stay.id)
					])
					if not other_stays:
						cage_to_free.sudo().write({'state': 'available'})

				# Set checkout time if checking out
				if stay.state == 'checked_out' and not stay.actual_check_out_datetime:
					stay.actual_check_out_datetime = fields.Datetime.now()

			# Cage changed while checked in
			elif stay.state == 'checked_in' and 'cage_id' in vals and old_cage != stay.cage_id:
				if not stay.cage_id:
					raise UserError(_("Cannot remove cage from checked-in stay."))
				if stay.cage_id.state != 'available':
					raise UserError(
						_("Cannot move to cage '%s' - it is %s.",
						  stay.cage_id.name, stay.cage_id.state))

				stay.cage_id.sudo().write({'state': 'occupied'})
				if old_cage:
					old_cage.sudo().write({'state': 'available'})

		return res

	# Actions
	def action_check_in(self):
		"""Check in the pet and link to daily encounter"""
		for stay in self.filtered(lambda s: s.state in ('draft', 'scheduled')):
			if not stay.vaccination_proof_received:
				raise UserError(_("Cannot check in without vaccination proof."))
			if not stay.consent_form_signed:
				raise UserError(_("Cannot check in without signed consent form."))

			if not stay.encounter_id:
				check_in_date = stay.check_in_datetime.date() if stay.check_in_datetime else fields.Date.context_today(
					stay)

				encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
					partner_id=stay.owner_id.id,
					patient_ids=[stay.pet_id.id],
					encounter_date=check_in_date,
					practitioner_id=False,
					room_id=False
				)
				stay.encounter_id = encounter.id

			stay.write({
				'state': 'checked_in',
				'check_in_datetime': fields.Datetime.now()
			})

			stay.message_post(
				body=_("Boarding check-in completed and linked to encounter %s", stay.encounter_id.name))

	def action_check_out(self):
		# Check permissions?
		# TODO: Check if billing is required/completed before check-out?
		for stay in self.filtered(lambda s: s.state == 'checked_in'):
			# Set actual check out time and state
			stay.write({
				'state': 'checked_out',
				'actual_check_out_datetime': fields.Datetime.now()  # Let write handle state change logic
			})
			# TODO: Trigger creation of pending billing items?
			self._create_boarding_billing_items()

	def action_cancel(self):
		"""Cancel the boarding stay"""
		for stay in self.filtered(lambda s: s.state not in ('checked_out', 'invoiced', 'cancelled')):
			if stay.state == 'checked_in' and stay.cage_id:
				stay.cage_id.sudo().write({'state': 'available'})
			stay.write({'state': 'cancelled'})

	def action_reset_to_draft(self):
		# Use with caution - may require resetting cage states manually if inconsistent
		for stay in self.filtered(lambda s: s.state == 'cancelled'):
			stay.write({'state': 'draft'})

	# --- Billing Logic ---
	def _create_boarding_billing_items(self):
		"""Create pending POS items for boarding stay and link to encounter"""
		self.ensure_one()

		if not self.boarding_product_id:
			boarding_product = self.env['product.product'].search([
				('product_sub_type_id.code', '=', 'BRD'),
				('active', '=', True),
				('sale_ok', '=', True)
			], limit=1)
			if boarding_product:
				self.boarding_product_id = boarding_product
			else:
				raise UserError(_("No boarding product configured. Please create a product with sub-type 'BRD'."))

		if not self.encounter_id:
			checkout_date = self.actual_check_out_datetime.date() if self.actual_check_out_datetime else fields.Date.context_today(
				self)

			encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
				partner_id=self.owner_id.id,
				patient_ids=[self.pet_id.id],
				encounter_date=checkout_date,
				practitioner_id=False,
				room_id=False
			)
			self.encounter_id = encounter.id

		pending_item = self.env['ths.pending.pos.item'].sudo().create({
			'partner_id': self.owner_id.id,
			'patient_ids': [Command.set([self.pet_id.id])],
			'product_id': self.boarding_product_id.id,
			'description': _("Boarding: %(pet)s - Cage %(cage)s (%(days)d days)",
							 pet=self.pet_id.name, cage=self.cage_id.name, days=self.duration_days),
			'qty': self.duration_days,
			# 'price_unit': self.daily_rate or self.boarding_product_id.list_price,
			'practitioner_id': False,
			'state': 'pending',
			'notes': _("Boarding Stay: %(ref)s", ref=self.name),
			'boarding_stay_id': self.id,
			'encounter_id': self.encounter_id.id,
		})

		self.message_post(
			body=_("Boarding billing item created and linked to encounter %s", self.encounter_id.name))
		return pending_item

	def action_view_pending_items(self):
		"""View related pending POS items"""
		self.ensure_one()
		return {
			'type': 'ir.actions.act_window',
			'name': _('Pending Billing Items'),
			'res_model': 'ths.pending.pos.item',
			'view_mode': 'list,form',
			'domain': [('boarding_stay_id', '=', self.id)],
			'context': {'create': False}
		}

	def action_view_encounter(self):
		"""View the daily encounter for this boarding stay"""
		self.ensure_one()
		if not self.encounter_id:
			return {}

		return {
			'name': _('Daily Encounter'),
			'type': 'ir.actions.act_window',
			'res_model': 'ths.medical.base.encounter',
			'view_mode': 'form',
			'res_id': self.encounter_id.id,
			'target': 'current'
		}

# TODO: Add boarding encounter daily care logging
# TODO: Implement boarding photo upload per encounter
# TODO: Add boarding feeding schedule integration
# TODO: Implement boarding exercise tracking
# TODO: Add boarding medication administration logging
# TODO: Implement boarding emergency contact notifications
# TODO: Add boarding pickup reminder system