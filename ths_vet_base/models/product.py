# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re

import logging

_logger = logging.getLogger(__name__)


class ThsProductSubType(models.Model):
	"""
	Model to define different subtypes for products, often used for
	classification in specific industries (e.g., medical).
	Includes automatic sequence creation based on code.
	"""
	_name = 'ths.product.sub.type'
	_description = 'Product Sub Type'
	_order = 'sequence asc, name asc'  # Order by sequence widget then name

	name = fields.Char(string='Name', required=True, translate=True)
	code = fields.Char(string='Code', required=True, copy=False, index=True, help="Short code for the sub-type, used for sequence generation (e.g., MED, LAB, CONS).")
	product_group = fields.Selection([('medicine', 'Medicine'), ('products_sale', 'Products for Sale'), ('consumables', 'Consumables'), ('lab', 'Laboratory'), ('rad', 'Radiology'),
									  ('equipment', 'Equipment'), ('services', 'Services'), ('consultation', 'Consultation'), ('operations', 'Operations'), ('dental', 'Dental'),
									  ('vaccines', 'Vaccines'), ('hospitalization', 'Hospitalization'), ('cafeteria', 'Cafeteria'), ('expenses', 'Expenses'),
									  ('boarding', 'Boarding'), ('grooming', 'Grooming'), ('subscriptions', 'Subscriptions')],
									 ondelete={'medicine': 'cascade', 'products_sale': 'cascade', 'consumables': 'cascade', 'lab': 'cascade', 'rad': 'cascade',
											   'equipment': 'cascade', 'services': 'cascade', 'consultation': 'cascade', 'operations': 'cascade', 'dental': 'cascade',
											   'vaccines': 'cascade', 'hospitalization': 'cascade', 'cafeteria': 'cascade', 'expenses': 'cascade', 'boarding': 'cascade',
											   'grooming': 'cascade', 'subscriptions': 'cascade'},
									 string='Product Group', help="General grouping category for this sub-type (e.g., drugs, services, consumables).")

	# Flag indicating if products of this sub-type are typically services
	is_for_service = fields.Boolean(string="Service Type", default=False, help="Check if products linked to this sub-type are generally services.")
	# Sequence used for generating product references/codes if needed
	sequence_id = fields.Many2one('ir.sequence', string='Product Sequence', copy=False, readonly=True, help="Sequence used for generating product codes of this sub-type.")
	# Flag to indicate if sequence should be used for internal reference
	is_for_internal_reference = fields.Boolean(string="Use for Internal Reference", default=False, help="If checked, the linked sequence will be used to generate product code.")
	# Sequence field for ordering records in the list view
	sequence = fields.Integer(string='Sequence', default=10)
	active = fields.Boolean(string='Active', default=True)

	# --- SQL Constraints ---
	_sql_constraints = [
		('code_uniq', 'unique (code)', "Product Sub Type code must be unique!"),
		('name_uniq', 'unique (name)', "Product Sub Type name must be unique!"),
	]

	# --- Overrides ---
	@api.model_create_multi
	def create(self, vals_list):
		""" Override create to automatically create sequence based on code. """
		sub_types = super(ThsProductSubType, self).create(vals_list)
		for sub_type in sub_types:
			try:
				sub_type.sudo()._create_sub_type_sequence_if_needed()
			except Exception as e:
				_logger.error(f"Error creating sequence for new Product Sub Type {sub_type.name}: {e}")
		return sub_types

	def write(self, vals):
		""" Override write to update sequence if code changes. """
		original_codes = {st.id: st.code for st in self}
		res = super(ThsProductSubType, self).write(vals)
		if 'code' in vals:
			for sub_type in self:
				if sub_type.code != original_codes.get(sub_type.id):
					try:
						sub_type.sudo()._create_sub_type_sequence_if_needed()
					except Exception as e:
						_logger.error(
							f"Error updating sequence for Product Sub Type {sub_type.name} after code change: {e}")
		return res

	# --- Helper Methods ---
	@staticmethod
	def _sanitize_code(code):
		""" Sanitize code for sequence prefix/code. """
		code = (code or '').strip().upper()
		code = re.sub(r'\s+', '_', code)
		code = re.sub(r'[^A-Z0-9_.-]+', '', code)  # Allow underscore, dot, hyphen
		return code or 'UNDEF'

	def _create_sub_type_sequence_if_needed(self):
		""" Creates or links an ir.sequence based on the sub-type code. """
		self.ensure_one()
		Sequence = self.env['ir.sequence']
		if not self.code:
			_logger.warning(f"Product Sub Type {self.id} ({self.name}): No code set, cannot create/link sequence.")
			if self.sequence_id:  # Unlink if code is removed
				self.write({'sequence_id': False})  # Called from sudo context
			return

		sanitized_code = self._sanitize_code(self.code)
		# Sequence code needs to be unique system-wide
		sequence_code = f'product.sub.type.seq.{sanitized_code}'
		# Sequence name should be descriptive
		sequence_name = f"Product Sub Type - {self.name} ({sanitized_code})"
		# Prefix for generated numbers
		sequence_prefix = f"{sanitized_code}-"

		# Search for existing sequence by code (best practice)
		# No company needed as sequences for products are often global
		existing_sequence = Sequence.sudo().search([('code', '=', sequence_code)], limit=1)

		sequence_to_link = False
		if existing_sequence:
			_logger.info(f"Sub Type {self.id}: Found existing sequence '{sequence_code}' (ID: {existing_sequence.id}).")
			sequence_to_link = existing_sequence
			# Update name/prefix if they differ? Optional.
			vals_to_write = {}
			if sequence_to_link.name != sequence_name: vals_to_write['name'] = sequence_name
			if sequence_to_link.prefix != sequence_prefix: vals_to_write['prefix'] = sequence_prefix
			if vals_to_write:
				try:
					sequence_to_link.sudo().write(vals_to_write)
				except Exception as e:
					_logger.warning(f"Sub Type {self.id}: Failed to update existing sequence details: {e}")
		else:
			# Create new sequence
			seq_vals = {
				'name': sequence_name,
				'code': sequence_code,
				'prefix': sequence_prefix,
				'padding': 5,  # e.g., MED-00001
				'company_id': False,  # Global sequence
				'implementation': 'standard',
			}
			try:
				# Use create with sudo as sequence creation might need higher privileges
				new_sequence = Sequence.sudo().create(seq_vals)
				sequence_to_link = new_sequence
				_logger.info(f"Sub Type {self.id}: Created sequence '{new_sequence.name}' (ID: {new_sequence.id}).")
			except Exception as e:
				_logger.error(f"Sub Type {self.id}: Failed to create sequence for code '{sanitized_code}': {e}")

		# Link the sequence if found/created and different from current
		if sequence_to_link and self.sequence_id != sequence_to_link:
			self.write({'sequence_id': sequence_to_link.id})  # Called from sudo context
		elif not sequence_to_link and self.sequence_id:
			# Unlink if sequence couldn't be found/created
			self.write({'sequence_id': False})


class ProductTemplate(models.Model):
	""" Inherit Product Template to add Product Sub Type field and domain logic. """
	_inherit = 'product.template'

	product_sub_type_id = fields.Many2one('ths.product.sub.type', string='Product Sub Type', index=True, tracking=True,
										  help="Select a specific sub-classification for this product (e.g., Medicine, Consultation, Retail).")
	ths_sub_type_domain = fields.Char(string='Sub Type Domain', compute='_compute_sub_type_domain', help="Computed field for the domain of Product Sub Type based on Type.")
	ths_membership_duration = fields.Integer(string='Membership Duration (Months)', help="Duration in months for membership services")
	ths_membership_duration_visible = fields.Boolean(compute='_compute_membership_duration_visible')
	ths_membership_duration_required = fields.Boolean(compute='_compute_membership_duration_visible')

	# --- Depends on 'type' field now ---
	@api.depends('type')
	def _compute_sub_type_domain(self):
		""" Compute domain string for product_sub_type_id based on the 'type' field (Goods/Service/Combo). """
		for record in self:
			domain = []  # Default: show all active sub types
			# Check against the 'type' field values
			if record.type == 'service':
				# If product type is Service, show only sub types marked as 'is_for_service'
				_logger.debug(f"Product {record.name}: Type is 'service', setting domain for service sub-types.")
				domain = [('is_for_service', '=', True)]
			elif record.type == 'consu':  # User selects 'Goods', which corresponds to 'consu'
				# If product type is Goods (consu), show only sub types NOT marked as 'is_for_service'
				_logger.debug(
					f"Product {record.name}: Type is 'consu' (Goods), setting domain for non-service sub-types.")
				domain = [('is_for_service', '=', False)]
			# For 'combo' or if type is not set, the domain remains empty (showing all active sub types)
			elif record.type == 'combo':
				_logger.debug(f"Product {record.name}: Type is 'combo', showing all active sub-types.")
			else:
				_logger.debug(f"Product {record.name}: Type is '{record.type}', showing all active sub-types.")

			record.ths_sub_type_domain = str(domain)

	# --- Onchange based on 'type' field ---
	@api.onchange('type')
	def _onchange_type_clear_sub_type(self):
		""" When the main product type (Goods/Service/Combo) changes,
			check if the current sub_type is still valid based on the new domain logic.
		"""
		# This logic helps clear the field if the user changes the type
		# making the previous sub-type selection invalid.
		if self.product_sub_type_id:
			current_sub_type_is_service = self.product_sub_type_id.is_for_service
			type_is_service = self.type == 'service'
			type_is_goods = self.type == 'consu'  # Goods corresponds to 'consu'

			# If type is service but sub_type is not for service, clear sub_type
			if type_is_service and not current_sub_type_is_service:
				_logger.debug(
					f"Product {self.name or 'New'}: Type changed to Service, clearing non-service Sub Type {self.product_sub_type_id.name}")
				self.product_sub_type_id = False
			# If type is goods (consu) but sub_type *is* for service, clear sub_type
			elif type_is_goods and current_sub_type_is_service:
				_logger.debug(
					f"Product {self.name or 'New'}: Type changed to Goods, clearing service Sub Type {self.product_sub_type_id.name}")
				self.product_sub_type_id = False

	@api.depends('product_sub_type_id')
	def _compute_membership_duration_visible(self):
		member_subtype = self.env.ref('ths_vet_base.product_sub_type_member', raise_if_not_found=False)
		for product in self:
			is_membership = product.product_sub_type_id == member_subtype if member_subtype else False
			# is_membership = product.product_sub_type_id.name == 'Membership'
			product.ths_membership_duration_visible = is_membership
			product.ths_membership_duration_required = is_membership

	@api.constrains('product_sub_type_id', 'ths_membership_duration')
	def _check_membership_duration(self):
		member_subtype = self.env.ref('ths_vet_base.product_sub_type_member', raise_if_not_found=False)
		for product in self:
			if (member_subtype and
					# if (product.product_sub_type_id.name == 'Membership' and
					product.product_sub_type_id == member_subtype and
					not product.ths_membership_duration):
				raise ValidationError(_('Membership Duration is required for membership services.'))


# TODO: Add membership pricing tiers based on duration
# TODO: Add automatic membership product creation wizard


class ProductProduct(models.Model):
	""" Inherit to add Product Sub Type field and domain logic. """
	_inherit = 'product.product'

	product_sub_type_id = fields.Many2one(related='product_tmpl_id.product_sub_type_id')

	# --- Computed Domain Field ---
	ths_sub_type_domain = fields.Char(related='product_tmpl_id.ths_sub_type_domain')
	ths_membership_duration = fields.Integer(related='product_tmpl_id.ths_membership_duration')
	ths_membership_duration_visible = fields.Boolean(related='product_tmpl_id.ths_membership_duration_visible')
	ths_membership_duration_required = fields.Boolean(related='product_tmpl_id.ths_membership_duration_required')