# -*- coding: utf-8 -*-

from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class ThsProductSubType(models.Model):
	"""  Inherit to add Vet specific product subtypes."""
	_inherit = 'ths.product.sub.type'

	product_group = fields.Selection(selection_add=[
		('boarding', 'Boarding'),
		('grooming', 'Grooming'),
		('subscriptions', 'Subscriptions')
	],
		ondelete={
			'boarding': 'cascade',
			'grooming': 'cascade',
			'subscriptions': 'cascade'
		}
	)