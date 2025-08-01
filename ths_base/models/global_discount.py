# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class GlobalDiscountMixin(models.AbstractModel):
	_name = 'global.discount.mixin'
	_description = 'Global Discount Mixin'

	partner_type_id = fields.Many2one('ths.partner.type', string='Partner Type', readonly=False, copy=True, index=True, ondelete='cascade',
									  help="Choose proper Partner Type to show related Partners")
	global_discount_type = fields.Selection([('percent', 'Percentage'), ('amount', 'Fixed Amount')], string='Global Disc. Type', default='percent', tracking=True)
	global_discount_rate = fields.Float(string='Global Disc. Rate', default=0.0, digits=(16, 3), tracking=True, help="Discount rate as percentage (0-100) or fixed amount")
	global_discount_amount = fields.Monetary(string='Global Disc. Amount', currency_field='company_currency', compute='_compute_global_discount_amount',
											 help="Calculated global discount amount")
	total_before_discount = fields.Monetary(string='Total before any discount', compute='_compute_discount_breakdown', currency_field='company_currency')
	total_discount_amount = fields.Monetary(string='Total Disc.', compute='_compute_discount_breakdown', currency_field='company_currency')
	is_global_discount_line = fields.Boolean(string='Global Discount Line', default=False, copy=False, readonly=True)
	company_currency = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id, required=True, readonly=True,
									   help="Currency for monetary calculations")

	def _get_discount_lines(self):
		"""
		Abstract method to be implemented by inheriting models.
		Returns the relevant line records for discount calculation.
		"""
		raise NotImplementedError(_("This method should be implemented in the inheriting model."))

	def _get_discount_product(self):
		"""
		Retrieves the global discount product.
		Can be overridden by inheriting models if a different product is needed.
		"""
		return self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)

	def _compute_global_discount_amount(self):
		for rec in self:
			lines = rec._get_discount_lines()
			if rec.global_discount_rate > 0 and lines:
				discount_product = rec._get_discount_product()
				regular_lines = lines.filtered(lambda l: l.display_type == 'product' and (not discount_product or l.product_id != discount_product))
				total_before_discount = sum(line.price_unit * line.quantity for line in regular_lines)

				if rec.global_discount_type == 'percent':
					rec.global_discount_amount = total_before_discount * (rec.global_discount_rate / 100)
				else:
					rec.global_discount_amount = rec.global_discount_rate
			else:
				rec.global_discount_amount = 0.0

	def _compute_discount_breakdown(self):
		for rec in self:
			lines = rec._get_discount_lines()
			discount_product = rec._get_discount_product()
			regular_lines = lines.filtered(lambda l: l.display_type == 'product' and (not discount_product or l.product_id != discount_product))

			if regular_lines:
				rec.total_before_discount = sum(line.price_unit * line.quantity for line in regular_lines)
				subtotal_before_global_discount = sum(regular_lines.mapped('price_subtotal'))
				line_discount_amount = rec.total_before_discount - subtotal_before_global_discount
				rec.total_discount_amount = line_discount_amount + rec.global_discount_amount
			else:
				rec.total_before_discount = 0.0
				rec.total_discount_amount = 0.0

	@api.constrains('global_discount_rate', 'global_discount_type')
	def _check_global_discount_rate(self):
		for rec in self:
			if rec.global_discount_type == 'percent' and (rec.global_discount_rate < 0 or rec.global_discount_rate > 100):
				raise ValidationError("Discount percentage must be between 0 and 100.")
			elif rec.global_discount_type == 'amount' and rec.global_discount_rate < 0:
				raise ValidationError("Discount amount cannot be negative.")