# -*- coding: utf-8 -*-

from odoo import models, fields
# from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
	_inherit = 'stock.move'

	ths_effective_date = fields.Date(
		string="Effective Date",
		copy=False, index=True,
		help="The date used for the actual stock movement and related accounting entries. "
			 "If set, this overrides the default processing date."
	)

	def _action_done(self, cancel_backorder=False):
		"""  Override _action_done:
					- Set move.date BEFORE super() based on ths_effective_date.
					- Check AFTER super() if the date was reset and correct if necessary.
					- Update move line date AFTER super().
		"""
		# _logger.info(f"Move {self.ids}: Entering _action_done. Context: {self.env.context}")
		self = self.with_context(self.env.context)
		moves_to_process = self.filtered(lambda m: m.state not in ('done', 'cancel'))
		moves_with_effective_date = moves_to_process.filtered(lambda m: m.ths_effective_date)
		original_move_dates = {move.id: move.date for move in moves_with_effective_date}

		# --- Effective Date Injection BEFORE Super() ---
		for move in moves_with_effective_date:
			effective_datetime_naive = datetime.combine(move.ths_effective_date, fields.time.min)
			effective_datetime_utc = effective_datetime_naive
			# _logger.info(
			# f"PRE-SUPER: Setting move {move.id} date to {effective_datetime_utc} based on effective date {move.ths_effective_date}")
			try:
				move.sudo().write({'date': effective_datetime_utc})
			except Exception as e:
				_logger.error(f"Error writing effective date PRE-super for move {move.id}: {e}")

		# --- Call original method ---
		res_moves = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)
		# _logger.info(f"Move(s) {res_moves.ids}: Returned from super()._action_done.")

		# --- Post-Super Verification / Correction for Move & Move Lines ---
		processed_moves_to_check = self.env['stock.move'].browse([
			move_id for move_id in original_move_dates.keys() if move_id in res_moves.ids
		])

		moves_corrected = self.env['stock.move']  # Track moves whose date was just corrected

		for move in processed_moves_to_check:
			if not move.exists() or not move.ths_effective_date: continue

			effective_datetime_naive = datetime.combine(move.ths_effective_date, fields.time.min)
			effective_datetime_utc = effective_datetime_naive
			current_move_date_utc = fields.Datetime.to_datetime(move.date)

			# Correct Stock Move date if needed
			if not current_move_date_utc or current_move_date_utc.date() != move.ths_effective_date:
				# _logger.warning(
				# f"POST-SUPER CHECK: Move {move.id} date ({move.date}) was reset. Target: {effective_datetime_utc}. Forcing correction.")
				try:
					move.sudo().write({'date': effective_datetime_utc})
					_logger.info(f"Applied post-super date correction for move {move.id}")
					moves_corrected |= move
				except Exception as e:
					_logger.error(f"Error applying post-super date correction for move {move.id}: {e}")
			else:
				_logger.info(
					f"POST-SUPER CHECK: Move {move.id} date ({move.date}) already matches effective date {move.ths_effective_date}.")

		# --- Update Stock Move Line Dates ---
		# Process moves that had an effective date, focusing on those just corrected or already correct
		moves_to_update_lines = processed_moves_to_check  # All moves that should have the effective date

		if moves_to_update_lines:
			# _logger.info(f"Attempting to align date on move lines for moves: {moves_to_update_lines.ids}")
			# Use sudo() for searching lines in case permissions changed
			lines_to_update = self.env['stock.move.line'].sudo().search([('move_id', 'in', moves_to_update_lines.ids)])
			if lines_to_update:
				# _logger.info(f"Found {len(lines_to_update)} move lines to check/update.")
				for line in lines_to_update:
					# Double check parent move still exists and has the date
					if line.move_id.exists() and line.move_id.ths_effective_date:
						line_effective_dt_naive = datetime.combine(line.move_id.ths_effective_date, fields.time.min)
						line_effective_dt_utc = line_effective_dt_naive
						current_line_date_utc = fields.Datetime.to_datetime(line.date)
						# Only write if different
						if not current_line_date_utc or current_line_date_utc.date() != line.move_id.ths_effective_date:
							try:
								line.sudo().write({'date': line_effective_dt_utc})
								# _logger.info(
								# f"Applied effective date {line.move_id.ths_effective_date} to move line {line.id}")
							except Exception as e:
								_logger.error(f"Error applying effective date to move line {line.id}: {e}")
						# else:
						#    _logger.debug(f"Move line {line.id} date already matches effective date.")
					# else: Skip line if parent move lost its effective date somehow

		return res_moves

	# --- Override for JE Header Date ---
	def _prepare_account_move_vals(
			self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id,
			cost):
		"""Prepare account move header vals. Force the 'date' field using ths_effective_date."""
		self.ensure_one()
		# _logger.info(f"==> ==> Move {self.id}: Entering _prepare_account_move_vals. Effective Date: {self.ths_effective_date}")
		vals = super(StockMove, self)._prepare_account_move_vals(credit_account_id, debit_account_id, journal_id, qty,
																 description, svl_id, cost)
		# _logger.debug(f"Move {self.id} - Super vals from _prepare_account_move_vals: {vals}")

		# Determine the date to use
		forced_date = self.env.context.get('force_period_date')
		# Use move's own ths_effective_date as highest priority for JE date
		final_date_to_use = self.ths_effective_date if self.ths_effective_date else (forced_date or vals.get('date'))

		if final_date_to_use and vals.get('date') != final_date_to_use:
			# _logger.info(f"Move {self.id} - _prepare_account_move_vals: Original date: {vals.get('date')}. Forcing JE date to: {final_date_to_use}")
			vals['date'] = final_date_to_use

		# --- Add Source Document Reference to JE Ref---
		ref_parts = []
		if self.origin: ref_parts.append(self.origin)
		if self.picking_id: ref_parts.append(self.picking_id.name)
		# MRP links (production_id, raw_material_production_id) are handled in ths_mrp module
		if self.scrap_id: ref_parts.append(self.scrap_id.name)
		if self.is_inventory: ref_parts.append("Inventory Adjustment")  # Check inventory flag

		if ref_parts:
			source_ref = " | ".join(ref_parts)
		else:
			source_ref = f'Move {self.id}'  # Fallback

		existing_ref = vals.get('ref', '')
		separator = ' - ' if existing_ref and source_ref else ''  # Add separator only if both exist
		# effective_date_str = f" (Eff: {fields.Date.to_string(self.ths_effective_date)})" if self.ths_effective_date else ""
		# Construct ref carefully avoiding double separators or adding one unnecessarily
		# vals['ref'] = f"{existing_ref}{separator}{source_ref}{effective_date_str}".strip()
		vals['ref'] = f"{existing_ref}{separator}{source_ref}".strip()
		# --- End Add Source ---

		return vals