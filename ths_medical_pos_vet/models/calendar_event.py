# -*- coding: utf-8 -*-

from odoo import models, api


class CalendarEvent(models.Model):
	_inherit = 'calendar.event'

	@api.model
	def _load_pos_data_fields(self, config_id):
		base_fields = super()._load_pos_data_fields(config_id)
		return base_fields + ['pet_owner_id']