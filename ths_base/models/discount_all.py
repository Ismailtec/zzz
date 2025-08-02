# -*- coding: utf-8 -*-

from collections import defaultdict
from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_repr


class PurchaseOrderDiscount(models.TransientModel):
	_name = 'purchase.order.discount'
	_description = "Purchase Order Discount Wizard"

	purchase_order_id = fields.Many2one('purchase.order', default=lambda self: self.env.context.get('active_id'), required=True)
	company_id = fields.Many2one(related='purchase_order_id.company_id')
	currency_id = fields.Many2one(related='purchase_order_id.currency_id')
	discount_amount = fields.Monetary(string="Amount")
	discount_percentage = fields.Float(string="Percentage")
	discount_type = fields.Selection(selection=[('line_discount', "On All Order Lines"), ('global_discount', "Global Discount %"), ('fixed_amount', "Fixed Amount")],
									 default='line_discount')
	tax_ids = fields.Many2many(string="Taxes", help="Taxes to add on the discount line.", comodel_name='account.tax',
							   domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]")

	@api.constrains('discount_type', 'discount_percentage')
	def _check_discount_amount(self):
		for wizard in self:
			if (
					wizard.discount_type in ('line_discount', 'global_discount')
					and wizard.discount_percentage > 1.0
			):
				raise ValidationError(_("Invalid discount amount"))

	def _prepare_discount_product_values(self):
		self.ensure_one()
		return {
			'name': _('Discount'),
			'type': 'service',
			'invoice_policy': 'order',
			'list_price': 0.0,
			'company_id': self.company_id.id,
			'taxes_id': None,
		}

	def _prepare_discount_line_values(self, product, amount, taxes, description=None):
		self.ensure_one()
		vals = {
			'order_id': self.purchase_order_id.id,
			'product_id': product.id,
			'sequence': 999,
			'price_unit': -amount,
			'taxes_id': [Command.set(taxes.ids)],
			'product_qty': 1,
		}
		if description:
			vals['name'] = description
		return vals

	def _get_discount_product(self):
		"""Get discount product - using your existing product"""
		discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
		if not discount_product:
			raise ValidationError(_("Global discount product not found. Please contact administrator."))
		return discount_product

	def _create_discount_lines(self):
		"""Create PO discount lines - exact copy of SO logic but for purchase.order.line"""
		self.ensure_one()
		discount_product = self._get_discount_product()

		if self.discount_type == 'fixed_amount':
			if not self.purchase_order_id.amount_total:
				return
			po_amount = self.purchase_order_id.amount_total
			# Fixed taxes cannot be discounted
			if any(tax.amount_type == 'fixed' for tax in self.purchase_order_id.order_line.taxes_id.flatten_taxes_hierarchy()):
				fixed_taxes_amount = 0
				for line in self.purchase_order_id.order_line:
					taxes = line.taxes_id.flatten_taxes_hierarchy()
					for tax in taxes.filtered(lambda tax: tax.amount_type == 'fixed'):
						fixed_taxes_amount += tax.amount * line.product_qty
				po_amount -= fixed_taxes_amount
			discount_percentage = self.discount_amount / po_amount
		else:  # so_discount
			discount_percentage = self.discount_percentage

		total_price_per_tax_groups = defaultdict(float)
		for line in self.purchase_order_id.order_line:
			if not line.product_qty or not line.price_unit:
				continue
			taxes = line.taxes_id.flatten_taxes_hierarchy()
			fixed_taxes = taxes.filtered(lambda t: t.amount_type == 'fixed')
			taxes -= fixed_taxes
			total_price_per_tax_groups[taxes] += line.price_unit * (1 - (line.discount or 0.0) / 100) * line.product_qty

		discount_dp = self.env['decimal.precision'].precision_get('Discount')

		if not total_price_per_tax_groups:
			return

		if len(total_price_per_tax_groups) == 1:
			taxes = next(iter(total_price_per_tax_groups.keys()))
			subtotal = total_price_per_tax_groups[taxes]
			vals_list = [{
				**self._prepare_discount_line_values(
					product=discount_product,
					amount=subtotal * discount_percentage,
					taxes=taxes,
					description=_(
						"Discount %(percent)s%%",
						percent=float_repr(discount_percentage * 100, discount_dp),
					),
				),
			}]
		else:
			vals_list = []
			for taxes, subtotal in total_price_per_tax_groups.items():
				discount_line_value = self._prepare_discount_line_values(
					product=discount_product,
					amount=subtotal * discount_percentage,
					taxes=taxes,
					description=_(
						"Discount %(percent)s%% - On products with taxes %(taxes)s",
						percent=float_repr(discount_percentage * 100, discount_dp),
						taxes=", ".join(taxes.mapped('name')),
					) if self.discount_type != 'fixed_amount' else _(
						"Discount - On products with taxes %(taxes)s",
						taxes=", ".join(taxes.mapped('name')),
					)
				)
				vals_list.append(discount_line_value)
		return self.env['purchase.order.line'].create(vals_list)

	def action_apply_discount(self):
		self.ensure_one()
		self = self.with_company(self.company_id)
		if self.discount_type == 'line_discount':
			self.purchase_order_id.order_line.write({'discount': self.discount_percentage * 100})
		else:
			self._create_discount_lines()


class AccountMoveDiscount(models.TransientModel):
	_name = 'account.move.discount'
	_description = "Invoice Discount Wizard"

	move_id = fields.Many2one('account.move', default=lambda self: self.env.context.get('active_id'), required=True)
	company_id = fields.Many2one(related='move_id.company_id')
	currency_id = fields.Many2one(related='move_id.currency_id')
	discount_amount = fields.Monetary(string="Amount")
	discount_percentage = fields.Float(string="Percentage")
	discount_type = fields.Selection(selection=[('line_discount', "On All Invoice Lines"), ('global_discount', "Global Discount"), ('fixed_amount', "Fixed Amount")],
									 default='line_discount')
	tax_ids = fields.Many2many(string="Taxes", help="Taxes to add on the discount line.", comodel_name='account.tax',
							   domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]")

	@api.constrains('discount_type', 'discount_percentage')
	def _check_discount_amount(self):
		for wizard in self:
			if (
					wizard.discount_type in ('line_discount', 'global_discount')
					and wizard.discount_percentage > 1.0
			):
				raise ValidationError(_("Invalid discount amount"))

	def _prepare_discount_line_values(self, product, amount, taxes, description=None):
		self.ensure_one()
		vals = {
			'move_id': self.move_id.id,
			'product_id': product.id,
			'sequence': 999,
			'price_unit': -amount,
			'tax_ids': [Command.set(taxes.ids)],
			'quantity': 1,
			'account_id': product.property_account_income_id.id or product.categ_id.property_account_income_categ_id.id,
		}
		if description:
			vals['name'] = description
		return vals

	def _get_discount_product(self):
		"""Get discount product - using your existing product"""
		discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
		if not discount_product:
			raise ValidationError(_("Global discount product not found. Please contact administrator."))
		return discount_product

	def _create_discount_lines(self):
		"""Create invoice discount lines - exact copy of SO logic but for account.move.line"""
		self.ensure_one()
		discount_product = self._get_discount_product()

		if self.discount_type == 'fixed_amount':
			if not self.move_id.amount_total:
				return
			invoice_amount = self.move_id.amount_total
			# Fixed taxes cannot be discounted
			invoice_lines = self.move_id.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
			if any(tax.amount_type == 'fixed' for tax in invoice_lines.tax_ids.flatten_taxes_hierarchy()):
				fixed_taxes_amount = 0
				for line in invoice_lines:
					taxes = line.tax_ids.flatten_taxes_hierarchy()
					for tax in taxes.filtered(lambda tax: tax.amount_type == 'fixed'):
						fixed_taxes_amount += tax.amount * line.quantity
				invoice_amount -= fixed_taxes_amount
			discount_percentage = self.discount_amount / invoice_amount
		else:  # so_discount
			discount_percentage = self.discount_percentage

		total_price_per_tax_groups = defaultdict(float)
		for line in self.move_id.invoice_line_ids:
			if line.display_type != 'product' or not line.quantity or not line.price_unit:
				continue
			taxes = line.tax_ids.flatten_taxes_hierarchy()
			fixed_taxes = taxes.filtered(lambda t: t.amount_type == 'fixed')
			taxes -= fixed_taxes
			total_price_per_tax_groups[taxes] += line.price_unit * (1 - (line.discount or 0.0) / 100) * line.quantity

		discount_dp = self.env['decimal.precision'].precision_get('Discount')

		if not total_price_per_tax_groups:
			return

		if len(total_price_per_tax_groups) == 1:
			taxes = next(iter(total_price_per_tax_groups.keys()))
			subtotal = total_price_per_tax_groups[taxes]
			vals_list = [{
				**self._prepare_discount_line_values(
					product=discount_product,
					amount=subtotal * discount_percentage,
					taxes=taxes,
					description=_(
						"Discount %(percent)s%%",
						percent=float_repr(discount_percentage * 100, discount_dp),
					),
				),
			}]
		else:
			vals_list = []
			for taxes, subtotal in total_price_per_tax_groups.items():
				discount_line_value = self._prepare_discount_line_values(
					product=discount_product,
					amount=subtotal * discount_percentage,
					taxes=taxes,
					description=_("Discount %(percent)s%% - On products with taxes %(taxes)s",
								  percent=float_repr(discount_percentage * 100, discount_dp),
								  taxes=", ".join(taxes.mapped('name')),
								  ) if self.discount_type != 'fixed_amount' else _("Discount - On products with taxes %(taxes)s", taxes=", ".join(taxes.mapped('name')), ))
				vals_list.append(discount_line_value)
		return self.env['account.move.line'].create(vals_list)

	def action_apply_discount(self):
		self.ensure_one()
		self = self.with_company(self.company_id)
		if self.discount_type == 'line_discount':
			self.move_id.invoice_line_ids.filtered(
				lambda l: l.display_type == 'product'
			).write({'discount': self.discount_percentage * 100})
		else:
			self._create_discount_lines()