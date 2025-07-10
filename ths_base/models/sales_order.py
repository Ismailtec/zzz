# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ths_hide_taxes = fields.Boolean(
        related="company_id.ths_hide_taxes",
        readonly=False,
        string="Hide Taxes",
        # compute='_compute_hide_taxes',
        help="Technical field to read the global config setting."
    )


class SalesOrderLine(models.Model):
    _inherit = "sale.order.line"

    ths_hide_taxes = fields.Boolean(
        related="company_id.ths_hide_taxes",
        readonly=False,
        string="Hide Taxes",
        help="Technical field to read the global config setting."
    )
