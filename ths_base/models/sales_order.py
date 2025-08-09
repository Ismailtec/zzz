# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


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
	paid_amount = fields.Monetary(string='Paid Amount', compute='_compute_paid_amount', currency_field='currency_id')
	payment_status = fields.Selection([('nothing', 'Nothing Paid'), ('partial', 'Partially Paid'), ('paid', 'Fully Paid')], string='Payment Status',
									  compute='_compute_payment_status')
	has_missing_deliveries = fields.Boolean(string='Has Missing Deliveries', store=False, compute='_compute_missing_deliveries')
	status_message = fields.Html(compute='_compute_status_message')
	show_status_bar = fields.Boolean(compute='_compute_status_message')
	ribbon_title = fields.Char(compute='_compute_status_message')

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

	@api.depends('paid_amount', 'amount_total')
	def _compute_payment_status(self):
		for order in self:
			if order.paid_amount >= order.amount_total:
				order.payment_status = 'paid'
			elif order.paid_amount > 0:
				order.payment_status = 'partial'
			else:
				order.payment_status = 'nothing'

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

	@api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_total', 'invoice_ids.amount_residual')
	def _compute_paid_amount(self):
		for order in self:
			paid_amount = 0.0
			for invoice in order.invoice_ids.filtered(lambda inv: inv.state == 'posted'):
				paid_amount += invoice.amount_total - invoice.amount_residual
			order.paid_amount = paid_amount

	@api.depends('state', 'invoice_ids', 'invoice_ids.state', 'order_line.product_uom_qty', 'order_line.qty_delivered', 'order_line.qty_returned', 'order_line.qty_invoiced',
				 'invoice_ids.payment_state')
	def _compute_status_message(self):
		for order in self:
			order.ribbon_title = False
			# Payment status
			if order.paid_amount >= order.amount_total:
				payment_text = 'Fully Paid'
				payment_class = 'text-success'
			elif order.paid_amount > 0:
				payment_text = 'Partially Paid'
				payment_class = 'text-warning'
			else:
				payment_text = 'Not Paid'
				payment_class = 'text-danger'

			# Delivery status
			if order.state != 'sale':
				delivery_text = 'Not Ready'
				delivery_class = 'text-muted'
			elif not order.has_missing_deliveries:
				if order.paid_amount >= order.amount_total:
					order.ribbon_title = 'Completed'

				delivery_text = 'Fully Delivered'
				delivery_class = 'text-info'
			elif any(line.qty_delivered > 0 for line in order.order_line.filtered(lambda l: l.product_id.type == 'consu')):
				delivery_text = 'Partially Delivered'
				delivery_class = 'text-warning'
			else:
				delivery_text = 'Not Delivered'
				delivery_class = 'text-danger'

			# Returns status
			total_returned = sum(order.order_line.mapped('qty_returned'))
			if total_returned > 0:
				returns_text = f'{total_returned} items returned'
				returns_class = 'text-danger'
			else:
				returns_text = None
				returns_class = None

			# Combine into full message
			status_parts = [f'<span class="{payment_class}">{payment_text}</span>', f'<span class="{delivery_class}">{delivery_text}</span>']
			if returns_text:
				status_parts.append(f'<span class="{returns_class}">({returns_text})</span>')

			order.status_message = ' • '.join(status_parts)
			order.show_status_bar = bool(order.paid_amount > 0 or any(line.qty_delivered > 0 for line in order.order_line) or total_returned > 0)

	@api.depends('state', 'order_line', 'order_line.product_uom_qty', 'order_line.product_id.type', 'picking_ids', 'picking_ids.state', 'picking_ids.move_ids',
				 'picking_ids.move_ids.state', 'picking_ids.move_ids.quantity', 'picking_ids.move_ids.product_uom_qty')
	def _compute_missing_deliveries(self):
		"""Check if there are missing deliveries for stockable products"""
		for order in self:
			has_missing = False
			if order.state == 'sale':
				stockable_lines = order.order_line.filtered(lambda l: l.product_id.type == 'consu')
				for line in stockable_lines:
					# Simple logic: ordered vs delivered (returns are separate)
					required = line.product_uom_qty
					delivered = line.qty_delivered
					missing = max(0.0, required - delivered)

					if missing > 0:
						has_missing = True
						break
			order.has_missing_deliveries = has_missing

	def action_create_missing_deliveries(self):
		"""Create deliveries for missing quantities"""
		self.ensure_one()

		if not self.has_missing_deliveries:
			return {'type': 'ir.actions.act_window_close'}

		# Get warehouse
		warehouse = self.warehouse_id or self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
		if not warehouse:
			raise UserError("No warehouse found for this company")

		missing_lines = []
		stockable_lines = self.order_line.filtered(lambda l: l.product_id.type == 'consu')

		for line in stockable_lines:
			ordered = line.product_uom_qty
			delivered = line.qty_delivered
			missing_qty = max(0.0, ordered - delivered)

			if missing_qty > 0:
				missing_lines.append({
					'sale_line': line,
					'missing_qty': missing_qty
				})

		if not missing_lines:
			return {'type': 'ir.actions.act_window_close'}

		if not missing_lines:
			return {'type': 'ir.actions.act_window_close'}

		picking_vals = {
			'partner_id': self.partner_shipping_id.id,
			'picking_type_id': warehouse.out_type_id.id,
			'location_id': warehouse.lot_stock_id.id,
			'location_dest_id': self.partner_shipping_id.property_stock_customer.id,
			'sale_id': self.id,
			'company_id': self.company_id.id,
		}

		new_picking = self.env['stock.picking'].create(picking_vals)

		for missing_line in missing_lines:
			line = missing_line['sale_line']
			move_vals = {
				'name': line.product_id.name,
				'product_id': line.product_id.id,
				'product_uom_qty': missing_line['missing_qty'],
				'product_uom': line.product_uom.id,
				'picking_id': new_picking.id,
				'location_id': warehouse.lot_stock_id.id,
				'location_dest_id': self.partner_shipping_id.property_stock_customer.id,
				'sale_line_id': line.id,
				'company_id': self.company_id.id,
			}
			self.env['stock.move'].create(move_vals)

		new_picking.action_confirm()
		new_picking.action_assign()

		return {
			'type': 'ir.actions.act_window',
			'name': 'New Delivery',
			'res_model': 'stock.picking',
			'res_id': new_picking.id,
			'view_mode': 'form',
			'target': 'current',
		}


class SalesOrderLine(models.Model):
	_inherit = "sale.order.line"

	ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")
	qty_returned = fields.Float(string='Returned Qty', compute='_compute_qty_returned', store=True)

	@api.depends('move_ids', 'move_ids.state', 'move_ids.quantity')
	def _compute_qty_returned(self):
		for line in self:
			# Count quantities from return moves (incoming moves from customer location)
			qty_returned = sum(line.move_ids.filtered(
				lambda m: m.state == 'done' and
						  m.location_id.usage == 'customer' and
						  m.location_dest_id.usage == 'internal'
			).mapped('quantity'))
			line.qty_returned = qty_returned