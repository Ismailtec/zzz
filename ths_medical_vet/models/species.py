# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ThsSpecies(models.Model):
	_name = 'ths.species'
	_description = 'Animal Species'

	name = fields.Char(required=True, translate=True)
	color = fields.Integer(string="Color Index", default=10)
	breed_ids = fields.One2many('ths.breed', 'species_id', string='Breeds')

	_sql_constraints = [('name_uniq', 'unique(name)', 'Species must be unique.')]

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