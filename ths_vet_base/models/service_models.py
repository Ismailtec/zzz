# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)


class VetSpecies(models.Model):
	_name = 'vet.species'
	_description = 'Animal Species'

	sequence = fields.Integer(string="#", default=20)
	name = fields.Char(required=True, translate=True)
	color = fields.Integer(string="Color Index", default=10)
	breed_ids = fields.One2many('vet.breed', 'species_id', string='Breeds')
	image = fields.Image(string='Species Image', max_width=256, max_height=256)

	_sql_constraints = [('name_uniq', 'unique(name)', 'Species must be unique.')]

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if 'name' in vals:
				vals['name'] = vals['name'].strip().title()
		return super().create(vals_list)

	def write(self, vals):
		if 'name' in vals:
			vals['name'] = vals['name'].strip().title()
		return super().write(vals)


class VetBreed(models.Model):
	_name = 'vet.breed'
	_description = 'Animal Breed'

	name = fields.Char(required=True, translate=True)
	species_id = fields.Many2one('vet.species', string='Species', required=True, ondelete='restrict')
	sequence = fields.Integer(string="#", default=20)
	_sql_constraints = [('name_species_uniq', 'unique(name, species_id)', 'Breed name must be unique per species!')]

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if 'name' in vals:
				vals['name'] = vals['name'].strip().title()
		return super().create(vals_list)

	def write(self, vals):
		if 'name' in vals:
			vals['name'] = vals['name'].strip().title()
		return super().write(vals)


class VetBoardingCage(models.Model):
	_name = 'vet.boarding.cage'
	_description = 'Veterinary Boarding Cage/Enclosure'
	_order = 'name asc'

	name = fields.Char(string='Cage Name/Number', required=True, index=True)
	allowed_species_ids = fields.Many2many('vet.species', string='Allowed Species')
	notes = fields.Text(string='Notes/Description')
	state = fields.Selection([('available', 'Available'), ('occupied', 'Occupied'), ('maintenance', 'Maintenance'), ], string='Status', default='available', index=True,
							 required=True)
	active = fields.Boolean(default=True, index=True)
	current_stay_id = fields.Many2one('vet.boarding.stay', string='Current Stay', compute='_compute_current_stay', store=False, help="The current boarding occupying this cage.")
	current_occupant_display = fields.Char(string="Current Occupant", compute='_compute_current_stay', store=False)

	@api.depends('state')  # Recompute when state changes
	def _compute_current_stay(self):
		""" Find the active stay associated with this cage """
		active_stays = self.env['vet.boarding.stay'].search([
			('cage_id', 'in', self.ids),
			('state', '=', 'checked_in')  # Only show currently checked-in stays
		])
		stays_by_cage = {stay.cage_id.id: stay for stay in active_stays}

		for cage in self:
			stay = stays_by_cage.get(cage.id)
			cage.current_stay_id = stay.id if stay else False
			cage.current_occupant_display = f"{stay.patient_ids.name} ({stay.name})" if stay and stay.patient_ids else ""


class VetBoardingLog(models.Model):
	_name = 'vet.boarding.log'
	_description = 'Boarding Log Entry'
	_order = 'date desc'

	boarding_stay_id = fields.Many2one('vet.boarding.stay', string='Boarding Stay', required=True, ondelete='cascade')
	date = fields.Datetime(string='Log Date', default=fields.Datetime.now, required=True)
	log_type = fields.Selection([('feeding', 'Feeding'), ('medication', 'Medication'), ('exercise', 'Exercise'), ('note', 'Note')], string='Type', required=True)
	description = fields.Text(string='Description', required=True)
	user_id = fields.Many2one('res.users', string='Logged By', default=lambda self: self.env.user, readonly=True)

	@api.model
	def default_get(self, fields_list):
		res = super().default_get(fields_list)
		boarding_stay_id = self.env.context.get('default_boarding_stay_id')
		if boarding_stay_id:
			res['boarding_stay_id'] = boarding_stay_id
		return res


# class VetBoardingSchedule(models.Model):
# 	_name = 'vet.boarding.schedule'
# 	_description = 'Boarding Schedule Log'
# 	_order = 'scheduled_time'
#
# 	boarding_stay_id = fields.Many2one('vet.boarding.stay', string='Boarding Stay', required=True, ondelete='cascade')
# 	schedule_type = fields.Selection([('food', 'Food'), ('medication', 'Medication')], string='Type', required=True)
# 	scheduled_time = fields.Datetime(string='Scheduled Time', required=True)
# 	next_time = fields.Datetime(string='Next Time')
# 	notes = fields.Text(string='Instructions')
# 	done = fields.Boolean(string='Done', default=False)
# 	user_id = fields.Many2one('res.users', string='Responsible User', default=lambda self: self.env.user)
#
# 	@api.model
# 	def default_get(self, fields_list):
# 		res = super().default_get(fields_list)
# 		boarding_stay_id = self.env.context.get('default_boarding_stay_id')
# 		if boarding_stay_id:
# 			res['boarding_stay_id'] = boarding_stay_id
# 		return res


class VetBoardingStay(models.Model):
	_name = 'vet.boarding.stay'
	_description = 'Veterinary Boarding Stay'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'check_in_datetime desc, name'
	_rec_name = 'name'

	patient_ids = fields.Many2many('res.partner', 'vet_boarding_stay_patient_rel', 'boarding_id', 'patient_id', string='Pets', context={'is_pet': True, 'default_is_pet': True},
								   store=True, readonly=False, index=True, tracking=True, domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]")
	name = fields.Char(string='Boarding Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', required=True, index=True, ondelete='cascade', help="Parent encounter for this boarding stay.")
	cage_id = fields.Many2one('vet.boarding.cage', string='Assigned Cage', required=True, index=True, domain="[('state', '=', 'available')]", tracking=True)
	cage_domain = fields.Char(string='Cage Domain', compute='_compute_cage_domain', store=False, readonly=True, help="Dynamic domain for cage selection based on pet's species.")
	check_in_datetime = fields.Datetime(string='Check-in', default=fields.Datetime.now, tracking=True)
	expected_check_out_datetime = fields.Datetime(string='Expected Check-out', required=True, tracking=True)
	actual_check_out_datetime = fields.Datetime(string='Actual Check-out', readonly=True, copy=False, tracking=True)
	duration_days = fields.Integer(string="Duration (Days)", compute='_compute_duration_days', store=True, help="Calculated duration in days based on check-in and check-out.")
	state = fields.Selection(
		[('draft', 'Draft'), ('scheduled', 'Scheduled'), ('checked_in', 'Checked In'), ('checked_out', 'Checked Out'), ('invoiced', 'Invoiced/Paid'), ('cancelled', 'Cancelled')],
		string='Status', default='draft', index=True, required=True, tracking=True, copy=False)
	notes = fields.Text(string='Internal Boarding Notes')

	# Boarding Information
	vaccination_proof_received = fields.Boolean(string='Vaccination Proof Received?', tracking=True)
	medical_conditions = fields.Text(string='Medical Conditions / Allergies')
	routines_preferences_quirks = fields.Text(string='Routines & Preferences')
	owner_brought_food = fields.Boolean(string='Own Food Provided?', default=False)
	food_instructions = fields.Text(string='Feeding Instructions')
	owner_brought_medication = fields.Boolean(string='Own Medication Provided?', default=False)
	medication_instructions = fields.Text(string='Medication Instructions')
	consent_form_signed = fields.Boolean(string='Consent Form Signed?', default=False, tracking=True)
	boarding_log_ids = fields.One2many('vet.boarding.log', 'boarding_stay_id', string='Boarding Logs')
	# schedule_ids = fields.One2many('vet.boarding.schedule', 'boarding_stay_id', string='Schedules')

	# Billing
	encounter_line_ids = fields.One2many('vet.encounter.line', 'source_model', string='Encounter Lines', readonly=False)

	@api.depends('patient_ids.species_id')
	def _compute_cage_domain(self):
		""" Dynamically computes the domain for the 'cage_id' field. Filters available cages by state and, if a pet's species is selected, by allowed species. """
		for record in self:
			domain = [('state', '=', 'available')]
			if record.patient_ids and record.patient_ids.species_id:
				# Get all unique species IDs from all selected pets
				species_ids = record.patient_ids.species_id.ids
				domain.append(('allowed_species_ids', 'in', species_ids))
			record.cage_domain = str(domain)

	@api.depends('check_in_datetime', 'expected_check_out_datetime')
	def _compute_duration_days(self):
		""" Calculate stay duration. Needs careful handling of partial days. """
		for stay in self:
			if stay.check_in_datetime and stay.expected_check_out_datetime:
				# Simple difference in days, rounds down.
				delta = stay.expected_check_out_datetime.date() - stay.check_in_datetime.date()
				stay.duration_days = delta.days + 1
			else:
				stay.duration_days = 0

	@api.onchange('check_in_datetime')
	def _compute_expected_check_out_datetime_ui_validation(self):
		""" UI sync for expected_check_out_datetime to be atleast = check_in_datetime + 1. """
		if self.check_in_datetime:
			self.expected_check_out_datetime = self.check_in_datetime + timedelta(hours=2)

	# @api.onchange('food_instructions', 'medication_instructions', 'duration_days')
	# def _onchange_generate_schedules(self):
	# 	"""Generate schedules from instructions and duration"""
	# 	self.schedule_ids = [(5, 0, 0)]  # Clear
	# 	if self.duration_days > 0 and (self.food_instructions or self.medication_instructions):
	# 		start_date = self.check_in_datetime.date() if self.check_in_datetime else fields.Date.today()
	# 		schedule_commands = []
	#
	# 		for day in range(self.duration_days):
	# 			date = start_date + timedelta(days=day)
	#
	# 			if self.food_instructions:
	# 				schedule_commands.append((0, 0, {
	# 					'schedule_type': 'food',
	# 					'scheduled_time': fields.Datetime.from_string(f"{date} 08:00:00"),
	# 					'notes': self.food_instructions,
	# 					'next_time': fields.Datetime.from_string(f"{date} 20:00:00") if day < self.duration_days - 1 else False
	# 				}))
	#
	# 			if self.medication_instructions:
	# 				schedule_commands.append((0, 0, {
	# 					'schedule_type': 'medication',
	# 					'scheduled_time': fields.Datetime.from_string(f"{date} 09:00:00"),
	# 					'notes': self.medication_instructions,
	# 					'next_time': fields.Datetime.from_string(f"{date} 21:00:00") if day < self.duration_days - 1 else False
	# 				}))
	#
	# 			self.schedule_ids = schedule_commands

	# @api.constrains('check_in_datetime', 'expected_check_out_datetime')
	# def _check_dates(self):
	# 	"""Auto-set expected checkout to be at least 4 hours after check-in"""
	# 	if self.check_in_datetime:
	# 		# Add 4 hours minimum
	# 		checkout_time = self.check_in_datetime + timedelta(hours=4)
	#
	# 		# Optional: Round to next business hour (9 AM - 6 PM)
	# 		if checkout_time.hour < 9:
	# 			checkout_time = checkout_time.replace(hour=9, minute=0, second=0)
	# 		elif checkout_time.hour > 18:
	# 			checkout_time = checkout_time.replace(hour=9, minute=0, second=0) + timedelta(days=1)
	#
	# 		self.expected_check_out_datetime = checkout_time
	#
	# 	for stay in self:
	# 		if stay.check_in_datetime and stay.expected_check_out_datetime and stay.expected_check_out_datetime < stay.check_in_datetime:
	# 			raise ValidationError(_("Expected Check-out date cannot be before Check-in date."))
	# 		if stay.actual_check_out_datetime and stay.check_in_datetime and stay.actual_check_out_datetime < stay.check_in_datetime:
	# 			raise ValidationError(_("Actual Check-out date cannot be before Check-in date."))

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
					_("Cage %s is already booked during this period.", stay.cage_id.name))

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

		return res

	@api.model_create_multi
	def create(self, vals_list):
		"""Assign sequence on creation"""
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('vet.boarding.stay') or _('New')

			if not vals.get('encounter_id') and vals.get('partner_id'):
				patient_ids = []
				if 'patient_ids' in vals and vals['patient_ids']:
					# Extract patient IDs from Many2many commands
					for command in vals['patient_ids']:
						if command[0] == 6:  # Replace command
							patient_ids = command[2]
						elif command[0] == 4:  # Link command
							patient_ids.append(command[1])

				check_in_date = fields.Date.today()
				if vals.get('check_in_datetime'):
					check_in_date = fields.Datetime.from_string(vals['check_in_datetime']).date()

				encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
					partner_id=vals['partner_id'],
					patient_ids=patient_ids,
					encounter_date=check_in_date,
					practitioner_id=False,
					room_id=False,
				)
				vals['encounter_id'] = encounter.id

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

				encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
					partner_id=stay.partner_id.id,
					patient_ids=stay.patient_ids.id,
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
			if stay.cage_id:
				stay.cage_id.sudo().write({'state': 'available'})

	def action_view_encounter(self):
		"""View the daily encounter for this boarding stay"""
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

	def action_view_encounter_lines(self):
		"""View related pending POS items"""
		self.ensure_one()
		return {
			'type': 'ir.actions.act_window',
			'name': _('Encounter Lines'),
			'res_model': 'vet.encounter.line',
			'view_mode': 'list,form',
			'domain': [('encounter_line_ids', '=', self.encounter_line_ids)],
			'context': {'create': False}
		}

	def action_view_documents(self):
		"""Smart button to view/upload documents for boarding records"""
		return self.action_view_documents_model(
			'ths_vet_base.documents_boarding_folder',
			'Boarding',
			'ths_vet_base.documents_tag_boarding'
		)

	@api.model
	def _cron_boarding_pickup_reminders(self):
		"""Cron to send pickup reminders 1 day before expected checkout"""
		tomorrow = fields.Date.today() + timedelta(days=1)
		stays = self.search([
			('state', '=', 'checked_in'),
			('expected_check_out_datetime', '>=', tomorrow),
			('expected_check_out_datetime', '<', tomorrow + timedelta(days=1))
		])
		template = self.env.ref('ths_vet_base.email_template_boarding_pickup_reminder', raise_if_not_found=False)
		if not template:
			return
		for stay in stays:
			try:
				template.send_mail(stay.id, force_send=True)
				stay.message_post(body=_("Pickup reminder sent to owner."))
			except Exception as e:
				_logger.error("Failed to send reminder for stay %s: %s", stay.id, e)

# @api.model
# def _cron_schedule_reminders(self):
# 	"""Remind users about upcoming food/medication schedules"""
# 	upcoming = self.env['vet.boarding.schedule'].search([
# 		('scheduled_time', '<', fields.Datetime.now() + timedelta(hours=1)),
# 		('done', '=', False)
# 	])
# 	for schedule in upcoming:
# 		schedule.boarding_stay_id.activity_schedule(
# 			'mail.mail_activity_data_todo',
# 			date_deadline=schedule.scheduled_time,
# 			summary=_('%s Schedule Reminder') % schedule.schedule_type.capitalize(),
# 			note=schedule.notes,
# 			user_id=schedule.user_id.id
# 		)


# TODO: Implement boarding photo upload per encounter
# TODO: Add boarding medication administration logging
# TODO: Add relation to checklist lines (One2many)

class VetPetMembership(models.Model):
	_name = 'vet.pet.membership'
	_description = 'Pet Membership Management'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'valid_from desc, name desc'

	patient_ids = fields.Many2many('res.partner', 'pet_membership_patient_rel', 'membership_id', 'patient_id', string='Pets', readonly=False, index=True,
								   context={'is_pet': True, 'default_is_pet': True}, domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]")
	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', readonly=True, copy=False, index=True, ondelete='set null', store=True)
	# encounter_line_ids = fields.One2many('vet.encounter.line', 'source_model', string='Encounter Lines', readonly=True)
	name = fields.Char(string='Membership Code', required=True, copy=False, readonly=True, default=lambda self: _('New'))
	membership_service_id = fields.Many2one('product.product', string='Membership Service', required=True, tracking=True, store=True)
	valid_from = fields.Date(string='Valid From', required=True, default=fields.Date.today, tracking=True)
	valid_to = fields.Date(string='Valid To', readonly=True, compute='_compute_valid_to', store=True)
	state = fields.Selection([('draft', 'Draft'), ('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled')], compute='_compute_membership_state', store=True,
							 string='Status', default='draft', required=True, tracking=True)
	is_paid = fields.Boolean(string='Paid', default=False, tracking=True)
	is_expiring_soon = fields.Boolean(string="Expiring Soon", compute='_compute_is_expiring_soon', store=True, help="Memberships is expiring within a month.")
	notes = fields.Text(string='Notes')

	@api.depends('valid_from', 'membership_service_id.ths_membership_duration')
	def _compute_valid_to(self):
		for membership in self:
			if membership.valid_from and membership.membership_service_id.ths_membership_duration:
				membership.valid_to = membership.valid_from + relativedelta(months=membership.membership_service_id.ths_membership_duration)
			else:
				membership.valid_to = False

	@api.depends('valid_from', 'valid_to')
	def _compute_membership_state(self):
		""" Compute the state of the membership """
		today = fields.Date.today()
		for membership in self:
			if membership.state == 'cancelled':
				continue

			if membership.valid_from and membership.valid_to:
				if membership.valid_from <= today <= membership.valid_to:
					membership.state = 'active'
				elif membership.valid_to < today:
					membership.state = 'expired'
				else:
					membership.state = 'draft'
			else:
				membership.state = 'draft'

	@api.depends('valid_to', 'state')
	def _compute_is_expiring_soon(self):
		""" Computes if the membership is active and expires within the next month. """
		today = fields.Date.today()
		one_month_from_now = today + relativedelta(months=1)
		for membership in self:
			if membership.state == 'active' and membership.valid_to and today <= membership.valid_to <= one_month_from_now:
				membership.is_expiring_soon = True
			else:
				membership.is_expiring_soon = False

	@api.constrains('valid_from', 'valid_to')
	def _check_validity_dates(self):
		"""Validate that the 'Valid From' date is not after 'Valid To' date."""
		for record in self:
			if record.valid_from and record.valid_to and record.valid_from > record.valid_to:
				raise ValidationError(_("The 'Valid From' date cannot be after the 'Valid To' date."))

	@api.constrains('state', 'patient_ids')
	def _check_one_active_membership_per_pet(self):
		""" Ensure each pet linked to this membership has only one active membership. """
		for record in self:
			if record.state == 'active' and record.patient_ids:
				for pet in record.patient_ids:
					existing_active_memberships = self.search([
						('patient_ids', 'in', pet.id),
						('state', '=', 'active'),
						('id', '!=', record.id)
					])
					if existing_active_memberships:
						raise ValidationError(_(
							"The pet '%s' already has an active membership: '%s'. "
							"A pet cannot have more than one active membership.",
							pet.display_name,
							existing_active_memberships[0].display_name
						))

	@api.constrains('patient_ids')
	def _check_single_pet_for_membership(self):
		""" Ensures that each membership record has only one pet in its patient_ids M2M field """
		for record in self:
			if len(record.patient_ids) > 1:
				raise ValidationError(_("A membership record must be associated with only one pet."))
			if not record.patient_ids:
				raise ValidationError(_("A membership record must be associated with at least one pet."))

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('vet.pet.membership') or _('New')

			patient_ids_command = vals.get('patient_ids')
			patient_ids = []
			if patient_ids_command:
				for command in patient_ids_command:
					if command[0] == 6:
						patient_ids.extend(command[2])
					elif command[0] == 4:
						patient_ids.append(command[1])

			if not patient_ids:
				raise UserError(_("Pet(s) are required to create a membership."))
			if len(patient_ids) > 1:
				raise UserError(_("A membership can only be created for one pet at a time."))

			primary_patient = self.env['res.partner'].browse(patient_ids[0])
			if not primary_patient.exists():
				raise UserError(_("Pet with ID %s does not exist.", patient_ids[0]))

			partner_id = vals.get('partner_id')
			if not partner_id:
				partner_id = primary_patient.pet_owner_id.id
				vals['partner_id'] = partner_id

			if not partner_id:
				raise UserError(_("Owner (Partner ID) is required to create membership if it cannot be derived from pet."))

			if not vals.get('encounter_id'):
				encounter_date = fields.Date.today()
				encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
					partner_id=partner_id,
					patient_ids=patient_ids,
					encounter_date=encounter_date,
					practitioner_id=False,
					room_id=False
				)
				vals['encounter_id'] = encounter.id

		return super().create(vals_list)

	def unlink(self):
		for record in self:
			if record.state != 'draft':
				raise UserError(_("You can only delete memberships in draft state."))
		return super().unlink()

	def action_start_membership(self):
		"""Start membership and create billing line if not paid"""
		for rec in self:
			if rec.state == 'draft':
				rec.write({'state': 'active'})
				if not rec.is_paid and rec.encounter_id and rec.membership_service_id:
					self.env['vet.encounter.line'].create({
						'encounter_id': rec.encounter_id.id,
						'partner_id': rec.partner_id.id,
						'patient_ids': [(6, 0, rec.patient_ids.ids)],
						'product_id': rec.membership_service_id.id,
						'qty': 1.0,
						'payment_status': 'pending',
						'source_model': 'vet.pet.membership',
						'notes': _("Membership Activation: %s") % rec.name
					})
					rec.message_post(body=_("Membership started; billing line created if unpaid."))
				else:
					rec.message_post(body=_("Membership started."))
			elif rec.state == 'active':
				rec.message_post(body=_("Membership is already active."))
			elif rec.state == 'expired':
				raise UserError(_("Cannot start an expired membership. Please renew it."))
			elif rec.state == 'cancelled':
				raise UserError(_("Cannot start a cancelled membership. Please create a new one."))

	def action_reset_to_draft(self):
		"""Reset membership state to draft. Useful for correction."""
		for rec in self:
			if rec.state in ['active', 'expired', 'cancelled']:
				rec.write({'state': 'draft'})
				rec.message_post(body=_("Membership reset to draft."))
			else:
				rec.message_post(body=_("Membership is already in draft state."))

	def action_renew(self):
		"""Renew membership by creating new record with extended dates"""
		self.ensure_one()
		if self.state != 'expired':
			raise UserError(_("Can only renew expired memberships."))

		new_vals = {
			'partner_id': self.partner_id.id,
			'patient_ids': [(6, 0, self.patient_ids.ids)],
			'membership_service_id': self.membership_service_id.id,
			'valid_from': fields.Date.today(),
			'state': 'draft',
			'notes': _("Renewed from %s (Original Membership ID: %s)") % (self.name, self.id)
		}
		new_membership = self.create(new_vals)
		self.message_post(body=_("Membership renewed as %s") % new_membership.name)
		return {
			'type': 'ir.actions.act_window',
			'name': _('Renewed Membership'),
			'res_model': 'vet.pet.membership',
			'view_mode': 'form',
			'res_id': new_membership.id,
			'target': 'current'
		}

	def action_cancel_membership(self):
		"""Action to explicitly cancel the membership."""
		for record in self:
			if record.state not in ('cancelled', 'expired'):
				record.write({'state': 'cancelled'})
				record.message_post(body=_("Membership cancelled by user."))
			else:
				raise UserError(_("Cannot cancel an already %s membership.") % dict(self._fields['state'].selection).get(record.state))

	@api.model
	def action_view_expiring_memberships(self):
		"""Action to open a view of memberships expiring soon."""
		today = fields.Date.today()
		expiring_domain = [
			('state', 'in', ('active', 'expired')),
			('valid_to', '>=', today),
			('valid_to', '<=', today + relativedelta(months=1))
		]
		return {
			'name': _('Expiring Memberships'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.pet.membership',
			'view_mode': 'list,form',
			'domain': expiring_domain,
			'context': {'create': False}
		}

	@api.model
	def _cron_update_membership_status(self):
		""" Cron job to automatically update membership statuses based on dates """
		today = fields.Date.today()

		draft_to_active = self.search([
			('state', '=', 'draft'),
			('valid_from', '<=', today),
		])
		for membership in draft_to_active:
			try:
				membership.state = 'active'
				membership.message_post(body=_("Membership automatically activated as of %s.", today))
			except ValidationError as e:
				# _logger.warning("Cron: Failed to activate membership %s for pet(s) %s: %s",
				# 				membership.name, ', '.join(membership.patient_ids.mapped('display_name')), e.args[0])
				membership.message_post(body=_("Cron activation failed: %s", e.args[0]))
			except Exception as e:
				_logger.error("Unexpected error during cron activation of membership %s: %s", membership.name, e)

		active_to_expired = self.search([
			('state', '=', 'active'),
			('valid_to', '<', today),
		])
		for membership in active_to_expired:
			membership.state = 'expired'
			membership.message_post(body=_("Membership automatically expired as of %s.", today))

	def action_notify_expiry(self):
		"""Send expiry notification for the current membership via email and WhatsApp (Odoo Enterprise)."""
		self.ensure_one()

		# Email Notification
		email_template = self.env.ref('ths_vet_base.email_template_membership_expiry', raise_if_not_found=False)
		if email_template:
			# Check if owner and email exist
			if not self.partner_id or not self.partner_id.email:
				_logger.warning("Cannot send expiry email for membership %s: Owner or email address is missing.", self.name)
				self.message_post(body=_("Could not send expiry email: Owner or email missing."))
			else:
				try:
					email_template.send_mail(self.id, force_send=True, email_values={'email_to': self.partner_id.email})
					self.message_post(body=_("Expiry email notification sent to %s.", self.partner_id.email))
				except Exception as e:
					_logger.error("Failed to send expiry email for membership %s: %s", self.name, e)
					self.message_post(body=_("Failed to send expiry email: %s", str(e)))
		else:
			_logger.warning("Email template 'ths_vet_base.email_template_membership_expiry' not found for membership expiry notification.")

		whatsapp_mail_template = self.env.ref('ths_vet_base.whatsapp_template_membership_expiry', raise_if_not_found=False)
		if whatsapp_mail_template:
			if not self.partner_id or not self.partner_id.mobile:
				# _logger.warning("Cannot send expiry WhatsApp for membership %s: Owner or mobile number is missing.", self.name)
				self.message_post(body=_("Could not send expiry WhatsApp: Owner or mobile missing."))
			else:
				try:
					whatsapp_composer = self.env['whatsapp.composer'].with_context({'active_id': self.id}).create(
						{
							'phone': self.partner_id.mobile or self.partner_id.phone if self.partner_id.mobile or self.partner_id.phone else None,
							'wa_template_id': whatsapp_mail_template.id,
							'res_model': 'vet.pet.membership',
						}
					)
					whatsapp_composer._send_whatsapp_template()

					self.message_post(body=_("Expiry WhatsApp notification sent to %s.", self.partner_id.mobile))
				except Exception as e:
					_logger.error("Failed to send expiry WhatsApp for membership %s: %s", self.name, e)
					self.message_post(body=_("Failed to send expiry WhatsApp: %s", str(e)))
		else:
			_logger.warning("WhatsApp template 'ths_vet_base.whatsapp_template_membership_expiry_mail' not found for membership expiry notification.")


# TODO: Add config check for email vs WhatsApp preference
# TODO: Add integration with billing/invoicing


class VetParkCheckin(models.Model):
	_name = 'vet.park.checkin'
	_description = 'Park Check-in Record'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'checkin_time desc, name'
	_rec_name = 'name'

	patient_ids = fields.Many2many('res.partner', 'park_checkin_patient_rel', 'checkin_id', 'patient_id', string='Pets', store=True, readonly=False,
								   index=True, tracking=True, context={'is_pet': True, 'default_is_pet': True, 'show_valid_park_members_only': True},
								   domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]")
	encounter_id = fields.Many2one('vet.encounter.header', string='Daily Encounter', readonly=True, copy=False, index=True, ondelete='set null',
								   help="Encounter this park visit belongs to")
	name = fields.Char(string='Check-in Ref', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
	expected_visit_hours = fields.Float(string='Expected Visit Time (Hours)', default=1.0, help="Expected duration of the park visit in hours. Minimum 1 hour.")
	checkin_time = fields.Datetime(string='Check-in Time', required=True, default=fields.Datetime.now, tracking=True)
	checkout_time = fields.Datetime(string='Check-out Time', tracking=True)
	duration_hours = fields.Float(string='Duration (Hours)', compute='_compute_duration', store=True, help="Duration of park visit in hours")
	_has_valid_membership_computed = fields.Boolean(string='All Pets Membership Valid', compute='_compute_has_valid_membership_check', store=False,
													help="Whether all selected pets on this check-in have valid membership for park access.")
	has_valid_membership = fields.Boolean(string='Pets Membership Valid', compute='_compute_has_valid_membership_check', store=False,
										  help="If all selected pets have valid membership.")
	state = fields.Selection([
		('draft', 'Draft'), ('checked_in', 'Checked In'), ('checked_out', 'Checked Out'), ('overdue', 'Overdue')], string='Status', default='draft', required=True, tracking=True)
	notes = fields.Text(string='Visit Notes')

	# --- Compute Methods ---
	@api.depends('checkin_time', 'checkout_time')
	def _compute_duration(self):
		"""Calculate visit duration in hours"""
		for record in self:
			if record.checkin_time and record.checkout_time:
				delta = record.checkout_time - record.checkin_time
				record.duration_hours = delta.total_seconds() / 3600.0
			else:
				record.duration_hours = 0.0

	@api.depends('patient_ids')
	def _compute_has_valid_membership_check(self):
		""" Determines if ALL selected pets in this check-in have a valid park membership. """
		today = fields.Date.today()
		for record in self:
			if not record.patient_ids:
				record.has_valid_membership = False
				continue

			all_pets_valid = True
			for pet in record.patient_ids:
				active_memberships = self.env['vet.pet.membership'].search([
					('patient_ids', 'in', pet.id),
					('state', '=', 'active'),
					('valid_from', '<=', today),
					('valid_to', '>=', today)
				], limit=1)

				if not active_memberships:
					all_pets_valid = False
					break

			record.has_valid_membership = all_pets_valid

	# --- Onchange Methods ---
	@api.onchange('checkin_time', 'expected_visit_hours')
	def _onchange_checkin_time_calculate_checkout(self):
		"""Auto-calculate checkout time based on checkin + expected hours (minimum 1 hour)"""
		if self.checkin_time:
			hours_to_add = max(self.expected_visit_hours or 1.0, 1.0)

			# Calculate checkout time
			self.checkout_time = self.checkin_time + timedelta(hours=hours_to_add)

	# --- Constraints ---
	@api.constrains('patient_ids', 'state')
	def _check_membership_access_on_checkin(self):
		"""Validate membership before allowing check-in to 'checked_in' state."""
		for record in self:
			if record.state == 'checked_in' and record.patient_ids:
				if not record.has_valid_membership:
					invalid_pets_names = []
					today = fields.Date.today()
					for pet in record.patient_ids:
						active_memberships = self.env['vet.pet.membership'].search([
							('patient_ids', 'in', pet.id),
							('state', '=', 'active'),
							('valid_from', '<=', today),
							('valid_to', '>=', today)
						], limit=1)
						if not active_memberships:
							invalid_pets_names.append(pet.name)
					if invalid_pets_names:
						raise ValidationError(_(
							"One or more selected pets do not have a valid active membership for today: %s",
							', '.join(invalid_pets_names)
						))

	@api.constrains('checkin_time', 'checkout_time')
	def _check_times(self):
		"""Validate check-in/check-out times: checkout must be after check-in."""
		for record in self:
			if record.checkin_time and record.checkout_time and record.checkout_time <= record.checkin_time:
				raise ValidationError(_("Check-out time must be after check-in time."))

	# --- CRUD Methods ---
	@api.model
	def default_get(self, fields_list):
		"""Set default values from encounter context or current time."""
		res = super().default_get(fields_list)

		encounter_id = self.env.context.get('default_encounter_id')
		if encounter_id:
			encounter = self.env['vet.encounter.header'].browse(encounter_id)
			if encounter.exists():
				res['encounter_id'] = encounter.id
				res['partner_id'] = encounter.partner_id.id
				if 'patient_ids' in fields_list and encounter.patient_ids:
					today = fields.Date.today()
					valid_membership_pets_ids = self.env['vet.pet.membership'].search([
						('patient_ids', 'in', encounter.patient_ids.ids),
						('state', '=', 'active'),
						('valid_from', '<=', today),
						('valid_to', '>=', today)
					]).mapped('patient_ids').ids

					res['patient_ids'] = [(6, 0, list(set(valid_membership_pets_ids)))]
				res['checkin_time'] = fields.Datetime.now()
		else:
			if 'checkin_time' in fields_list:
				res['checkin_time'] = fields.Datetime.now()
		return res

	@api.model_create_multi
	def create(self, vals_list):
		"""Override to assign sequence, handle encounter creation, and set initial state."""
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('park.checkin') or _('New')

			partner_id = vals.get('partner_id')
			patient_ids_command = vals.get('patient_ids')

			patient_ids = []
			if patient_ids_command:
				for cmd in patient_ids_command:
					if cmd[0] == 6:
						patient_ids.extend(cmd[2])
					elif cmd[0] == 4:
						patient_ids.append(cmd[1])

			if partner_id and patient_ids:
				checkin_time_val = vals.get('checkin_time', fields.Datetime.now())
				encounter_date = fields.Datetime.to_datetime(checkin_time_val).date()

				encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
					partner_id=partner_id,
					patient_ids=patient_ids,
					encounter_date=encounter_date,
					practitioner_id=False,
					room_id=False
				)
				vals['encounter_id'] = encounter.id

			if vals.get('patient_ids') and not vals.get('state'):
				vals['state'] = 'checked_in'
				if not vals.get('checkin_time'):
					vals['checkin_time'] = fields.Datetime.now()

		checkins = super().create(vals_list)

		for checkin in checkins:
			if checkin.state == 'checked_in':
				message_body = _("Checked In to park at %s. Linked to encounter %s.",
								 checkin.checkin_time.strftime('%Y-%m-%d %H:%M'),
								 checkin.encounter_id.name if checkin.encounter_id else _("N/A"))
			else:
				message_body = _("Park visit created. Linked to encounter %s.",
								 checkin.encounter_id.name if checkin.encounter_id else _("N/A"))
			checkin.message_post(body=message_body)

		return checkins

	@api.model
	def _get_checkin_domain_by_context(self):
		domain = []
		date_filter = self.env.context.get('search_checkin_time_range')
		today = fields.Date.context_today(self)

		if date_filter == 'today':
			domain += [
				('checkin_time', '>=', fields.Datetime.to_datetime(f"{today} 00:00:00")),
				('checkin_time', '<=', fields.Datetime.to_datetime(f"{today} 23:59:59")),
			]

		elif date_filter == 'this_week':
			start_week = today - timedelta(days=today.weekday())
			end_week = start_week + timedelta(days=6)
			domain += [
				('checkin_time', '>=', fields.Datetime.to_datetime(f"{start_week} 00:00:00")),
				('checkin_time', '<=', fields.Datetime.to_datetime(f"{end_week} 23:59:59")),
			]

		elif date_filter == 'last_week':
			start_last_week = today - timedelta(days=today.weekday() + 7)
			end_last_week = start_last_week + timedelta(days=6)
			domain += [
				('checkin_time', '>=', fields.Datetime.to_datetime(f"{start_last_week} 00:00:00")),
				('checkin_time', '<=', fields.Datetime.to_datetime(f"{end_last_week} 23:59:59")),
			]

		return domain

	# --- Actions ---
	def action_checkin(self):
		for checkin in self.filtered(lambda c: c.state == 'draft'):
			if not checkin.patient_ids:
				raise ValidationError(_("You Can't check in without a Pet."))

			checkin.write({
				'checkin_time': fields.Datetime.now(),
				'state': 'checked_in'
			})
			checkin.message_post(body=_("Checked In to park at %s", checkin.checkin_time))

	def action_checkout(self):
		"""Check out from park"""
		for checkin in self.filtered(lambda c: c.state == 'checked_in'):
			checkin.write({
				'checkout_time': fields.Datetime.now(),
				'state': 'checked_out'
			})
			checkin.message_post(body=_("Checked out from park after %.2f hours", checkin.duration_hours))

	def action_extend_visit(self):
		"""Extend park visit (reset checkout) with 12-hour validation """
		now = fields.Datetime.now()
		twelve_hours_ago = now - timedelta(hours=12)

		for checkin in self.filtered(lambda c: c.state == 'checked_out'):
			if checkin.checkout_time and checkin.checkout_time < twelve_hours_ago:
				hours_ago = (now - checkin.checkout_time).total_seconds() / 3600
				raise UserError(
					_("Cannot extend park visit for %s.\n\n"
					  "Visit was checked out %.1f hours ago (more than 12 hours).\n"
					  "Please create a new park visit instead.") %
					(', '.join(checkin.patient_ids.mapped('name')), hours_ago)
				)

			checkin.write({
				'checkout_time': False,
				'state': 'checked_in'
			})

			checkin.message_post(
				body=_("Park visit extended - checkout time reset, status changed to checked in")
			)

	def _is_checked_out(self):
		"""Check if checkout time passed but state is not checked_out - mark as overdue"""
		self.ensure_one()
		if self.checkout_time and self.state != 'checked_out':
			now = fields.Datetime.now()
			if now > self.checkout_time:
				# Auto-update to overdue if checkout time has passed
				self.state = 'overdue'
				return True
		return self.state == 'checked_out'

	def action_reset_to_draft(self):
		for checkin in self.filtered(lambda c: c.state in ('checked_in', 'checked_out', 'overdue')):
			checkin.write({
				'state': 'draft',
				'checkin_time': False,
				'checkout_time': False
			})
			checkin.message_post(body=_("Check-in record reset to draft by user."))

	def action_view_encounter(self):
		"""View the daily encounter for this park visit"""
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

	def action_view_pet_memberships(self):
		"""View memberships for pets in this check-in"""
		self.ensure_one()
		if not self.patient_ids:
			return {}

		return {
			'name': _('Pet Memberships'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.pet.membership',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', self.patient_ids.ids)],
			'context': {
				'default_partner_id': self.partner_id.id,
				'default_patient_ids': [(6, 0, self.patient_ids.ids)] if self.patient_ids else False,
				'search_default_filter_active': 1,
			}
		}

	def action_view_documents(self):
		"""Smart button to view/upload documents for park records"""
		return self.action_view_documents_model(
			'ths_vet_base.documents_park_folder',
			'Park/Membership',
			'ths_vet_base.documents_tag_park'
		)

	@api.model
	def _cron_mark_overdue_visits(self):
		"""Cron job to automatically mark overdue park visits"""
		now = fields.Datetime.now()
		overdue_visits = self.search([
			('checkout_time', '<', now),
			('state', 'in', ['draft', 'checked_in'])
		])

		for visit in overdue_visits:
			visit.state = 'overdue'
			visit.message_post(
				body=_("Visit marked as overdue - checkout time was %s") % visit.checkout_time.strftime('%Y-%m-%d %H:%M:%S'),
				message_type='notification'
			)


# TODO: Add park capacity management per time slot
# TODO: Implement park activity tracking per pet
# TODO: Add park social interaction logging
# TODO: Implement park incident reporting system
# TODO: Add park weather condition tracking
# TODO: Implement park usage analytics per member
# TODO: Add park equipment usage tracking
# TODO: Implement park group activity coordination
# TODO: Add membership expiration warnings
# TODO: Add membership usage tracking per visit


class VetParkReportWizard(models.TransientModel):
	_name = 'vet.park.report.wizard'
	_description = 'Park Usage Report Wizard'

	date_from = fields.Date(string='From Date', required=True, default=fields.Date.today)
	date_to = fields.Date(string='To Date', required=True, default=fields.Date.today)
	patient_ids = fields.Many2many('res.partner', string='Pets', domain="[('is_pet', '=', True), ('pet_owner_id', '=?', pet_owner_id)]")
	pet_owner_id = fields.Many2one('res.partner', string='Pet Owner', domain="[('is_pet_owner', '=', True)]")

	def generate_report(self):
		domain = [
			('checkin_time', '>=', self.date_from),
			('checkin_time', '<=', self.date_to + timedelta(days=1)),
			('state', '=', 'checked_out')
		]
		if self.patient_ids:
			domain.append(('patient_ids', 'in', self.patient_ids.ids))
		if self.pet_owner_id:
			domain.append(('partner_id', '=', self.pet_owner_id.id))
		checkins = self.env['vet.park.checkin'].search(domain)
		data = {'date_from': self.date_from, 'date_to': self.date_to}
		report_action = self.env.ref('ths_vet_base.action_report_park_usage').report_action(checkins.ids, data=data, config=False)
		report_action.update({'close_on_report_download': True})
		return report_action


class VetVaccination(models.Model):
	_name = 'vet.vaccination'
	_description = 'Pet Vaccination Record'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'date desc, id desc'
	_rec_name = 'vaccine_type_id'

	patient_ids = fields.Many2many('res.partner', 'vet_vaccination_patient_rel', 'vaccination_id', 'patient_id', string='Pets', context={'is_pet': True, 'default_is_pet': True},
								   store=True, readonly=False, index=True, tracking=True, domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]")
	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', required=True, index=True, ondelete='cascade', help="Encounter for this vaccination.")
	encounter_line_ids = fields.One2many('vet.encounter.line', 'source_model', string='Encounter Lines', readonly=True)

	vaccine_type_id = fields.Many2one('vet.vaccine.type', string='Vaccine Type', required=True, tracking=True)
	date = fields.Date(string='Vaccination Date', required=True, default=fields.Date.context_today, tracking=True)
	expiry_date = fields.Date(string='Expiry Date', compute='_compute_expiry_date', store=True, readonly=False, tracking=True)
	batch_number = fields.Char(string='Batch/Lot Number', tracking=True)
	clinic_name = fields.Char(string='Clinic/Hospital Name', default=lambda self: self.env.company.name)
	# photo = fields.Binary(string='Photo', attachment=True)
	notes = fields.Text(string='Notes')

	# Status tracking
	is_expired = fields.Boolean(string='Expired', compute='_compute_is_expired', store=True)
	days_until_expiry = fields.Integer(string='Days Until Expiry', compute='_compute_days_until_expiry', store=True)

	@api.depends('date', 'vaccine_type_id.validity_months')
	def _compute_expiry_date(self):
		"""Calculate expiry date based on vaccine type validity"""
		for record in self:
			if record.date and record.vaccine_type_id and record.vaccine_type_id.validity_months:
				record.expiry_date = record.date + relativedelta(months=record.vaccine_type_id.validity_months)
			else:
				record.expiry_date = False

	@api.depends('expiry_date')
	def _compute_is_expired(self):
		"""Check if vaccination is expired"""
		today = fields.Date.context_today(self)
		for record in self:
			record.is_expired = bool(record.expiry_date and record.expiry_date < today)

	@api.depends('expiry_date')
	def _compute_days_until_expiry(self):
		"""Calculate days until expiry"""
		today = fields.Date.context_today(self)
		for record in self:
			if record.expiry_date:
				delta = record.expiry_date - today
				record.days_until_expiry = delta.days
			else:
				record.days_until_expiry = 0

	@api.constrains('date', 'expiry_date')
	def _check_dates(self):
		"""Ensure expiry date is after vaccination date"""
		for record in self:
			if record.date and record.expiry_date and record.expiry_date <= record.date:
				raise ValidationError(_("Expiry date must be after vaccination date."))

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
				res['date'] = fields.Date.context_today(self)

		return res

	@api.model_create_multi
	def create(self, vals_list):
		"""Override to link vaccinations to daily encounters before creation"""
		for vals in vals_list:
			# Create encounter BEFORE record creation if not provided
			if not vals.get('encounter_id') and vals.get('partner_id'):
				patient_id_list = []
				if 'patient_ids' in vals and vals['patient_ids']:
					# Extract patient IDs from Many2many commands
					for command in vals['patient_ids']:
						if command[0] == 6:  # Replace command
							patient_id_list = command[2]
						elif command[0] == 4:  # Link command
							patient_id_list.append(command[1])  # This is an ID

				vaccination_date = vals.get('date', fields.Date.today())
				encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
					partner_id=vals['partner_id'],
					patient_ids=patient_id_list,
					encounter_date=vaccination_date,
					practitioner_id=self.practitioner_id.id if self.practitioner_id else None,
					room_id=False
				)
				vals['encounter_id'] = encounter.id

		vaccinations = super().create(vals_list)

		# Schedule reminders after creation
		for vaccination in vaccinations:
			vaccination._schedule_vaccination_reminder()

			# if vaccination.photo and vaccination.patient_ids:
			# 	first_pet = vaccination.patient_ids[0]
			# 	attach = self.env['ir.attachment'].search([('res_model', '=', self._name), ('res_field', '=', 'photo'), ('res_id', '=', vaccination.id)], limit=1)
			# 	if attach:
			# 		copy_attach = attach.copy()
			# 		tag_vaccines = self.env.ref('ths_vet_base.documents_tag_vaccines', raise_if_not_found=False)
			# 		tag_pets = self.env.ref('ths_vet_base.documents_tag_pets', raise_if_not_found=False)
			# 		tag_ids = [tag.id for tag in (tag_vaccines, tag_pets) if tag]
			# 		self.env['documents.document'].create({
			# 			'name': attach.name or f'Vaccination Photo {vaccination.id}',
			# 			'type': 'binary',
			# 			'attachment_id': copy_attach.id,
			# 			'folder_id': self.env.ref('ths_vet_base.documents_vaccine_folder').id,
			# 			'tag_ids': [(6, 0, tag_ids)],
			# 			'res_model': 'res.partner',
			# 			'res_id': first_pet.id,
			# 		})

		return vaccinations

	# def write(self, vals):
	# 	res = super().write(vals)
	# 	if 'photo' in vals:
	# 		for vaccination in self:
	# 			if vaccination.photo and vaccination.patient_ids:
	# 				first_pet = vaccination.patient_ids[0]
	# 				attach = self.env['ir.attachment'].search([('res_model', '=', self._name), ('res_field', '=', 'photo'), ('res_id', '=', vaccination.id)], limit=1)
	# 				if attach:
	# 					copy_attach = attach.copy()
	# 					tag_vaccines = self.env.ref('ths_vet_base.documents_tag_vaccines', raise_if_not_found=False)
	# 					tag_pets = self.env.ref('ths_vet_base.documents_tag_pets', raise_if_not_found=False)
	# 					tag_ids = [tag.id for tag in (tag_vaccines, tag_pets) if tag]
	# 					self.env['documents.document'].create({
	# 						'name': attach.name or f'Vaccination Photo {vaccination.id}',
	# 						'type': 'binary',
	# 						'attachment_id': copy_attach.id,
	# 						'folder_id': self.env.ref('ths_vet_base.documents_vaccine_folder').id,
	# 						'tag_ids': [(6, 0, tag_ids)],
	# 						'res_model': 'res.partner',
	# 						'res_id': first_pet.id,
	# 					})
	# 	return res

	def _schedule_vaccination_reminder(self):
		"""Schedule reminder activity on pet owner for vaccination renewal"""
		if self.expiry_date and self.patient_ids and self.patient_ids.pet_owner_id:
			reminder_date = self.expiry_date - relativedelta(days=30)
			if reminder_date > fields.Date.today():
				self.patient_ids.pet_owner_id.activity_schedule(
					'mail.mail_activity_data_todo',
					date_deadline=reminder_date,
					summary=_('Vaccination Renewal Reminder for %s') % self.patient_ids.name,
					note=_('The %s vaccination for %s expires on %s. Schedule renewal.') % (self.vaccine_type_id.name, self.patient_ids.name, self.expiry_date),
					user_id=self.env.user.id
				)

	def action_view_encounter(self):
		"""View the daily encounter for this vaccination"""
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

	def action_view_documents(self):
		"""Smart button to view/upload documents for vaccination records"""
		return self.action_view_documents_model(
			'ths_vet_base.documents_vaccine_folder',
			'Vaccination',
			'ths_vet_base.documents_tag_vaccines'
		)

	def action_schedule_reminder(self):
		"""Schedule activity reminder for vaccination renewal"""
		self.ensure_one()
		if self.expiry_date:
			# Schedule 30 days before expiry
			reminder_date = self.expiry_date - relativedelta(days=30)
			if reminder_date > fields.Date.context_today(self):
				self.activity_schedule(
					'mail.mail_activity_data_todo',
					date_deadline=reminder_date,
					summary=_('Vaccination Renewal: %s for %s') % (self.vaccine_type_id.name, self.patient_ids.name),
					note=_('The %s vaccination for %s will expire on %s. Please schedule a renewal appointment.') % (
						self.vaccine_type_id.name, self.patient_ids.name, self.expiry_date),
					user_id=self.env.user.id,
				)

	@api.model
	def _cron_update_vaccination_status(self):
		"""Cron job to update vaccination expiry status daily"""
		today = fields.Date.context_today(self)
		vaccinations_to_update = self.search([
			('expiry_date', '<', today),
			('is_expired', '=', False)
		])

		vaccinations_to_update._compute_is_expired()
		vaccinations_to_update._compute_days_until_expiry()

		return True


class VetVaccineType(models.Model):
	_name = 'vet.vaccine.type'
	_description = 'Vaccine Type'
	_order = 'name'

	name = fields.Char(string='Vaccine Name', required=True)
	code = fields.Char(string='Code', required=True)
	validity_months = fields.Integer(string='Validity (Months)', required=True, default=12, help="Number of months this vaccine remains valid")
	description = fields.Text(string='Description')
	active = fields.Boolean(default=True)

	_sql_constraints = [
		('code_uniq', 'unique (code)', 'Vaccine code must be unique!'),
	]


# TODO: Add vaccination encounter batch processing
# TODO: Implement vaccination reminder encounter creation
# TODO: Add vaccination adverse reaction tracking per encounter
# TODO: Implement vaccination certificate generation from encounter
# TODO: Add vaccination inventory integration with encounter
# TODO: Implement vaccination effectiveness tracking


class VetTreatmentPlan(models.Model):
	_name = 'vet.treatment.plan'
	_description = 'Veterinary Treatment Plan'
	_inherit = ['vet.encounter.mixin', 'mail.thread', 'mail.activity.mixin']
	_order = 'treatment_date desc, name'
	_rec_name = 'name'

	name = fields.Char(string='Treatment Plan Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
	encounter_id = fields.Many2one('vet.encounter.header', string='Related Encounter', required=True, index=True, ondelete='cascade',
								   help="Encounter this treatment plan belongs to")
	patient_ids = fields.Many2many('res.partner', 'vet_treatment_plan_patient_rel', 'treatment_plan_id', 'patient_id', string='Pets',
								   context={'is_pet': True, 'default_is_pet': True},
								   store=True, readonly=False, index=True, tracking=True, domain="[('is_pet', '=', True), ('pet_owner_id', '=?', partner_id)]")

	# Treatment Details
	treatment_date = fields.Date(string='Treatment Start Date', required=True, default=fields.Date.today)
	estimated_duration = fields.Integer(string='Estimated Duration (days)', help="Expected treatment duration")
	actual_end_date = fields.Date(string='Actual End Date', help="When treatment was completed")
	priority = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')], string='Priority', default='medium', required=True)
	state = fields.Selection([('draft', 'Draft'), ('active', 'Active'), ('on_hold', 'On Hold'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], string='Status',
							 default='draft', tracking=True)

	# Clinical Information
	diagnosis = fields.Text(string='Primary Diagnosis', required=True)
	secondary_diagnosis = fields.Text(string='Secondary Diagnosis')
	treatment_goals = fields.Text(string='Treatment Goals')
	contraindications = fields.Text(string='Contraindications')
	special_instructions = fields.Text(string='Special Instructions')

	# Medications and Treatments
	medication_plan = fields.Text(string='Medication Plan')
	dosage_instructions = fields.Text(string='Dosage Instructions')
	dietary_restrictions = fields.Text(string='Dietary Restrictions')
	exercise_restrictions = fields.Text(string='Exercise Restrictions')

	# Follow-up and Monitoring
	monitoring_schedule = fields.Text(string='Monitoring Schedule')
	follow_up_schedule = fields.Text(string='Follow-up Schedule')
	warning_signs = fields.Text(string='Warning Signs to Watch For')
	emergency_instructions = fields.Text(string='Emergency Instructions')

	# Progress Tracking
	progress_notes = fields.Text(string='Progress Notes')
	treatment_line_ids = fields.One2many('vet.treatment.plan.line', 'treatment_plan_id', string='Treatment Tasks')

	# Costs and Insurance
	estimated_cost = fields.Monetary(string='Estimated Cost', currency_field='currency_id')
	actual_cost = fields.Monetary(string='Actual Cost', currency_field='currency_id')
	currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
	insurance_approved = fields.Boolean(string='Insurance Pre-approved')
	insurance_notes = fields.Text(string='Insurance Notes')

	# Computed Fields
	completion_percentage = fields.Float(string='Completion %', compute='_compute_completion_percentage')
	days_active = fields.Integer(string='Days Active', compute='_compute_days_active')
	overdue_tasks = fields.Integer(string='Overdue Tasks', compute='_compute_overdue_tasks')

	@api.depends('treatment_line_ids.state')
	def _compute_completion_percentage(self):
		for plan in self:
			if not plan.treatment_line_ids:
				plan.completion_percentage = 0.0
			else:
				completed = len(plan.treatment_line_ids.filtered(lambda l: l.state == 'completed'))
				total = len(plan.treatment_line_ids)
				plan.completion_percentage = (completed / total) * 100 if total > 0 else 0.0

	@api.depends('treatment_date')
	def _compute_days_active(self):
		today = fields.Date.today()
		for plan in self:
			if plan.treatment_date:
				delta = today - plan.treatment_date
				plan.days_active = delta.days if delta.days >= 0 else 0
			else:
				plan.days_active = 0

	@api.depends('treatment_line_ids.due_date', 'treatment_line_ids.state')
	def _compute_overdue_tasks(self):
		today = fields.Date.today()
		for plan in self:
			overdue = plan.treatment_line_ids.filtered(
				lambda l: l.state not in ('completed', 'cancelled') and l.due_date and l.due_date < today
			)
			plan.overdue_tasks = len(overdue)

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('vet.treatment.plan') or _('New')
		return super().create(vals_list)

	def action_start_treatment(self):
		"""Start the treatment plan"""
		self.write({'state': 'active'})
		self.message_post(body=_("Treatment plan started"))

	def action_complete_treatment(self):
		"""Complete the treatment plan"""
		self.write({
			'state': 'completed',
			'actual_end_date': fields.Date.today()
		})
		# Complete all pending tasks
		self.treatment_line_ids.filtered(lambda l: l.state == 'pending').write({'state': 'completed'})
		self.message_post(body=_("Treatment plan completed"))

	def action_put_on_hold(self):
		"""Put treatment plan on hold"""
		self.write({'state': 'on_hold'})
		self.message_post(body=_("Treatment plan put on hold"))

	def action_resume_treatment(self):
		"""Resume treatment plan from hold"""
		self.write({'state': 'active'})
		self.message_post(body=_("Treatment plan resumed"))


class VetTreatmentPlanLine(models.Model):
	_name = 'vet.treatment.plan.line'
	_description = 'Treatment Plan Task Line'
	_order = 'due_date, sequence, id'

	treatment_plan_id = fields.Many2one('vet.treatment.plan', string='Treatment Plan', required=True, ondelete='cascade')
	sequence = fields.Integer(string='Sequence', default=10)
	name = fields.Char(string='Task Description', required=True)
	task_type = fields.Selection([('medication', 'Medication'), ('examination', 'Examination'), ('procedure', 'Procedure'), ('followup', 'Follow-up'), ('monitoring', 'Monitoring'),
								  ('other', 'Other')], string='Task Type', required=True)
	due_date = fields.Date(string='Due Date')
	completed_date = fields.Date(string='Completed Date')
	assigned_to = fields.Many2one('res.users', string='Assigned To')
	state = fields.Selection([('pending', 'Pending'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], string='Status', default='pending',
							 required=True)
	notes = fields.Text(string='Notes')
	result = fields.Text(string='Result/Outcome')

	@api.onchange('state')
	def _onchange_state(self):
		if self.state == 'completed' and not self.completed_date:
			self.completed_date = fields.Date.today()