# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.osv import expression
#import logging
from markupsafe import Markup

#_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # --- Link to Landed Costs ---
    # Using compute to find related LCs based on PO or Bill link
    ths_stock_landed_cost_ids = fields.One2many(
        'stock.landed.cost',
        compute='_compute_landed_costs',  # Compute based on PO/Bill link
        string='Landed Costs (Related)',
        copy=False,
        help="Landed Costs related to this document (via PO or direct Bill link)."
    )
    landed_cost_count = fields.Integer(compute='_compute_landed_costs', string="# Landed Costs")
    ths_hide_taxes = fields.Boolean(
        related="company_id.ths_hide_taxes",
        readonly=False,
        string="Hide Taxes",
        help="Technical field to read the global config setting."
    )

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
                #_logger.error(f"Error during automatic LC sync for Bill {bill.name}: {e}")
                bill.message_post(body=_(
                    "Warning: Failed to automatically update linked Landed Cost record. Please check manually. Error: %s",
                    e))
        return res

    def _sync_posted_bill_to_landed_cost(self):
        """ Finds related DRAFT LC and updates its cost lines from this bill """
        self.ensure_one()
        #_logger.info(f"Bill {self.name}: Checking for draft LC to sync cost lines...")

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
            #_logger.info(f"Bill {self.name}: No related draft Landed Cost found to sync.")
            # --- Auto-Create LC from Bill if none found ---
            #_logger.info(f"Bill {self.name}: Attempting to auto-create LC.")
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
                    split_method = bill_line.product_id.split_method_landed_cost or 'equal';
                    account_id = bill_line.account_id.id
                    if not account_id: accounts_data = bill_line.product_id.product_tmpl_id.get_product_accounts(); account_id = accounts_data.get(
                        'stock_input') and accounts_data['stock_input'].id
                    if not account_id: continue
                    new_cost_lines_vals.append((0, 0, {'product_id': bill_line.product_id.id, 'name': bill_line.name,
                                                       'account_id': account_id, 'split_method': split_method,
                                                       'price_unit': bill_line.price_subtotal}))
                if new_cost_lines_vals:
                    new_lc.write({'cost_lines': new_cost_lines_vals})
                #_logger.info(f"Bill {self.name}: Auto-created and populated LC {new_lc.name}")
                # Post message on Bill
                lc_link = Markup(new_lc._get_html_link()) if hasattr(new_lc, '_get_html_link') else new_lc.name
                self.message_post(body=_("Automatically created Landed Cost %s from this Bill.", lc_link))
                # Post message on LC
                bill_link = Markup(self._get_html_link()) if hasattr(self, '_get_html_link') else self.name
                new_lc.message_post(body=_("Landed Cost created automatically from Vendor Bill %s.", bill_link))
            #else:
                #_logger.info(f"Bill {self.name}: No LC lines found on bill, no LC created.")
            return  # Exit after creating

        # --- If existing draft LC was found ---
        #_logger.info(f"Bill {self.name}: Found draft LC {related_lc.name}. Syncing cost lines...")
        new_cost_lines_vals = []
        bill_lc_lines = self.invoice_line_ids.filtered(
            lambda l: l.product_id and l.product_id.product_tmpl_id.landed_cost_ok)
        for bill_line in bill_lc_lines:
            split_method = bill_line.product_id.split_method_landed_cost or 'equal';
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
        #_logger.info(f"Bill {self.name}: Synced {len(new_cost_lines_vals)} lines to LC {related_lc.name}.")

    # Get Default Date on Bill
    @api.model
    def default_get(self, fields_list):
        defaults = super(AccountMove, self).default_get(fields_list)

        # Check if creating a Vendor Bill and invoice_date default is needed
        if 'invoice_date' in fields_list and not defaults.get('invoice_date'):
            # Check context for move type (more reliable than checking defaults['move_type'])
            if self.env.context.get('default_move_type') == 'in_invoice':
                defaults['invoice_date'] = fields.Date.context_today(self)

        return defaults

class AccountInvoiceLine(models.Model):
    _inherit = "account.move.line"

    ths_hide_taxes = fields.Boolean(
        related="company_id.ths_hide_taxes",
        readonly=False,
        string="Hide Taxes",
        help="Technical field to read the global config setting."
    )