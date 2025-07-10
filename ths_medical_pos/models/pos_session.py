# -*- coding: utf-8 -*-

from odoo import models, api, fields

import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
	_inherit = 'pos.session'

	# Define data tiers for synchronization
	CRITICAL_MODELS = ['res.partner', 'ths.medical.base.encounter', 'ths.pending.pos.item', 'calendar.event']
	PERIODIC_MODELS = ['ths.treatment.room', 'appointment.resource']
	STATIC_MODELS = ['ths.partner.type']

	@api.model
	def _load_pos_data_models(self, config_id):
		"""Add medical models to POS loading list with sync type tags"""
		original = super()._load_pos_data_models(config_id)

		# Normalize all to dicts
		model_dicts = [
			entry if isinstance(entry, dict) else {'model': entry}
			for entry in original
		]
		existing_model_names = {entry['model'] for entry in model_dicts}

		medical_models = self.CRITICAL_MODELS + self.PERIODIC_MODELS + self.STATIC_MODELS
		for model_name in medical_models:
			if model_name not in existing_model_names:
				try:
					model = self.env[model_name]
					if hasattr(model, '_load_pos_data'):
						sync_type = (
							'bus' if model_name in self.CRITICAL_MODELS else
							'periodic' if model_name in self.PERIODIC_MODELS else
							'static'
						)
						model_dicts.append({'model': model_name, 'sync_type': sync_type})
					else:
						_logger.warning(f"POS: Model {model_name} has no _load_pos_data method")
				except Exception as e:
					_logger.error(f"POS: Error adding model {model_name}: {e}")

		return model_dicts

	@api.model
	def sync_periodic_data(self):
		"""Batch sync for periodic models"""
		from datetime import timedelta

		sessions = self.search([('state', '=', 'opened')])
		sync_data = {}

		# Get records modified in last 2 minutes for periodic models
		cutoff_time = fields.Datetime.now() - timedelta(minutes=2)

		for model_name in self.PERIODIC_MODELS:
			try:
				model = self.env[model_name]
				recent_records = model.search([
					('write_date', '>=', cutoff_time)
				])
				if recent_records and hasattr(model, '_load_pos_data'):
					model_data = model._load_pos_data({})
					recent_data = [r for r in model_data.get('data', []) if r.get('id') in recent_records.ids]
					if recent_data:
						sync_data[model_name] = recent_data
			except Exception as e:
				_logger.error(f"Error syncing periodic data for {model_name}: {e}")

		if sync_data:
			# Send batch update via bus to all active POS sessions
			for session in sessions:
				# Use proper Odoo 18 bus channel format
				channel = 'pos.sync.channel' #(self._cr.dbname, 'pos.session', session.id)
				self.env['bus.bus']._sendone(
					channel,
					'batch_sync',
					{'type': 'batch_sync', 'data': sync_data}
				)

		return sync_data

# TODO: Add caching for frequently accessed encounter data
# TODO: Add batch loading optimization for large datasets