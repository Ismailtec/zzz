# -*- coding: utf-8 -*-

from odoo import models, fields
from datetime import datetime


# import logging

# _logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # --- Add Effective Date Field ---
    ths_effective_date = fields.Date(
        string="Effective Date",
        copy=False,
        help="Effective date for the inventory adjustment move and accounting entries. "
             "If blank, the current date will be used.",
        # Default to today, user can override in inventory adjustment view
        default=fields.Date.context_today
    )

    # --- Override Move Value Preparation ---
    def _get_inventory_move_values(self, qty, location_id, location_dest_id, package_id=False, package_dest_id=False):
        """
        Override to inject ths_effective_date from the quant record (set by user during adjustment)
        into the values for the inventory adjustment stock move.
        """
        self.ensure_one()
        # Get the standard values
        move_vals = super(StockQuant, self)._get_inventory_move_values(
            qty, location_id, location_dest_id, package_id=package_id, package_dest_id=package_dest_id
        )

        # Determine the effective date to use (from quant or fallback to today)
        final_date_to_use = self.ths_effective_date or fields.Date.context_today(self)

        # Inject the custom effective date field
        move_vals['ths_effective_date'] = final_date_to_use

        # Also explicitly set the standard 'date' field for the move creation
        # Combine Date with minimum time for Datetime field
        effective_datetime = datetime.combine(final_date_to_use, datetime.min.time())
        move_vals['date'] = effective_datetime

        # _logger.debug(f"Quant {self.id} adjustment: Injecting effective date {final_date_to_use} into move values: {move_vals}") # Logger removed

        return move_vals
