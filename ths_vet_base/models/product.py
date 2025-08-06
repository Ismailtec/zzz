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
	ths_exclude_from_auto_code = fields.Boolean(string='Exclude from Auto Code', default=False, help="Check this to prevent automatic internal reference generation")
	ths_auto_code_generated = fields.Boolean(string='Auto Code Generated', default=False, copy=False, help="Technical field to track if code was auto-generated")
	ths_code_generation_trigger = fields.Datetime(string='Code Generation Trigger', default=fields.Datetime.now)
	ths_computed_default_code = fields.Char(string='Computed Default Code', compute='_compute_default_code_with_trigger', store=True)

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

	@api.onchange('product_sub_type_id')
	def _onchange_product_sub_type_id(self):
		"""Auto-generate code when sub-type changes (live)"""
		if self.product_sub_type_id and self.product_sub_type_id.is_for_internal_reference:
			# Only auto-generate if no existing code and not excluded
			if not self.default_code and not self.ths_exclude_from_auto_code:
				new_code = self._generate_internal_reference()
				if new_code:
					self.default_code = new_code
					self.ths_auto_code_generated = True

	@api.depends('ths_code_generation_trigger', 'product_sub_type_id', 'ths_auto_code_generated')
	def _compute_default_code_with_trigger(self):
		"""Compute default code - this will trigger UI refresh when ths_code_generation_trigger changes"""
		for product in self:
			product.ths_computed_default_code = str(product.ths_code_generation_trigger) if product.ths_code_generation_trigger else ''

	@api.onchange('default_code')
	def _onchange_default_code(self):
		"""Validate manually entered code against sequence format"""
		if (self.default_code and
				self.product_sub_type_id and
				self.product_sub_type_id.is_for_internal_reference and
				self.product_sub_type_id.sequence_id and
				not self.ths_exclude_from_auto_code):

			if not self._validate_code_format(self.default_code):
				self.ths_auto_code_generated = False
			else:
				self.ths_auto_code_generated = True

	@api.onchange('ths_exclude_from_auto_code')
	def _onchange_exclude_from_auto_code(self):
		"""Handle exclusion toggle"""
		if self.ths_exclude_from_auto_code:
			if self.default_code:
				self.ths_auto_code_generated = False
		else:
			if (self.product_sub_type_id and
					self.product_sub_type_id.is_for_internal_reference and
					not self.default_code):
				new_code = self._generate_internal_reference()
				if new_code:
					self.default_code = new_code
					self.ths_auto_code_generated = True

	def _get_expected_code_format(self):
		"""Get the expected code format for the current sub-type"""
		self.ensure_one()
		if (self.product_sub_type_id and
				self.product_sub_type_id.sequence_id):
			sequence = self.product_sub_type_id.sequence_id
			prefix = sequence.prefix or ''
			padding = '0' * (sequence.padding or 5)
			suffix = sequence.suffix or ''
			return f"{prefix}{padding}{suffix}"
		return "No format defined"

	def _validate_code_format(self, code):
		"""Validate if the code matches the expected sequence format"""
		self.ensure_one()
		if not code or not self.product_sub_type_id or not self.product_sub_type_id.sequence_id:
			return True  # No validation if no sequence

		sequence = self.product_sub_type_id.sequence_id
		prefix = sequence.prefix or ''
		suffix = sequence.suffix or ''

		# Check if code starts with prefix and ends with suffix
		if prefix and not code.startswith(prefix):
			return False
		if suffix and not code.endswith(suffix):
			return False

		# Extract the number part
		start_pos = len(prefix)
		end_pos = len(code) - len(suffix) if suffix else len(code)
		number_part = code[start_pos:end_pos]

		# Check if the middle part is numeric and matches padding
		if not number_part.isdigit():
			return False

		# Check padding (optional - you might want to be flexible here)
		expected_padding = sequence.padding or 5
		if len(number_part) != expected_padding:
			return False

		return True

	def _suggest_next_code_in_sequence(self):
		"""Suggest what the next code should be based on existing codes"""
		self.ensure_one()
		if not self.product_sub_type_id or not self.product_sub_type_id.sequence_id:
			return False

		sequence = self.product_sub_type_id.sequence_id
		prefix = sequence.prefix or ''

		# Find existing products with same prefix
		existing_codes = self.search([
			('default_code', 'like', f'{prefix}%'),
			('product_sub_type_id', '=', self.product_sub_type_id.id),
			('id', '!=', self.id)
		]).mapped('default_code')

		# Extract numbers and find the highest
		max_number = 0
		for code in existing_codes:
			if code and code.startswith(prefix):
				number_part = code[len(prefix):].split('-')[0] if '-' in code else code[len(prefix):]
				try:
					number = int(number_part)
					max_number = max(max_number, number)
				except ValueError:
					continue

		# Generate next number
		next_number = max_number + 1
		padding = sequence.padding or 5
		suffix = sequence.suffix or ''

		return f"{prefix}{str(next_number).zfill(padding)}{suffix}"

	def _should_auto_generate_code(self):
		"""Check if product should get auto-generated code"""
		self.ensure_one()
		return (
				self.product_sub_type_id and
				self.product_sub_type_id.is_for_internal_reference and
				self.product_sub_type_id.sequence_id and
				not self.ths_exclude_from_auto_code
		)

	def _generate_internal_reference(self):
		"""Generate new internal reference using sub-type sequence (reuse gaps)"""
		self.ensure_one()

		if not self.product_sub_type_id or not self.product_sub_type_id.sequence_id:
			return False

		try:
			sequence = self.product_sub_type_id.sequence_id
			prefix = sequence.prefix or ''
			suffix = sequence.suffix or ''
			padding = sequence.padding or 5

			# Find existing codes with this prefix
			existing_products = self.search([
				('default_code', 'like', f'{prefix}%'),
				('product_sub_type_id', '=', self.product_sub_type_id.id),
				('id', '!=', self.id),
				('active', '=', True)
			])

			used_numbers = set()
			for product in existing_products:
				if product.default_code and product.default_code.startswith(prefix):
					# Extract number from code
					number_part = product.default_code[len(prefix):]
					if suffix:
						number_part = number_part[:-len(suffix)]
					try:
						used_numbers.add(int(number_part))
					except ValueError:
						continue

			# Find the first unused number starting from 1
			next_number = 1
			while next_number in used_numbers:
				next_number += 1

			# Generate the code
			new_code = f"{prefix}{str(next_number).zfill(padding)}{suffix}"
			return new_code

		except Exception as e:
			_logger.error(f"Error generating sequence code: {e}")
			return False

	def action_generate_internal_reference(self):
		"""Manual action to generate/regenerate internal reference"""
		for product in self:
			if not product.product_sub_type_id:
				raise ValidationError(_("Please select a Product Sub Type first."))

			if not product.product_sub_type_id.is_for_internal_reference:
				raise ValidationError(_("Selected Product Sub Type is not configured for internal reference generation."))

			if not product.product_sub_type_id.sequence_id:
				raise ValidationError(_("No sequence configured for this Product Sub Type."))

			new_code = product._generate_internal_reference()
			if new_code:
				# Update both the actual field AND the trigger
				product.write({
					'default_code': new_code,
					'ths_auto_code_generated': True,
					'ths_code_generation_trigger': fields.Datetime.now()
				})

	def action_clear_auto_generated_flag(self):
		"""Clear the auto-generated flag (for manual codes)"""
		self.write({
			'ths_auto_code_generated': False,
			'ths_code_generation_trigger': fields.Datetime.now()  # Trigger UI refresh
		})

	@api.constrains('default_code')
	def _check_unique_default_code(self):
		"""Ensure internal reference is unique"""
		for product in self:
			if product.default_code:
				duplicate = self.search([
					('default_code', '=', product.default_code),
					('id', '!=', product.id),
					('active', '=', True)
				], limit=1)
				if duplicate:
					raise ValidationError(_("Internal Reference '%s' already exists for product '%s'") %
										  (product.default_code, duplicate.name))

	@api.model_create_multi
	def create(self, vals_list):
		"""Override create to auto-generate internal reference codes"""
		products = super().create(vals_list)

		for product in products:
			# Auto-generate code if conditions are met
			if product._should_auto_generate_code():
				try:
					new_code = product._generate_internal_reference()
					if new_code:
						product.write({
							'default_code': new_code,
							'ths_auto_code_generated': True
						})
						_logger.info(f"Auto-generated code '{new_code}' for product {product.name}")
				except Exception as e:
					_logger.error(f"Failed to auto-generate code for product {product.name}: {e}")

		return products

	def write(self, vals):
		"""Override write to handle sub-type changes"""
		result = super().write(vals)

		# If sub-type changed, check if we need to auto-generate new code
		if 'product_sub_type_id' in vals:
			for product in self:
				if (product._should_auto_generate_code() and
						not product.default_code and
						not product.ths_exclude_from_auto_code):
					try:
						new_code = product._generate_internal_reference()
						if new_code:
							product.write({
								'default_code': new_code,
								'ths_auto_code_generated': True
							})
					except Exception as e:
						_logger.error(f"Failed to auto-generate code for product {product.name}: {e}")

		return result


# TODO: Add membership pricing tiers based on duration


class ProductProduct(models.Model):
	""" Inherit to add Product Sub Type field and domain logic. """
	_inherit = 'product.product'

	product_sub_type_id = fields.Many2one(related='product_tmpl_id.product_sub_type_id')

	# --- Computed Domain Field ---
	ths_sub_type_domain = fields.Char(related='product_tmpl_id.ths_sub_type_domain')
	ths_membership_duration = fields.Integer(related='product_tmpl_id.ths_membership_duration')
	ths_membership_duration_visible = fields.Boolean(related='product_tmpl_id.ths_membership_duration_visible')
	ths_membership_duration_required = fields.Boolean(related='product_tmpl_id.ths_membership_duration_required')