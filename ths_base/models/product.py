# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.tools.float_utils import float_compare
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
	_inherit = 'product.product'

	ths_last_standard_price = fields.Float(string="Last Cost Price", digits='Product Price',
										   help="Snapshot of standard_price just before the last landed cost application or any other change")

	# Override the method responsible for selecting the bestseller
	def _select_seller(self, partner_id=False, quantity=0.0, date=None, uom_id=False, params=None):
		""" Selects the best seller for a given product and quantity. OVERRIDE: Prioritizes a vendor marked with 'Manual Priority' and sequence=0/1, otherwise selects the valid seller with the lowest price. """
		self.ensure_one()
		if date is None:
			date = fields.Date.context_today(self)
		precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')

		# _logger.info(
		# f"Selecting seller for {self.display_name}, qty: {quantity}, date: {date}, precision_digits: {precision_digits}")

		all_sellers = self.product_tmpl_id.seller_ids
		if partner_id:
			all_sellers = all_sellers.filtered(lambda s: s.partner_id == partner_id)

		if not all_sellers:
			# _logger.warning(f"No sellers found for {self.display_name} (partner filter: {bool(partner_id)})")
			return self.env['product.supplierinfo']

		# --- Check for manual override ---
		# Consider sequence 0 and 1 as top manual priority
		manual_override_sellers = all_sellers.filtered(
			lambda s: s.ths_manual_priority_vendor and s.sequence <= 1
		).sorted('sequence')  # Sort by sequence 0 then 1

		if manual_override_sellers:
			top_manual_seller = manual_override_sellers[0]
			# Check if this manually selected vendor is valid in the current context
			is_manual_valid = (
					(top_manual_seller.date_start is False or top_manual_seller.date_start <= date) and
					(top_manual_seller.date_end is False or top_manual_seller.date_end >= date) and
					(quantity is None or float_compare(quantity, top_manual_seller.min_qty,
													   precision_digits=precision_digits) != -1)
			)
			if is_manual_valid:
				# _logger.info(
				# f"Manual override: Selecting seller {top_manual_seller.partner_id.name} based on ths_manual_priority_vendor flag and sequence {top_manual_seller.sequence}.")
				return top_manual_seller
		# else:
		# _logger.info(
		# f"Manual override vendor {top_manual_seller.partner_id.name} found but is not valid (date/min_qty). Proceeding to lowest price.")

		# --- ELSE: Proceed with lowest price logic ---
		# _logger.info(f"No valid manual override found/selected. Proceeding with lowest price selection.")
		valid_sellers = all_sellers.filtered(
			lambda s:
			(s.date_start is False or s.date_start <= date) and
			(s.date_end is False or s.date_end >= date) and
			(quantity is None or float_compare(quantity, s.min_qty, precision_digits=precision_digits) != -1)
		)

		if not valid_sellers:
			# _logger.warning(
			# f"No *valid* sellers found for {self.display_name} based on date/min_qty after checking for manual override.")
			return self.env['product.supplierinfo']

		# Sort valid sellers by price (ascending)
		sorted_sellers_by_price = valid_sellers.sorted(key=lambda s: (s.price, s.sequence, s.id))

		if not sorted_sellers_by_price:
			# _logger.error(
			# f"Sorting by price resulted in empty list for {self.display_name}, though valid_sellers was not empty.")
			return self.env['product.supplierinfo']

		best_seller = sorted_sellers_by_price[0]
		# _logger.info(
		# f"Lowest price selection: Selecting seller {best_seller.partner_id.name} with price {best_seller.price} {best_seller.currency_id.symbol}. Found {len(valid_sellers)} valid options (after filtering).")
		return best_seller


class ProductBrand(models.Model):
	_name = 'product.brand'
	_description = 'Product Brand'
	_order = 'name'

	name = fields.Char(string='Brand Name', required=True, index=True)
	logo = fields.Image(string='Logo')


class ProductTemplate(models.Model):
	_inherit = 'product.template'

	product_brand = fields.Many2one('product.brand', string="Product Brand", index=True, tracking=True, ondelete='set null', help="Used for filtering and reports ONLY")
	ths_category_domain = fields.Char(string='Category Domain', compute='_compute_category_domain', help="Computing the domain of Product Category based on Product Type.")
	ths_hide_taxes = fields.Boolean(compute='_compute_ths_hide_taxes', readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")

	@api.depends_context('company')
	def _compute_ths_hide_taxes(self):
		for tmpl in self:
			tmpl.ths_hide_taxes = self.env.company.ths_hide_taxes

	# --- Compute Method for Category Domain ---
	@api.depends('type')  # Depends on the standard product type field ('consu', 'service', 'combo')
	def _compute_category_domain(self):
		""" Compute domain string for categ_id based on the 'type' field (Goods/Service/Combo). """
		for record in self:
			domain = []  # Default: show all categories
			if record.type == 'service':
				# If product type is Service, show categories marked 'Services Only' or 'All Products'
				# Assumes 'product_type_filter' field exists on product.category model
				domain = ['|', ('product_type_filter', '=', 'service'), ('product_type_filter', '=', 'all')]
				_logger.debug(f"Product {record.name or 'New'}: Type is 'service', setting category domain: {domain}")
			elif record.type == 'consu':  # User selects 'Goods', which corresponds to 'consu'
				# If product type is Goods (consu), show categories marked 'Products Only' or 'All Products'
				domain = ['|', ('product_type_filter', '=', 'product'), ('product_type_filter', '=', 'all')]
				_logger.debug(
					f"Product {record.name or 'New'}: Type is 'consu' (Goods), setting category domain: {domain}")
			# For 'combo' or if type is not set, the domain remains empty (showing all categories)
			elif record.type == 'combo':
				_logger.debug(f"Product {record.name or 'New'}: Type is 'combo', showing all categories.")
			else:
				_logger.debug(f"Product {record.name or 'New'}: Type is '{record.type}', showing all categories.")

			record.ths_category_domain = str(domain)  # Store domain as string

	# --- Onchange Method for Type to Clear Category ---
	@api.onchange('type')
	def _onchange_type_clear_category(self):
		""" When the main product type (Goods/Service/Combo) changes,
			check if the current category is still valid based on the new domain logic.
		"""
		# This helps clear the category if the user changes type, making the selection invalid
		# Check if category is set and if it has a specific filter type ('all' is always valid)
		if self.categ_id and hasattr(self.categ_id,
									 'product_type_filter') and self.categ_id.product_type_filter != 'all':
			current_categ_filter = self.categ_id.product_type_filter
			type_is_service = self.type == 'service'
			type_is_goods = self.type == 'consu'  # Goods corresponds to 'consu'

			# If type is service but category is 'Products Only', clear category
			if type_is_service and current_categ_filter == 'product':
				_logger.debug(
					f"Product {self.name or 'New'}: Type changed to Service, clearing 'Products Only' Category {self.categ_id.name}")
				self.categ_id = False
			# If type is goods but category is 'Services Only', clear category
			elif type_is_goods and current_categ_filter == 'service':
				_logger.debug(
					f"Product {self.name or 'New'}: Type changed to Goods, clearing 'Services Only' Category {self.categ_id.name}")
				self.categ_id = False


class ProductSupplierinfo(models.Model):
	_inherit = 'product.supplierinfo'

	# Set the default order for this model
	# Records will be sorted by price ascending, then by sequence, then by ID
	_order = 'price asc, sequence asc, id asc'

	ths_manual_priority_vendor = fields.Boolean(string="Priority",
												help="If checked, this vendor will be selected for replenishment IF their sequence is set to the lowest value (e.g., 0 or 1), overriding the automatic lowest price selection.")