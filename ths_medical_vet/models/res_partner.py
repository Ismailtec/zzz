# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
	_inherit = 'res.partner'

	# --- CORE VET RELATIONSHIP FIELDS ---

	pet_owner_id = fields.Many2one(
		'res.partner',
		context={'is_pet': False},
		string='Pet Owner',
		index=True,
		help="The owner responsible for this pet and billing.",
		tracking=True,
		domain="[('partner_type_id.name','=','Pet Owner')]",
		ondelete='restrict',  # Prevent deletion of owners who have pets
	)

	pet_ids = fields.One2many(
		'res.partner',
		'pet_owner_id',
		context={'is_pet': True},
		string='Pets',
		help="Pets owned by this Pet Owner."
	)

	pet_count = fields.Integer(
		compute='_compute_pet_count',
		string="# Pets",
		help="Number of pets owned by this Pet Owner."
	)

	# --- COMPUTED TYPE FLAGS ---

	is_pet = fields.Boolean(
		compute="_compute_type_flags",
		store=True,
		index=True,
		help="True if this partner is a Pet."
	)

	is_pet_owner = fields.Boolean(
		compute="_compute_type_flags",
		store=True,
		index=True,
		help="True if this partner is a Pet Owner."
	)

	appointment_count = fields.Integer("# Appointments", compute='_compute_appointment_count')

	# --- PET-SPECIFIC MEDICAL FIELDS ---
	species_id = fields.Many2one(
		'ths.species',
		string='Species',
		tracking=True,
		help="Species of the pet (Dog, Cat, etc.)"
	)

	breed_id = fields.Many2one(
		'ths.breed',
		string='Breed',
		tracking=True,
		help="Specific breed of the pet."
	)

	# Pet health and identification fields
	is_neutered_spayed = fields.Boolean(
		string="Neutered / Spayed",
		help="Whether the pet has been neutered or spayed."
	)

	ths_microchip = fields.Char(
		string='Microchip Number',
		index=True,
		help="Unique microchip identification number."
	)

	ths_deceased = fields.Boolean(
		string='Deceased',
		default=False,
		tracking=True,
		help="Mark if the pet is deceased."
	)

	ths_deceased_date = fields.Date(
		string='Date of Death',
		help="Date when the pet passed away."
	)

	# Additional vet-specific fields
	ths_insurance_number = fields.Char(
		string='Pet Insurance Number',
		help="Pet insurance policy number if applicable."
	)

	ths_emergency_contact = fields.Many2one(
		'res.partner',
		string='Emergency Contact',
		help="Emergency contact person if pet owner is unavailable."
	)

	pet_membership_ids = fields.One2many(
		'vet.pet.membership',
		'patient_ids',
		string='Pet Memberships',
		help="Memberships associated with this pet for services and benefits."
	)

	pet_membership_count = fields.Integer(
		compute='_compute_pet_membership_count',
		string="# Memberships"
	)
	pet_badge_data = fields.Json(string="Pet Badge Data", compute="_compute_pet_badge_data", store=True)

	# --- Address and contact fields ---
	ths_owner_street = fields.Char(
		string="Owner's Street (Computed)",
		compute='_compute_owner_address_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved street from the pet owner. Not stored on the pet record."
	)
	ths_owner_street2 = fields.Char(
		string="Owner's Street2 (Computed)",
		compute='_compute_owner_address_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved street2 from the pet owner. Not stored on the pet record."
	)
	ths_owner_city = fields.Char(
		string="Owner's City (Computed)",
		compute='_compute_owner_address_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved city from the pet owner. Not stored on the pet record."
	)
	ths_owner_state_id = fields.Many2one(
		'res.country.state',
		string="Owner's State (Computed)",
		compute='_compute_owner_address_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved state from the pet owner. Not stored on the pet record."
	)
	ths_owner_zip = fields.Char(
		string="Owner's Zip (Computed)",
		compute='_compute_owner_address_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved zip from the pet owner. Not stored on the pet record."
	)
	ths_owner_country_id = fields.Many2one(
		'res.country',
		string="Owner's Country (Computed)",
		compute='_compute_owner_address_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved country from the pet owner. Not stored on the pet record."
	)
	ths_owner_mobile = fields.Char(
		string="Owner's Mobile (Computed)",
		compute='_compute_owner_contact_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved mobile number from the pet owner. Not stored on the pet record."
	)
	ths_owner_phone = fields.Char(
		string="Owner's Phone (Computed)",
		compute='_compute_owner_contact_info',
		store=False,
		readonly=True,
		help="Dynamically retrieved phone number from the pet owner. Not stored on the pet record."
	)

	# --- CORE COMPUTED METHODS ---
	@api.depends('partner_type_id')
	def _compute_type_flags(self):
		"""Compute pet/owner flags based on partner type"""
		pet_type = self.env.ref('ths_medical_vet.partner_type_pet', raise_if_not_found=False)
		owner_type = self.env.ref('ths_medical_vet.partner_type_pet_owner', raise_if_not_found=False)

		for rec in self:
			rec.is_pet = rec.partner_type_id == pet_type if pet_type else False
			rec.is_pet_owner = rec.partner_type_id == owner_type if owner_type else False

	@api.depends('pet_owner_id.street', 'pet_owner_id.street2', 'pet_owner_id.city',
				 'pet_owner_id.state_id', 'pet_owner_id.zip', 'pet_owner_id.country_id')
	def _compute_owner_address_info(self):
		""" Compute method to dynamically get address fields from the pet owner. """
		for pet in self:
			if pet.pet_owner_id:
				pet.ths_owner_street = pet.pet_owner_id.street
				pet.ths_owner_street2 = pet.pet_owner_id.street2
				pet.ths_owner_city = pet.pet_owner_id.city
				pet.ths_owner_state_id = pet.pet_owner_id.state_id
				pet.ths_owner_zip = pet.pet_owner_id.zip
				pet.ths_owner_country_id = pet.pet_owner_id.country_id
			else:
				# Clear fields if pet owner is removed or changed
				pet.ths_owner_street = False
				pet.ths_owner_street2 = False
				pet.ths_owner_city = False
				pet.ths_owner_state_id = False
				pet.ths_owner_zip = False
				pet.ths_owner_country_id = False

	@api.depends('pet_owner_id.mobile', 'pet_owner_id.phone')
	def _compute_owner_contact_info(self):
		""" Compute method to dynamically get contact fields from the pet owner. """
		for pet in self:
			if pet.pet_owner_id:
				pet.ths_owner_mobile = pet.pet_owner_id.mobile
				pet.ths_owner_phone = pet.pet_owner_id.phone
			else:
				# Clear fields if pet owner is removed or changed
				pet.ths_owner_mobile = False
				pet.ths_owner_phone = False

	@api.depends('pet_ids')
	def _compute_pet_count(self):
		"""Count active pets for each owner"""
		for partner in self:
			if partner.is_pet_owner:
				partner.pet_count = len(partner.pet_ids.filtered('active'))
			else:
				partner.pet_count = 0

	@api.depends('is_pet')
	def _compute_pet_membership_count(self):
		for partner in self:
			if partner.is_pet:
				partner.pet_membership_count = self.env['vet.pet.membership'].search_count([
					('partner_id', '=', partner.parent_id.id),
				])
			else:
				partner.pet_membership_count = 0

	@api.depends('is_pet', 'is_pet_owner')
	def _compute_appointment_count(self):
		for rec in self:
			appointment_domain = []

			if rec.is_pet:
				appointment_domain = [('patient_ids', 'in', rec.id)]
			elif rec.is_pet_owner:
				appointment_domain = [('pet_owner_id', '=', rec.id)]
			else:
				pass

			if appointment_domain:
				rec.appointment_count = self.env['calendar.event'].search_count(appointment_domain)
			else:
				rec.appointment_count = 0

	# @api.depends('species_id.color', 'name', 'species_id.name')
	# def _compute_pet_badge_data(self):
	# 	for rec in self:
	# 		badge_data = []
	# 		if rec.species_id:
	# 			badge_data.append({
	# 				'name': rec.name,
	# 				'species': rec.species_id.name,
	# 				'color': rec.species_id.color or 0,
	# 			})
	# 		rec.pet_badge_data = badge_data
	@api.depends('species_id')
	def _compute_pet_badge_data(self):
		for rec in self:
			if rec.species_id:
				rec.pet_badge_data = [{
					'name': rec.name,
					'species': rec.species_id.name,
					'color': rec.species_id.color or 0,
				}]
			else:
				rec.pet_badge_data = []

	@api.depends('name', 'is_pet', 'pet_owner_id', 'pet_owner_id.name')
	def _compute_display_name(self):
		"""Enhanced display name for pets with owner info"""
		pets = self.filtered('is_pet')
		others = self - pets

		if pets:
			# Prefetch owner names for efficiency
			pets.mapped('pet_owner_id.name')

			show_owner = self.env.context.get('show_pet_owner', True)

			for pet in pets:
				base_name = pet.name or ''

				if show_owner and pet.pet_owner_id:
					# Clean format: "Pet Name [Owner Name]"
					if ' [' in base_name and base_name.endswith(']'):
						base_name = base_name.split(' [')[0]

					pet.display_name = f"{base_name} [{pet.pet_owner_id.name}]"
				else:
					pet.display_name = base_name

		# Let parent handle non-pets
		if others:
			super(ResPartner, others)._compute_display_name()

	# --- ESSENTIAL CONSTRAINTS ---

	@api.constrains('partner_type_id', 'pet_owner_id')
	def _check_pet_owner_required(self):
		"""Ensure active pets have owners"""
		pet_type = self.env.ref('ths_medical_vet.partner_type_pet', raise_if_not_found=False)
		if not pet_type:
			return

		for partner in self:
			if (partner.active and
					partner.partner_type_id == pet_type and
					not partner.pet_owner_id and
					partner.id):  # Only for existing records
				raise ValidationError(
					_("Pet '%s' must have an owner assigned.", partner.name)
				)

	@api.constrains('ths_deceased', 'ths_deceased_date')
	def _check_deceased_date_logic(self):
		"""Validate deceased date logic"""
		for partner in self:
			if partner.ths_deceased and not partner.ths_deceased_date:
				partner.ths_deceased_date = fields.Date.today()
			elif not partner.ths_deceased and partner.ths_deceased_date:
				partner.ths_deceased_date = False

	# --- ONCHANGE METHODS ---

	@api.onchange('pet_owner_id')
	def _onchange_pet_owner_set_parent(self):
		"""Set parent_id when owner is selected (for contact hierarchy)"""
		# self.partner_type_id = self.env.ref('ths_medical_vet.partner_type_pet', raise_if_not_found=False).id
		if self.is_pet and self.pet_owner_id and not self.parent_id:
			self.parent_id = self.pet_owner_id

	@api.onchange('ths_deceased')
	def _onchange_deceased_set_date(self):
		"""Auto-set deceased date when marking as deceased"""
		if self.ths_deceased and not self.ths_deceased_date:
			self.ths_deceased_date = fields.Date.today()
		elif not self.ths_deceased:
			self.ths_deceased_date = False

	@api.onchange('pet_owner_id')
	def _onchange_pet_owner_id_sync_info(self):
		""" Onchange to immediately populate owner's address/contact info when a pet owner is selected/set. """
		if self.pet_owner_id:
			# Trigger the re-computation of the depends fields directly on the current record.
			self._compute_owner_address_info()
			self._compute_owner_contact_info()
		else:
			# Clear fields if owner is unlinked in the UI
			self.ths_owner_street = False
			self.ths_owner_street2 = False
			self.ths_owner_city = False
			self.ths_owner_state_id = False
			self.ths_owner_zip = False
			self.ths_owner_country_id = False
			self.ths_owner_mobile = False
			self.ths_owner_phone = False

	# --- OVERRIDE CREATE/WRITE FOR BUSINESS LOGIC ---
	@api.model_create_multi
	def create(self, vals_list):
		pet_type = self.env.ref('ths_medical_vet.partner_type_pet', raise_if_not_found=False)
		owner_type = self.env.ref('ths_medical_vet.partner_type_pet_owner', raise_if_not_found=False)

		for vals in vals_list:
			partner_type_id = vals.get('partner_type_id')

			if pet_type and partner_type_id == pet_type.id:
				vals['is_pet'] = True
				vals['is_company'] = pet_type.is_company
				if vals.get('pet_owner_id') and not vals.get('parent_id'):
					vals['parent_id'] = vals['pet_owner_id']

			elif owner_type and partner_type_id == owner_type.id:
				vals['is_pet_owner'] = True
				vals['is_company'] = owner_type.is_company
				vals.setdefault('customer_rank', 1)

			# Handle deceased logic
			if vals.get('ths_deceased') and not vals.get('ths_deceased_date'):
				vals['ths_deceased_date'] = fields.Date.today()
			elif 'ths_deceased' in vals and not vals['ths_deceased']:
				vals['ths_deceased_date'] = False

		return super().create(vals_list)

	def write(self, vals):
		pet_type = self.env.ref('ths_medical_vet.partner_type_pet', raise_if_not_found=False)
		owner_type = self.env.ref('ths_medical_vet.partner_type_pet_owner', raise_if_not_found=False)

		for partner in self:
			new_type_id = vals.get('partner_type_id', partner.partner_type_id.id)

			if pet_type and new_type_id == pet_type.id:
				vals['is_pet'] = True
				vals['is_company'] = False
				if vals.get('pet_owner_id') and not vals.get('parent_id', partner.parent_id.id):
					vals['parent_id'] = vals['pet_owner_id']

			elif owner_type and new_type_id == owner_type.id:
				vals['is_pet_owner'] = True
				vals['is_company'] = False
				if 'customer_rank' not in vals and not partner.customer_rank:
					vals['customer_rank'] = 1

			# Deceased logic preserved here
			if vals.get('ths_deceased') and not vals.get('ths_deceased_date'):
				vals['ths_deceased_date'] = fields.Date.today()
			elif 'ths_deceased' in vals and not vals['ths_deceased']:
				vals['ths_deceased_date'] = False

		res = super().write(vals)

		# Recompute display name if any of the key pet-related fields changed
		if {'name', 'pet_owner_id', 'partner_type_id'} & set(vals.keys()):
			self.invalidate_recordset(['display_name'])

		return res

	# --- BUSINESS ACTION METHODS ---

	def action_view_partner_pets(self):
		"""Action to view pets linked to this Pet Owner"""
		self.ensure_one()
		if not self.is_pet_owner:
			return {}

		pet_type = self.env.ref('ths_medical_vet.partner_type_pet', raise_if_not_found=False)
		if not pet_type:
			return {}

		return {
			'name': _('Pets of %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'res.partner',
			'view_mode': 'kanban,list,form',
			'domain': [('pet_owner_id', '=', self.id)],
			'context': {
				'default_pet_owner_id': self.id,
				'default_partner_type_id': pet_type.id,
				'default_parent_id': self.id,
				'show_pet_owner': False,
				'create': True,
			}
		}

	def action_view_partner_pet_owners(self):
		"""Action to view the pet owner for this pet"""
		self.ensure_one()
		if not self.is_pet:
			return {}

		pet_owner_type = self.env.ref('ths_medical_vet.partner_type_pet_owner', raise_if_not_found=False)
		if not pet_owner_type:
			return {}

		return {
			'name': _('Pet Owner: %s') % self.pet_owner_id.name,
			'type': 'ir.actions.act_window',
			'res_model': 'res.partner',
			'view_mode': 'form',
			'res_id': self.pet_owner_id.id,
			'target': 'current',
			'context': {
				'show_pet_owner': True,
				'default_pet_ids': [(6, 0, [self.id])],
				'default_partner_type_id': pet_owner_type.id,
				'create': True,
			}
		}

	def action_view_medical_history(self):
		"""View complete medical history for a pet"""
		self.ensure_one()
		if not self.is_pet:
			return {}

		return {
			'name': _('Medical History: %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'ths.medical.base.encounter',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', [self.id])],
			'context': {
				'search_default_groupby_date': 1,
				'create': False,
			}
		}

	def action_view_appointments(self):
		"""View appointments for this pet or pet owner"""
		self.ensure_one()

		if self.is_pet:
			domain = [('patient_ids', 'in', [self.id])]
			name = _('Appointments for %s') % self.name
			context = {
				'default_patient_ids': [(6, 0, [self.id])],
				'default_pet_owner_id': self.pet_owner_id.id if self.pet_owner_id else False,
			}
		elif self.is_pet_owner:
			domain = [('pet_owner_id', '=', self.id)]
			name = _('Appointments for %s') % self.name
			context = {
				'default_pet_owner_id': self.id,
			}
		else:
			return {}

		return {
			'name': name,
			'type': 'ir.actions.act_window',
			'res_model': 'calendar.event',
			'view_mode': 'calendar,list,form',
			'domain': domain,
			'context': context,
		}

	def action_view_pet_memberships(self):
		"""View memberships for this pet owner"""
		self.ensure_one()
		domain = [
			('partner_id', '=', self.pet_owner_id.id),
			('patient_ids', 'in', self.id),
		]
		memberships = self.env['vet.pet.membership'].search(domain)
		if len(memberships) == 1:
			return {
				'type': 'ir.actions.act_window',
				'name': _('Pet Membership'),
				'res_model': 'vet.pet.membership',
				'view_mode': 'form',
				'res_id': memberships.id,
				'target': 'current',
			}
		return {
			'name': _('Pet Memberships for %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.pet.membership',
			'view_mode': 'list,form',
			'domain': domain,
			'context': {
				'default_partner_id': self.pet_owner_id.id,
				'default_patient_ids': [(6, 0, [self.id])],
			},
		}

	# --- HELPER METHODS ---

	def _get_pet_age_display(self):
		"""Calculate and format pet age for display"""
		self.ensure_one()
		if not self.is_pet or not self.ths_dob:
			return ''

		today = fields.Date.today()
		end_date = self.ths_deceased_date if self.ths_deceased else today

		age_days = (end_date - self.ths_dob).days
		age_years = age_days // 365
		age_months = (age_days % 365) // 30

		if age_years > 0:
			return _('%d years, %d months') % (age_years, age_months)
		else:
			return _('%d months') % age_months

	def _get_next_appointment(self):
		"""Get next scheduled appointment for pet or owner"""
		self.ensure_one()

		if self.is_pet:
			domain = [('patient_ids', 'in', [self.id])]
		elif self.is_pet_owner:
			domain = [('pet_owner_id', '=', self.id)]
		else:
			return False

		domain.extend([
			('start', '>=', fields.Datetime.now()),
			('appointment_status', 'in', ['draft', 'confirmed'])
		])

		return self.env['calendar.event'].search(domain, order='start asc', limit=1)

# TODO: Future enhancements
# TODO: Add integration with pet insurance systems
# TODO: Add automatic vaccination reminders
# TODO: Add pet boarding system integration
# TODO: Add pet photo management
# TODO: Add emergency contact notification system