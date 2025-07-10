# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ParkCheckin(models.Model):
	_name = 'park.checkin'
	_description = 'Park Check-in Record'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_order = 'checkin_time desc, name'
	_rec_name = 'name'

	name = fields.Char(
		string='Check-in Reference',
		required=True,
		copy=False,
		readonly=True,
		index=True,
		default=lambda self: _('New')
	)

	partner_id = fields.Many2one(
		'res.partner',
		string='Pet Owner',
		context={'is_pet': False},
		required=True,
		index=True,
		domain="[('partner_type_id.name', '=', 'Pet Owner')]",
		tracking=True,
		help="Pet owner accessing the park"
	)

	patient_ids = fields.Many2many(
		'res.partner',
		'park_checkin_pet_rel',
		'checkin_id',
		'pet_id',
		context={'is_pet': True},
		string='Pets',
		domain="[('partner_type_id.name', '=', 'Pet'), ('pet_owner_id', '=', partner_id)]",
		tracking=True,
		help="Pets accompanying the owner to the park"
	)

	checkin_time = fields.Datetime(
		string='Check-in Time',
		required=True,
		default=fields.Datetime.now,
		tracking=True,
	)

	checkout_time = fields.Datetime(
		string='Check-out Time',
		tracking=True,
	)

	duration_hours = fields.Float(
		string='Duration (Hours)',
		compute='_compute_duration',
		store=True,
		help="Duration of park visit in hours"
	)

	encounter_id = fields.Many2one(
		'ths.medical.base.encounter',
		string='Daily Encounter',
		readonly=True,
		copy=False,
		index=True,
		ondelete='set null',
		help="Daily encounter this park visit belongs to"
	)

	# Membership validation
	membership_valid = fields.Boolean(
		string='Membership Valid',
		compute='_compute_membership_valid',
		store=True,
		help="Whether pets have valid membership for park access"
	)

	state = fields.Selection([
		('checked_in', 'Checked In'),
		('checked_out', 'Checked Out')
	], string='Status', default='checked_in', required=True, tracking=True)

	notes = fields.Text(string='Visit Notes')
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

	# --- Compute Methods ---
	@api.depends('checkin_time', 'checkout_time')
	def _compute_duration(self):
		"""Calculate visit duration in hours"""
		for record in self:
			if record.checkin_time and record.checkout_time:
				delta = record.checkout_time - record.checkin_time
				record.duration_hours = delta.total_seconds() / 3600.0
			else:
				record.duration_hours = 0.0

	@api.depends('partner_id', 'patient_ids')
	def _compute_membership_valid(self):
		"""Check if pets have valid membership using new membership model"""
		for record in self:
			if record.patient_ids:
				record.membership_valid = self.env['vet.pet.membership'].check_pet_membership_validity(
					record.patient_ids.ids
				)
			else:
				record.membership_valid = False

	# --- Constraints ---
	@api.constrains('partner_id')
	def _check_membership_access(self):
		"""Validate membership before allowing check-in using new model"""
		for record in self:
			if record.patient_ids and not record.membership_valid:
				raise ValidationError(_(
					"One or more pets do not have valid membership for park access. "
					"Please check membership status for: %s",
					', '.join(record.patient_ids.mapped('name'))
				))

	@api.constrains('checkin_time', 'checkout_time')
	def _check_times(self):
		"""Validate check-in/check-out times"""
		for record in self:
			if record.checkout_time and record.checkout_time <= record.checkin_time:
				raise ValidationError(_("Check-out time must be after check-in time."))

	@api.model
	def _get_checkin_domain_by_context(self):
		domain = []
		date_filter = self.env.context.get('search_checkin_time_range')
		today = fields.Date.context_today(self)

		if date_filter == 'today':
			domain += [
				('checkin_time', '>=', fields.Datetime.to_datetime(f"{today} 00:00:00")),
				('checkin_time', '<=', fields.Datetime.to_datetime(f"{today} 23:59:59")),
			]

		elif date_filter == 'this_week':
			start_week = today - timedelta(days=today.weekday())
			end_week = start_week + timedelta(days=6)
			domain += [
				('checkin_time', '>=', fields.Datetime.to_datetime(f"{start_week} 00:00:00")),
				('checkin_time', '<=', fields.Datetime.to_datetime(f"{end_week} 23:59:59")),
			]

		elif date_filter == 'last_week':
			start_last_week = today - timedelta(days=today.weekday() + 7)
			end_last_week = start_last_week + timedelta(days=6)
			domain += [
				('checkin_time', '>=', fields.Datetime.to_datetime(f"{start_last_week} 00:00:00")),
				('checkin_time', '<=', fields.Datetime.to_datetime(f"{end_last_week} 23:59:59")),
			]

		return domain

	# --- CRUD Methods ---
	@api.model_create_multi
	def create(self, vals_list):
		"""Override to create encounter and assign sequence"""
		for vals in vals_list:
			if vals.get('name', _('New')) == _('New'):
				vals['name'] = self.env['ir.sequence'].sudo().next_by_code('park.checkin') or _('New')

		checkins = super().create(vals_list)

		for checkin in checkins:
			if not checkin.encounter_id:
				checkin_date = checkin.checkin_time.date()

				encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
					partner_id=checkin.partner_id.id,
					patient_ids=checkin.patient_ids.ids,
					encounter_date=checkin_date,
					practitioner_id=False,
					room_id=False
				)
				checkin.encounter_id = encounter.id

				checkin.message_post(body=_("Park visit linked to encounter %s", encounter.name))

		return checkins

	# --- Actions ---
	def action_checkout(self):
		"""Check out from park"""
		for checkin in self.filtered(lambda c: c.state == 'checked_in'):
			checkin.write({
				'checkout_time': fields.Datetime.now(),
				'state': 'checked_out'
			})
			checkin.message_post(body=_("Checked out from park after %.2f hours", checkin.duration_hours))

	def action_view_encounter(self):
		"""View the daily encounter for this park visit"""
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

	def action_extend_visit(self):
		"""Extend park visit (reset checkout)"""
		for checkin in self.filtered(lambda c: c.state == 'checked_out'):
			checkin.write({
				'checkout_time': False,
				'state': 'checked_in'
			})
			checkin.message_post(body=_("Park visit extended"))

# TODO: Add park capacity management per time slot
# TODO: Implement park activity tracking per pet
# TODO: Add park social interaction logging
# TODO: Implement park incident reporting system
# TODO: Add park weather condition tracking
# TODO: Implement park usage analytics per member
# TODO: Add park equipment usage tracking
# TODO: Implement park group activity coordination
# TODO: Add membership expiration warnings
# TODO: Add membership usage tracking per visit