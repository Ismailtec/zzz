# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv import expression
# from datetime import datetime
import logging
from markupsafe import Markup  # For chatter message links

_logger = logging.getLogger(__name__)


class StockLandedCost(models.Model):
	_inherit = 'stock.landed.cost'

	# --- Helper Methods for Domains ---
	def _get_base_bill_domain_list(self):
		""" Returns the base domain LIST for vendor bills. """
		company_id = self.company_id.id if self.company_id else self.env.company.id
		return [('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('company_id', '=', company_id)]

	def _get_base_picking_domain_list(self):
		""" Returns the base domain LIST for pickings. """
		company_id = self.company_id.id if self.company_id else self.env.company.id
		return [
			('state', '=', 'done'),
			('picking_type_code', '=', 'incoming'),
			('company_id', '=', company_id),
			('move_ids.stock_valuation_layer_ids', '!=', False)
		]

	# --- Compute Methods for Domain Fields ---
	@api.depends('purchase_order_id', 'company_id')
	def _compute_bill_domain(self):
		""" Compute domain string for vendor_bill_id based on purchase_order_id. """
		for record in self:
			base_domain = record._get_base_bill_domain_list()
			po = record.purchase_order_id
			if po:
				# Link bill via lines linked to the specific PO
				po_domain_part = [('invoice_line_ids.purchase_line_id.order_id', '=', po.id)]
				final_domain = expression.AND([base_domain, po_domain_part])
			else:
				final_domain = base_domain
			record.bill_domain = str(final_domain)

	@api.depends('purchase_order_id', 'company_id')
	def _compute_picking_domain(self):
		""" Compute domain string for picking_ids based on purchase_order_id. """
		for record in self:
			base_domain = record._get_base_picking_domain_list()
			po = record.purchase_order_id
			if po:
				po_domain_part = [('purchase_id', '=', po.id)]
				final_domain = expression.AND([base_domain, po_domain_part])
			else:
				final_domain = base_domain
			record.picking_domain = str(final_domain)

	# --- Default Methods ---
	@api.model
	def _default_ths_effective_date(self):
		return self.env.context.get('default_date') or fields.Date.context_today(self)

	# --- Fields ---
	ths_effective_date = fields.Date(
		string="Effective Date", copy=False, index=True,
		help="Effective date for the accounting entry.",
		readonly=False,  # Let XML handle readonly
		default=_default_ths_effective_date
	)
	purchase_order_id = fields.Many2one(
		'purchase.order',
		string='Purchase Order',
		compute='_compute_po_id',
		store=True,
		readonly=False,  # Let XML handle readonly
		help="Filters related bills and transfers, Auto-populated from the Vendor Bill's linked Purchase Order if created from Bill."
	)
	# Computed domain fields
	picking_domain = fields.Char(
		string='Picking Domain',
		compute='_compute_picking_domain'
	)
	bill_domain = fields.Char(
		string='Vendor Bill Domain',
		compute='_compute_bill_domain'
	)
	manual_po_selection = fields.Boolean(
		string="Manual PO Selection",
		help="Track if PO was manually selected to avoid auto-override.",
		default=False,
		copy=False
	)
	# Technical field for dependency tracking
	# compute_trigger = fields.Integer(
	#     compute='_compute_auto_trigger',
	#     store=True,
	#     help="Triggers computation when vendor bill + pickings + lines change."
	# )

	# --- Fields for Reversal ---
	is_reversed = fields.Boolean("Is Reversed Entry?", default=False, copy=False, readonly=True)
	original_lc_id = fields.Many2one('stock.landed.cost', 'Original Landed Cost', index=True, copy=False, readonly=True)
	reversal_lc_id = fields.Many2one('stock.landed.cost', 'Reversal Landed Cost', index=True, copy=False, readonly=True)

	# Inherited fields - Needed for domains
	vendor_bill_id = fields.Many2one('account.move')
	picking_ids = fields.Many2many('stock.picking')
	cost_lines = fields.One2many('stock.landed.cost.lines', 'cost_id')
	account_move_id = fields.Many2one('account.move')

	# --- Compute Methods ---
	@api.depends('vendor_bill_id', 'vendor_bill_id.line_ids.purchase_line_id.order_id', 'picking_ids.purchase_id')
	def _compute_po_id(self):
		"""
		Auto-set PO from Vendor Bill or Pickings unless manually set.
		If PO is set from Vendor Bill, also attempt to auto-set Pickings.
		"""
		for cost in self:
			if cost.manual_po_selection:
				continue

			original_po = cost.purchase_order_id  # Store original PO before calculation

			# --- Priority 1: Determine PO from Vendor Bill ---
			derived_po_from_bill = False
			if cost.vendor_bill_id:
				# Use invoice_line_ids as per your previous working domain logic
				po_lines = cost.vendor_bill_id.invoice_line_ids.filtered(lambda l: l.purchase_line_id)
				pos = po_lines.mapped('purchase_line_id.order_id')
				if len(pos) == 1:
					derived_po_from_bill = pos
					# Set the PO field
					cost.purchase_order_id = derived_po_from_bill
					_logger.info(
						f"LC {cost.name or 'New'}: PO {derived_po_from_bill.name} derived from Bill {cost.vendor_bill_id.name}.")

					# --- Attempt to auto-populate pickings based on derived PO ---
					_logger.info(
						f"LC {cost.name or 'New'}: Attempting to auto-populate pickings for PO {derived_po_from_bill.name}.")
					# Use the helper method to get the correct domain for this PO
					picking_domain_list = cost._get_picking_domain()  # This uses the just-set cost.purchase_order_id
					eligible_pickings = self.env['stock.picking'].search(picking_domain_list)
					if len(eligible_pickings) == 1:
						# Check if it's different from current selection before writing
						if cost.picking_ids != eligible_pickings:
							cost.picking_ids = [(6, 0, eligible_pickings.ids)]
							_logger.info(
								f"Auto-selecting Picking(s) based on Bill's PO: {eligible_pickings.mapped('name')}")
						else:
							_logger.info("Picking already correctly set.")
					else:
						_logger.info(f"Found {len(eligible_pickings)} pickings for derived PO. Clearing pickings.")
						# Clear pickings if multiple or zero found for the derived PO
						cost.picking_ids = [(5, 0, 0)]
				# --- End picking auto-population ---

				else:
					# Bill exists but doesn't link to a single PO
					_logger.info(
						f"LC {cost.name or 'New'}: Bill {cost.vendor_bill_id.name} does not link to a single PO. Clearing PO and Pickings.")
					cost.purchase_order_id = False
					cost.picking_ids = [(5, 0, 0)]  # Clear pickings if PO couldn't be determined from bill

			# --- Priority 2: Determine PO from Pickings (only if no PO derived from Bill) ---
			elif cost.picking_ids:
				# If PO wasn't set via bill, try via pickings
				pos = cost.picking_ids.mapped('purchase_id')
				derived_po_from_picking = pos if len(pos) == 1 else False
				cost.purchase_order_id = derived_po_from_picking
				_logger.info(
					f"LC {cost.name or 'New'}: PO {derived_po_from_picking.name if derived_po_from_picking else 'False'} derived from Pickings.")
			# When PO is derived from picking, we don't clear/re-set pickings here to avoid loops.
			# We also don't auto-set the bill here, that's handled by the bill's onchange if needed.
			else:
				# No Bill and no Pickings, ensure PO is clear
				cost.purchase_order_id = False

			# Log if PO changed during compute (for debugging)
			if cost.purchase_order_id != original_po:
				_logger.debug(
					f"LC {cost.name or 'New'}: PO changed from {original_po.name if original_po else 'False'} to {cost.purchase_order_id.name if cost.purchase_order_id else 'False'} during compute.")

	# @api.depends('cost_lines.price_unit')
	# def _compute_auto_trigger(self):
	#     """Smart automatic computation trigger - Keep your logic"""
	#     for record in self:
	#         record.compute_trigger = (record.compute_trigger or 0) + 1
	#         record.compute_landed_cost()
	# if not self.env.context.get('auto_computing'):
	#     try:
	#         # Log before calling compute
	#         _logger.info(
	#             f"LC {record.name or 'New'} - Auto Trigger: Conditions met. Calling compute_landed_cost.")
	#         #record.with_context(auto_computing=True).compute_landed_cost()
	#
	#     except Exception as e:
	#         _logger.error(f"Error during automatic compute_landed_cost for LC {record.id}: {e}")

	# --- Onchange Methods ---
	@api.onchange('ths_effective_date')
	def _onchange_ths_effective_date(self):
		""" When Effective Date changes, update the main Date field """
		if not isinstance(self.id, models.NewId):  # Avoid running on initial empty record
			if self.ths_effective_date:
				current_date = self.date
				if current_date != self.ths_effective_date:
					self.date = self.ths_effective_date
					_logger.info(
						f"LC {self.name or 'New'}: Onchange set main date to {self.date} from effective_date {self.ths_effective_date}")

	@api.onchange('purchase_order_id')
	def _onchange_purchase_order_id(self):
		"""Track manual PO selection and auto-select Bill/Pickings."""
		if self.purchase_order_id:
			self.manual_po_selection = True

			# Clear existing Bill/Pickings
			self.vendor_bill_id = False
			self.picking_ids = [(5, 0, 0)]

			# Auto-select Bill if only one matches
			bills = self.env['account.move'].search(self._get_bill_domain())
			if len(bills) == 1: self.vendor_bill_id = bills

			# Auto-select Pickings if only one matches
			pickings = self.env['stock.picking'].search(self._get_picking_domain())
			if len(pickings) == 1: self.picking_ids = pickings

		else:  # Handle clearing PO
			self.manual_po_selection = False  # Allow auto-compute again if PO cleared
			self.vendor_bill_id = False
			self.picking_ids = [(5, 0, 0)]
		return {}

	@api.onchange('vendor_bill_id')
	def _onchange_vendor_bill_id(self):
		"""
		If bill changes:
		1. Reset manual PO flag & trigger PO compute.
		2. If single PO determined, try auto-select Pickings.
		3. Auto-populate Cost Lines from the selected Bill's landed cost lines.
		4. Show multi-PO warning if needed.
		"""
		# Detect if bill actually changed
		bill_changed = False
		origin_bill_id = self._origin.vendor_bill_id.id if hasattr(self,
																   '_origin') and self._origin and self._origin.vendor_bill_id else None
		current_bill_id = self.vendor_bill_id.id if self.vendor_bill_id else None

		if current_bill_id != origin_bill_id:
			bill_changed = True

		if bill_changed:
			# _logger.info(
			#     f"LC {self.display_name or 'New'}: Bill changed/set/cleared to {current_bill_id}. Resetting related fields.")
			self.manual_po_selection = False
			self.purchase_order_id = False
			self.picking_ids = [(5, 0, 0)]
			self.cost_lines = [(5, 0, 0)]  # Clear cost lines too

			# Trigger PO computation based on the newly selected bill
			self._compute_po_id()

			# --- Auto-populate Cost Lines (Only if a bill is now selected) ---
			if self.vendor_bill_id:
				new_cost_lines_vals = []
				bill_landed_cost_lines = self.vendor_bill_id.invoice_line_ids.filtered(
					lambda line: line.product_id and line.product_id.product_tmpl_id.landed_cost_ok
				)
				# _logger.info(
				#     f"Found {len(bill_landed_cost_lines)} landed cost type lines on Bill {self.vendor_bill_id.name}.")
				for bill_line in bill_landed_cost_lines:
					split_method = bill_line.product_id.split_method_landed_cost or 'equal'
					account_id = bill_line.account_id.id
					if not account_id:
						accounts_data = bill_line.product_id.product_tmpl_id.get_product_accounts()
						account_id = accounts_data.get('stock_input') and accounts_data['stock_input'].id
					if not account_id:
						# _logger.warning(
						#     f"Could not determine account for LC line from product {bill_line.product_id.name} on bill line {bill_line.id}. Skipping line.")
						continue

					new_cost_lines_vals.append((0, 0, {
						'product_id': bill_line.product_id.id,
						'name': bill_line.name,
						'account_id': account_id,
						'split_method': split_method,
						'price_unit': bill_line.price_subtotal,
					}))

				if new_cost_lines_vals:
					# _logger.info(
					#     f"Populating {len(new_cost_lines_vals)} cost lines from Bill {self.vendor_bill_id.name}")
					self.cost_lines = new_cost_lines_vals

				# --- Auto-select Pickings (based on potentially derived PO) ---
				derived_po = self.purchase_order_id
				if derived_po:
					# _logger.info(
					#     f"LC {self.display_name or 'New'}: PO {derived_po.name} derived from Bill. Checking for single Picking.")
					picking_domain_str = self.picking_domain
					try:
						picking_domain_list = eval(
							picking_domain_str) if picking_domain_str else self._get_base_picking_domain_list()
					except Exception:
						# _logger.error(f"Failed to evaluate picking domain string: {picking_domain_str}");
						picking_domain_list = self._get_base_picking_domain_list()

					if picking_domain_list:
						eligible_pickings = self.env['stock.picking'].search(picking_domain_list)
						if len(eligible_pickings) == 1:
							if not self.picking_ids or self.picking_ids.ids != eligible_pickings.ids:
								self.picking_ids = [(6, 0, eligible_pickings.ids)]
							# _logger.info(
							# 	f"Auto-selecting Picking(s) based on Bill's PO: {eligible_pickings.mapped('name')}")
						else:
							_logger.info(
								f"Found {len(eligible_pickings)} pickings for derived PO {derived_po.name}. Manual selection required.")
					else:
						_logger.warning(f"Could not determine picking domain for derived PO {derived_po.name}")
				# --- End Auto-select Pickings ---

				# # --- Explicitly Trigger Compute if all conditions met ---
				# current_bill = self.vendor_bill_id
				# if current_bill and self.picking_ids and self.cost_lines.filtered(lambda l: l.price_unit and l.split_method):
				#     _logger.info(
				#         f"LC {self.display_name or 'New'}: Triggering compute_landed_cost after populating lines/pickings.")
				#     # Use try-except as compute might fail
				#     try:
				#         self.compute_landed_cost()
				#     except Exception as e:
				#         _logger.error(f"Error during automatic compute_landed_cost: {e}")
				#         # Optionally show a warning to the user
				#         #return {'warning': {'title': _('Computation Error'), 'message': _("Could not automatically compute costs: %s", e)}}
				# # --- End Explicit Trigger ---

				# --- Multi-PO Warning ---
				po_lines = self.vendor_bill_id.invoice_line_ids.filtered(lambda l: l.purchase_line_id)
				pos = po_lines.mapped('purchase_line_id.order_id')
				if len(pos) > 1:
					return {'warning': {'title': _('Multiple POs Detected'), 'message': _(
						'This bill (%s) references multiple POs (%s). Please select a specific PO manually.',
						self.vendor_bill_id.name, ", ".join(pos.mapped('name')))}}

		return {}

	# --- Helper Methods ---
	def _get_bill_domain(self):
		if self.purchase_order_id:
			return [('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
					('invoice_line_ids.purchase_line_id.order_id', '=', self.purchase_order_id.id)]
		return [('move_type', '=', 'in_invoice'), ('state', '=', 'posted')]  # Base domain if no PO

	def _get_picking_domain(self):
		if self.purchase_order_id:
			return [('picking_type_code', '=', 'incoming'), ('state', '=', 'done'),
					('move_ids.purchase_line_id.order_id', '=', self.purchase_order_id.id)]
		return [('picking_type_code', '=', 'incoming'), ('state', '=', 'done')]  # Base domain if no PO

	# --- Overridden Methods ---
	# def compute_landed_cost(self):  # Keep your override
	#     """Override to prevent infinite loops"""
	#     if self.env.context.get('auto_computing'):
	#         return super().compute_landed_cost()
	#     return super(StockLandedCost, self.with_context(auto_computing=True)).compute_landed_cost()

	def button_validate(self):
		""" Extend standard validation to ensure proper cost recomputation """
		# Snapshot
		_logger.info(f"LC {self.id}: Taking snapshot of product costs before validation.")
		products_to_snapshot = self.valuation_adjustment_lines.mapped('product_id').filtered(
			lambda p: p.cost_method in ('average', 'fifo'))
		if products_to_snapshot:
			_logger.info(f"LC {self.id}: Snapping cost for products: {products_to_snapshot.ids}")
			for product in products_to_snapshot:
				try:
					product.sudo().write({'ths_last_standard_price': product.standard_price})
				except Exception as e:
					_logger.error(f"Failed to snapshot cost for product {product.id}: {e}")
		else:
			_logger.info(f"LC {self.id}: No relevant products found on adjustment lines to snapshot cost for.")

		# Effective date context logic
		context_with_date = self.env.context.copy()
		final_je_date = self.ths_effective_date or self.date
		if final_je_date:
			context_with_date['force_period_date'] = final_je_date

		# Auto Compute incase forgotten by user
		self.compute_landed_cost()

		res = super(StockLandedCost, self.with_context(context_with_date)).button_validate()

		# Keep JE Ref update logic
		if self.account_move_id:
			try:
				new_ref = f"LC: {self.name or '/'}";
				ref_parts = []
				if self.purchase_order_id: ref_parts.append(f"PO: {self.purchase_order_id.name}")
				if self.vendor_bill_id: ref_parts.append(f"Bill: {self.vendor_bill_id.name or '/'}")
				# Include reversal info in ref if applicable
				if self.original_lc_id: ref_parts.append(f"Reversal of: {self.original_lc_id.name}")
				# if self.ths_effective_date: ref_parts.append(f"EffDt: {fields.Date.to_string(self.ths_effective_date)}")
				if ref_parts: new_ref += " (" + " | ".join(ref_parts) + ")"
				self.account_move_id.sudo().write({'ref': new_ref})
			# _logger.info(f"LC {self.id}: Updated JE {self.account_move_id.name} ref to: {new_ref}")
			except Exception as e:
				_logger.error(f"LC {self.id}: Failed to update JE ref: {e}")

			# *** ADD CHATTER TO JE ***
			try:
				lc_link = Markup(self._get_html_link()) if hasattr(self, '_get_html_link') else self.name
				body_msg = _("Journal Entry created from Landed Cost: %s", lc_link)
				self.account_move_id.message_post(body=body_msg)
			# _logger.info(f"Posted chatter on JE {self.account_move_id.name} linking back to LC {self.id}")
			except Exception as e:
				_logger.error(f"Failed to post chatter on JE {self.account_move_id.name}: {e}")
			# *** END ADD CHATTER ***

			# Verify Date
			if final_je_date and self.account_move_id.date != final_je_date:
				_logger.warning(
					f"LC {self.id}: JE {self.account_move_id.name} date ({self.account_move_id.date}) != effective date ({final_je_date}).")
		return res

	# --- Reversal Method ---
	def action_create_reversal(self):
		""" Creates a reversing Landed Cost entry. """
		self.ensure_one()
		if self.state != 'done':
			raise UserError(_("Only posted Landed Costs can be reversed."))
		if self.reversal_lc_id:
			raise UserError(_("This Landed Cost has already been reversed by %s.", self.reversal_lc_id.display_name))
		if self.is_reversed:
			raise UserError(_("This Landed Cost is already a reversal entry itself."))

		# _logger.info(f"Creating reversal for Landed Cost {self.name} ({self.id})")

		# Prepare default values for the copy
		default_vals = {
			'name': _('REVERSAL of %s', self.name),
			'is_reversed': True,
			'original_lc_id': self.id,
			'state': 'draft',
			'account_move_id': False,
			'date': self.ths_effective_date or self.date,
			'ths_effective_date': self.ths_effective_date or self.date,
			'purchase_order_id': self.purchase_order_id.id,
			'vendor_bill_id': self.vendor_bill_id.id,
			'picking_ids': [(6, 0, self.picking_ids.ids)],
			# Cost lines will be copied automatically, negate amounts next
		}

		# Create the reversal LC record
		try:
			reversal_lc = self.copy(default=default_vals)
		# _logger.info(f"Created reversal LC {reversal_lc.name} ({reversal_lc.id})")
		except Exception as e:
			# _logger.error(f"Failed to create reversal LC copy for {self.name}: {e}")
			raise UserError(_("Could not create the reversal entry. Error: %s", e))

		# Negate cost line amounts
		if reversal_lc.cost_lines:
			# _logger.info(f"Negating cost lines for reversal LC {reversal_lc.name}")
			# Use loop for safety
			for line in reversal_lc.cost_lines: line.price_unit = -line.price_unit
		self.write({'reversal_lc_id': reversal_lc.id, 'is_reversed': True})

		# Automatically compute and validate the reversal
		# _logger.info(f"Computing and validating reversal LC {reversal_lc.name}")
		try:
			reversal_lc.compute_landed_cost()
			reversal_lc.button_validate()
		# _logger.info(f"Reversal LC {reversal_lc.name} validated successfully.")
		except Exception as e:
			# _logger.error(f"Failed to compute/validate reversal LC {reversal_lc.name}: {e}")
			error_msg = _(
				"Failed to automatically compute/validate the reversal entry. Please review it manually. Error: %s", e)
			self.message_post(body=error_msg)
			reversal_lc.message_post(body=error_msg)
			action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
			action['res_id'] = reversal_lc.id
			action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
			return action

		# Add chatter messages AFTER successful validation
		orig_link = Markup(self._get_html_link()) if hasattr(self, '_get_html_link') else self.name
		rev_link = Markup(reversal_lc._get_html_link()) if hasattr(reversal_lc, '_get_html_link') else reversal_lc.name
		self.message_post(body=_("Reversed by %(reversal_lc)s created by %(user_name)s.", reversal_lc=rev_link,
								 user_name=self.env.user.name))
		reversal_lc.message_post(body=_("Reversal of %(original_lc)s created by %(user_name)s.", original_lc=orig_link,
										user_name=self.env.user.name))
		action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
		action['res_id'] = self.id
		action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
		return action

	# --- Actions for Smart Buttons ---
	def action_view_original_lc(self):
		""" Returns action to view the original Landed Cost record """
		self.ensure_one()
		if not self.original_lc_id:
			return False
		action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
		action['res_id'] = self.original_lc_id.id
		action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
		action['target'] = 'current'
		return action

	def action_view_reversal_lc(self):
		""" Returns action to view the reversal Landed Cost record """
		self.ensure_one()
		if not self.reversal_lc_id:
			return False
		action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
		action['res_id'] = self.reversal_lc_id.id
		action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
		action['target'] = 'current'
		return action