# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.osv import expression

from markupsafe import Markup


class AccountMove(models.Model):
	_inherit = 'account.move'

	# --- Link to Landed Costs ---
	# Using compute to find related LCs based on PO or Bill link
	ths_stock_landed_cost_ids = fields.One2many('stock.landed.cost', compute='_compute_landed_costs', string='Landed Costs (Related)', copy=False,
												help="Landed Costs related to this document (via PO or direct Bill link).")
	landed_cost_count = fields.Integer(compute='_compute_landed_costs', string="# Landed Costs")
	ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")
	partner_type_id = fields.Many2one('ths.partner.type', string='Partner Type', readonly=False, copy=True, index=True, ondelete='cascade',
									  help="Choose proper Partner Type to show related Partners")

	payment_journal_name = fields.Char(string='Payment Journal', compute='_compute_payment_info', store=True)
	payment_method_name = fields.Char(string='Payment Method', compute='_compute_payment_info', store=True)
	amount_paid = fields.Monetary(string='Amount Paid', compute='_compute_payment_info', store=True)

	global_discount_type = fields.Selection([('percent', 'Percentage'), ('amount', 'Fixed Amount')], string='Global Discount Type', default='percent', tracking=True)
	global_discount_rate = fields.Float(string='Global Discount Rate', default=0.0, digits=(16, 3), tracking=True, help="Discount rate as percentage (0-100) or fixed amount")
	global_discount_amount = fields.Monetary(string='Global Discount Amount', currency_field='currency_id', compute='_compute_global_discount_amount',
											 help="Calculated global discount amount")
	subtotal_before_global_discount = fields.Monetary(string='Subtotal Before Global Discount', compute='_compute_discount_breakdown', currency_field='currency_id')
	line_discount_amount = fields.Monetary(string='Line Discounts Total', compute='_compute_discount_breakdown', currency_field='currency_id')

	@api.onchange('partner_type_id')
	def _onchange_partner_type_clear_partner(self):
		"""Clear partner when partner type changes"""
		if self.partner_type_id:
			self.partner_id = False

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		super()._onchange_partner_id()
		if self.partner_id and self.partner_id.partner_type_id:
			self.partner_type_id = self.partner_id.partner_type_id

	@api.depends('payment_state', 'line_ids.matched_debit_ids', 'line_ids.matched_credit_ids')
	def _compute_payment_info(self):
		"""Compute payment information when invoice is paid"""
		for move in self:
			if move.payment_state == 'paid':
				# Find payment lines
				payment_lines = move.line_ids.filtered(lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable'])
				payments = payment_lines.mapped('matched_debit_ids.debit_move_id.payment_id') | payment_lines.mapped('matched_credit_ids.credit_move_id.payment_id')

				if payments:
					payment = payments[0]  # Take first payment
					move.payment_journal_name = payment.journal_id.name
					move.payment_method_name = payment.payment_method_line_id.name
					move.amount_paid = payment.amount
				else:
					move.payment_journal_name = ''
					move.payment_method_name = ''
					move.amount_paid = 0.0
			else:
				move.payment_journal_name = ''
				move.payment_method_name = ''
				move.amount_paid = 0.0

	@api.depends('invoice_line_ids.price_subtotal', 'global_discount_type', 'global_discount_rate')
	def _compute_global_discount_amount(self):
		for move in self:
			# Early exit if no discount rate
			if not move.global_discount_rate or move.global_discount_rate <= 0:
				move.global_discount_amount = 0.0
				continue

			# Get global discount product to exclude from calculation
			discount_product = move.env.ref('ths_base.product_global_discount', raise_if_not_found=False)

			# Calculate based on lines excluding the global discount line itself
			regular_lines = move.invoice_line_ids.filtered(
				lambda l: not l.display_type and (not discount_product or l.product_id != discount_product)
			)

			# Early exit if no regular lines
			if not regular_lines:
				move.global_discount_amount = 0.0
				continue

			subtotal_before_global_discount = sum(regular_lines.mapped('price_subtotal'))

			if move.global_discount_type == 'percent':
				move.global_discount_amount = subtotal_before_global_discount * (move.global_discount_rate / 100)
			else:  # amount
				move.global_discount_amount = min(move.global_discount_rate, subtotal_before_global_discount)

	@api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.price_unit', 'invoice_line_ids.quantity', 'invoice_line_ids.discount')
	def _compute_discount_breakdown(self):
		for move in self:
			# Get global discount product to exclude from calculation
			discount_product = move.env.ref('ths_base.product_global_discount', raise_if_not_found=False)

			regular_lines = move.invoice_line_ids.filtered(
				lambda l: not l.display_type and (not discount_product or l.product_id != discount_product)
			)

			if regular_lines:
				# Subtotal before any discounts (using price_unit * quantity) - This is "Total W/o Disc"
				subtotal_before_discounts = sum(line.price_unit * line.quantity for line in regular_lines)

				# Current subtotal (after line discounts but before global discount)
				subtotal_after_line_discounts = sum(regular_lines.mapped('price_subtotal'))

				# Set the field that shows in "Total W/o Disc" to be before ALL discounts
				move.subtotal_before_global_discount = subtotal_before_discounts

				# Line discount amount (difference between before and after line discounts)
				move.line_discount_amount = subtotal_before_discounts - subtotal_after_line_discounts
			else:
				move.subtotal_before_global_discount = 0.0
				move.line_discount_amount = 0.0

	@api.onchange('global_discount_type', 'global_discount_rate')
	def _onchange_global_discount(self):
		"""Update global discount line when discount changes"""
		if self.state == 'draft':
			# Only update if there's actually a discount to apply
			if self.global_discount_rate > 0:
				self._update_global_discount_line()
			else:
				# Remove any existing global discount line if rate is 0
				self._remove_global_discount_line()

	@api.onchange('global_discount_type')
	def _onchange_global_discount_type(self):
		"""Clear the rate when discount type changes"""
		if self.state == 'draft':
			self.global_discount_rate = 0.0
			# Remove any existing global discount line since rate is now 0
			self._remove_global_discount_line()

	@api.onchange('invoice_line_ids')
	def _onchange_invoice_line_ids(self):
		"""Clear global discount when all regular lines are deleted"""
		if self.state == 'draft':
			# Get global discount product to exclude from calculation
			discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)

			regular_lines = self.invoice_line_ids.filtered(
				lambda l: not l.display_type and (not discount_product or l.product_id != discount_product)
			)

			# If no regular lines exist, clear global discount
			if not regular_lines:
				self.global_discount_type = 'percent'
				self.global_discount_rate = 0.0
				self._remove_global_discount_line()

	def _remove_global_discount_line(self):
		"""Remove global discount line if it exists"""
		if self.state != 'draft':
			return

		discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
		if not discount_product:
			return

		existing_discount_line = self.invoice_line_ids.filtered(
			lambda l: l.product_id == discount_product
		)

		if existing_discount_line:
			# Use unlink instead of command to properly remove the line
			existing_discount_line.unlink()

	def _update_global_discount_line(self):
		"""Add, update, or remove global discount line - ONLY creates lines when amount > 0"""
		self.ensure_one()

		if self.state != 'draft':
			return

		# Get global discount product
		discount_product = self.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
		if not discount_product:
			return

		# Find existing global discount line
		existing_discount_line = self.invoice_line_ids.filtered(
			lambda l: l.product_id == discount_product
		)

		# Calculate discount amount
		self._compute_global_discount_amount()

		# CRITICAL: Only create/update if amount is actually greater than 0
		if self.global_discount_amount > 0.01:  # Use small threshold to avoid floating point issues
			# Create or update discount line
			discount_line_vals = {
				'product_id': discount_product.id,
				'name': f"Global Discount ({self.global_discount_rate}{'%' if self.global_discount_type == 'percent' else ' ' + self.currency_id.symbol})",
				'quantity': 1,
				'price_unit': -self.global_discount_amount,  # Negative for discount
				'account_id': discount_product.property_account_income_id.id or
							  discount_product.categ_id.property_account_income_categ_id.id,
			}

			if existing_discount_line:
				# Update existing line
				existing_discount_line.write({
					'name': discount_line_vals['name'],
					'price_unit': discount_line_vals['price_unit'],
				})
			else:
				# Create new line - but only if amount > 0
				self.env['account.move.line'].create({
					**discount_line_vals,
					'move_id': self.id,
				})
		else:
			# Remove existing discount line if amount is 0 or less
			if existing_discount_line:
				existing_discount_line.unlink()

	@api.constrains('global_discount_rate', 'global_discount_type')
	def _check_global_discount_rate(self):
		for move in self:
			if move.global_discount_type == 'percent' and (move.global_discount_rate < 0 or move.global_discount_rate > 100):
				raise ValidationError("Discount percentage must be between 0 and 100.")
			elif move.global_discount_type == 'amount' and move.global_discount_rate < 0:
				raise ValidationError("Discount amount cannot be negative.")

	def _compute_landed_costs(self):
		""" Find landed costs linked via PO (if bill from PO) or directly """
		LandedCost = self.env['stock.landed.cost']
		for move in self:
			landed_costs = LandedCost
			# Find via direct link (most reliable if set)
			landed_costs |= LandedCost.search([('vendor_bill_id', '=', move.id)])
			# Find via PO link (can find LCs created from PO before bill link)
			po_ids = move.invoice_line_ids.purchase_line_id.order_id.ids
			if po_ids:
				landed_costs |= LandedCost.search(
					[('purchase_order_id', 'in', list(set(po_ids)))])  # Use set for unique POs

			move.ths_stock_landed_cost_ids = landed_costs
			move.landed_cost_count = len(landed_costs)

	def action_view_landed_costs(self):
		""" Smart button action to view related landed costs """
		self.ensure_one()
		action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
		landed_costs = self.ths_stock_landed_cost_ids
		action['domain'] = [('id', 'in', landed_costs.ids)]
		action['context'] = dict(self.env.context)
		# Pre-fill bill and potentially PO if creating new from list
		action['context']['default_vendor_bill_id'] = self.id
		# Find unique PO linked to lines
		po_ids = self.invoice_line_ids.purchase_line_id.order_id.ids
		if len(set(po_ids)) == 1:
			action['context']['default_purchase_order_id'] = po_ids[0]
		if len(landed_costs) == 1:
			action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
			action['res_id'] = landed_costs.id
		return action

	# --- Override Post Action ---
	def action_post(self):
		""" Override to sync cost lines to related draft LC """
		res = super(AccountMove, self).action_post()
		# After posting, find related draft LC and update its cost lines
		for bill in self.filtered(lambda m: m.move_type == 'in_invoice' and m.state == 'posted'):
			try:
				bill._sync_posted_bill_to_landed_cost()
			except Exception as e:
				# _logger.error(f"Error during automatic LC sync for Bill {bill.name}: {e}")
				bill.message_post(body=_(
					"Warning: Failed to automatically update linked Landed Cost record. Please check manually. Error: %s",
					e))
		return res

	def _sync_posted_bill_to_landed_cost(self):
		""" Finds related DRAFT LC and updates its cost lines from this bill """
		self.ensure_one()
		# _logger.info(f"Bill {self.name}: Checking for draft LC to sync cost lines...")

		# Find associated POs from bill lines
		po_ids = self.invoice_line_ids.purchase_line_id.order_id.ids
		unique_po_ids = list(set(po_ids))

		# Find draft LC linked to this Bill OR linked to the PO(s)
		# Prioritize LC linked directly to the bill first
		domain = [('state', '=', 'draft')]
		bill_domain = [('vendor_bill_id', '=', self.id)]
		po_domain = [('purchase_order_id', 'in', unique_po_ids)] if unique_po_ids else [('id', '=', 0)]

		related_lc = self.env['stock.landed.cost'].search(expression.AND([domain, bill_domain]), limit=1)
		if not related_lc and unique_po_ids:
			# If not linked to bill, find one linked to the PO
			related_lc = self.env['stock.landed.cost'].search(expression.AND([domain, po_domain]), limit=1)

		if not related_lc:
			# _logger.info(f"Bill {self.name}: No related draft Landed Cost found to sync.")
			# --- Auto-Create LC from Bill if none found ---
			# _logger.info(f"Bill {self.name}: Attempting to auto-create LC.")
			bill_lc_lines = self.invoice_line_ids.filtered(
				lambda l: l.product_id and l.product_id.product_tmpl_id.landed_cost_ok)
			if bill_lc_lines:
				lc_vals = {
					'vendor_bill_id': self.id,
					'date': self.invoice_date or fields.Date.context_today(self),
					'ths_effective_date': self.invoice_date or fields.Date.context_today(self),
					# Link to PO only if unique
					'purchase_order_id': unique_po_ids[0] if len(unique_po_ids) == 1 else False,
				}
				new_lc = self.env['stock.landed.cost'].create(lc_vals)
				# Now populate lines (similar to onchange logic)
				new_cost_lines_vals = []
				for bill_line in bill_lc_lines:
					split_method = bill_line.product_id.split_method_landed_cost or 'equal'
					account_id = bill_line.account_id.id
					if not account_id: accounts_data = bill_line.product_id.product_tmpl_id.get_product_accounts(); account_id = accounts_data.get(
						'stock_input') and accounts_data['stock_input'].id
					if not account_id: continue
					new_cost_lines_vals.append((0, 0, {'product_id': bill_line.product_id.id, 'name': bill_line.name,
													   'account_id': account_id, 'split_method': split_method,
													   'price_unit': bill_line.price_subtotal}))
				if new_cost_lines_vals:
					new_lc.write({'cost_lines': new_cost_lines_vals})
				# _logger.info(f"Bill {self.name}: Auto-created and populated LC {new_lc.name}")
				# Post message on Bill
				lc_link = Markup(new_lc._get_html_link()) if hasattr(new_lc, '_get_html_link') else new_lc.name
				self.message_post(body=_("Automatically created Landed Cost %s from this Bill.", lc_link))
				# Post message on LC
				bill_link = Markup(self._get_html_link()) if hasattr(self, '_get_html_link') else self.name
				new_lc.message_post(body=_("Landed Cost created automatically from Vendor Bill %s.", bill_link))
			# else:
			# _logger.info(f"Bill {self.name}: No LC lines found on bill, no LC created.")
			return  # Exit after creating

		# --- If existing draft LC was found ---
		# _logger.info(f"Bill {self.name}: Found draft LC {related_lc.name}. Syncing cost lines...")
		new_cost_lines_vals = []
		bill_lc_lines = self.invoice_line_ids.filtered(
			lambda l: l.product_id and l.product_id.product_tmpl_id.landed_cost_ok)
		for bill_line in bill_lc_lines:
			split_method = bill_line.product_id.split_method_landed_cost or 'equal'
			account_id = bill_line.account_id.id
			if not account_id: accounts_data = bill_line.product_id.product_tmpl_id.get_product_accounts(); account_id = accounts_data.get(
				'stock_input') and accounts_data['stock_input'].id
			if not account_id: continue
			new_cost_lines_vals.append((0, 0, {'product_id': bill_line.product_id.id, 'name': bill_line.name,
											   'account_id': account_id, 'split_method': split_method,
											   'price_unit': bill_line.price_subtotal}))

		# Update the LC: Link the bill, replace cost lines
		update_vals = {
			'vendor_bill_id': self.id,  # Ensure bill is linked
			'cost_lines': [(5, 0, 0)] + new_cost_lines_vals,  # Replace lines
			# Update PO link only if currently empty on LC and unique PO found on bill
			'purchase_order_id': related_lc.purchase_order_id.id or (
				unique_po_ids[0] if len(unique_po_ids) == 1 else False),
		}
		related_lc.write(update_vals)
		related_lc.message_post(body=_("Cost lines updated based on posted Vendor Bill %s.", self.display_name))

	# Get Default Date on Bill and partner type if passed through context
	@api.model
	def default_get(self, fields_list):
		defaults = super(AccountMove, self).default_get(fields_list)

		# Check if creating a Vendor Bill and invoice_date default is needed
		if 'invoice_date' in fields_list and not defaults.get('invoice_date'):
			# Check context for move type (more reliable than checking defaults['move_type'])
			if self.env.context.get('default_move_type') == 'in_invoice':
				defaults['invoice_date'] = fields.Date.context_today(self)

		partner_id = defaults.get('partner_id') or self.env.context.get('default_partner_id')
		if partner_id and 'partner_type_id' in fields_list:
			partner = self.env['res.partner'].browse(partner_id)
			if partner.partner_type_id:
				defaults['partner_type_id'] = partner.partner_type_id.id

		return defaults

	@api.model_create_multi
	def create(self, vals_list):
		moves = super().create(vals_list)
		for move in moves:
			# Only create global discount line if there's actually a discount AND regular lines
			if (move.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund') and
					move.global_discount_rate > 0.01 and
					move.state == 'draft'):

				# Check if there are regular lines (non-discount lines)
				discount_product = move.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
				regular_lines = move.invoice_line_ids.filtered(
					lambda l: not l.display_type and (not discount_product or l.product_id != discount_product)
				)

				# Only create discount line if there are regular lines to apply discount to
				if regular_lines:
					move._update_global_discount_line()
		return moves

	def write(self, vals):
		result = super().write(vals)

		# Only update global discount line if relevant fields changed AND there's a discount rate
		should_update_discount = (
				any(field in vals for field in ['global_discount_type', 'global_discount_rate']) and
				self.state == 'draft'
		)

		if should_update_discount:
			for move in self:
				if move.global_discount_rate > 0.01:
					# Check if there are regular lines
					discount_product = move.env.ref('ths_base.product_global_discount', raise_if_not_found=False)
					regular_lines = move.invoice_line_ids.filtered(
						lambda l: not l.display_type and (not discount_product or l.product_id != discount_product)
					)

					if regular_lines:
						move._update_global_discount_line()
					else:
						# No regular lines, remove any discount line
						move._remove_global_discount_line()
				else:
					# No discount rate, remove any discount line
					move._remove_global_discount_line()

		return result


class AccountInvoiceLine(models.Model):
	_inherit = "account.move.line"

	ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")


class AccountJournal(models.Model):
	_inherit = 'account.journal'

	end_user_payment_method = fields.Boolean(string='Payment Method', default=False, help="If checked, this journal will appear in the POS-like payment interface")
	ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")