# -*- coding: utf-8 -*-

from odoo import models, api


class PosSession(models.Model):
	_inherit = 'pos.session'

	@api.model
	def _load_pos_data_models(self, config_id):
		"""Add vet-specific models to POS with tier classification"""
		original_models = super()._load_pos_data_models(config_id)

		# Define vet-specific model tiers
		vet_critical_models = ['res.partner', 'vet.pet.membership', 'park.checkin']
		vet_periodic_models = ['ths.species']
		vet_static_models = []

		all_vet_models = vet_critical_models + vet_periodic_models + vet_static_models

		# Extract model names from dicts or plain strings
		existing_models = {
			m['model'] if isinstance(m, dict) else m
			for m in original_models
			if isinstance(m, (dict, str))
		}

		for model_name in all_vet_models:
			if model_name not in existing_models:
				sync_type = (
					'bus' if model_name in vet_critical_models else
					'periodic' if model_name in vet_periodic_models else
					'static'
				)
				original_models.append({'model': model_name, 'sync_type': sync_type})

		# ✅ Extend the parent class tier definitions properly
		# parent_critical = getattr(type(self), 'CRITICAL_MODELS', [])
		# parent_periodic = getattr(type(self), 'PERIODIC_MODELS', [])
		# type(self).CRITICAL_MODELS = parent_critical + vet_critical_models
		# type(self).PERIODIC_MODELS = parent_periodic + vet_periodic_models

		@property
		def critical_models(self):
			"""Get combined critical models from base and vet"""
			base_critical = getattr(super(), 'CRITICAL_MODELS', [])
			vet_critical = ['vet.pet.membership', 'park.checkin']
			return base_critical + vet_critical

		@property
		def periodic_models(self):
			"""Get combined periodic models from base and vet"""
			base_periodic = getattr(super(), 'PERIODIC_MODELS', [])
			vet_periodic = ['ths.species']
			return base_periodic + vet_periodic

		@property
		def static_models(self):
			"""Get combined static models from base and vet"""
			base_static = getattr(super(), 'STATIC_MODELS', [])
			vet_static = []  # No vet-specific static models currently
			return base_static + vet_static

		return [m['model'] if isinstance(m, dict) else m for m in original_models]