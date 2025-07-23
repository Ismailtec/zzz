# -*- coding: utf-8 -*-

from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


class ThsMedicalEncounter(models.Model):
	""" Extend to include medical encounter payments """
	_inherit = 'ths.medical.base.encounter'

	# Service relationships - all services linked to this encounter
	pos_order_ids = fields.One2many(
		'pos.order',
		'encounter_id',
		string='POS Orders',
		help="All POS orders for this encounter"
	)

	# Payment tracking
	total_pos_pending_amount = fields.Float(
		string='Total POS Pending Amount',
		compute='_compute_pos_payment_status',
		store=True,
		help="Total amount of unpaid items"
	)
	total_pos_paid_amount = fields.Float(
		string='Total POS Paid Amount',
		compute='_compute_pos_payment_status',
		store=True,
		help="Total amount of paid items"
	)
	has_pos_pending_payments = fields.Boolean(
		string='Has POS Pending Payments',
		compute='_compute_pos_payment_status',
		store=True,
		help="True if there are unpaid items"
	)

	# --- Compute Methods ---
	@api.depends('pos_order_ids.amount_total', 'pos_order_ids.state')
	def _compute_pos_payment_status(self):
		"""Compute payment status from linked POS orders and pending items"""
		for encounter in self:
			# Calculate from POS orders
			paid_orders = encounter.pos_order_ids.filtered(lambda o: o.state in ('paid', 'invoiced', 'done'))
			pending_orders = encounter.pos_order_ids.filtered(lambda o: o.state == 'draft')

			if encounter.pos_order_ids:
				encounter.total_pos_paid_amount = sum(paid_orders.mapped('amount_total'))
				encounter.total_pos_pending_amount = sum(pending_orders.mapped('amount_total'))
				encounter.has_pos_pending_payments = encounter.total_pos_pending_amount > 0

			# Update encounter state based on payments
			if encounter.has_pos_pending_payments:
				encounter.state = 'in_progress'
			else:
				encounter.state = 'done'

	# --- POS Data Loading Methods ---
	@api.model
	def _load_pos_data_domain(self, data):
		"""Domain for loading encounters in POS"""
		return [
			('partner_id', '!=', False),
			('state', 'in', ['in_progress', 'done'])
		]

	@api.model
	def _load_pos_data_fields(self, config_id):
		"""Fields to load for encounters in POS"""
		return [
			'id', 'name', 'encounter_date', 'partner_id',
			'patient_ids', 'practitioner_id', 'room_id', 'state', 'appointment_ids', 'pending_pos_items'
		]

	@api.model
	def _load_pos_data(self, data):
		domain = self._load_pos_data_domain(data)
		all_fields = self._load_pos_data_fields(None)
		result = []
		for rec in self.search(domain):
			entry = rec.read(all_fields)[0]
			# entry['patient_ids'] = rec.patient_ids.patient_name('patient_ids')
			result.append(entry)
		return {'data': result, 'fields': all_fields}

	def _compute_pos_order(self):
		"""Compute total POS orders for this encounter"""
		pos_order_data = self.env['pos.order']._read_group(
			domain=[('encounter_id', 'in', self.ids)],
			groupby=['encounter_id'], aggregates=['__count']
		)
		self_ids = set(self._ids)

		self.pos_order_count = 0
		for encounter, count in pos_order_data:
			while encounter:
				if encounter.id in self_ids:
					encounter.pos_order_count += count

	def _trigger_pos_sync(self, operation='update'):
		"""Trigger POS sync for partner updates"""
		# IMPORTANT: Add this guard. If self is empty, there are no records to sync.
		if not self:
			return

		PosSession = self.env['pos.session']

		if self._name in PosSession.CRITICAL_MODELS:
			try:
				active_sessions = PosSession.search([('state', '=', 'opened')])

				current_data = []
				if operation != 'delete':
					fields_to_sync = self._load_pos_data_fields(False)
					current_data = self.read(fields_to_sync)
				else:
					current_data = [{'id': record_id} for record_id in self.ids]

				for session in active_sessions:
					channel = 'pos.sync.channel'  # (self._cr.dbname, 'pos.session', session.id)
					self.env['bus.bus']._sendone(
						channel,
						'critical_update',
						{
							'type': 'critical_update',
							'model': self._name,
							'operation': operation,
							'records': current_data
						}
					)
					_logger.info(f"POS Sync - Data sent to bus for res.partner (action: {operation}, IDs: {self.ids})")
			except Exception as e:
				_logger.error(f"Error triggering POS sync for {self._name} (IDs: {self.ids}): {e}")

	@api.model_create_multi
	def create(self, vals_list):
		"""Override create to trigger sync"""
		records = super().create(vals_list)
		records._trigger_pos_sync('create')
		return records

	def write(self, vals):
		"""Override write to trigger sync"""
		result = super().write(vals)
		self._trigger_pos_sync('update')
		return result

	def unlink(self):
		"""Override unlink to trigger sync"""
		self._trigger_pos_sync('delete')
		return super().unlink()