# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, Command
from odoo.exceptions import ValidationError, UserError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
	_inherit = 'pos.order'

	# Vet-specific fields
	pet_owner_id = fields.Many2one(
		'res.partner',
		string='Pet Owner',
		domain="[('partner_type_id.name', '=', 'Pet Owner')]",
		help="Pet owner responsible for billing"
	)
	patient_ids = fields.Many2many(
		'res.partner',
		'pos_order_patient_rel',
		'order_id',
		'patient_id',
		string='Pets',
		domain="[('partner_type_id.name', '=', 'Pet')]",
		help="Pets receiving services in this order"
	)
	encounter_id = fields.Many2one('ths.medical.base.encounter', string='Encounter', index=True)
	practitioner_id = fields.Many2one('appointment.resource', string='Practitioner')
	room_id = fields.Many2one('appointment.resource', string='Room')

	def _get_encounter_domain(self, partner_id, encounter_date):
		"""Vet override: Find encounters for pet owners"""
		return [
			('pet_owner_id', '=', partner_id),
			('encounter_date', '=', encounter_date)
		]

	def _get_encounter_vals(self, partner_id, encounter_date):
		"""Vet override: Create encounters for pet owners"""
		pet_owner = self.env['res.partner'].browse(partner_id)
		encounter_vals = {
			'partner_id': partner_id,
			'pet_owner_id': partner_id,
			'encounter_date': encounter_date,
			'state': 'in_progress',
			'patient_ids': [(6, 0, pet_owner.pet_ids.ids)] if pet_owner.pet_ids else [(5,)]
		}
		return encounter_vals

	@api.model
	def _create_new_order_popup(self, partner_id):
		"""Create popup data for new vet order setup"""
		try:
			partner = self.env['res.partner'].browse(partner_id)
			if not partner.exists():
				raise UserError(_("Partner not found"))

			if not (partner.partner_type_id and partner.partner_type_id.name == 'Pet Owner'):
				return False

			today = date.today()
			existing_encounter = self.env['ths.medical.base.encounter'].search([
				('pet_owner_id', '=', partner_id),
				('encounter_date', '=', today)
			], limit=1)

			pets = self.env['res.partner'].search([
				('pet_owner_id', '=', partner_id),
				('partner_type_id.name', '=', 'Pet'),
				('active', '=', True),
				('ths_deceased', '=', False)
			])

			practitioners = self.env['appointment.resource'].search([
				('resource_category', '=', 'practitioner'),
				('active', '=', True)
			])

			rooms = self.env['appointment.resource'].search([
				('resource_category', '=', 'location'),
				('active', '=', True)
			])

			pets_data = [{
				'id': pet.id,
				'name': pet.name,
				'species_id': pet.species_id.id if pet.species_id else False,
			} for pet in pets]

			practitioners_data = [{'id': p.id, 'name': p.name} for p in practitioners]
			rooms_data = [{'id': r.id, 'name': r.name} for r in rooms]

			selected_pets = existing_encounter.patient_ids.ids if existing_encounter else []
			selected_practitioner = existing_encounter.practitioner_id.id if existing_encounter and existing_encounter.practitioner_id else False
			selected_room = existing_encounter.room_id.id if existing_encounter and existing_encounter.room_id else False

			return {
				'partner_id': partner_id,
				'partner_name': partner.name,
				'existing_encounter': existing_encounter.id if existing_encounter else False,
				'pets': pets_data,
				'practitioners': practitioners_data,
				'rooms': rooms_data,
				'selected_pets': selected_pets,
				'selected_practitioner': selected_practitioner,
				'selected_room': selected_room,
			}

		except Exception as e:
			_logger.error(f"Error creating new order popup data: {e}")
			raise UserError(_("Error setting up order: %s") % str(e))

	@api.model
	def _process_order(self, order, draft, existing_order=None):
		order_data = order if isinstance(order, dict) else {}
		partner_id = order_data.get('pet_owner_id') or order_data.get('partner_id')
		encounter_id = None
		encounter_was_new = False

		if partner_id:
			encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
				partner_id=partner_id,
				patient_ids=order_data.get('patient_ids', []),
				encounter_date=fields.Date.today(),
				practitioner_id=order_data.get('practitioner_id', False),
				room_id=order_data.get('room_id', False)
			)
			encounter_id = encounter.id
			existing_orders_count = self.env['pos.order'].search_count([
				('encounter_id', '=', encounter.id),
				('state', 'in', ['paid', 'done', 'invoiced'])
			])
			encounter_was_new = existing_orders_count == 0
			order_data['encounter_id'] = encounter_id
			order_data['encounter_created_by_pos'] = encounter_was_new

		order_id = super()._process_order(order, draft, existing_order)
		pos_order = self.browse(order_id)
		if not pos_order:
			_logger.error(f"Failed to browse POS Order {order_id}.")
			return order_id

		if encounter_id:
			encounter = self.env['ths.medical.base.encounter'].browse(encounter_id)
			pos_order.write({
				'pet_owner_id': partner_id,
				'patient_ids': [(6, 0, encounter.patient_ids.ids)] if encounter.patient_ids else False,
				'practitioner_id': encounter.practitioner_id.id if encounter.practitioner_id else False,
				'room_id': encounter.room_id.id if encounter.room_id else False,
				'encounter_id': encounter_id,
			})

		ui_order_lines = order_data.get('lines', [])
		ui_order_lines_data = {line[2].get('uuid'): line[2] for line in ui_order_lines if
							   isinstance(line, (list, tuple)) and len(line) > 2 and isinstance(line[2],
																								dict) and 'uuid' in
							   line[2]}

		for line in pos_order.lines:
			ui_line_data = ui_order_lines_data.get(line.uuid, {})
			line_extras = ui_line_data.get('extras', {}) if isinstance(ui_line_data, dict) else {}
			line_update_vals = {}
			if line_extras.get('patient_ids'):
				line_update_vals['patient_ids'] = [(6, 0, line_extras['patient_ids'])]
			if line_extras.get('practitioner_id'):
				line_update_vals['practitioner_id'] = line_extras['practitioner_id']
			if line_extras.get('room_id'):
				line_update_vals['room_id'] = line_extras['room_id']
			if line_extras.get('discount'):
				line_update_vals['discount'] = line_extras['discount']
			if pos_order.encounter_id:
				line_update_vals['encounter_id'] = pos_order.encounter_id.id
			if line_update_vals:
				line.write(line_update_vals)

			if line_extras.get('ths_pending_item_id'):
				pending_item = self.env['ths.pending.pos.item'].browse(line_extras['ths_pending_item_id'])
				if pending_item and pending_item.state == 'pending':
					pending_item.write({
						'pos_order_line_id': line.id,
						'state': 'processed',
						'processed_date': fields.Datetime.now(),
						'processed_by': self.env.user.id,
					})

			if line_extras.get('patient_ids'):
				for pet_id in line_extras['patient_ids']:
					membership_status = self._get_pet_membership_status(pet_id)
					if membership_status == 'active':
						membership = self.env['vet.pet.membership'].search([
							('patient_ids', 'in', [pet_id]),
							('state', '=', 'running'),
							('is_paid', '=', True)
						], limit=1)
					# if membership and membership.membership_service_id.discount:
					#     line.discount = max(line.discount, membership.membership_service_id.discount)

		return order_id

	def _link_to_park_checkin(self):
		encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
			partner_id=self.pet_owner_id.id or self.partner_id.id,
			patient_ids=self.patient_ids.ids,
			encounter_date=fields.Date.today(),
			practitioner_id=self.practitioner_id,
			room_id=self.room_id,
		)
		checkin_vals = {
			'partner_id': self.pet_owner_id.id or self.partner_id.id,
			'patient_ids': [Command.set(self.patient_ids.ids)],
			'encounter_id': encounter.id,
			'checkin_time': fields.Datetime.now(),
			'state': 'checked_in',
		}
		self.env['park.checkin'].create(checkin_vals)

	def _update_patient_medical_file(self, encounter_id, pet_ids):
		encounter = self.env['ths.medical.base.encounter'].browse(encounter_id)
		if encounter:
			encounter.write({
				'patient_ids': [(6, 0, pet_ids)],
			})

	def _process_new_order_popup_result(self, popup_data):
		"""Process the result from PetOrderSetupPopup"""
		try:
			partner_id = popup_data.get('partner_id')
			selected_pets = popup_data.get('selected_pets', [])
			selected_practitioner = popup_data.get('selected_practitioner')
			selected_room = popup_data.get('selected_room')

			if not partner_id:
				raise UserError(_("Partner ID is required"))

			today = date.today()
			encounter = self.env['ths.medical.base.encounter'].search([
				('pet_owner_id', '=', partner_id),
				('encounter_date', '=', today)
			], limit=1)

			encounter_vals = {
				'patient_ids': [(6, 0, selected_pets)] if selected_pets else [(5,)],
				'practitioner_id': selected_practitioner if selected_practitioner else False,
				'room_id': selected_room if selected_room else False,
				'state': 'in_progress',
			}

			if encounter:
				encounter.write(encounter_vals)
				_logger.info(f"Updated encounter {encounter.id} with popup selections")
			else:
				encounter_vals.update({
					'partner_id': partner_id,
					'pet_owner_id': partner_id,
					'encounter_date': today,
					'name': f"Encounter - {self.env['res.partner'].browse(partner_id).name} - {today}",
				})
				encounter = self.env['ths.medical.base.encounter'].create(encounter_vals)
				_logger.info(f"Created new encounter {encounter.id} from popup selections")

			if selected_pets:
				self._process_pet_park_checkins(selected_pets, encounter)

			return {
				'encounter_id': encounter.id,
				'encounter_name': encounter.name,
				'patient_ids': [(pet.id, pet.name) for pet in encounter.patient_ids],
				'practitioner_id': [encounter.practitioner_id.id,
									encounter.practitioner_id.name] if encounter.practitioner_id else False,
				'room_id': [encounter.room_id.id, encounter.room_id.name] if encounter.room_id else False,
				'success': True,
			}

		except Exception as e:
			_logger.error(f"Error processing new order popup result: {e}")
			raise UserError(_("Error processing order setup: %s") % str(e))

	def _process_pet_park_checkins(self, pet_ids, encounter):
		try:
			park_checkins = self.env['park.checkin'].search([
				('patient_ids', 'in', pet_ids),
				('state', '=', 'checked_in'),
				('encounter_id', '=', False)
			])
			if park_checkins:
				park_checkins.write({'encounter_id': encounter.id})
				_logger.info(f"Linked {len(park_checkins)} park check-ins to encounter {encounter.id}")
		except Exception as e:
			_logger.error(f"Error processing pet park check-ins: {e}")

	def _get_pet_membership_status(self, pet_id):
		try:
			membership = self.env['vet.pet.membership'].search([
				('patient_ids', 'in', [pet_id]),
				('state', '=', 'running'),
				('is_paid', '=', True)
			], limit=1)
			return 'active' if membership else 'inactive'
		except Exception as e:
			_logger.error(f"Error checking pet membership status: {e}")
			return 'unknown'

	def _validate_pet_owner_relationship(self):
		for order in self:
			if order.pet_owner_id and order.patient_ids:
				for pet in order.patient_ids:
					if pet.pet_owner_id != order.pet_owner_id:
						raise ValidationError(
							_("Pet '%s' does not belong to owner '%s'") % (pet.name, order.pet_owner_id.name)
						)

	@api.constrains('pet_owner_id', 'patient_ids')
	def _check_pet_owner_consistency(self):
		self._validate_pet_owner_relationship()

	def get_vet_order_summary(self):
		self.ensure_one()
		summary = {
			'pet_owner': self.pet_owner_id.name if self.pet_owner_id else None,
			'pets': [(p.id, p.name, p.species_id.name if p.species_id else None) for p in self.patient_ids],
			'practitioner': self.practitioner_id.name if self.practitioner_id else None,
			'room': self.room_id.name if self.room_id else None,
			'encounter': self.encounter_id.name if self.encounter_id else None,
		}
		return summary

	def action_view_pet_owner_orders(self):
		self.ensure_one()
		if not self.pet_owner_id:
			return {}
		return {
			'name': _('Orders for %s') % self.pet_owner_id.name,
			'type': 'ir.actions.act_window',
			'res_model': 'pos.order',
			'view_mode': 'list,form',
			'domain': [('pet_owner_id', '=', self.pet_owner_id.id)],
			'context': {'create': False}
		}