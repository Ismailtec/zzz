# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
	_inherit = 'res.partner'

	# Re-purpose the standard 'city' field to be a Many2one to res.country.area
	city = fields.Many2one(
		'res.country.area',
		string='Area/District',
		ondelete='restrict',
	)

	state_id = fields.Many2one(
		"res.country.state", string='State',
		ondelete='restrict',
		domain="[('country_id', '=?', country_id)]",
		tracking=True,
	)

	@api.model
	def _default_country_id(self):
		return self.env['res.country'].search([('code', '=', 'KW')], limit=1).id

	country_id = fields.Many2one(
		'res.country', string='Country', ondelete='restrict', tracking=True,
		default=_default_country_id  # Set Kuwait as default
	)

	# Computed domain for the 'city' field
	@api.depends('state_id', 'country_id')
	def _compute_city_domain(self):
		for partner in self:
			domain = []
			if partner.country_id:
				domain.append(('country_id', '=', partner.country_id.id))
			if partner.state_id:
				domain.append(('state_id', '=', partner.state_id.id))
			partner.city_domain = str(domain)  # Must be a string representation of the domain

	city_domain = fields.Char(compute='_compute_city_domain', store=False)

	@api.onchange('city')
	def _onchange_city_area(self):
		if self.city:
			# When an Area/District is selected, automatically set its associated State (Governorate) and Country
			if self.city.state_id and self.state_id != self.city.state_id:
				self.state_id = self.city.state_id.id
			if self.city.country_id and self.country_id != self.city.country_id:
				self.country_id = self.city.country_id.id

	@api.onchange('state_id')
	def _onchange_state_id(self):
		# Clear city if selected state changes and the current city is not consistent with the new state
		if self.city and self.city.state_id != self.state_id:
			self.city = False
		# If state is set but country is not (and city is present), ensure country is set from state
		if self.state_id and not self.country_id:
			self.country_id = self.state_id.country_id.id

	@api.onchange('country_id')
	def _onchange_country_id(self):
		# Clear city and state if selected country changes and they are not consistent
		if self.city and self.city.country_id != self.country_id:
			self.city = False
			self.state_id = False  # Also clear state if it was linked to the old country
		elif self.state_id and self.state_id.country_id != self.country_id:
			self.state_id = False  # Only clear state if it was linked to the old country

	@api.model
	def _prepare_display_address(self, without_company=False):
		"""Override the base address preparation method to inject the name
        of the Many2one 'city' field (res.country.area) into the arguments
        for the address format."""
		address_format, args = super()._prepare_display_address(without_company=without_company)
		address_format = self._get_address_format()
		if self.city:
			args['city'] = self.city.name
		if self.state_id:
			# args['state_code'] = self.state_id.code or ''
			args['state_name'] = self.state_id.name or ''
		return address_format, args

	@api.depends('street', 'zip', 'city', 'country_id')
	def _compute_complete_address(self):
		"""  Override to compute a complete address string with city name. """
		for record in self:
			record.contact_address_complete = ''
			if record.street:
				record.contact_address_complete += record.street + ', '
			if record.zip:
				record.contact_address_complete += record.zip + ' '
			if record.city:
				record.contact_address_complete += record.city.name + ', '
			if record.state_id:
				record.contact_address_complete += record.state_id.name + ', '
			if record.country_id:
				record.contact_address_complete += record.country_id.name
			record.contact_address_complete = record.contact_address_complete.strip().strip(',')