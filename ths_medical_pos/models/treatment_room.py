# -*- coding: utf-8 -*-

from odoo import models, api


class ThsTreatmentRoom(models.Model):
	_inherit = 'ths.treatment.room'

	@api.model
	def _load_pos_data_domain(self, data):
		"""Domain for loading treatment rooms in POS"""
		return [('active', '=', True)]

	@api.model
	def _load_pos_data_fields(self, config_id):
		"""Fields to load for treatment rooms in POS"""
		return ['id', 'name', 'resource_id', 'department_id', 'medical_staff_ids', 'appointment_resource_id']

	@api.model
	def _load_pos_data(self, data):
		"""Load treatment rooms data for POS"""
		try:
			domain = self._load_pos_data_domain(data)
			model_fields = self._load_pos_data_fields(None)
			return {
				'data': self.search_read(domain, model_fields, load=False),
				'fields': model_fields
			}
		except Exception as e:
			print(f"Error in treatment_room _load_pos_data: {e}")
			return {'data': [], 'fields': []}

	def _trigger_pos_sync(self, operation='update'):
		"""Trigger POS sync for treatment room updates - PERIODIC MODEL"""
		# Note: This is a periodic model, sync will be handled by periodic batch sync
		pass