# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.osv import expression
from odoo.exceptions import ValidationError

# Use user's requested import block for translate library
try:
	from translate import Translator
except ImportError:
	# This will stop Odoo from loading if the library is missing
	raise ImportError(
		'This module needs translate to automatically write word in arabic. '
		'Please install translate on your system. (sudo pip3 install translate)')

import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
	_inherit = 'res.partner'

	partner_type_id = fields.Many2one('ths.partner.type', string='Partner Type', required=True, index=True, tracking=True,
									  default=lambda self: self.env.ref('ths_base.partner_type_contact', raise_if_not_found=False))
	# Added Arabic Name field
	name_ar = fields.Char("Name (Arabic)", store=True, copy=True)
	gender = fields.Selection([('male', 'Male'), ('female', 'Female')], string='Gender')
	ths_gov_id = fields.Char(string='ID Number', help="National Identifier (ID)", readonly=False, copy=False, store=True)
	ths_nationality = fields.Many2one('res.country', 'Nationality', copy=False, store=True)
	ths_dob = fields.Date(string='Date of Birth')
	ths_age = fields.Char(string='Age', compute='_compute_ths_age', store=False)

	# --- Onchange Methods ---
	@api.onchange('name')
	def onchange_name_translate(self):
		"""Translates the English name to Arabic on change."""
		if not self.name or not self.name.strip():
			self.name_ar = False
			return

		try:
			translator = Translator(to_lang="ar")
			result = translator.translate(self.name)

			self.name_ar = result if result else f"[Pending: {self.name}]"

		except (ConnectionError, TimeoutError) as e:
			_logger.error(f"Network error during translation for '{self.name}': {e}")
			self.name_ar = f"[Network error: {self.name}]"
		except ImportError as e:
			_logger.error(f"Translator library not available: {e}")
			self.name_ar = f"[Library error: {self.name}]"
		except AttributeError as e:
			_logger.error(f"Translator attribute error for '{self.name}': {e}")
			self.name_ar = f"[Translation error: {self.name}]"
		except Exception as e:
			_logger.error(f"Unexpected translation error for '{self.name}': {type(e).__name__}: {e}")
			self.name_ar = f"[Error: {self.name}]"

	@api.onchange('partner_type_id')
	def _onchange_partner_type_id(self):
		""" Update standard company_type based on the partner type flags. """
		if self.partner_type_id:
			self.company_type = 'company' if self.partner_type_id.is_company else 'person'
		else:
			self.company_type = 'person'

	@api.constrains('ths_gov_id')
	def _check_id_numeric(self):
		for rec in self:
			if rec.ths_gov_id and not rec.ths_gov_id.isdigit():
				raise ValidationError(_("ID Number must contain only digits."))

	# === Compute Methods ===
	@api.depends('ths_dob')
	def _compute_ths_age(self):
		"""Compute accurate age from date of birth"""
		for partner in self:
			partner.ensure_one()

			# Early returns for optimization
			if partner.is_company or not partner.ths_dob:
				partner.ths_age = "N/A"
				continue

			today = fields.Date.context_today(partner)
			delta = relativedelta(today, partner.ths_dob)

			# Simple format
			parts = []
			if delta.years: parts.append(f"{delta.years}y")
			if delta.months: parts.append(f"{delta.months}m")
			if delta.days: parts.append(f"{delta.days}d")

			partner.ths_age = " ".join(parts) or "0d"

	# --- Helper to get HR Handled Type IDs ---
	@api.model
	def _get_hr_handled_partner_type_ids(self):
		""" Safely gets the database IDs for partner types managed by ths_hr. """
		hr_handled_type_ids = []
		# Check if ths_hr module is installed before trying to access its data
		module_ths_hr = self.env['ir.module.module'].sudo().search(
			[('name', '=', 'ths_hr'), ('state', '=', 'installed')], limit=1)
		if module_ths_hr:
			hr_handled_type_xmlids = [
				'ths_hr.partner_type_employee',
				'ths_hr.partner_type_part_time_employee',
				'ths_hr.partner_type_external_employee',
			]
			for xmlid in hr_handled_type_xmlids:
				hr_type_record = self.env.ref(xmlid, raise_if_not_found=False)
				if hr_type_record:
					hr_handled_type_ids.append(hr_type_record.id)
		return hr_handled_type_ids

	# --- Override Create Method ---
	@api.model_create_multi
	def create(self, vals_list):
		hr_types = self._get_hr_handled_partner_type_ids()
		for vals in vals_list:
			if vals.get('partner_type_id'):
				ptype = self.env['ths.partner.type'].browse(vals['partner_type_id'])
				vals['is_company'] = ptype.is_company if ptype.is_company else False
				if ptype.is_customer:
					vals.setdefault('customer_rank', 1)
		partners = super().create(vals_list)
		# Generate ref
		to_ref = partners.filtered(lambda x: x.partner_type_id.sequence_id
											 and not x.ref and x.partner_type_id.id not in hr_types)
		for p in to_ref:
			try:
				p.ref = p.partner_type_id.sequence_id.next_by_id()
			except Exception as e:
				_logger.error(f"Ref gen failed for partner {p.id}: {e}")
		return partners

	def write(self, vals):
		original = {p.id: p.partner_type_id.id for p in self} if 'partner_type_id' in vals else {}
		res = super().write(vals)
		hr_types = self._get_hr_handled_partner_type_ids()
		for partner in self:
			if 'partner_type_id' in vals:
				new_t = partner.partner_type_id
				partner.is_company = new_t.is_company if new_t.is_company else False
				if new_t.is_customer and not partner.customer_rank:
					partner.customer_rank = 1
				old_t = original.get(partner.id)
				if old_t and old_t != new_t.id and new_t.id not in hr_types:
					partner.ref = False
					if new_t.sequence_id:
						try:
							partner.ref = new_t.sequence_id.next_by_id()
						except Exception as e:
							_logger.error(f"Ref regen failed for {partner.id}: {e}")
		return res

	# --- Helper Methods ---
	@staticmethod
	def _match_vals_to_partner(vals, partner):
		""" Helper to match vals dictionary to a created partner record. """
		if vals.get('name') and partner.name and partner.name == vals.get('name'):
			if 'email' in vals or 'vat' in vals:
				if vals.get('email') and partner.email and partner.email == vals.get('email'): return True
				if vals.get('vat') and partner.vat and partner.vat == vals.get('vat'): return True
				return False
			else:
				return True
		return False

	# --- Name Search Override ---
	@api.model
	def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
		""" Override name_search to include additional searchable fields.
			Searches across: name, ref, mobile, phone, email, name_ar, ths_gov_id  """
		args = args or []

		# If no search term provided, return standard search
		if operator == 'ilike' and not (name or '').strip():
			domain = []
		else:
			# Define base searchable fields (always available)
			base_fields = ['name', 'ref', 'mobile', 'phone', 'email', 'ths_gov_id']

			# Define optional fields with defensive checking
			optional_fields = []

			# Safely add name_ar if available (from ths_base or ths_hr)
			if 'name_ar' in self._fields:
				optional_fields.append('name_ar')

			# Safely add ths_gov_id if available and field is not False/None
			if 'ths_gov_id' in self._fields:
				# Additional check: ensure field is properly defined
				gov_id_field = self._fields.get('ths_gov_id')
				if gov_id_field and hasattr(gov_id_field, 'type') and gov_id_field.type == 'char':
					optional_fields.append('ths_gov_id')

			# Combine all available fields
			searchable_fields = base_fields + optional_fields

			_logger.info(f"SEARCH DEBUG: Base fields: {base_fields}")
			_logger.info(f"SEARCH DEBUG: Optional fields: {optional_fields}")
			_logger.info(f"SEARCH DEBUG: Final searchable fields: {searchable_fields}")

			# Create OR domain across all searchable fields
			domain = expression.OR([
				[(field, operator, name)] for field in searchable_fields
			])

		# Execute search with combined domain
		return self._search(
			expression.AND([domain, args]),
			limit=limit,
			access_rights_uid=name_get_uid,
			order=order
		)