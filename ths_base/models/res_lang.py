# -*- coding: utf-8 -*-

from odoo import models, api


class ResLang(models.Model):
	_inherit = 'res.lang'

	@api.model
	def format(self, percent: str, value, grouping: bool = False) -> str:
		# Call original format method with exact parameters
		formatted = super().format(percent, value, grouping=grouping)

		if not formatted:
			return formatted

		# Get decimal separator from current lang
		decimal_sep = self.decimal_point

		# Strip trailing zeros after decimal and remove decimal if no digits left
		if decimal_sep in formatted:
			integer, decimal = formatted.split(decimal_sep, 1)
			decimal = decimal.rstrip('0')
			formatted = integer + decimal_sep + decimal if decimal else integer

		return formatted