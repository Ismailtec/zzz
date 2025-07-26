# -*- coding: utf-8 -*-
import re

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

from odoo.osv import expression

_logger = logging.getLogger(__name__)


class ThsPartnerType(models.Model):
	""" Inherit Partner Type to add HR-specific flags. """
	_inherit = 'ths.partner.type'

	is_patient = fields.Boolean(string="Patient", default=False, help="Check if this partner type specifically represents Patients.")
	is_pet = fields.Boolean(string="Pet", default=False, help="Check if this partner type specifically represents Pets.")
	is_pet_owner = fields.Boolean(string="Pet Owner", default=False, help="Check if this partner type specifically represents Pet Owners.")
	pet_count = fields.Integer(string='Pet Count', compute='_compute_type_counts', help="Number of pets using this type")
	pet_owner_count = fields.Integer(string='Pet Owner Count', compute='_compute_type_counts', help="Number of pet owners using this type")

	def _compute_type_counts(self):
		"""Compute usage statistics for this partner type"""
		for ptype in self:
			if ptype.is_pet:
				ptype.pet_count = self.env['res.partner'].search_count([
					('partner_type_id', '=', ptype.id),
					('is_pet', '=', True)
				])
			else:
				ptype.pet_count = 0

			if ptype.is_pet_owner:
				ptype.pet_owner_count = self.env['res.partner'].search_count([
					('partner_type_id', '=', ptype.id),
					('is_pet_owner', '=', True)
				])
			else:
				ptype.pet_owner_count = 0

	@api.constrains('is_pet', 'is_pet_owner')
	def _check_veterinary_type_exclusivity(self):
		"""Ensure veterinary types are mutually exclusive"""
		for ptype in self:
			active_flags = sum([ptype.is_pet, ptype.is_pet_owner])
			if active_flags > 1:
				raise ValidationError(_("Partner type can only be one of: Pet, Pet Owner (not multiple)"))

	def action_view_pets(self):
		"""View all pets using this partner type"""
		self.ensure_one()
		return {
			'name': _('Pets - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'res.partner',
			'view_mode': 'kanban,list,form',
			'domain': [
				('partner_type_id', '=', self.id),
				('is_pet', '=', True)
			],
			'context': {
				'default_partner_type_id': self.id,
				'default_is_pet': True,
				'show_pet_owner': True,
			}
		}

	def action_view_pet_owners(self):
		"""View all pet owners using this partner type"""
		self.ensure_one()
		return {
			'name': _('Pet Owners - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'res.partner',
			'view_mode': 'kanban,list,form',
			'domain': [
				('partner_type_id', '=', self.id),
				('is_pet_owner', '=', True)
			],
			'context': {
				'default_partner_type_id': self.id,
				'default_is_pet_owner': True,
				'default_customer_rank': 1,
			}
		}


class ResPartner(models.Model):
	_inherit = 'res.partner'

	# --- CORE VET RELATIONSHIP FIELDS ---
	pet_owner_id = fields.Many2one('res.partner', string='Pet Owner', index=True, tracking=True, domain="[('is_pet_owner','=',True)]", ondelete='restrict',
								   context={'is_pet_owner': True, 'default_is_pet_owner': True, 'is_pet': False, 'default_is_pet': False})
	pet_ids = fields.One2many('res.partner', 'pet_owner_id', string='Pets Owned', help="Pets owned by this Pet Owner.",
							  context={'is_pet_owner': False, 'default_is_pet_owner': False, 'is_pet': True, 'default_is_pet': True})
	pet_count = fields.Integer(compute='_compute_pet_count', string="# Pets", help="Number of pets owned by this Pet Owner.")
	is_pet = fields.Boolean(compute="_compute_type_flags", store=True, index=True, help="True if this partner is a Pet. (Main filter)")
	is_pet_owner = fields.Boolean(compute="_compute_type_flags", store=True, index=True, help="True if this partner is a Pet Owner. (Main filter)")

	# --- APPOINTMENT & SERVICE COUNTS ---
	appointment_count = fields.Integer("# Appointments", compute='_compute_appointment_count')
	documents_count = fields.Integer(string="Photos/Documents", compute='_compute_documents_count')
	encounter_count = fields.Integer(string="# Encounters", compute='_compute_encounter_count')
	vaccination_count = fields.Integer(string="# Vaccinations", compute='_compute_vaccination_count')
	boarding_count = fields.Integer(string="# Boardings", compute='_compute_boarding_count')
	park_count = fields.Integer(string="# Park Visits", compute='_compute_park_count')

	# --- COMMUNICATION PREFERENCES ---
	send_whatsapp_reminder = fields.Boolean(string='Send WhatsApp Reminders', default=True)
	preferred_communication = fields.Selection([('email', 'Email'), ('phone', 'Phone'), ('whatsapp', 'WhatsApp'), ('sms', 'SMS')], string='Preferred Communication',
											   default='whatsapp', help="Preferred method for appointment reminders and notifications")
	phone_normalized = fields.Char(string="Normalized Phone", compute='_compute_number_normalized', store=True, index=True,
								   help="Only digits of the phone number for search purposes.")
	mobile_normalized = fields.Char(string="Normalized Mobile", compute='_compute_number_normalized', store=True, index=True,
									help="Only digits of the mobile number for search purposes.")

	# --- PET-SPECIFIC MEDICAL FIELDS ---
	species_id = fields.Many2one('vet.species', string='Species', tracking=True, help="Species of the pet (Dog, Cat, etc.)")
	species_color = fields.Integer(related='species_id.color', string='Species color', store=True, readonly=True)
	species_image = fields.Image(related='species_id.image', string='Species Image')
	breed_id = fields.Many2one('vet.breed', string='Breed', tracking=True, help="Specific breed of the pet.")
	is_neutered_spayed = fields.Boolean(string="Neutered / Spayed", help="Whether the pet has been neutered or spayed.")
	ths_microchip = fields.Char(string='Microchip Number', index=True, help="Unique microchip identification number.")
	ths_deceased = fields.Boolean(string='Deceased', default=False, tracking=True, help="Mark if the pet is deceased.")
	ths_deceased_date = fields.Date(string='Date of Death', help="Date when the pet passed away.")
	ths_insurance_number = fields.Char(string='Pet Insurance Number', help="Pet insurance policy number if applicable.")
	ths_emergency_contact = fields.Char(string='Emergency Contact Number', help="Emergency contact number if pet owner is unavailable.")

	# --- MEDICAL HISTORY FIELDS ---
	last_visit_date = fields.Date(string='Last Visit', compute='_compute_medical_summary', store=True, help="Date of last veterinary visit")
	next_vaccination_due = fields.Date(string='Next Vaccination Due', compute='_compute_medical_summary', store=True, help="Date when next vaccination is due")
	medical_alerts = fields.Text(string='Medical Alerts', help="Important medical alerts for this pet")
	dietary_restrictions = fields.Text(string='Dietary Restrictions', help="Special dietary needs or restrictions")

	# --- MEMBERSHIP & SERVICES ---
	pet_membership_ids = fields.One2many('vet.pet.membership', 'patient_ids', string='Pet Memberships', help="Membership for Park.")
	pet_membership_count = fields.Integer(compute='_compute_pet_membership_count', string="# Memberships")

	# --- DISPLAY & UI ENHANCEMENTS ---
	pet_badge_data = fields.Json(string="Pet Badge Data", compute="_compute_pet_badge_data", store=True)
	full_medical_summary = fields.Html(string="Medical Summary", compute='_compute_full_medical_summary', help="Complete medical summary for this pet")

	# --- CORE COMPUTED METHODS ---
	@api.depends('partner_type_id')
	def _compute_type_flags(self):
		"""Compute pet/owner flags based on partner type"""
		pet_type = self.env.ref('ths_vet_base.partner_type_pet', raise_if_not_found=False)
		owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)

		for rec in self:
			rec.is_pet = rec.partner_type_id == pet_type if pet_type else False
			rec.is_pet_owner = rec.partner_type_id == owner_type if owner_type else False

	@api.depends('phone', 'mobile')
	def _compute_number_normalized(self):
		"""Compute the normalized version of the phone/mobile number (digits only)."""
		for partner in self:
			partner.phone_normalized = re.sub(r'\D', '', partner.phone) if partner.phone else False
			partner.mobile_normalized = re.sub(r'\D', '', partner.mobile) if partner.mobile else False

	@api.depends('pet_owner_id.street', 'pet_owner_id.street2', 'pet_owner_id.city', 'pet_owner_id.state_id', 'pet_owner_id.zip', 'pet_owner_id.country_id')
	def _compute_owner_address_info(self):
		""" Compute method to dynamically get address fields from the pet owner. """
		for pet in self:
			if pet.pet_owner_id:
				pet.street = pet.pet_owner_id.street
				pet.street2 = pet.pet_owner_id.street2
				pet.city = pet.pet_owner_id.city
				pet.state_id = pet.pet_owner_id.state_id
				pet.zip = pet.pet_owner_id.zip
				pet.country_id = pet.pet_owner_id.country_id
			else:
				# Clear fields if pet owner is removed or changed
				pet.street = False
				pet.street2 = False
				pet.city = False
				pet.state_id = False
				pet.zip = False
				pet.country_id = False

	@api.depends('pet_owner_id.mobile', 'pet_owner_id.phone', 'pet_owner_id.email')
	def _compute_owner_contact_info(self):
		""" Compute method to dynamically get contact fields from the pet owner. """
		for pet in self:
			if pet.pet_owner_id:
				pet.mobile = pet.pet_owner_id.mobile
				pet.phone = pet.pet_owner_id.phone
				pet.email = pet.pet_owner_id.email
			else:
				# Clear fields if pet owner is removed or changed
				pet.mobile = False
				pet.phone = False
				pet.email = False

	@api.depends('pet_ids', 'pet_ids.active')
	def _compute_pet_count(self):
		"""Count active pets for each owner"""
		for partner in self:
			if partner.is_pet_owner:
				partner.pet_count = len(partner.pet_ids.filtered(lambda p: p.active and not p.ths_deceased))
			else:
				partner.pet_count = 0

	@api.depends('pet_membership_ids')
	def _compute_pet_membership_count(self):
		"""Count pet memberships"""
		for pet in self:
			pet.pet_membership_count = len(pet.pet_membership_ids)

	@api.model
	def _get_valid_park_member_ids(self):
		""" Helper method to find IDs of pets with an active, valid park membership for today. """
		today = fields.Date.today()
		active_memberships = self.env['vet.pet.membership'].search([
			('state', '=', 'active'),
			('valid_from', '<=', today),
			('valid_to', '>=', today),
			('patient_ids', '!=', False)
		])

		valid_pet_ids = set()
		for membership in active_memberships:
			valid_pet_ids.update(membership.patient_ids.ids)

		return list(valid_pet_ids)

	@api.model
	def name_search(self, name='', args=None, operator='ilike', limit=100):
		args = list(args or [])

		search_domain = []
		if name:
			search_domain = expression.OR([
				[('name', operator, name)],
				[('email', operator, name)],
				[('mobile_normalized', operator, name)],
				[('phone_normalized', operator, name)],
				[('ths_gov_id', operator, name)],
			])

		if args and search_domain:
			current_domain = expression.AND([args, search_domain])
		elif args:
			current_domain = args
		else:
			current_domain = search_domain

		if self.env.context.get('show_valid_park_members_only'):
			valid_pet_ids = self._get_valid_park_member_ids()

			if not valid_pet_ids:
				final_domain = expression.AND([current_domain, [('id', '=', False)]])
			else:
				final_domain = expression.AND([current_domain, [('id', 'in', valid_pet_ids)]])

			if not any(arg[0] == 'is_pet' for arg in args if isinstance(arg, (list, tuple))):
				final_domain = expression.AND([final_domain, [('is_pet', '=', True)]])

			partners = self.search_fetch(final_domain, ['display_name'], limit=limit)
			return [(partner.id, partner.display_name) for partner in partners]

		partners = self.search_fetch(current_domain, ['display_name'], limit=limit)
		return [(partner.id, partner.display_name) for partner in partners]

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

	@api.depends('is_pet', 'is_pet_owner')
	def _compute_encounter_count(self):
		"""Count encounters for pets and pet owners"""
		for rec in self:
			if rec.is_pet:
				rec.encounter_count = self.env['vet.encounter.header'].search_count([
					('patient_ids', 'in', rec.id)
				])
			elif rec.is_pet_owner:
				rec.encounter_count = self.env['vet.encounter.header'].search_count([
					('partner_id', '=', rec.id)
				])
			else:
				rec.encounter_count = 0

	@api.depends('is_pet', 'is_pet_owner')
	def _compute_vaccination_count(self):
		"""Count vaccinations for pets and pet owners"""
		for partner in self:
			if partner.is_pet:
				partner.vaccination_count = self.env['vet.vaccination'].search_count([
					('patient_ids', 'in', partner.id)
				])
			elif partner.is_pet_owner:
				# Count all vaccinations where this person is the pet owner
				partner.vaccination_count = self.env['vet.vaccination'].search_count([
					('partner_id', '=', partner.id)
				])
			else:
				partner.vaccination_count = 0

	@api.depends('is_pet', 'is_pet_owner')
	def _compute_boarding_count(self):
		"""Count Boardings for pets and pet owners"""
		for partner in self:
			if partner.is_pet:
				partner.boarding_count = self.env['vet.boarding.stay'].search_count([
					('patient_ids', 'in', partner.id),
					('state', 'not in', ('draft', 'cancelled'))
				])
			elif partner.is_pet_owner:
				partner.boarding_count = self.env['vet.boarding.stay'].search_count([
					('partner_id', '=', partner.id),
					('state', 'not in', ('draft', 'cancelled'))
				])
			else:
				partner.boarding_count = 0

	@api.depends('is_pet', 'is_pet_owner')
	def _compute_park_count(self):
		"""Count Park Visits for pets and pet owners"""
		for partner in self:
			if partner.is_pet:
				partner.park_count = self.env['vet.park.checkin'].search_count([
					('patient_ids', 'in', partner.id),
					('state', '!=', 'draft')
				])
			elif partner.is_pet_owner:
				partner.park_count = self.env['vet.park.checkin'].search_count([
					('partner_id', '=', partner.id),
					('state', '!=', 'draft')
				])
			else:
				partner.park_count = 0

	@api.depends('is_pet', 'is_pet_owner')
	def _compute_documents_count(self):
		"""Count documents/photos for pets and pet owners"""
		for partner in self:
			if partner.is_pet:
				domain = [('partner_id', '=', partner.id)]
				partner.documents_count = self.env['documents.document'].search_count(domain)
			elif partner.is_pet_owner:
				# Count pet owner's personal docs + all their pets' docs
				pet_ids = self.env['res.partner'].search([
					('pet_owner_id', '=', partner.id),
					('is_pet', '=', True)
				]).ids
				domain = [
					'|',
					('res_model', '=', 'res.partner'), ('res_id', '=', partner.id),
					('res_model', '=', 'res.partner'), ('res_id', 'in', pet_ids)
				]
				partner.documents_count = self.env['documents.document'].search_count(domain)
			else:
				partner.documents_count = 0

	@api.depends('species_id', 'species_id.color')
	def _compute_pet_badge_data(self):
		"""Compute data for pet species badge display"""
		for rec in self:
			if rec.is_pet and rec.species_id:
				rec.pet_badge_data = {
					'name': rec.name or '',
					'species': rec.species_id.name,
					'color': rec.species_id.color or 0,
					'deceased': rec.ths_deceased
				}
			else:
				rec.pet_badge_data = {}

	@api.depends('is_pet', 'appointment_count', 'vaccination_count', 'last_visit_date')
	def _compute_medical_summary(self):
		"""Compute medical summary fields"""
		for partner in self:
			if not partner.is_pet:
				partner.last_visit_date = False
				partner.next_vaccination_due = False
				continue

			# Get last appointment
			last_appointment = self.env['calendar.event'].search([
				('patient_ids', 'in', partner.id),
				('appointment_status', 'in', ['completed', 'paid'])
			], order='start desc', limit=1)

			partner.last_visit_date = last_appointment.start.date() if last_appointment else False

			# Get next vaccination due
			next_vaccination = self.env['vet.vaccination'].search([
				('patient_ids', 'in', partner.id),
				('expiry_date', '>', fields.Date.today())
			], order='expiry_date asc', limit=1)

			partner.next_vaccination_due = next_vaccination.expiry_date if next_vaccination else False

	@api.depends('is_pet', 'last_visit_date', 'vaccination_count', 'medical_alerts', 'dietary_restrictions', 'ths_microchip', 'ths_insurance_number')
	def _compute_full_medical_summary(self):
		"""Generate complete HTML medical summary"""
		for partner in self:
			if not partner.is_pet:
				partner.full_medical_summary = ""
				continue

			summary_parts = []

			# Basic info
			if partner.species_id or partner.breed_id:
				basic_info = f"<strong>Species:</strong> {partner.species_id.name or 'Unknown'}"
				if partner.breed_id:
					basic_info += f" - {partner.breed_id.name}"
				summary_parts.append(basic_info)

			# Medical status
			status_items = []
			if partner.is_neutered_spayed:
				status_items.append("Spayed/Neutered")
			if partner.ths_microchip:
				status_items.append(f"Microchipped ({partner.ths_microchip})")
			if status_items:
				summary_parts.append(f"<strong>Status:</strong> {', '.join(status_items)}")

			# Recent activity
			if partner.last_visit_date:
				summary_parts.append(f"<strong>Last Visit:</strong> {partner.last_visit_date}")
			if partner.vaccination_count:
				summary_parts.append(f"<strong>Vaccinations:</strong> {partner.vaccination_count} on record")

			# Alerts
			if partner.medical_alerts:
				summary_parts.append(f"<strong class='text-warning'>Medical Alerts:</strong> {partner.medical_alerts}")
			if partner.dietary_restrictions:
				summary_parts.append(f"<strong>Diet:</strong> {partner.dietary_restrictions}")

			partner.full_medical_summary = "<br/>".join(summary_parts) if summary_parts else ""

	@api.depends('image_1920', 'gender', 'is_pet_owner', 'species_id', 'is_pet')
	def _compute_avatar_128(self):
		"""Override standard avatar computation"""
		for partner in self:
			if partner.image_1920:
				# Standard Odoo logic for uploaded images
				super(ResPartner, partner)._compute_avatar_128()
			elif partner.is_pet_owner:
				if partner.gender == 'male':
					partner.avatar_128 = self.env.company.male_owner_avatar
				elif partner.gender == 'female':
					partner.avatar_128 = self.env.company.female_owner_avatar
				else:
					super(ResPartner, partner)._compute_avatar_128()
			elif partner.is_pet and partner.species_id:
				if partner.species_id.image:
					partner.avatar_128 = partner.species_id.image
				else:
					partner.avatar_128 = False
			else:
				super(ResPartner, partner)._compute_avatar_128()

	# --- ESSENTIAL CONSTRAINTS ---
	@api.constrains('ths_deceased', 'ths_deceased_date')
	def _check_deceased_date_logic(self):
		"""Validate deceased date logic"""
		for partner in self:
			if partner.ths_deceased and not partner.ths_deceased_date:
				partner.ths_deceased_date = fields.Date.today()
			elif not partner.ths_deceased and partner.ths_deceased_date:
				partner.ths_deceased_date = False

	@api.constrains('pet_owner_id')
	def _check_pet_owner_logic(self):
		"""Prevent circular pet ownership"""
		for partner in self:
			if partner.is_pet and partner.pet_owner_id:
				if partner.pet_owner_id == partner:
					raise ValidationError(_("A pet cannot be its own owner"))
				if partner.pet_owner_id.is_pet:
					raise ValidationError(_("Pet owner must be a Pet Owner type, not another pet"))

	@api.constrains('ths_microchip')
	def _check_microchip_unique(self):
		"""Ensure microchip numbers are unique"""
		for partner in self:
			if partner.ths_microchip and partner.is_pet:
				existing = self.search([
					('ths_microchip', '=', partner.ths_microchip),
					('is_pet', '=', True),
					('id', '!=', partner.id)
				])
				if existing:
					raise ValidationError(_("Microchip number %s is already assigned to %s") %
										  (partner.ths_microchip, existing[0].name))

	# --- ONCHANGE METHODS ---
	@api.onchange('parent_id', 'is_pet')
	def _onchange_pet_owner_set_parent(self):
		"""Set pet_owner_id when owner is selected (for contact hierarchy)"""
		if self.is_pet and self.parent_id and not self.pet_owner_id:
			if self.parent_id.is_pet_owner:
				self.pet_owner_id = self.parent_id

	@api.onchange('ths_deceased')
	def _onchange_deceased_set_date(self):
		"""Auto-set deceased date when marking as deceased"""
		if self.ths_deceased and not self.ths_deceased_date:
			self.ths_deceased_date = fields.Date.today()
		elif not self.ths_deceased:
			self.ths_deceased_date = False

	@api.onchange('pet_owner_id')
	def _onchange_pet_owner_id_sync_info(self):
		"""Sync contact information from pet owner"""
		if self.pet_owner_id:
			# Trigger the re-computation of the depends fields directly on the current record.
			self._compute_owner_address_info()
			self._compute_owner_contact_info()
		else:
			# Clear fields if owner is unlinked in the UI
			self.street = False
			self.street2 = False
			self.city = False
			self.state_id = False
			self.zip = False
			self.country_id = False
			self.mobile = False
			self.phone = False
			self.email = False

	@api.onchange('species_id')
	def _onchange_species_clear_breed(self):
		"""Clear species breed ids on changing species"""
		self.breed_id = False

	# --- OVERRIDE CREATE/WRITE FOR BUSINESS LOGIC ---
	@api.model_create_multi
	def create(self, vals_list):
		pet_type = self.env.ref('ths_vet_base.partner_type_pet', raise_if_not_found=False)
		owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)

		for vals in vals_list:
			partner_type_id = vals.get('partner_type_id')

			if pet_type and partner_type_id == pet_type.id:
				vals['is_pet'] = True
				vals['is_company'] = False
				vals['supplier_rank'] = 0
				vals.setdefault('customer_rank', 0)
				if vals.get('pet_owner_id') and not vals.get('parent_id'):
					vals['parent_id'] = vals['pet_owner_id']

			elif owner_type and partner_type_id == owner_type.id:
				vals['is_pet_owner'] = True
				vals['is_company'] = False
				vals.setdefault('customer_rank', 1)

			# Handle deceased logic
			if vals.get('ths_deceased') and not vals.get('ths_deceased_date'):
				vals['ths_deceased_date'] = fields.Date.today()
			elif 'ths_deceased' in vals and not vals['ths_deceased']:
				vals['ths_deceased_date'] = False

		return super().create(vals_list)

	def write(self, vals):
		pet_type = self.env.ref('ths_vet_base.partner_type_pet', raise_if_not_found=False)
		owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)

		if 'partner_type_id' in vals:
			new_type_id = vals['partner_type_id']

			for partner in self:
				# Converting to pet
				if pet_type and new_type_id == pet_type.id and not partner.is_pet:
					vals.update({
						'is_pet': True,
						'is_company': False,
						'supplier_rank': 0
					})

				# Converting to pet owner
				elif owner_type and new_type_id == owner_type.id and not partner.is_pet_owner:
					vals.update({
						'is_pet_owner': True,
						'is_company': False
					})
					if not partner.customer_rank:
						vals['customer_rank'] = 1

			if 'pet_owner_id' in vals:
				for partner in self.filtered('is_pet'):
					if vals['pet_owner_id'] and not vals.get('parent_id', partner.parent_id.id):
						vals['parent_id'] = vals['pet_owner_id']

			# Deceased logic preserved here
			if vals.get('ths_deceased') and not vals.get('ths_deceased_date'):
				vals['ths_deceased_date'] = fields.Date.today()
			elif 'ths_deceased' in vals and not vals['ths_deceased']:
				vals['ths_deceased_date'] = False

		res = super().write(vals)

		# Recompute display name if any of the key pet-related fields changed
		if {'name', 'pet_owner_id', 'partner_type_id', 'is_pet'} & set(vals.keys()):
			self.invalidate_recordset(['display_name'])

		return res

	# --- BUSINESS ACTION METHODS ---

	def action_view_partner_pets(self):
		"""Action to view pets linked to this Pet Owner"""
		self.ensure_one()
		if not self.is_pet_owner:
			return {}

		pet_type = self.env.ref('ths_vet_base.partner_type_pet', raise_if_not_found=False)
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
				'default_is_pet': True,
				'show_pet_owner': True,
				'create': True,
			}
		}

	def action_view_partner_pet_owners(self):
		"""Action to view the pet owner for this pet"""
		self.ensure_one()
		if not self.is_pet:
			return {}

		pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)
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
				'show_pet_owner': False,
				'default_pet_ids': [(6, 0, [self.id])],
				'default_partner_type_id': pet_owner_type.id,
				'default_is_pet_owner': True,
				'default_is_pet': False,
				'create': True,
			}
		}

	def action_view_encounters(self):
		"""View the daily encounters for this Partner/Pet Owner/Pet"""
		self.ensure_one()
		if not (self.is_pet or self.is_pet_owner):
			return {}

		pet_owner_type = self.env.ref('ths_vet_base.partner_type_pet_owner', raise_if_not_found=False)
		pet_type = self.env.ref('ths_vet_base.partner_type_pet', raise_if_not_found=False)
		if not pet_owner_type and not pet_type:
			return {}

		if self.is_pet:
			return {
				'name': _('Encounters'),
				'type': 'ir.actions.act_window',
				'res_model': 'vet.encounter.header',
				'view_mode': 'list,form',
				'domain': [('patient_ids', 'in', self.id)],
				'target': 'current',
				'context': {
					'default_pet_owner_id': self.pet_owner_id.id,
					'default_patient_ids': [(6, 0, [self.id])],
					'default_partner_type_id': 'pet_type.id',
					'default_is_pet': True,
					'show_pet_owner': True,
					'create': True}
			}
		else:
			return {
				'name': _('Encounters'),
				'type': 'ir.actions.act_window',
				'res_model': 'vet.encounter.header',
				'view_mode': 'list,form',
				'domain': [('partner_id', '=', self.id)],
				'target': 'current',
				'context': {
					'default_pet_owner_id': self.id,
					'default_patient_ids': [],
					'default_partner_type_id': 'pet_owner_type.id',
					'default_is_pet': False,
					'default_is_pet_owner': True,
					'create': True}
			}

	def action_view_medical_history(self):
		"""View complete medical history for a pet"""
		self.ensure_one()
		if not self.is_pet:
			return {}

		return {
			'name': _('Medical History: %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
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
			'view_mode': 'list,calendar,form',
			'domain': domain,
			'context': context,
		}

	def action_view_boarding_stays(self):
		"""View boarding stays"""
		self.ensure_one()
		if not (self.is_pet or self.is_pet_owner):
			return {}

		if self.is_pet:
			domain = [('patient_ids', 'in', self.id)]
			context = {
				'default_partner_id': self.pet_owner_id.id if self.pet_owner_id else False,
				'default_patient_ids': [(6, 0, [self.id])],
			}
			name = _('Boarding Stays for %s') % self.name
		else:  # is_pet_owner
			domain = [('partner_id', '=', self.id)]
			context = {
				'default_partner_id': self.id,
			}
			name = _('Boarding Stays for %s') % self.name

		return {
			'name': name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.boarding.stay',
			'view_mode': 'list,form',
			'domain': domain,
			'context': context,
			'target': 'current',
		}

	def action_view_vaccinations(self):
		"""View vaccinations"""
		self.ensure_one()
		if not (self.is_pet or self.is_pet_owner):
			return {}

		if self.is_pet:
			domain = [('patient_ids', 'in', self.id)]
			context = {
				'default_partner_id': self.pet_owner_id.id if self.pet_owner_id else False,
				'default_patient_ids': [(6, 0, [self.id])],
			}
			name = _('Vaccinations for %s') % self.name
		else:  # is_pet_owner
			domain = [('partner_id', '=', self.id)]
			context = {
				'default_partner_id': self.id,
			}
			name = _('Vaccinations for %s') % self.name

		return {
			'name': name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.vaccination',
			'view_mode': 'list,form',
			'domain': domain,
			'context': context,
			'target': 'current',
		}

	def action_view_vaccination_reminders(self):
		"""View scheduled vaccination reminders for pets"""
		self.ensure_one()
		if not self.is_pet_owner:
			return {}
		domain = [('res_model', '=', 'res.partner'), ('res_id', 'in', self.pet_ids.ids), ('activity_type_id.xml_id', '=', 'mail.mail_activity_data_todo')]
		return {
			'name': _('Vaccination Reminders'),
			'type': 'ir.actions.act_window',
			'res_model': 'mail.activity',
			'view_mode': 'list,form',
			'domain': domain,
			'context': {'create': False}
		}

	def action_view_park_checkins(self):
		"""View Park Check-ins"""
		self.ensure_one()
		if not (self.is_pet or self.is_pet_owner):
			return {}

		if self.is_pet:
			domain = [('patient_ids', 'in', self.id)]
			context = {
				'default_partner_id': self.pet_owner_id.id if self.pet_owner_id else False,
				'default_patient_ids': [(6, 0, [self.id])],
			}
			name = _('Park Check-ins for %s') % self.name
		else:  # is_pet_owner
			domain = [('partner_id', '=', self.id)]
			context = {
				'default_partner_id': self.id,
			}
			name = _('Park Check-ins for %s') % self.name

		return {
			'name': name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.park.checkin',
			'view_mode': 'list,form',
			'domain': domain,
			'context': context,
			'target': 'current',
		}

	def action_view_pet_memberships(self):
		"""View memberships for this pet or pet owner"""
		self.ensure_one()

		if self.is_pet:
			domain = [('patient_ids', 'in', self.id)]
			context = {
				'default_partner_id': self.pet_owner_id.id if self.pet_owner_id else False,
				'default_patient_ids': [(6, 0, [self.id])],
			}
		elif self.is_pet_owner:
			domain = [('partner_id', '=', self.id)]
			context = {
				'default_partner_id': self.id,
			}
		else:
			return {}

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
			'context': context,
		}

	def action_view_documents(self):
		"""View pet photos/documents"""
		self.ensure_one()
		if not (self.is_pet or self.is_pet_owner):
			return {}

		folder_main = self.env.ref('ths_vet_base.documents_pet_folder', raise_if_not_found=False)
		folder_owner = self.env.ref('ths_vet_base.documents_pet_owner_info', raise_if_not_found=False)
		tag_pets = self.env.ref('ths_vet_base.documents_tag_pets', raise_if_not_found=False)
		tag_pet_owner = self.env.ref('ths_vet_base.documents_tag_pet_owner', raise_if_not_found=False)

		if self.is_pet:
			default_folder = folder_main.id if folder_main else False
			default_tag = tag_pets.id if tag_pets else False
			domain = [
				'|',
				'&',
				'&', ('type', '=', 'folder'),
				('folder_id', '=', folder_main.id if folder_main else False),
				('id', '!=', folder_owner.id if folder_owner else False),
				'&', ('res_model', '=', 'res.partner'), ('res_id', '=', self.id)
			]
			window_name = _('Photos/Documents for %s') % self.name
			default_folder = folder_main.id if folder_main else False

		else:
			default_folder = folder_owner.id if folder_owner else False
			default_tag = tag_pet_owner.id if tag_pet_owner else False
			pet_ids = self.env['res.partner'].search([
				('pet_owner_id', '=', self.id),
				('is_pet', '=', True)
			]).ids

			domain = [
				'|',
				'&', ('type', '=', 'folder'), ('folder_id', '=', folder_main.id if folder_main else False),
				'|',
				'&', ('type', '=', 'folder'), ('id', '=', folder_owner.id if folder_owner else False),
				'|',
				'&', ('res_model', '=', 'res.partner'), ('res_id', '=', self.id),
				'&', ('res_model', '=', 'res.partner'), ('res_id', 'in', pet_ids)
			]
			window_name = _('Photos/Documents')
			default_folder = folder_owner.id if folder_owner else False

		context = {
			'default_res_model': 'res.partner',
			'default_res_id': self.id,
			'default_partner_id': self.id,
			'default_folder_id': default_folder,
			'default_tag_ids': [(6, 0, [default_tag])] if default_tag else False,
			'searchpanel_default_folder_id': default_folder,
			'res_model': 'res.partner',
			'partner_id': self.id,
		}

		return {
			'name': window_name,
			'type': 'ir.actions.act_window',
			'res_model': 'documents.document',
			'view_mode': 'kanban,list,form',
			'target': 'current',
			'domain': domain,
			'context': context
		}

	def action_schedule_appointment(self):
		"""Quick action to schedule appointment for this pet/owner"""
		self.ensure_one()

		context = {}
		if self.is_pet:
			context.update({
				'default_pet_owner_id': self.pet_owner_id.id if self.pet_owner_id else False,
				'default_patient_ids': [(6, 0, [self.id])],
			})
		elif self.is_pet_owner:
			context['default_pet_owner_id'] = self.id

		return {
			'name': _('Schedule Appointment'),
			'type': 'ir.actions.act_window',
			'res_model': 'calendar.event',
			'view_mode': 'form',
			'target': 'new',
			'context': context
		}

	# --- HELPER METHODS ---

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

	@api.depends('ths_dob', 'ths_deceased', 'ths_deceased_date')
	def _compute_ths_age(self):
		"""Extended age calculation that handles deceased pets"""
		super()._compute_ths_age()

		for partner in self:
			if partner.ths_deceased and partner.ths_deceased_date and partner.ths_dob:
				# Recalculate with deceased date
				delta = relativedelta(partner.ths_deceased_date, partner.ths_dob)

				parts = []
				if delta.years: parts.append(f"{delta.years}y")
				if delta.months: parts.append(f"{delta.months}m")
				if delta.days: parts.append(f"{delta.days}d")

				partner.ths_age = " ".join(parts) or "0d"

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
			('appointment_status', 'in', ['request', 'booked'])
		])

		return self.env['calendar.event'].search(domain, order='start asc', limit=1)

	def _get_health_status(self):
		"""Get overall health status indicator for pets"""
		self.ensure_one()
		if not self.is_pet:
			return 'unknown'

		if self.ths_deceased:
			return 'deceased'

		# Check if vaccinations are up to date
		overdue_vaccinations = self.env['vet.vaccination'].search_count([
			('patient_ids', 'in', self.id),
			('expiry_date', '<', fields.Date.today())
		])

		if overdue_vaccinations:
			return 'needs_attention'

		# Check recent visits
		if self.last_visit_date:
			days_since_visit = (fields.Date.today() - self.last_visit_date).days
			if days_since_visit > 365:  # More than a year
				return 'overdue_checkup'

		return 'healthy'

	@api.model
	def search_pets_by_owner(self, owner_name):
		"""Search pets by owner name - utility method"""
		return self.search([
			('is_pet', '=', True),
			('pet_owner_id.name', 'ilike', owner_name)
		])

	@api.model
	def get_pets_needing_vaccination(self):
		"""Get pets with overdue vaccinations"""
		overdue_vaccination_pet_ids = self.env['vet.vaccination'].search([
			('expiry_date', '<', fields.Date.today())
		]).mapped('patient_ids.id')

		return self.browse(overdue_vaccination_pet_ids)


# TODO: Future enhancements
# TODO: Add integration with pet insurance systems
# TODO: Add automatic vaccination reminders
# TODO: Add pet photo management
# TODO: Add emergency contact notification system

class ResCompany(models.Model):
	_inherit = 'res.company'

	male_owner_avatar = fields.Binary(string='Default Male Owner Avatar')
	female_owner_avatar = fields.Binary(string='Default Female Owner Avatar')


class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	module_ths_vet_base = fields.Boolean(string='Veterinary Management')
	default_appointment_duration = fields.Integer(string='Default Appointment Duration (minutes)', default_model='calendar.event',
												  config_parameter='ths_vet_base.default_appointment_duration', default=30)
	enable_automatic_reminders = fields.Boolean(string='Enable Automatic Appointment Reminders', config_parameter='ths_vet_base.enable_automatic_reminders')
	enable_whatsapp_reminders = fields.Boolean(string='Enable WhatsApp Reminders', config_parameter='ths_vet_base.enable_whatsapp_reminders', default=True)

	require_microchip_for_pets = fields.Boolean(string='Require Microchip for Pet Registration', config_parameter='ths_vet_base.require_microchip_for_pets', default=False)

	male_owner_avatar = fields.Binary(related='company_id.male_owner_avatar', readonly=False, string='Default Male Pet Owner Avatar')
	female_owner_avatar = fields.Binary(related='company_id.female_owner_avatar', readonly=False, string='Default Female Pet Owner Avatar')

# TODO: Add integration with external pet registries
# TODO: Implement pet photo facial recognition
# TODO: Add GPS tracking integration for lost pets
# TODO: Create pet genealogy/breeding tracking