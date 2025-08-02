# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class SaleOrderDiscount(models.TransientModel):
	_inherit = 'sale.order.discount'

	def _get_discount_product(self):
		"""Return product.product used for discount line"""
		self.ensure_one()
		discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
		if not discount_product:
			if (
					self.env['product.product'].has_access('create')
					and self.company_id.has_access('write')
					and self.company_id._filtered_access('write')
					and self.company_id.check_field_access_rights('write', ['sale_discount_product_id'])
			):
				self.company_id.sale_discount_product_id = self.env['product.product'].create(
					self._prepare_discount_product_values()
				)
			else:
				raise ValidationError(_(
					"There does not seem to be any discount product configured for this company yet."
					" You can either use a per-line discount, or ask an administrator to grant the"
					" discount the first time."
				))
			discount_product = self.company_id.sale_discount_product_id
		return discount_product


class SaleOrder(models.Model):
	_inherit = 'sale.order'

	ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")
	partner_type_id = fields.Many2one('ths.partner.type', string='Partner Type', readonly=False, copy=True, index=True, ondelete='cascade',
									  help="Choose proper Partner Type to show related Partners")
	total_before_discount = fields.Monetary(string='Total before Discount', compute='_compute_discount_totals')
	total_discount_amount = fields.Monetary(string='Total Discount', compute='_compute_discount_totals')

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		super()._onchange_partner_id()
		if self.partner_id and self.partner_id.partner_type_id:
			self.partner_type_id = self.partner_id.partner_type_id

	@api.model
	def default_get(self, fields_list):
		defaults = super().default_get(fields_list)

		partner_id = defaults.get('partner_id') or self.env.context.get('default_partner_id')
		if partner_id and 'partner_type_id' in fields_list:
			partner = self.env['res.partner'].browse(partner_id)
			if partner.partner_type_id:
				defaults['partner_type_id'] = partner.partner_type_id.id

		return defaults

	@api.depends('order_line.price_subtotal', 'order_line.price_unit', 'order_line.product_uom_qty', 'order_line.discount')
	def _compute_discount_totals(self):
		for order in self:
			# Get discount product (following Odoo's method)
			discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
			if not discount_product:
				discount_product = self.company_id.sale_discount_product_id

			regular_lines = order.order_line.filtered(lambda l: not discount_product or l.product_id != discount_product)

			if not regular_lines:
				order.total_before_discount = 0.0
				order.total_discount_amount = 0.0
				continue

			# Total before any discounts (price_unit * qty)
			order.total_before_discount = sum(line.price_unit * line.product_uom_qty for line in regular_lines)

			# Current subtotal (after line discounts)
			subtotal_after_line_discounts = sum(regular_lines.mapped('price_subtotal'))

			# Line discount amount
			line_discount_amount = order.total_before_discount - subtotal_after_line_discounts

			# Global discount amount (from discount lines)
			global_discount_lines = order.order_line.filtered(lambda l: discount_product and l.product_id == discount_product)
			global_discount_amount = abs(sum(global_discount_lines.mapped('price_subtotal')))

			# Total discount = line discounts + global discount
			order.total_discount_amount = line_discount_amount + global_discount_amount


class SalesOrderLine(models.Model):
	_inherit = "sale.order.line"

	ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")