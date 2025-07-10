# -*- coding: utf-8 -*-

from odoo import models, api

import logging

_logger = logging.getLogger(__name__)


class VetPetMembership(models.Model):
	_inherit = 'vet.pet.membership'

	@api.model
	def _load_pos_data_domain(self, data):
		return []

	@api.model
	def _load_pos_data_fields(self, config_id):
		return ['name', 'partner_id', 'patient_ids', 'membership_service_id', 'state', 'is_paid']

	@api.model
	def _load_pos_data(self, data):
		try:
			fields = self._load_pos_data_fields(None)
			records = self.search([])
			result = []

			for rec in records:
				entry = rec.read(fields)[0]
				# Safe patient_ids formatting
				if rec.patient_ids:
					entry['patient_ids'] = [[p.id, p.name] for p in rec.patient_ids]
				else:
					entry['patient_ids'] = []
				result.append(entry)

			return {'data': result, 'fields': fields}
		except Exception as e:
			print(f"Error in Park Membership _load_pos_data: {e}")
			return {'data': [], 'fields': []}

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