# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResCountryArea(models.Model):
	_name = 'res.country.area'
	_description = 'Country Area/District'
	_order = 'name'
	_rec_name = 'name'
	_rec_name_search = ['name', 'code']

	name = fields.Char(string='Area Name', required=True, translate=True)
	code = fields.Char(string='Area Code', help="Optional unique code for the area.")
	state_id = fields.Many2one(
		'res.country.state',
		string='Governorate/State',
		domain="[('country_id', '=?', country_id)]",
		help="The Governorate (Odoo State) this area belongs to.",
		ondelete='restrict'
	)
	country_id = fields.Many2one(
		'res.country',
		string='Country',
		required=True,
		default=lambda self: self.env.ref('base.kw', raise_if_not_found=False),
		ondelete='restrict'
	)

	_sql_constraints = [
		('name_country_state_uniq', 'unique(name, country_id, state_id)',
		 'The area name must be unique per State/Country!'),
		('code_country_state_uniq', 'unique(code, country_id, state_id)',
		 'The area code must be unique per State/Country!')
	]

	# Auto-set country_id when state_id is selected
	@api.onchange('state_id')
	def _onchange_state_id(self):
		if self.state_id and self.state_id.country_id:
			self.country_id = self.state_id.country_id
		else:
			self.country_id = self.env.ref('base.ae', raise_if_not_found=False)