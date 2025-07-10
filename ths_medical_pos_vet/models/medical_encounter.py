# -*- coding: utf-8 -*-

from odoo import models, api


class MedicalEncounter(models.Model):
	_inherit = 'ths.medical.base.encounter'

	@api.model
	def _load_pos_data_fields(self, config_id):
		base_fields = super()._load_pos_data_fields(config_id)
		vet_fields = ['pet_owner_id']
		return base_fields + vet_fields