# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountMove(models.Model):
	_inherit = 'account.move'

	company_id = fields.Many2one(comodel_name='res.company', string='Branch', compute='_compute_company_id', inverse='_inverse_company_id', store=True, readonly=False,
								 precompute=True, index=True)

class AccountPayment(models.Model):
	_inherit = 'account.payment'

	company_id = fields.Many2one(comodel_name='res.company', string='Branch', compute='_compute_company_id', store=True, readonly=False, precompute=True, index=False,
								 required=True)