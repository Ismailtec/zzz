# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ThsBreed(models.Model):
	_name = 'ths.breed'
	_description = 'Animal Breed'

	name = fields.Char(required=True, translate=True)
	species_id = fields.Many2one('ths.species', string='Species', required=True, ondelete='restrict')
	_sql_constraints = [('name_uniq', 'unique(name)', 'Breed must be unique.')]

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if 'name' in vals:
				vals['name'] = vals['name'].strip().title()
		return super().create(vals_list)

	def write(self, vals):
		if 'name' in vals:
			vals['name'] = vals['name'].strip().title()
		return super().write(vals)