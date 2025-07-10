# models/res_company.py
# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ResCompany(models.Model):
	_inherit = 'res.company'

	# Re-purpose the standard 'city' field to be a Many2one to res.country.area
	# This aligns company addresses with the new area structure.
	city = fields.Many2one(
		'res.country.area',
		string='Area/District',
		ondelete='restrict',
		help="The Area/District where the company is located."
	)

	# Computed domain for the 'city' field, similar to res.partner
	@api.depends('state_id', 'country_id')
	def _compute_company_city_domain(self):
		"""
		Computes the domain for the 'city' (Area/District) field based on the
		selected Country and State (Governorate) of the company.
		"""
		for company in self:
			domain = []
			if company.country_id:
				domain.append(('country_id', '=', company.country_id.id))
			if company.state_id:
				domain.append(('state_id', '=', company.state_id.id))
			company.company_city_domain = domain

	company_city_domain = fields.Char(
		compute='_compute_company_city_domain',
		store=False,
		readonly=True
	)

	# Override _compute_address to handle custom city field
	@api.depends(lambda self: [f'partner_id.{fname}' for fname in self._get_company_address_field_names()] + ['city'])
	def _compute_address(self):
		"""Override to compute address fields, including the custom city Many2one."""
		for company in self.filtered(lambda company: company.partner_id):
			address_data = company.partner_id.sudo().address_get(adr_pref=['contact'])
			if address_data['contact']:
				partner = company.partner_id.browse(address_data['contact']).sudo()
				address_update = company._get_company_address_update(partner)
				# Update standard fields from partner
				company.update({key: val for key, val in address_update.items() if key != 'city'})
				# Sync custom city using partner_id.city (Many2one to res.country.area)
				if partner.city and (not company.city or company.city.id != partner.city.id):
					company.city = partner.city.id
				elif not partner.city and company.city:
					company.city = False
			else:
				# Clear address fields if no contact address
				company.street = False
				company.street2 = False
				company.zip = False
				company.city = False
				company.state_id = False
				company.country_id = False

	# Inverse methods to update partner_id when company address changes
	def _inverse_street(self):
		for company in self:
			if company.partner_id:
				company.partner_id.street = company.street

	def _inverse_street2(self):
		for company in self:
			if company.partner_id:
				company.partner_id.street2 = company.street2

	def _inverse_zip(self):
		for company in self:
			if company.partner_id:
				company.partner_id.zip = company.zip

	def _inverse_city(self):
		for company in self:
			if company.partner_id:
				if company.city:
					company.partner_id.city = company.city.name
				else:
					company.partner_id.city = False

	def _inverse_state(self):
		for company in self:
			if company.partner_id:
				company.partner_id.state_id = company.state_id

	def _inverse_country(self):
		for company in self:
			if company.partner_id:
				company.partner_id.country_id = company.country_id

	# Onchange methods for consistency with res.partner address logic
	@api.onchange('city')
	def _onchange_company_city_kw(self):
		"""  Autopopulates State and Country based on selected Area/District for the company. """
		if self.city:
			if not self.state_id or self.state_id != self.city.state_id:
				self.state_id = self.city.state_id
			if not self.country_id or self.country_id != self.city.country_id:
				self.country_id = self.city.country_id

	# TODO: Add logic to clear state/country if city is cleared and they were linked to that city
	#       Similar to res.partner, if needed, for more strict cascading.

	@api.onchange('state_id')
	def _onchange_company_state_id_kw(self):
		"""
		On state (Governorate) change, ensures country is set and clears the Area/District
		if it no longer belongs to the new state/country for the company.
		"""
		if self.state_id and not self.country_id:
			self.country_id = self.state_id.country_id
		elif self.state_id and self.state_id.country_id != self.country_id:
			# Clear state if it was linked to the old country that doesn't match the new one
			self.state_id = False

		# Clear the city field if it's not applicable to the new state
		if self.city and (self.city.state_id != self.state_id or self.city.country_id != self.country_id):
			self.city = False

	@api.onchange('country_id')
	def _onchange_company_country_id_kw(self):
		"""  On country change, clears state_id and Area/District for the company.  """
		if self.country_id and self.state_id and self.state_id.country_id != self.country_id:
			# Clear state if it no longer matches the new country
			self.state_id = False

		# Clear the city field if it's not applicable to the new country
		if self.city and self.city.country_id != self.country_id:
			self.city = False


class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	@api.depends('company_id')
	def _compute_company_informations(self):
		for record in self:
			informations = '%s\n' % record.company_id.street if record.company_id.street else ''
			informations += '%s\n' % record.company_id.street2 if record.company_id.street2 else ''
			informations += '%s' % record.company_id.zip if record.company_id.zip else ''
			informations += '\n' if record.company_id.zip and not record.company_id.city else ''
			informations += ' - ' if record.company_id.zip and record.company_id.city else ''
			informations += '%s\n' % record.company_id.city.name if record.company_id.city else ''
			informations += '%s\n' % record.company_id.state_id.display_name if record.company_id.state_id else ''
			informations += '%s' % record.company_id.country_id.display_name if record.company_id.country_id else ''
			vat_display = record.company_id.country_id.vat_label or _('VAT')
			vat_display = '\n' + vat_display + ': '
			informations += '%s %s' % (vat_display, record.company_id.vat) if record.company_id.vat else ''
			record.company_informations = informations