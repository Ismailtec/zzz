# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class AccountPayment(models.Model):
	_inherit = 'account.payment'

	partner_type_id = fields.Many2one('ths.partner.type', string='Partner Type', readonly=False, copy=True, index=True, ondelete='cascade',
									  help="Choose proper Partner Type to show related Partners")
	amount_used = fields.Monetary(string='Amount Used', currency_field='currency_id', compute='_compute_amount_used', store=True, readonly=True, help="Amount used of this payment",
								  tracking=True)
	amount_remaining = fields.Monetary(string='Amount Remaining', currency_field='currency_id', readonly=True, compute='_compute_amount_remaining', store=True,
									   help="Unused remaining amount")

	@api.onchange('partner_type_id')
	def _onchange_partner_type_clear_partner(self):
		"""Clear partner when partner type changes"""
		if self.partner_type_id and self.partner_id.partner_type_id.id != self.partner_type_id.id:
			self.partner_id = False

	@api.depends('partner_id')
	def _compute_partner_type_id(self):
		for record in self:
			if record.partner_id and not record.partner_type_id:
				record.partner_type_id = record.partner_id.partner_type_id.id

	@api.depends('move_id.line_ids.matched_debit_ids', 'move_id.line_ids.matched_credit_ids', 'amount')
	def _compute_amount_used(self):
		"""Compute used amount based on reconciled invoices"""
		for payment in self:
			if not payment.move_id:
				payment.amount_used = 0.0
				continue

			amount_used = 0.0
			# Get payment move lines (usually the receivable/payable account lines)
			payment_lines = payment.move_id.line_ids.filtered(
				lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
			)

			for line in payment_lines:
				# Calculate reconciled amounts from both debit and credit matches
				for partial in line.matched_debit_ids:
					if partial.credit_move_id == line:
						amount_used += partial.amount
				for partial in line.matched_credit_ids:
					if partial.debit_move_id == line:
						amount_used += partial.amount

			payment.amount_used = amount_used

	@api.depends('amount', 'amount_used')
	def _compute_amount_remaining(self):
		"""Compute remaining amount as total amount minus used amount"""
		for payment in self:
			payment.amount_remaining = payment.amount - payment.amount_used

	@api.model
	def default_get(self, fields_list):
		"""Auto-populate partner_type_id from partner"""
		defaults = super().default_get(fields_list)

		# Get partner_id from defaults or context
		partner_id = defaults.get('partner_id') or self.env.context.get('default_partner_id')
		if partner_id and 'partner_type_id' in fields_list:
			partner = self.env['res.partner'].browse(partner_id)
			if partner.exists() and partner.partner_type_id:
				defaults['partner_type_id'] = partner.partner_type_id.id

		return defaults

	@api.constrains('amount_used', 'amount')
	def _check_amount_used(self):
		"""Ensure amount_used doesn't exceed total amount"""
		for payment in self:
			if payment.amount_used > payment.amount:
				raise ValidationError(
					f"Amount used ({payment.amount_used}) cannot exceed total payment amount ({payment.amount})"
				)

	def action_update_amount_used(self, used_amount):
		"""Method to update the amount used - can be called from other modules"""
		self.ensure_one()
		if used_amount > self.amount:
			raise UserError(f"Cannot use {used_amount} from payment of {self.amount}")
		self.amount_used = used_amount