# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ths_hide_taxes = fields.Boolean(
        related="company_id.ths_hide_taxes",
        string="Hide Taxes",
        # default= True,
        readonly=False,
        help="Hide the 'Taxes' column by default on Orders/Invoices/Bills/Products etc.")

    # @api.depends('company_id')
    # def _compute_ths_hide_taxes(self):
    #     for record in self:
    #         record.ths_hide_taxes = record.company_id.ths_hide_taxes

    # def _inverse_ths_hide_taxes(self):
    #     for record in self:
    #         record.company_id.ths_hide_taxes = record.ths_hide_taxes


class ResCompany(models.Model):
    _inherit = "res.company"

    ths_hide_taxes = fields.Boolean(
        string="Hide Taxes",
        help="Hide the 'Taxes' column by default on Orders/Invoices/Bills/Products etc.")
