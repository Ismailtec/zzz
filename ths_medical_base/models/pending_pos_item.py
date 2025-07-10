# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class ThsPendingPosItem(models.Model):
	_name = 'ths.pending.pos.item'
	_description = 'Pending POS Billing Item'
	_order = 'create_date desc'
	_inherit = ['mail.thread', 'mail.activity.mixin']

	name = fields.Char(compute='_compute_name', store=True, readonly=True)

	encounter_id = fields.Many2one(
		'ths.medical.base.encounter',
		string='Source Encounter',
		ondelete='cascade',
		index=True,
		copy=False,
		help="Daily encounter this item belongs to"
	)

	partner_id = fields.Many2one(
		'res.partner',
		string='Patient',  # In human medical, patient is the customer
		store=True,
		index=True,
		required=True,
		help="The patient receiving treatment and responsible for payment. This is both the service recipient and the billing customer."
	)

	patient_ids = fields.Many2many(
		'res.partner',
		'ths_pending_pos_patient_rel',
		'encounter_id',
		'patient_id',
		string='Patients',
		domain="[('partner_type_id.is_patient', '=', True)]",
		readonly=False,
		store=True,
		help="The patient who received the service/product. This is the same person as the billing customer."
	)

	product_id = fields.Many2one(
		'product.product',
		string='Product/Service',
		required=True,
		domain="[('available_in_pos', '=', True), ('sale_ok', '=', True)]"
	)
	description = fields.Text(
		string='Description',
		help="Optional override for the product description on the POS line."
	)
	qty = fields.Float(
		string='Quantity',
		required=True,
		digits='Product Unit of Measure',
		default=1.0
	)
	discount = fields.Float(
		string='Discount (%)',
		digits='Discount',
		default=0.0
	)
	sub_total = fields.Float(
		string='Subtotal',
		compute='_compute_sub_total',
		store=True,
		digits='Product Price',
		help="Subtotal based on POS-processed price."
	)

	practitioner_id = fields.Many2one(
		'appointment.resource',
		string='Practitioner',
		required=False,
		index=True,
		domain="[('resource_category', '=', 'practitioner')]",
		help="The medical staff member who provided this service/item."
	)

	room_id = fields.Many2one(
		'appointment.resource',
		string='Room',
		store=False,
		index=True,
		domain="[('resource_category', '=', 'location')]",
	)
	room_id_domain = fields.Char(
		compute='_compute_room_id_domain',
		store=False,
		help="Domain for selecting the room based on the practitioner."
	)

	commission_pct = fields.Float(
		string='Commission %',
		digits='Discount',
		help="Commission percentage for the practitioner for this specific item."
	)

	state = fields.Selection([
		('pending', 'Pending'),
		('processed', 'Processed in POS'),
		('cancelled', 'Cancelled')
	], string='Status', default='pending', required=True, index=True, copy=False, tracking=True)

	pos_order_line_id = fields.Many2one(
		'pos.order.line',
		string='POS Order Line',
		readonly=True,
		copy=False,
		ondelete='set null',
	)
	processed_date = fields.Datetime(string='Processed Date', readonly=True, copy=False)
	processed_by = fields.Many2one('res.users', string='Processed By', readonly=True, copy=False)

	notes = fields.Text(string='Internal Notes')
	company_id = fields.Many2one(
		'res.company',
		string='Company',
		store=True,
		index=True,
		required=True,
		default=lambda self: self.env.company
	)

	@api.depends('product_id', 'encounter_id', 'patient_ids')
	def _compute_name(self):
		for item in self:
			name = item.product_id.name or _("Pending Item")
			if item.patient_ids:
				patient_names = ", ".join(item.patient_ids.mapped('name'))
				name += f" - {patient_names}"
			if item.encounter_id:
				name += f" ({item.encounter_id.name})"
			item.name = name

	@api.depends('practitioner_id')
	def _compute_room_id_domain(self):
		for record in self:
			if record.practitioner_id and record.practitioner_id.ths_department_id:
				record.room_id_domain = str([
					('resource_category', '=', 'location'),
					('ths_department_id', '=', record.practitioner_id.ths_department_id.id)
				])
			else:
				record.room_id_domain = str([('resource_category', '=', 'location')])

	@api.depends('qty', 'discount', 'pos_order_line_id.price_unit')
	def _compute_sub_total(self):
		"""Compute subtotal based on POS-derived price if processed, otherwise 0."""
		for item in self:
			if item.state == 'processed' and item.pos_order_line_id:
				price_unit = item.pos_order_line_id.price_unit
				item.sub_total = price_unit * item.qty * (1 - (item.discount / 100.0))
			elif item.product_id.list_price:
				item.sub_total = item.product_id.list_price * item.qty * (1 - (item.discount / 100.0))
			else:
				item.sub_total = 0.0

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		if self.partner_id:
			self.patient_ids = self.partner_id

	def create(self, vals_list):
		processed_vals_list = []
		for vals in vals_list:
			if vals.get('partner_id') and not vals.get('encounter_id'):
				partner_id = vals['partner_id']
				encounter_date = fields.Date.context_today(self)

				line_patient_ids = []
				if 'patient_ids' in vals and isinstance(vals['patient_ids'], list):
					for command in vals['patient_ids']:
						if command[0] == 6 and command[1] == 0:
							if command[2] and isinstance(command[2], list):
								line_patient_ids.extend(command[2])
						elif command[0] == 4:
							line_patient_ids.append(command[1])

				practitioner_id_from_vals = vals.get('practitioner_id')
				room_id_from_vals = vals.get('room_id')

				practitioner_id = self.env['appointment.resource'].browse(
					practitioner_id_from_vals) if practitioner_id_from_vals else False
				room_id = self.env['appointment.resource'].browse(room_id_from_vals) if room_id_from_vals else False

				encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
					partner_id,
					line_patient_ids,
					encounter_date,
					practitioner_id,
					room_id
				)
				vals['encounter_id'] = encounter.id

			processed_vals_list.append(vals)

		new_items = super().create(processed_vals_list)
		return new_items

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

				if item.practitioner_id and (
						not encounter.practitioner_id or encounter.practitioner_id.id != item.practitioner_id.id):
					encounter.practitioner_id = item.practitioner_id.id

				if item.room_id and (not encounter.room_id or encounter.room_id.id != item.room_id.id):
					encounter.room_id = item.room_id.id

		return res

	def action_cancel(self):
		processed_items = self.filtered(lambda i: i.state == 'processed')
		if processed_items:
			_logger.warning("Attempting to cancel already processed pending items: %s. Only setting state.",
							processed_items.ids)
			processed_items.write({'pos_order_line_id': False})

		self.write({'state': 'cancelled'})
		_logger.info("Cancelled pending items: %s", self.ids)
		return True

	def action_reset_to_pending(self):
		if any(item.state == 'processed' for item in self):
			raise UserError(_("Cannot reset items that have already been processed in Point of Sale via this action."))

		items_to_reset = self.filtered(lambda i: i.state == 'cancelled')
		if items_to_reset:
			items_to_reset.write({'state': 'pending'})
			_logger.info("Reset cancelled pending items to pending: %s", items_to_reset.ids)
		return True

	def action_reset_to_pending_from_pos(self):
		_logger.info("Action 'Reset to Pending from POS' called for items: %s", self.ids)
		items_to_reset = self.filtered(lambda i: i.state in ('processed', 'cancelled'))
		if not items_to_reset:
			_logger.warning("No items found in 'processed' or 'cancelled' state to reset from POS refund for ids: %s",
							self.ids)
			return False

		vals_to_write = {
			'state': 'pending',
			'pos_order_line_id': False
		}
		items_to_reset.write(vals_to_write)
		_logger.info("Reset pending items %s state to 'pending' and unlinked POS line due to refund.",
					 items_to_reset.ids)

		for item in items_to_reset:
			item.message_post(body=_("Item status reset to 'Pending' due to linked POS Order Line refund."))

		return True

	def action_view_encounter(self):
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

	def _prepare_pos_order_line_data(self):
		"""Prepare data for POS order line creation."""
		self.ensure_one()
		return {
			'product_id': self.product_id.id,
			'qty': self.qty,
			'discount': self.discount,
			'order_id': False,  # To be set by POS when creating the order
			'price_unit': self.product_id.lst_price,  # Default to list price, POS can override
			'description': self.description or self.product_id.name,
		}

# TODO: Add pending item automatic grouping by encounter
# TODO: Implement pending item priority system
# TODO: Add pending item expiration warnings
# TODO: Implement pending item bulk processing
# TODO: Add pending item approval workflow for high-value items