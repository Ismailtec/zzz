# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
# from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
	_inherit = 'stock.picking'

	# --- Fields ---
	ths_effective_date = fields.Date(
		string="Effective Date",
		compute="_compute_ths_effective_date",
		store=True,
		compute_sudo=True,
		copy=False,
		index=True,
		help="The primary date for this operation. Sets the Scheduled Date and Deadline. "
			 "Used as the effective date for stock moves and related accounting.",
		readonly=False,
		tracking=True,
	)

	# --- Link to Landed Costs ---
	# Using compute to find related LCs based on PO
	ths_stock_landed_cost_ids = fields.One2many(
		'stock.landed.cost',
		compute='_compute_landed_costs',  # Compute based on PO link
		string='Landed Costs (Related)',
		copy=False,
		help="Landed Costs related to this document (via PO)."
	)
	landed_cost_count = fields.Integer(compute='_compute_landed_costs', string="# Landed Costs")

	@api.depends('purchase_id.ths_stock_landed_cost_ids')  # Depend on the PO's LC link
	def _compute_landed_costs(self):
		""" Find landed costs linked via the associated Purchase Order """
		for picking in self:
			if picking.purchase_id:
				# Read directly from the related PO field
				landed_costs = picking.purchase_id.ths_stock_landed_cost_ids
				picking.ths_stock_landed_cost_ids = landed_costs
				picking.landed_cost_count = len(landed_costs)
			else:
				picking.ths_stock_landed_cost_ids = False
				picking.landed_cost_count = 0

	@api.depends("purchase_id.ths_effective_date")
	def _compute_ths_effective_date(self):
		for picking in self:
			if picking.purchase_id:
				picking.ths_effective_date = picking.purchase_id.ths_effective_date
			else:
				# Fallback: Set to today's date if no PO or PO has no date
				picking.ths_effective_date = fields.Date.today()

	# --- Onchange Methods ---
	@api.onchange('ths_effective_date')
	def _onchange_ths_effective_date(self):
		""" When Effective Date changes, update Scheduled Date and Deadline Date. """
		if self.ths_effective_date:
			effective_dt_naive = datetime.combine(
				self.ths_effective_date,
				datetime.min.time()  # Sets time to 00:00:00 Or: fields.time.min (if imported)
			)
			self.scheduled_date = effective_dt_naive
			self.date_deadline = effective_dt_naive
			# _logger.info(f"Onchange: Set scheduled_date & date_deadline to {effective_dt_naive}")

	# --- Overridden Methods ---
	def button_validate(self):
		""" Override validation: Pass ths_effective_date to moves and force_period_date in context.
			Also link picking to draft LC after validation """
		date_to_apply = self.ths_effective_date
		context_for_moves = self.env.context.copy()
		if date_to_apply:
			context_for_moves['force_period_date'] = date_to_apply

			# Update moves with ths_effective_date if missing
			self.move_ids.filtered(
				lambda m: m.state not in ('done', 'cancel') and not m.ths_effective_date
			).write({'ths_effective_date': date_to_apply})

		res = super(StockPicking, self.with_context(context_for_moves)).button_validate()

		# After validation, find related draft LC and add this picking
		# Use try-except to avoid blocking validation if LC logic fails
		try:
			for picking in self.filtered(lambda p: p.state == 'done' and p.purchase_id):
				# Find DRAFT LC linked to the same PO
				domain = [('purchase_order_id', '=', picking.purchase_id.id), ('state', '=', 'draft')]
				# Search for LCs related to this picking's PO
				related_lcs = self.env['stock.landed.cost'].search(domain)
				if related_lcs:
					# _logger.info(f"Picking {picking.name}: Linking self to draft LCs {related_lcs.ids}")
					# Add this picking to the existing pickings on the LC(s) using command 4
					related_lcs.sudo().write({'picking_ids': [(4, picking.id)]})
		except Exception as e:
			# _logger.error(f"Error linking picking {self.name} to LC: {e}")
			# Don't block validation, maybe add chatter?
			self.message_post(body=_(
				"Warning: Failed to automatically link this transfer to its Landed Cost record(s). Please check manually. Error: %s",
				e))
		return res

	# --- Action for Smart Button ---
	def action_view_landed_costs(self):
		""" Return action to view landed costs related to this picking (via PO) """
		self.ensure_one()
		action = self.env['ir.actions.actions']._for_xml_id('stock_landed_costs.action_stock_landed_cost')
		landed_costs = self.ths_stock_landed_cost_ids
		action['domain'] = [('id', 'in', landed_costs.ids)]
		action['context'] = dict(self.env.context)
		# Pre-fill picking and PO if creating new from list
		action['context']['default_picking_ids'] = [(6, 0, [self.id])]
		if self.purchase_id:
			action['context']['default_purchase_order_id'] = self.purchase_id.id
		if len(landed_costs) == 1:
			action['views'] = [(self.env.ref('stock_landed_costs.view_stock_landed_cost_form').id, 'form')]
			action['res_id'] = landed_costs.id
		return action