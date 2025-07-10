# -*- coding: utf-8 -*-

from odoo import models, api


class Species(models.Model):
	_inherit = 'ths.species'

	@api.model
	def _load_pos_data_domain(self, data):
		return []

	@api.model
	def _load_pos_data_fields(self, config_id):
		return ['name', 'color']

	@api.model
	def _load_pos_data(self, data):
		fields = self._load_pos_data_fields(None)
		return {'data': self.search_read([], fields, load=False), 'fields': fields}

	def _trigger_pos_sync(self, operation='update'):
		"""Trigger POS sync for species updates - PERIODIC MODEL"""
		# Note: This is a periodic model, sync will be handled by periodic batch sync
		pass