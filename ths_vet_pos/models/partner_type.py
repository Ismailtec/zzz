# -*- coding: utf-8 -*-

from odoo import models, api


class ThsPartnerType(models.Model):
	_inherit = 'ths.partner.type'

	@api.model
	def _load_pos_data_domain(self, data):
		"""Domain for loading partner types in POS"""
		return [('active', '=', True)]

	@api.model
	def _load_pos_data_fields(self, config_id):
		"""Fields to load for partner types in POS"""
		return ['id', 'name', 'is_patient', 'is_employee', 'is_customer', 'is_company', 'is_individual']

	@api.model
	def _load_pos_data(self, data):
		"""Load partner types data for POS"""
		try:
			domain = self._load_pos_data_domain(data)
			model_fields = self._load_pos_data_fields(None)
			return {
				'data': self.search_read(domain, model_fields, load=False),
				'fields': model_fields
			}
		except Exception as e:
			print(f"Error in partner_type _load_pos_data: {e}")
			return {'data': [], 'fields': []}

	def _trigger_pos_sync(self, operation='update'):
		"""Trigger POS sync for partner type updates - STATIC MODEL"""
		# Note: This is a static model, rarely changes, manual refresh recommended
		pass