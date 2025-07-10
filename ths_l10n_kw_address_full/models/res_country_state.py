# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCountryState(models.Model):
	_inherit = 'res.country.state'

	# Add an one2many field to easily see and manage areas belonging to this state
	area_ids = fields.One2many(
		'res.country.area',
		'state_id',
		string='Areas / Districts',
		help="List of areas or districts belonging to this Governorate/State."
	)