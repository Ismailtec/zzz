# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
	_inherit = 'product.template'

	ths_membership_duration = fields.Integer(
		string='Membership Duration (Months)',
		help="Duration in months for membership services"
	)

	ths_membership_duration_visible = fields.Boolean(
		compute='_compute_membership_duration_visible'
	)

	ths_membership_duration_required = fields.Boolean(
		compute='_compute_membership_duration_visible'
	)

	@api.depends('product_sub_type_id')
	def _compute_membership_duration_visible(self):
		member_subtype = self.env.ref('ths_medical_vet.product_sub_type_member', raise_if_not_found=False)
		for product in self:
			is_membership = product.product_sub_type_id == member_subtype if member_subtype else False
			# is_membership = product.product_sub_type_id.name == 'Membership'
			product.ths_membership_duration_visible = is_membership
			product.ths_membership_duration_required = is_membership

	@api.constrains('product_sub_type_id', 'ths_membership_duration')
	def _check_membership_duration(self):
		member_subtype = self.env.ref('ths_medical_vet.product_sub_type_member', raise_if_not_found=False)
		for product in self:
			if (member_subtype and
					# if (product.product_sub_type_id.name == 'Membership' and
					product.product_sub_type_id == member_subtype and
					not product.ths_membership_duration):
				raise ValidationError(_('Membership Duration is required for membership services.'))


# TODO: Add membership pricing tiers based on duration
# TODO: Add automatic membership product creation wizard


class ProductProduct(models.Model):
	_inherit = 'product.product'

	# Inherit the computed fields from template
	ths_membership_duration = fields.Integer(related='product_tmpl_id.ths_membership_duration')
	ths_membership_duration_visible = fields.Boolean(related='product_tmpl_id.ths_membership_duration_visible')