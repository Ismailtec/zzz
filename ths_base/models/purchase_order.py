# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
	_inherit = 'purchase.order'

	# --- Fields ---
	ths_effective_date = fields.Date(
		string="Date",
		copy=False,
		index=True,
		help="The primary effective date for this order. Sets the Order Deadline and lines' Expected Arrival. "
			 "This date will be propagated to the corresponding receipts (attempted via picking default_get).",
		default=fields.Date.context_today,
		tracking=True,
	)
	# Link to potentially multiple LC records created from this PO or related Bills
	ths_stock_landed_cost_ids = fields.One2many(
		'stock.landed.cost',
		'purchase_order_id',
		string='Landed Costs',
		copy=False,
		readonly=True,
		help="Landed Cost record(s) generated or linked from this PO."
	)
	ths_landed_cost_count = fields.Integer(
		compute='_compute_landed_cost_count',
		string="# Landed Costs"
	)
	ths_hide_taxes = fields.Boolean(
		related="company_id.ths_hide_taxes",
		readonly=False,
		string="Hide Taxes",
		help="Technical field to read the global config setting."
	)

	# --- Compute Methods ---
	@api.depends('ths_stock_landed_cost_ids')
	def _compute_landed_cost_count(self):
		""" Compute count for the smart button """
		for order in self:
			order.ths_landed_cost_count = len(order.ths_stock_landed_cost_ids)

	# --- Onchange Method ---
	@api.onchange('ths_effective_date')
	def _onchange_ths_effective_date(self):
		""" When Effective Date changes, update Order Deadline and Line Expected Arrival. """
		if self.ths_effective_date:
			# Ensure it's a date object before combining
			effective_date_only = self.ths_effective_date
			if isinstance(self.ths_effective_date, str):
				effective_date_only = fields.Date.from_string(self.ths_effective_date)

			if effective_date_only:
				effective_dt_naive = datetime.combine(effective_date_only, fields.time.min)
				self.date_order = effective_dt_naive
				# _logger.info(f"PO {self.name or 'New'}: Onchange set date_order to {self.date_order}")
				if self.order_line:
					# _logger.info(
					# f"PO {self.name or 'New'}: Updating {len(self.order_line)} lines' date_planned to {effective_dt_naive}")
					# Use update() for efficiency on potentially many lines
					self.order_line.update({'date_planned': effective_dt_naive})

	def _prepare_picking(self):
		"""Populating ths_effective_date on the stock picking"""
		res = super(PurchaseOrder, self)._prepare_picking()
		res['ths_effective_date'] = self.ths_effective_date
		return res

	# --- Action for Smart Button ---
	def action_view_landed_costs(self):
		""" Return action to view landed costs related to this PO """
		self.ensure_one()
		action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
		landed_costs = self.ths_stock_landed_cost_ids
		action['domain'] = [('id', 'in', landed_costs.ids)]
		action['context'] = dict(self.env.context)
		action['context']['default_purchase_order_id'] = self.id
		if self.partner_id:
			action['context']['default_partner_id'] = self.partner_id.id
		if len(landed_costs) == 1:
			action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
			action['res_id'] = landed_costs.id
		return action

	# @api.onchange('partner_id')
	# def _onchange_partner_id_set_vendor_type(self):
	#     vendor_type = self.env.ref('ths_base.partner_type_vendor', raise_if_not_found=False)
	#     if self.partner_id and vendor_type:
	#         # only set if blank or wrong
	#         if not self.partner_id.partner_type_id or \
	#                 self.partner_id.partner_type_id != vendor_type:
	#             self.partner_id.partner_type_id = vendor_type

	# --- Override button_confirm ---
	def button_confirm(self):
		""" Override to trigger LC creation/update after confirmation """
		res = super(PurchaseOrder, self).button_confirm()
		for order in self:
			try:
				order._create_or_update_landed_cost_from_po()
			except Exception as e:
				# Log error but don't block PO confirmation
				_logger.error(f"Error during automatic LC creation/update for PO {order.name}: {e}")
		return res

	def _create_or_update_landed_cost_from_po(self):
		"""
		Finds/Creates ONE draft Landed Cost record linked to this PO
		and populates its cost lines based on PO lines marked as landed costs.
		Called from button_confirm.
		"""
		self.ensure_one()
		# _logger.info(f"PO {self.name}: Checking for landed cost lines upon confirmation...")

		# Find PO lines with products marked as landed costs
		po_lc_lines = self.order_line.filtered(
			lambda l: l.product_id and l.product_id.product_tmpl_id.landed_cost_ok
		)

		if not po_lc_lines:
			_logger.info(f"PO {self.name}: No landed cost lines found.")
			# if existing_draft_lcs:
			#    _logger.warning(f"PO {self.name}: LC lines removed, but draft LCs {existing_draft_lcs.ids} still exist. Not deleting automatically.")
			return

		# _logger.info(f"PO {self.name}: Found {len(po_lc_lines)} landed cost lines. Finding/Creating LC record...")

		LandedCost = self.env['stock.landed.cost']
		# Find existing DRAFT landed cost linked ONLY to this PO
		domain = [('purchase_order_id', '=', self.id), ('state', '=', 'draft')]
		existing_lc = LandedCost.search(domain, limit=1)

		# Prepare cost line values from PO lines
		cost_lines_vals = []
		for po_line in po_lc_lines:
			# Use the product's default expense account or fallback
			accounts = po_line.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=self.fiscal_position_id)
			account_id = accounts.get('expense') or po_line.product_id.categ_id.property_account_expense_categ_id
			if not account_id:
				# _logger.warning(
				# f"PO {self.name}: Cannot find expense account for LC product {po_line.product_id.name} on line {po_line.id}. Skipping.")
				continue  # Skip if no account defined

			cost_lines_vals.append((0, 0, {
				'product_id': po_line.product_id.id,
				'name': po_line.name,
				'account_id': account_id.id,
				'split_method': po_line.product_id.split_method_landed_cost or 'equal',
				'price_unit': po_line.price_subtotal,
			}))

		if not cost_lines_vals:
			_logger.warning(f"PO {self.name}: No valid cost lines could be prepared. No LC created/updated.")
			return

		# Determine effective date to use
		lc_date = self.ths_effective_date or self.date_order.date() or fields.Date.context_today(self)

		if existing_lc:
			# Update existing draft LC: Replace cost lines
			# _logger.info(
			# f"PO {self.name}: Updating existing draft LC {existing_lc.name} ({existing_lc.id}) with {len(cost_lines_vals)} lines.")
			update_vals = {
				'cost_lines': [(5, 0, 0)] + cost_lines_vals,  # Replace all existing lines
				'date': lc_date,
				'ths_effective_date': lc_date,
			}
			existing_lc.write(update_vals)
			existing_lc.message_post(
				body=_("Cost lines updated based on confirmed Purchase Order %s.", self.display_name))
		else:
			# Create new draft LC
			# _logger.info(f"PO {self.name}: Creating new draft LC with {len(cost_lines_vals)} lines.")
			lc_vals = {
				'purchase_order_id': self.id,
				'vendor_bill_id': False,  # Bill comes later
				'date': lc_date,
				'ths_effective_date': lc_date,
				'cost_lines': cost_lines_vals,
			}
			new_lc = LandedCost.create(lc_vals)
			# _logger.info(f"PO {self.name}: Created new Landed Cost {new_lc.name} ({new_lc.id})")
			# Post message on LC
			po_link = Markup(self._get_html_link()) if hasattr(self, '_get_html_link') else self.name
			new_lc.message_post(body=_("Landed Cost created automatically from Purchase Order %s.", po_link))
			# Post message on PO
			lc_link = Markup(new_lc._get_html_link()) if hasattr(new_lc, '_get_html_link') else new_lc.name
			self.message_post(
				body=_("Automatically created Landed Cost %(lc_link)s based on lines in %(po_link)s.", lc_link=lc_link,
					   po_link=po_link))


class PurchaseOrderLine(models.Model):
	_inherit = "purchase.order.line"

	ths_hide_taxes = fields.Boolean(
		related="company_id.ths_hide_taxes",
		readonly=False,
		string="Hide Taxes",
		help="Technical field to read the global config setting."
	)