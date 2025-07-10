# -*- coding: utf-8 -*-

from odoo import models, fields, api
#from odoo.osv import expression

import logging

_logger = logging.getLogger(__name__)  # Define logger


class ProductTemplate(models.Model):
	""" Inherit Product Template to add Product Sub Type field and domain logic. """
	_inherit = 'product.template'

	product_sub_type_id = fields.Many2one(
		'ths.product.sub.type',
		string='Product Sub Type',
		index=True,
		tracking=True,  # Track changes
		help="Select a specific sub-classification for this product (e.g., Medicine, Consultation, Retail)."
	)

	# --- Computed Domain Field ---
	ths_sub_type_domain = fields.Char(
		string='Sub Type Domain',
		compute='_compute_sub_type_domain',
		help="Technical field for computing the domain of Product Sub Type based on Product Type."
	)

	# --- Depends on 'type' field now ---
	@api.depends('type')
	def _compute_sub_type_domain(self):
		""" Compute domain string for product_sub_type_id based on the 'type' field (Goods/Service/Combo). """
		for record in self:
			domain = []  # Default: show all active sub types
			# Check against the 'type' field values
			if record.type == 'service':
				# If product type is Service, show only sub types marked as 'is_for_service'
				_logger.debug(f"Product {record.name}: Type is 'service', setting domain for service sub-types.")
				domain = [('is_for_service', '=', True)]
			elif record.type == 'consu':  # User selects 'Goods', which corresponds to 'consu'
				# If product type is Goods (consu), show only sub types NOT marked as 'is_for_service'
				_logger.debug(
					f"Product {record.name}: Type is 'consu' (Goods), setting domain for non-service sub-types.")
				domain = [('is_for_service', '=', False)]
			# For 'combo' or if type is not set, the domain remains empty (showing all active sub types)
			elif record.type == 'combo':
				_logger.debug(f"Product {record.name}: Type is 'combo', showing all active sub-types.")
			else:
				_logger.debug(f"Product {record.name}: Type is '{record.type}', showing all active sub-types.")

			record.ths_sub_type_domain = str(domain)

	# --- Onchange based on 'type' field ---
	@api.onchange('type')
	def _onchange_type_clear_sub_type(self):
		""" When the main product type (Goods/Service/Combo) changes,
			check if the current sub_type is still valid based on the new domain logic.
		"""
		# This logic helps clear the field if the user changes the type
		# making the previous sub-type selection invalid.
		if self.product_sub_type_id:
			current_sub_type_is_service = self.product_sub_type_id.is_for_service
			type_is_service = self.type == 'service'
			type_is_goods = self.type == 'consu'  # Goods corresponds to 'consu'

			# If type is service but sub_type is not for service, clear sub_type
			if type_is_service and not current_sub_type_is_service:
				_logger.debug(
					f"Product {self.name or 'New'}: Type changed to Service, clearing non-service Sub Type {self.product_sub_type_id.name}")
				self.product_sub_type_id = False
			# If type is goods (consu) but sub_type *is* for service, clear sub_type
			elif type_is_goods and current_sub_type_is_service:
				_logger.debug(
					f"Product {self.name or 'New'}: Type changed to Goods, clearing service Sub Type {self.product_sub_type_id.name}")
				self.product_sub_type_id = False


class ProductProduct(models.Model):
	""" Inherit to add Product Sub Type field and domain logic. """
	_inherit = 'product.product'

	product_sub_type_id = fields.Many2one(related='product_tmpl_id.product_sub_type_id')

	# --- Computed Domain Field ---
	ths_sub_type_domain = fields.Char(related='product_tmpl_id.ths_sub_type_domain')