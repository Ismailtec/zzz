# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

import logging

_logger = logging.getLogger(__name__)


class ThsPendingPosItem(models.Model):
	_inherit = 'ths.pending.pos.item'

	partner_id = fields.Many2one(
		'res.partner',
		string='Pet Owner (Billing)',
		domain="[('partner_type_id.name', '=', 'Pet Owner')]",
		context={'is_pet': False},
		required=True,
		index=True,
		tracking=True,
		help="Pet owner who will be billed for this service. This is the billing customer in veterinary practice."
	)

	patient_ids = fields.Many2many(
		'res.partner',
		'ths_pending_pos_patient_rel',
		'encounter_id',
		'patient_id',
		string='Pets',
		domain="[('partner_type_id', '=', 'Pet')]",
		context={'is_pet': True},
		readonly=False,
		store=True,
		help="Pets receiving this service."
	)

	pet_owner_id = fields.Many2one(
		'res.partner',
		string='Pet Owner',
		related='partner_id',
		store=True,
		readonly=True,
		help="Pet owner responsible for billing (same as partner_id in vet context)."
	)

	patient_ids_domain = fields.Char(
		compute='_compute_patients_domain',
		store=False
	)

	available_patient_ids_domain = fields.Char(
		compute='_compute_available_patient_domain',
		store=False
	)

	boarding_stay_id = fields.Many2one(
		'vet.boarding.stay',
		string='Source Boarding Stay',
		ondelete='cascade',
		index=True,
		copy=False,
	)

	@api.depends('partner_id')
	def _compute_patients_domain(self):
		for rec in self:
			if rec.partner_id and rec.partner_id.partner_type_id.name == 'Pet Owner':
				rec.patient_ids_domain = str([
					('pet_owner_id', '=', rec.partner_id.id),
					('partner_type_id', '=', 'Pet')
				])
			else:
				rec.patient_ids_domain = str([('partner_type_id', '=', 'Pet')])

	@api.depends('pet_owner_id', 'encounter_id.patient_ids')
	def _compute_available_patient_domain(self):
		for rec in self:
			domain = [('partner_type_id.name', '=', 'Pet')]

			filtered_by_encounter_pets = False

			if rec.encounter_id and rec.encounter_id.patient_ids:
				encounter_pet_ids = rec.encounter_id.patient_ids.ids
				if encounter_pet_ids:
					domain.append(('id', 'in', encounter_pet_ids))
					filtered_by_encounter_pets = True

			if not filtered_by_encounter_pets and rec.pet_owner_id:
				domain.append(('pet_owner_id', '=', rec.pet_owner_id.id))

			rec.available_patient_ids_domain = str(domain)

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		if self.partner_id:
			self.pet_owner_id = self.partner_id

	@api.onchange('patient_ids')
	def _onchange_patient_sync_owner(self):
		if self.patient_ids and self.patient_ids.pet_owner_id:
			if not self.partner_id:
				self.partner_id = self.patient_ids.pet_owner_id
			elif self.partner_id != self.patient_ids.pet_owner_id:
				return {
					'warning': {
						'title': _('Pet Owner Mismatch'),
						'message': _(
							'Pet "%s" belongs to "%s", but billing customer is set to "%s". '
							'Please select a pet that belongs to the billing customer.',
							self.patient_ids.name,
							self.patient_ids.pet_owner_id.name,
							self.partner_id.name
						)
					}
				}
		return None

	@api.onchange('encounter_id')
	def _onchange_encounter_sync_data(self):
		if self.encounter_id:
			if hasattr(self.encounter_id, 'partner_id') and self.encounter_id.pet_owner_id:
				if not self.encounter_id.pet_owner_id:
					self.partner_id = self.encounter_id.pet_owner_id
				if not self.practitioner_id and self.encounter_id.practitioner_id:
					self.practitioner_id = self.encounter_id.practitioner_id

	@api.constrains('partner_id', 'patient_ids')
	def _check_vet_billing_consistency(self):
		for item in self:
			if item.partner_id and item.partner_id.partner_type_id.name != 'Pet Owner':
				raise ValidationError(_(
					"Billing customer must be a Pet Owner. "
					"Current: %s (%s)",
					item.partner_id.name,
					item.partner_id.partner_type_id.name
				))
			if item.patient_ids and item.patient_ids.partner_type_id.name != 'Pet':
				raise ValidationError(_(
					"Patient must be a Pet. "
					"Current: %s (%s)",
					item.patient_ids.name,
					item.patient_ids.partner_type_id.name
				))
			if item.partner_id and item.patient_ids and item.patient_ids.pet_owner_id != item.partner_id:
				raise ValidationError(_(
					"Pet '%s' does not belong to Pet Owner '%s'. "
					"Pet's actual owner: %s",
					item.patient_ids.name,
					item.partner_id.name,
					item.patient_ids.pet_owner_id.name if item.patient_ids.pet_owner_id else 'None'
				))

	def create(self, vals_list):
		processed_vals_list = []
		for vals in vals_list:
			if 'patient_ids' in vals and not vals.get('partner_id'):
				patient_ids_data = vals['patient_ids']
				first_patient_id = False
				if patient_ids_data and isinstance(patient_ids_data, list):
					for command in patient_ids_data:
						if command[0] == 6 and command[1] == 0:
							if command[2] and isinstance(command[2], list):
								first_patient_id = command[2][0]
								break
						elif command[0] == 4:
							first_patient_id = command[1]
							break
				if first_patient_id:
					patient_record = self.env['res.partner'].browse(first_patient_id)
					if patient_record.exists() and patient_record.pet_owner_id:
						vals['partner_id'] = patient_record.pet_owner_id.id
			processed_vals_list.append(vals)
		new_items = super().create(processed_vals_list)
		return new_items

	def _get_billing_summary(self):
		self.ensure_one()
		summary = {
			'pet_owner': self.partner_id.name if self.partner_id else 'No Owner',
			'pet_name': self.patient_ids.name if self.patient_ids else 'No Pet',
			'service': self.product_id.name if self.product_id else 'No Service',
			'amount': self.qty * self.product_id.lst_price * (1 - self.discount / 100) if self.product_id else 0.0,
			'practitioner': self.practitioner_id.name if self.practitioner_id else 'No Practitioner'
		}
		return summary

	def _format_display_name(self):
		self.ensure_one()
		parts = []
		if self.patient_ids:
			parts.append(f"Pet: {self.patient_ids.name}")
		if self.product_id:
			parts.append(f"Service: {self.product_id.name}")
		if self.partner_id:
			parts.append(f"Owner: {self.partner_id.name}")
		return " | ".join(parts) if parts else self.name or f"Pending Item #{self.id}"

	def action_view_pet_medical_history(self):
		self.ensure_one()
		if not self.patient_ids:
			return {}
		return {
			'name': _('Medical History: %s') % self.patient_ids.name,
			'type': 'ir.actions.act_window',
			'res_model': 'ths.medical.base.encounter',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', [self.patient_ids.id])],
			'context': {'search_default_groupby_date': 1, 'create': False},
		}

	def action_view_owner_billing_history(self):
		self.ensure_one()
		if not self.partner_id:
			return {}
		return {
			'name': _('Billing History: %s') % self.partner_id.name,
			'type': 'ir.actions.act_window',
			'res_model': 'ths.pending.pos.item',
			'view_mode': 'list,form',
			'domain': [('partner_id', '=', self.partner_id.id)],
			'context': {'search_default_groupby_state': 1, 'create': False},
		}

	def action_create_follow_up_service(self):
		self.ensure_one()
		if not self.patient_ids or not self.partner_id:
			raise UserError(_("Pet and Pet Owner must be set to create follow-up service."))
		return {
			'name': _('Create Follow-up Service'),
			'type': 'ir.actions.act_window',
			'res_model': 'ths.pending.pos.item',
			'view_mode': 'form',
			'target': 'new',
			'context': {
				'default_partner_id': self.partner_id.id,
				'default_patient_ids': self.patient_ids.id,
				'default_practitioner_id': self.practitioner_id.id,
				'default_room_id': self.room_id.id,
				'default_encounter_id': self.encounter_id.id,
				'default_notes': f"Follow-up for: {self.product_id.name if self.product_id else 'Previous Service'}",
			}
		}

	def action_reset_to_pending_from_pos(self):
		for item in self:
			if item.partner_id and item.patient_ids:
				if item.patient_ids.pet_owner_id != item.partner_id:
					raise UserError(_(
						"Cannot reset item: Pet '%s' does not belong to Pet Owner '%s'",
						item.patient_ids.name,
						item.partner_id.name
					))
		return super().action_reset_to_pending_from_pos()

	def _prepare_pos_order_line_data(self):
		data = super()._prepare_pos_order_line_data()
		data.update({
			'patient_ids': self.patient_ids.id,
			'pet_owner_id': self.partner_id.id,
			'practitioner_id': self.practitioner_id.id if self.practitioner_id.id else False,
			'room_id': self.room_id.id if self.room_id else False,
		})
		return data

	def _get_vet_service_summary(self):
		self.ensure_one()
		return {
			'service_type': 'Veterinary Service',
			'pet_info': f"{self.patient_ids.name}" if self.patient_ids else 'Unknown Pet',
			'owner_info': self.partner_id.name if self.partner_id else 'Unknown Owner',
			'practitioner_info': self.practitioner_id.name if self.practitioner_id else 'Unknown Practitioner',
			'room_info': self.room_id.name if self.room_id else 'Unknown Room',
			'billing_amount': self.qty * self.product_id.lst_price * (
						1 - self.discount / 100) if self.product_id else 0.0,
			'discount_amount': self.qty * (self.discount / 100) if self.product_id else 0.0,
			'commission_amount': (self.qty * self.product_id.lst_price * (1 - self.discount / 100)) * (
					self.commission_pct / 100) if self.product_id and self.commission_pct else 0,
		}

# TODO: Add pet-specific pricing rules integration
# TODO: Implement multi-pet service bundling discounts
# TODO: Add pet weight-based medication dosage calculations
# TODO: Implement species-specific service filtering