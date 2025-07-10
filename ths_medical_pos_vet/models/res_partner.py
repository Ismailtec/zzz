# -*- coding: utf-8 -*-

from odoo import models, api


class ResPartner(models.Model):
	_inherit = 'res.partner'

	@api.model
	def _load_pos_data_fields(self, config_id):
		base_fields = super()._load_pos_data_fields(config_id)
		return base_fields + [
			'is_pet', 'is_pet_owner', 'pet_owner_id',
			'species_id', 'ths_deceased', 'pet_ids', 'pet_membership_ids',
		]

	@api.model
	def _load_pos_data(self, data):
		result = super()._load_pos_data(data)
		result['fields'] = list(set(result['fields'] + [
			'is_pet', 'is_pet_owner', 'pet_owner_id',
			'species_id', 'ths_deceased', 'pet_ids', 'pet_membership_ids',
		]))

		return result