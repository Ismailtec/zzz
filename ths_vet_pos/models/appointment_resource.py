# -*- coding: utf-8 -*-

from odoo import models, api


class AppointmentResource(models.Model):
	_inherit = 'appointment.resource'

	@api.model
	def _load_pos_data_domain(self, data):
		"""Domain for loading appointment resources in POS"""
		return [('resource_category', 'in', ['practitioner', 'location']),
		        ('active', '=', True)]

	@api.model
	def _load_pos_data_fields(self, config_id):
		"""Fields to load for appointment resources in POS"""
		return ['id', 'name', 'resource_category', 'ths_department_id', 'treatment_room_id', 'employee_id']

	@api.model
	def _load_pos_data(self, data):
		"""Load appointment resources data for POS"""
		try:
			domain = self._load_pos_data_domain(data)
			model_fields = self._load_pos_data_fields(None)
			return {
				'data': self.search_read(domain, model_fields, load=False),
				'fields': model_fields
			}
		except Exception as e:
			print(f"Error in appointment_resource _load_pos_data: {e}")
			return {'data': [], 'fields': []}

	def _trigger_pos_sync(self, operation='update'):
		"""Trigger POS sync for appointment resource updates - PERIODIC MODEL"""
		# Note: This is a periodic model, sync will be handled by periodic batch sync
		pass