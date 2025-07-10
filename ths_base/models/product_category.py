# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.osv import expression

import logging

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    """ Inherit Product Category to add product type filtering preference. """
    _inherit = 'product.category'

    # --- New Field ---
    # Defines what type of products should primarily be associated with this category view action
    product_type_filter = fields.Selection(
        [
            ('all', 'All Products'),  # Default, show services and goods
            ('service', 'Services Only'),  # Show only services
            ('product', 'Products Only')  # Show only storable/consumable goods
        ],
        string='Category Product Type Filter',
        required=True,
        default='all',
        help="Filter the products shown by default when viewing this category's products.\n"
             "- All Products: Shows storable, consumable, and service products.\n"
             "- Services Only: Shows only service products.\n"
             "- Products Only: Shows only storable and consumable products."
    )

    # --- Override Action Method ---
    # Overrides the method that returns the action to view products associated with the category
    def action_view_products(self):
        """ Override the action to view products to apply the type filter. """
        # Get the standard action dictionary (usually for product.template)
        action = self.env['ir.actions.actions']._for_xml_id('stock.product_template_action_product')

        # Ensure domain is a list
        action_domain = action.get('domain', [])
        if isinstance(action_domain, str):
            try:
                action_domain = eval(action_domain)
            except Exception:
                action_domain = []

        # Apply the category filter (standard behavior)
        category_domain = [('categ_id', 'child_of', self.ids)]
        base_domain = expression.AND([action_domain, category_domain])

        # Apply the new type filter based on the category setting
        type_domain = []
        # Apply based on the first record if called on multiple.
        category_to_filter_by = self[0] if self else self

        if category_to_filter_by and category_to_filter_by.product_type_filter != 'all':
            filter_setting = category_to_filter_by.product_type_filter
            if filter_setting == 'service':
                # Use detailed_type for accurate filtering
                type_domain = [('detailed_type', '=', 'service')]
                _logger.debug(f"Applying service filter for category {category_to_filter_by.display_name}")
            elif filter_setting == 'product':
                # Filter for storable ('product') and consumable ('consu')
                type_domain = [('detailed_type', 'in', ['product', 'consu'])]
                _logger.debug(f"Applying product/consu filter for category {category_to_filter_by.display_name}")

        # Combine the base domain with the new type domain
        final_domain = expression.AND([base_domain, type_domain])

        # Update the action dictionary
        action['domain'] = final_domain
        # Also update context to potentially set default category
        action_context = action.get('context', {})
        if isinstance(action_context, str):
            try:
                action_context = eval(action_context)
            except Exception:
                action_context = {}
        action_context.update(
            {'search_default_categ_id': self.ids[0]} if self else {})  # Use search_default for category
        action['context'] = action_context

        # _logger.debug(f"Final domain for action_view_products: {final_domain}")
        return action
