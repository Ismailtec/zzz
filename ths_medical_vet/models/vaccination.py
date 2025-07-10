# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class VetVaccination(models.Model):
	_name = 'vet.vaccination'
	_description = 'Pet Vaccination Record'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_order = 'date desc, id desc'
	_rec_name = 'vaccine_type_id'

	pet_id = fields.Many2one(
		'res.partner',
		string='Pet',
		context={'is_pet': True},
		required=True,
		index=True,
		domain="[('partner_type_id.name', '=', 'Pet')]",
		tracking=True,
	)
	owner_id = fields.Many2one(
		'res.partner',
		context={'is_pet': False},
		string='Pet Owner',
		domain="[('partner_type_id.name', '=', 'Pet Owner')]",
		store=True,
		readonly=False,
	)
	pet_id_domain = fields.Char(
		compute='_compute_pet_domain',
		store=False
	)
	vaccine_type_id = fields.Many2one(
		'vet.vaccine.type',
		string='Vaccine Type',
		required=True,
		tracking=True,
	)
	date = fields.Date(
		string='Vaccination Date',
		required=True,
		default=fields.Date.context_today,
		tracking=True,
	)
	expiry_date = fields.Date(
		string='Expiry Date',
		compute='_compute_expiry_date',
		store=True,
		readonly=False,
		tracking=True,
	)
	batch_number = fields.Char(
		string='Batch/Lot Number',
		tracking=True,
	)
	practitioner_id = fields.Many2one(
		'appointment.resource',
		string='Service Provider',
		domain="[('resource_category', '=', 'practitioner')]",
		store=True,
		index=True,
	)
	clinic_name = fields.Char(
		string='Clinic/Hospital Name',
		default=lambda self: self.env.company.name,
	)
	notes = fields.Text(string='Notes')

	encounter_id = fields.Many2one(
		'ths.medical.base.encounter',
		string='Daily Encounter',
		readonly=True,
		copy=False,
		index=True,
		ondelete='set null',
		help="Daily encounter this vaccination belongs to"
	)

	# Status tracking
	is_expired = fields.Boolean(
		string='Expired',
		compute='_compute_is_expired',
		store=True,
	)
	days_until_expiry = fields.Integer(
		string='Days Until Expiry',
		store=True,
		compute='_compute_days_until_expiry',
	)

	company_id = fields.Many2one(
		'res.company',
		string='Company',
		default=lambda self: self.env.company,
	)

	@api.depends('owner_id')
	def _compute_pet_domain(self):
		"""Compute domain for pets based on selected owner"""
		for rec in self:
			if rec.owner_id:
				# Filter pets by selected owner
				rec.pet_id_domain = str([
					('pet_owner_id', '=', rec.owner_id.id),
					('partner_type_id.name', '=', 'Pet')
				])
			else:
				# Show all pets when no owner selected
				rec.pet_id_domain = str([('partner_type_id.name', '=', 'Pet')])

	@api.depends('date', 'vaccine_type_id.validity_months')
	def _compute_expiry_date(self):
		"""Calculate expiry date based on vaccine type validity"""
		for record in self:
			if record.date and record.vaccine_type_id and record.vaccine_type_id.validity_months:
				record.expiry_date = record.date + relativedelta(months=record.vaccine_type_id.validity_months)
			else:
				record.expiry_date = False

	@api.depends('expiry_date')
	def _compute_is_expired(self):
		"""Check if vaccination is expired"""
		today = fields.Date.context_today(self)
		for record in self:
			record.is_expired = bool(record.expiry_date and record.expiry_date < today)

	@api.depends('expiry_date')
	def _compute_days_until_expiry(self):
		"""Calculate days until expiry"""
		today = fields.Date.context_today(self)
		for record in self:
			if record.expiry_date:
				delta = record.expiry_date - today
				record.days_until_expiry = delta.days
			else:
				record.days_until_expiry = 0

	@api.constrains('date', 'expiry_date')
	def _check_dates(self):
		"""Ensure expiry date is after vaccination date"""
		for record in self:
			if record.date and record.expiry_date and record.expiry_date <= record.date:
				raise ValidationError(_("Expiry date must be after vaccination date."))

	@api.model_create_multi
	def create(self, vals_list):
		"""Override to link vaccinations to daily encounters"""
		vaccinations = super().create(vals_list)

		for vaccination in vaccinations:
			if not vaccination.encounter_id and vaccination.owner_id:
				encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
					partner_id=vaccination.owner_id.id,
					patient_ids=[vaccination.pet_id.id],
					encounter_date=vaccination.date,
					practitioner_id=vaccination.practitioner_id.id if vaccination.practitioner_id else False,
					room_id=False
				)
				vaccination.encounter_id = encounter.id

				vaccination.message_post(body=_("Vaccination linked to encounter %s", encounter.name))

		return vaccinations

	def action_view_encounter(self):
		"""View the daily encounter for this vaccination"""
		self.ensure_one()
		if not self.encounter_id:
			return {}

		return {
			'name': _('Daily Encounter'),
			'type': 'ir.actions.act_window',
			'res_model': 'ths.medical.base.encounter',
			'view_mode': 'form',
			'res_id': self.encounter_id.id,
			'target': 'current'
		}

	def action_schedule_reminder(self):
		"""Schedule activity reminder for vaccination renewal"""
		self.ensure_one()
		if self.expiry_date:
			# Schedule 30 days before expiry
			reminder_date = self.expiry_date - relativedelta(days=30)
			if reminder_date > fields.Date.context_today(self):
				self.activity_schedule(
					'mail.mail_activity_data_todo',
					date_deadline=reminder_date,
					summary=_('Vaccination Renewal: %s for %s') % (self.vaccine_type_id.name, self.pet_id.name),
					note=_('The %s vaccination for %s will expire on %s. Please schedule a renewal appointment.') % (
						self.vaccine_type_id.name, self.pet_id.name, self.expiry_date),
					user_id=self.env.user.id,
				)


class VetVaccineType(models.Model):
	_name = 'vet.vaccine.type'
	_description = 'Vaccine Type'
	_order = 'name'

	name = fields.Char(string='Vaccine Name', required=True)
	code = fields.Char(string='Code', required=True)
	validity_months = fields.Integer(
		string='Validity (Months)',
		required=True,
		default=12,
		help="Number of months this vaccine remains valid"
	)
	description = fields.Text(string='Description')
	active = fields.Boolean(default=True)

	_sql_constraints = [
		('code_uniq', 'unique (code)', 'Vaccine code must be unique!'),
	]

# TODO: Add vaccination encounter batch processing
# TODO: Implement vaccination reminder encounter creation
# TODO: Add vaccination adverse reaction tracking per encounter
# TODO: Implement vaccination certificate generation from encounter
# TODO: Add vaccination inventory integration with encounter
# TODO: Implement vaccination effectiveness tracking