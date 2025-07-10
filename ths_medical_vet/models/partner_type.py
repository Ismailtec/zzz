# -*- coding: utf-8 -*-

from odoo import models, fields


class ThsPartnerType(models.Model):
	""" Inherit Partner Type to add is_pet and is_pet_owner flags. """
	_inherit = 'ths.partner.type'

	is_pet = fields.Boolean(
		string="Pet",
		default=False,
		help="Check if this partner type specifically represents Pets."
	)

	is_pet_owner = fields.Boolean(
		string="Pet Owner",
		default=False,
		help="Check if this partner type specifically represents Pet Owners."
	)