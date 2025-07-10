# -*- coding: utf-8 -*-

from odoo import models, fields, api


class VetBoardingCage(models.Model):
	_name = 'vet.boarding.cage'
	_description = 'Veterinary Boarding Cage/Enclosure'
	_order = 'name asc'

	name = fields.Char(string='Cage Name/Number', required=True, index=True)
	allowed_species_ids = fields.Many2many('ths.species', string='Allowed Species')
	notes = fields.Text(string='Notes/Description')
	state = fields.Selection([
		('available', 'Available'),
		('occupied', 'Occupied'),
		('maintenance', 'Maintenance'),
	], string='Status', default='available', index=True, required=True)
	active = fields.Boolean(default=True, index=True)
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

	_sql_constraints = [
		('name_company_uniq', 'unique (name, company_id)', 'Cage name must be unique per company!')
	]

	# Field to show current occupant ( Pet Name (Stay Ref) )
	current_stay_id = fields.Many2one(
		'vet.boarding.stay',
		string='Current Stay',
		compute='_compute_current_stay',
		store=False,  # Dynamic lookup
		help="The current boarding stay occupying this cage.",
	)
	current_occupant_display = fields.Char(
		string="Current Occupant",
		compute='_compute_current_stay',
		store=False,
	)

	@api.depends('state')  # Recompute when state changes
	def _compute_current_stay(self):
		""" Find the active stay associated with this cage """
		active_stays = self.env['vet.boarding.stay'].search([
			('cage_id', 'in', self.ids),
			('state', '=', 'checked_in')  # Only show currently checked-in stays
		])
		stays_by_cage = {stay.cage_id.id: stay for stay in active_stays}

		for cage in self:
			stay = stays_by_cage.get(cage.id)
			cage.current_stay_id = stay.id if stay else False
			cage.current_occupant_display = f"{stay.pet_id.name} ({stay.name})" if stay and stay.pet_id else ""