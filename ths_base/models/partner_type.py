# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ThsPartnerType(models.Model):
	"""  Model to define different types for partners (e.g., Vendor, Customer).
		Includes flags for classification and links to sequences for reference generation.
		Can be hierarchical.  """
	_name = 'ths.partner.type'
	_description = 'Partner Type'
	_parent_store = True  # Enable parent/child features
	_order = 'parent_path asc, name asc'

	name = fields.Char(string='Name', required=True)
	parent_id = fields.Many2one(
		'ths.partner.type',
		string='Parent Partner Type',
		index=True,
		ondelete='cascade'  # If parent deleted, delete children
	)
	# Field for hierarchical path (computed automatically by _parent_store=True)
	parent_path = fields.Char(index=True)  # , unaccent=False)
	child_ids = fields.One2many('ths.partner.type', 'parent_id', string='Child Types')

	sequence_id = fields.Many2one(
		'ir.sequence',
		string='Reference Sequence',
		copy=False,
		help="Sequence used to generate the Internal Reference for partners of this type."
	)
	is_company = fields.Boolean(
		string="Company",
		required=True,
		default=False,
		help="Check if partners of this type are typically companies/organizations."
	)
	is_individual = fields.Boolean(
		string="Individual",
		required=True,
		default=True,
		help="Check if partners of this type are typically individuals/persons."
	)
	is_customer = fields.Boolean(
		string="Customer Type",
		default=False,
		help="Check if this partner type typically represents customers/clients."
	)
	# Note: is_employee flag is added by ths_hr module via inheritance
	active = fields.Boolean(
		string='Active',
		default=True,
		help="If unchecked, the type cannot be selected for new partners."
	)

	# --- Constraints ---
	@api.constrains('is_company', 'is_individual')
	def _check_company_individual_exclusive(self):
		""" Ensure only one of 'is_company' or 'is_individual' is True. """
		for record in self:
			if record.is_company and record.is_individual:
				raise ValidationError(_("A partner type cannot be both 'Company' and 'Individual'."))
			if not record.is_company and not record.is_individual:
				raise ValidationError(_("A partner type must be either 'Company' or 'Individual'."))

	# --- SQL Constraints ---
	_sql_constraints = [
		('name_uniq', 'unique (name)', "Partner Type name already exists!"),
	]

	# --- Helper Methods ---
	@api.onchange('is_company')
	def _onchange_is_company(self):
		""" Set is_individual based on is_company. """
		# This onchange helps the user in the UI, the constraint enforces it.
		if self.is_company:
			self.is_individual = False
		else:
			if not self.is_individual:
				self.is_individual = True

	@api.onchange('is_individual')
	def _onchange_is_individual(self):
		""" Set is_company based on is_individual. """
		# This onchange helps the user in the UI, the constraint enforces it.
		if self.is_individual:
			self.is_company = False
		else:
			if not self.is_company:
				self.is_company = True