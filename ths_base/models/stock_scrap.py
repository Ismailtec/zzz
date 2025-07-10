# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class StockScrap(models.Model):
	_inherit = 'stock.scrap'

	# --- Fields ---
	@api.model
	def _default_ths_effective_date(self):
		# Default to today
		return fields.Date.today()

	ths_effective_date = fields.Date(
		string="Effective Date",
		copy=False,
		index=True,
		help="If set, this date will be used as the effective date for the "
			 "stock move and related accounting entries upon validation.",
		readonly=False,
		default=_default_ths_effective_date,
	)

	# --- Onchange Method ---
	@api.onchange('date_done')
	def _onchange_date_done(self):
		""" Suggest effective date based on Date Done """
		if self.date_done and not self.ths_effective_date:
			# Ensure we assign only the date part if date_done is Datetime
			self.ths_effective_date = self.date_done.date() if isinstance(self.date_done, datetime) else self.date_done

	# --- Overridden Methods ---
	def _prepare_move_values(self):
		"""  Override: Prepare stock move vals. Inject the 'ths_effective_date'.  """
		# Get standard move values
		vals = super(StockScrap, self)._prepare_move_values()

		# Inject our effective date if it's set on the scrap record
		if self.ths_effective_date:
			# _logger.info(f"Scrap {self.id}: Injecting ths_effective_date {self.ths_effective_date} into move values.")
			vals['ths_effective_date'] = self.ths_effective_date
		else:
			# _logger.info(f"Scrap {self.id}: No ths_effective_date set, ensuring key is False in move vals.")
			# Explicitly set to False so stock.move doesn't use unrelated context/defaults
			vals['ths_effective_date'] = False

		# _logger.debug(f"Scrap {self.id}: Move values prepared: {vals}")
		return vals