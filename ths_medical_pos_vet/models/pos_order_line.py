# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

import logging

from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosOrderLine(models.Model):
	_inherit = 'pos.order.line'

	# For Veterinary medical
	patient_ids = fields.Many2many(
		'res.partner',
		'ths_pos_order_line_patient_rel',
		'pos_order_line_id',
		'patient_id',
		string='Pets',
		domain="[('partner_type_id.name', '=', 'Pet')]",
		help="Patients who received this service."
	)

	pet_owner_id = fields.Many2one(
		comodel_name='res.partner',
		string='Pet Owner',
		related='order_id.partner_id',
		store=True,
		readonly=True,
		help="The owner of the pet receiving this service."
	)

	# === VET-SPECIFIC CONSTRAINTS ===
	@api.constrains('patient_ids', 'order_id')
	def _check_vet_pet_owner_consistency(self):
		"""  Vet override: Ensure pets belong to the order's pet owner
			Replaces base medical constraint with vet-specific logic  """
		for line in self:
			if line.order_id.pet_owner_id:
				# Check single pet assignment
				if line.patient_ids:
					if line.patient_ids.pet_owner_id != line.order_id.pet_owner_id:
						raise ValidationError(
							_("Pet '%s' does not belong to pet owner '%s'") %
							(line.patient_ids.name, line.order_id.pet_owner_id.name)
						)

				# Check multiple pets assignment
				if line.patient_ids:
					for pet in line.patient_ids:
						if pet.pet_owner_id != line.order_id.pet_owner_id:
							raise ValidationError(
								_("Pet '%s' does not belong to pet owner '%s'") %
								(pet.name, line.order_id.pet_owner_id.name)
							)

	# === ONCHANGE METHODS FOR VET ===

	@api.onchange('patient_ids')
	def _onchange_vet_patients_sync(self):
		"""Sync first pet from patient_ids to single pet field"""
		if self.patient_ids:
			# Set first pet as primary
			self.patient_ids = self.patient_ids[0]
		else:
			# Clear single pet if no pets selected
			self.patient_ids = False

	# === HELPER METHODS FOR VET ===

	def _get_medical_context_summary(self):
		"""  Vet override: Enhanced medical context summary with pet-specific information  """
		self.ensure_one()
		summary_parts = []

		# Pet information with species
		if self.patient_ids:
			pet_info = []
			for pet in self.patient_ids:
				pet_name = pet.name
				if pet.species_id:
					pet_name += f" ({pet.species_id.name})"
				pet_info.append(pet_name)
			summary_parts.append(f"Pets: {', '.join(pet_info)}")

		# Pet owner information
		if self.pet_owner_id:
			summary_parts.append(f"Owner: {self.pet_owner_id.name}")

		# Provider information
		if self.practitioner_id:
			summary_parts.append(f"Provider: {self.practitioner_id.name}")

		# Room information
		if self.room_id:
			summary_parts.append(f"Room: {self.room_id.name}")

		# Commission information
		if self.ths_commission_pct:
			summary_parts.append(f"Commission: {self.ths_commission_pct}%")

		# Encounter information
		if self.encounter_id:
			summary_parts.append(f"Encounter: {self.encounter_id.name}")

		return " | ".join(summary_parts) if summary_parts else "No vet context"

	def _get_patient_info_for_reporting(self):
		"""  Vet override: Get pet information formatted for reporting with species data  """
		self.ensure_one()
		if not self.patient_ids:
			return "No pets assigned"

		info_parts = []
		for pet in self.patient_ids:
			pet_info = [pet.name]

			# Add species information
			if pet.species_id:
				pet_info.append(f"Species: {pet.species_id.name}")

			# Add pet owner information
			if pet.pet_owner_id:
				pet_info.append(f"Owner: {pet.pet_owner_id.name}")

			# Add reference number if available
			if pet.ref:
				pet_info.append(f"Ref: {pet.ref}")

			# Add membership status
			membership_status = self.order_id._get_pet_membership_status(pet.id)
			if membership_status == 'active':
				pet_info.append("Member")

			info_parts.append(" • ".join(pet_info))

		return " | ".join(info_parts)

	# === VET-SPECIFIC INTEGRATION METHODS ===

	# def _apply_pet_membership_discount(self):
	# 	"""  Apply membership discount if pet has active membership  """
	# 	self.ensure_one()
	#
	# 	if not self.patient_ids:
	# 		return False
	#
	# 	for pet in self.patient_ids:
	# 		if self._get_pet_membership_status(pet.id) == 'active':
	# 			# Find membership discount rule
	# 			membership = self.env['vet.pet.membership'].search([
	# 				('patient_ids', 'in', [pet.id]),
	# 				('state', '=', 'running'),
	# 				('is_paid', '=', True)
	# 			], limit=1)
	#
	# 			if membership and membership.discount_percentage:
	# 				# Apply discount (this would need to be integrated with POS discount system)
	# 				discount_amount = (self.price_unit * membership.discount_percentage) / 100
	# 				_logger.info(f"Applied {membership.discount_percentage}% membership discount to line {self.id}")
	# 				return discount_amount
	#
	# 	return False

	# def _link_to_park_checkin(self):
	# 	"""Link this service to active park check-in if applicable"""
	# 	self.ensure_one()
	#
	# 	if not self.patient_ids:
	# 		return False
	#
	# 	for pet in self.patient_ids:
	# 		# Find active park check-in for this pet
	# 		park_checkin = self.env['park.checkin'].search([
	# 			('patient_ids', '=', pet.id),
	# 			('state', '=', 'checked_in'),
	# 			('encounter_id', '=', self.encounter_id.id if self.encounter_id else False)
	# 		], limit=1)
	#
	# 		if park_checkin:
	# 			# Link service to park check-in
	# 			park_checkin.write({
	# 				'pos_order_line_id': self.id,
	# 				'service_provided': True
	# 			})
	# 			_logger.info(f"Linked service line {self.id} to park check-in {park_checkin.id}")
	# 			return True
	#
	# 	return False

	# === REPORTING METHODS ===

	def get_vet_line_summary(self):
		"""Get veterinary-specific line summary"""
		self.ensure_one()

		summary = {
			'product': self.product_id.name,
			'quantity': self.qty,
			'price': self.price_unit,
			'pets': [(p.id, p.name, p.species_id.name if p.species_id else None) for p in self.patient_ids],
			'pet_owner': self.pet_owner_id.name if self.pet_owner_id else None,
			'practitioner': self.practitioner_id.name if self.practitioner_id else None,
			'room': self.room_id.name if self.room_id else None,
			'commission': self.ths_commission_pct,
			# 'membership_discount': self._apply_pet_membership_discount(),
		}

		return summary

# TODO: Add pet medical history integration
# TODO: Add species-specific service validation
# TODO: Add multi-pet service bundling discounts
# TODO: Add park check-in service automation


# @api.model
# def _load_pos_data_fields(self, config_id):
# 	"""  Override to include medical-specific fields in POS data export  """
# 	line_data = super()._load_pos_data_fields(config_id)
# 	# Add medical-specific fields to the export
# 	line_data.extend([
# 		'pet_owner_id',
# 	])
# 	return line_data