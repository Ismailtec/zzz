# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, Command
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ThsMedicalBaseEncounter(models.Model):
	_inherit = 'ths.medical.base.encounter'

	# Override patient_ids for vet context - now refers to pets
	patient_ids = fields.Many2many(
		'res.partner',
		'medical_encounter_patient_rel',
		'encounter_id',
		'patient_id',
		string='Pets',  # Relabeled for veterinary context
		domain="[('partner_type_id.name', '=', 'Pet'),('pet_owner_id', '=?', partner_id.id)]",
		context={'is_pet': True},
		store=True,
		help="Pets receiving veterinary care in this encounter."
	)

	# Pet Owner field - computed from appointment or manually set
	pet_owner_id = fields.Many2one(
		'res.partner',
		string='Pet Owner',
		context={'is_pet': False},
		store=True,
		readonly=False,
		domain="[('partner_type_id.name','=','Pet Owner')]",
		index=True,
		tracking=True,
		help="Pet owner responsible for billing. Usually inherited from appointment.",
	)

	# Computed domain string for pets based on selected owner
	patient_ids_domain = fields.Char(
		compute='_compute_patient_domain',
		store=False
	)

	default_patient_ids_enc = fields.Many2many(
		'res.partner',
		string="Default Patients from Encounter",
		compute='_compute_default_patient_ids_enc',
		store=False,
		readonly=True,
		help="Provides the list of patients from the current encounter to default on all O2M fields."
	)

	boarding_ids = fields.One2many(
		'vet.boarding.stay',
		'encounter_id',
		string='Boarding Stays',
		help="All boarding stays for this encounter"
	)
	vaccination_ids = fields.One2many(
		'vet.vaccination',
		'encounter_id',
		string='Vaccinations',
		help="All vaccinations for this encounter"
	)
	park_checkin_ids = fields.One2many(
		'park.checkin',
		'encounter_id',
		string='Park Check-ins',
		help="All park visits for this encounter"
	)

	# Multi-pet summary fields
	total_pets_count = fields.Integer(
		string='Total Pets',
		compute='_compute_pets_summary',
		store=False,
		readonly=True,
		help="Total number of pets in this encounter"
	)

	pets_summary = fields.Char(
		string='Pets Summary',
		compute='_compute_pets_summary',
		store=False,
		readonly=True,
		help="Summary of all pets in this encounter"
	)

	all_pets_species = fields.Char(
		string='All Species',
		compute='_compute_pets_summary',
		store=False,
		readonly=True,
		help="All species represented in this encounter"
	)

	pet_badge_data = fields.Json(string="Pet Badge Data", compute="_compute_pet_badge_data", store=True)

	# pet_names_display = fields.Char(
	#     string="Pet Names Display",
	#     compute="_compute_pet_names_display",
	#     store=True,
	# )
	# pet_badge_display = fields.Char(
	# 	string="Pet Names with species Display",
	# 	compute="_compute_pet_badge_display",
	# 	store=True,
	# )

	@api.depends('partner_id')
	def _compute_patient_domain(self):
		"""Compute domain for pets based on selected owner"""
		for rec in self:
			if rec.partner_id:
				# Filter pets by selected owner
				rec.patient_ids_domain = str([
					('pet_owner_id', '=', rec.partner_id.id),
					('partner_type_id.name', '=', 'Pet')
				])
			else:
				# Show all pets when no owner selected
				rec.patient_ids_domain = str([('partner_type_id.name', '=', 'Pet')])

	@api.depends('patient_ids')
	def _compute_default_patient_ids_enc(self):
		"""  Computes the list of patient IDs from the current encounter to be used as defaults for other O2M fields. """
		for rec in self:
			# Command.set([ID1, ID2, ...]) is used to set Many2many fields with a list of IDs.
			rec.default_patient_ids_enc = [Command.set(rec.patient_ids.ids)]

	# --- CORE VET LOGIC: INHERIT PET OWNER FROM PATIENT ---
	@api.depends('patient_ids.pet_owner_id')
	def _compute_pet_owner_from_patients(self):
		"""
		Compute pet owner from selected pets - ensures consistency
		"""
		for encounter in self:
			if encounter.patient_ids:
				owners = encounter.patient_ids.mapped('pet_owner_id')
				unique_owners = list(set(owners.ids)) if owners else []

				if len(unique_owners) == 1:
					encounter.pet_owner_id = owners[0]
					encounter.partner_id = owners[0]  # Sync billing customer
				elif len(unique_owners) > 1:
					# Multiple owners - clear to force manual selection
					encounter.pet_owner_id = False
				else:
					encounter.pet_owner_id = False

	@api.model
	def _find_or_create_daily_encounter(
			self, partner_id, patient_ids=None, encounter_date=None, practitioner_id=None, room_id=None):
		"""Override for vet-specific encounter creation"""
		encounter = super()._find_or_create_daily_encounter(
			partner_id, patient_ids, encounter_date, practitioner_id, room_id
		)

		pet_owner_id = partner_id

		# Update pet_owner_id on the encounter if it's provided and different
		if pet_owner_id and (not encounter.pet_owner_id or encounter.pet_owner_id.id != pet_owner_id):
			encounter.write({'pet_owner_id': pet_owner_id})

		return encounter

	# --- PET DETAILS COMPUTATION ---
	# @api.depends('patient_ids')
	# def _compute_primary_pet_details(self):
	# 	"""Compute details from first/primary pet for backward compatibility"""
	# 	for encounter in self:
	# 		primary_pet = encounter.patient_ids[:1]  # Take first pet
	# 		if primary_pet:
	# 			encounter.species = getattr(primary_pet, 'species_id', False)
	# 			encounter.breed = getattr(primary_pet, 'breed_id', False)
	# 			encounter.pet_age = getattr(primary_pet, 'ths_age', False)
	# 			encounter.pet_gender = getattr(primary_pet, 'gender', False)
	# 		else:
	# 			encounter.species = False
	# 			encounter.breed = False
	# 			encounter.pet_age = False
	# 			encounter.pet_gender = False

	@api.depends('patient_ids', 'patient_ids.name', 'patient_ids.species_id', 'patient_ids.species_id.name')
	def _compute_pets_summary(self):
		for encounter in self:
			pets = encounter.patient_ids
			encounter.total_pets_count = len(pets)

			if not pets:
				encounter.pets_summary = "No pets"
				encounter.all_pets_species = ""
			elif len(pets) == 1:
				encounter.pets_summary = pets[0].name or ''
				species_name = pets[0].species_id.name if pets[0].species_id and hasattr(pets[0].species_id,
																								 'name') else ''
				encounter.all_pets_species = species_name
			else:
				names = pets[:3].mapped('name')
				if len(pets) > 3:
					encounter.pets_summary = f"{', '.join(names)} and {len(pets) - 3} more"
				else:
					encounter.pets_summary = ', '.join(names)

				species = [s.name for s in pets.mapped('species_id') if s and hasattr(s, 'name')]
				encounter.all_pets_species = ', '.join(set(species)) if species else ''

	# --- ONCHANGE FOR MANUAL ADJUSTMENTS ---
	@api.onchange('pet_owner_id')
	def _onchange_pet_owner_sync_billing(self):
		"""When pet owner changes manually, sync with billing customer"""
		if self.pet_owner_id:
			self.partner_id = self.pet_owner_id

	@api.onchange('patient_ids')
	def _onchange_pets_validate_owner(self):
		"""Validate that all pets belong to the same owner"""
		if self.patient_ids:
			owners = self.patient_ids.mapped('pet_owner_id')
			unique_owners = list(set(owners.ids)) if owners else []

			if len(unique_owners) > 1:
				return {
					'warning': {
						'title': _('Multiple Pet Owners'),
						'message': _(
							'Selected pets belong to different owners. All pets in an encounter must belong to the same owner.')
					}
				}
			elif len(unique_owners) == 1 and not self.pet_owner_id:
				# Auto-set owner if not already set
				self.pet_owner_id = owners[0]
				self.partner_id = owners[0]

		return None

	# @api.depends('patient_ids.name')
	# def _compute_pet_names_display(self):
	#     for rec in self:
	#         rec.pet_names_display = ', '.join(rec.patient_ids.mapped('name')) if rec.patient_ids else ''

	@api.constrains('patient_ids', 'pet_owner_id', 'state')
	def _check_vet_encounter_consistency(self):
		"""Validate vet encounter consistency - relaxed for in_progress state"""
		for encounter in self:
			# Only strict validation for done encounters
			if encounter.state == 'done' and encounter.patient_ids and encounter.pet_owner_id:
				wrong_owner_pets = encounter.patient_ids.filtered(
					lambda p: p.pet_owner_id != encounter.pet_owner_id
				)
				if wrong_owner_pets:
					raise ValidationError(_(
						"All pets must belong to the same owner. "
						"Pets %s belong to different owners.",
						', '.join(wrong_owner_pets.mapped('name'))
					))

			# Ensure billing customer is set for encounters with pets
			if encounter.patient_ids and not encounter.partner_id:
				raise ValidationError(_(
					"Pet Owner (billing customer) must be set for encounters with pets."
				))

	# @api.depends('pet_badge_data')
	# def _compute_pet_badge_display(self):
	# 	"""Generate display name summary for encounter pets"""
	# 	for rec in self:
	# 		names = [
	# 			f"{entry.get('name')} ({entry.get('species')})"
	# 			for entry in rec.pet_badge_data
	# 		]
	# 		rec.pet_badge_display = ', '.join(names)

	@api.depends('patient_ids')
	def _compute_pet_badge_data(self):
		for rec in self:
			badge_data = []
			for pet in rec.patient_ids:
				if pet and hasattr(pet, 'pet_badge_data') and pet.pet_badge_data:
					badge_data.extend(pet.pet_badge_data)
			rec.pet_badge_data = badge_data

	# --- VET-SPECIFIC BUSINESS METHODS ---
	# def _get_primary_pet(self):
	# 	"""Get the primary/first pet for this encounter"""
	# 	self.ensure_one()
	# 	return self.patient_ids[0] if self.patient_ids else False

	def _get_all_pets_species(self):
		"""Get unique species of all pets in this encounter"""
		self.ensure_one()
		return self.patient_ids.mapped('species_id').mapped('name')

	def action_view_pet_medical_histories(self):
		"""View individual medical histories for all pets in this encounter"""
		self.ensure_one()
		if not self.patient_ids:
			return {}

		return {
			'name': _('Pet Medical Histories'),
			'type': 'ir.actions.act_window',
			'res_model': 'ths.medical.base.encounter',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', self.patient_ids.ids)],
			'context': {
				'search_default_groupby_patients': 1,
				'create': False,
			}
		}

	def action_view_boarding_stays(self):
		"""View boarding stays for this encounter"""
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
		"""View vaccinations for this encounter"""
		self.ensure_one()
		return {
			'name': _('Vaccinations'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.vaccination',
			'view_mode': 'list,form',
			'domain': [('encounter_id', '=', self.id)],
			'context': {'create': False}
		}

	# TODO: Add vet-specific encounter methods
	def action_create_vaccination_records(self):
		"""Create vaccination records for pets in this encounter"""
		# TODO: Implement vaccination record creation
		pass

	def action_schedule_follow_up_for_pets(self):
		"""Schedule follow-up appointments for pets"""
		# TODO: Implement follow-up scheduling for individual pets
		pass

	def action_create_treatment_plan(self):
		"""Create treatment plan for pets"""
		# TODO: Implement treatment plan creation
		pass

# TODO: Add breed-specific service recommendations
# TODO: Implement multi-pet family discount calculations
# TODO: Add pet weight/size tracking per encounter
# TODO: Implement species-specific treatment protocols
# TODO: Add pet photo capture integration per encounter
# TODO: Implement vaccination reminder system based on encounter history
# TODO: Add pet behavioral notes tracking
# TODO: Implement cross-pet medical history analysis