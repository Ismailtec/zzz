# -*- coding: utf-8 -*-

from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")
    partner_type_id = fields.Many2one('ths.partner.type', string='Partner Type', readonly=False, copy=True, index=True, ondelete='cascade',
                                      help="Choose proper Partner Type to show related Partners")

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        super()._onchange_partner_id()
        if self.partner_id and self.partner_id.partner_type_id:
            self.partner_type_id = self.partner_id.partner_type_id

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        partner_id = defaults.get('partner_id') or self.env.context.get('default_partner_id')
        if partner_id and 'partner_type_id' in fields_list:
            partner = self.env['res.partner'].browse(partner_id)
            if partner.partner_type_id:
                defaults['partner_type_id'] = partner.partner_type_id.id

        return defaults





class SalesOrderLine(models.Model):
    _inherit = "sale.order.line"

    ths_hide_taxes = fields.Boolean(related="company_id.ths_hide_taxes", readonly=False, string="Hide Taxes", help="Technical field to read the global config setting.")