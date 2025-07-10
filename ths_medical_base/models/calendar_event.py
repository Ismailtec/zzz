# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
	""" Inherit Calendar Event to add medical context and encounter creation. """
	_inherit = 'calendar.event'

	name = fields.Char(default="Draft")

	practitioner_id = fields.Many2one(
		'appointment.resource',
		string='Service Provider',
		domain="[('resource_category', '=', 'practitioner')]",
		compute='_compute_appointment_ars',
		store=True,
		readonly=False,
		tracking=True,
		help="The specific service provider (as an appointment resource) for this event."
	)
	room_id = fields.Many2one(
		'appointment.resource',
		string='Room',
		domain="[('resource_category', '=', 'location')]",
		compute='_compute_appointment_ars',
		store=True,
		readonly=False,
		tracking=True,
		copy=False,
		help="The specific room (as an appointment resource) for this event."
	)

	practitioner_id_domain = fields.Char(compute='_compute_ar_domains')
	room_id_domain = fields.Char(compute='_compute_ar_domains')

	# Patient receiving the service (in base module: human patient who is also the customer)
	patient_ids = fields.Many2many(
		'res.partner',
		'calendar_event_patient_rel',
		'event_id',
		'patient_id',
		string='Patients',
		index=True,
		tracking=True,
		store=True,
		readonly=False,
		domain="['|', ('partner_type_id.is_patient', '=', True), ('partner_type_id.name', '=', 'Walk-in')]",
		help="Patients linked to this appointment. In human medical practice, these are the people receiving treatment and responsible for payment."
	)

	ths_reason_for_visit = fields.Text(string='Reason for Visit')

	appointment_status = fields.Selection(
		selection_add=[
			('draft', 'Draft'),
			('confirmed', 'Confirmed'),
			('checked_in', 'Checked In'),
			('in_progress', 'In Progress'),
			('completed', 'Completed'),
			('billed', 'Billed'),
			('cancelled_by_patient', 'Cancelled (Patient)'),
			('cancelled_by_clinic', 'Cancelled (Clinic)'),
			('no_show', 'No Show')
		],
		ondelete={
			'draft': 'cascade', 'confirmed': 'cascade', 'checked_in': 'cascade',
			'in_progress': 'cascade', 'completed': 'cascade', 'billed': 'cascade',
			'cancelled_by_patient': 'cascade', 'cancelled_by_clinic': 'cascade',
			'no_show': 'cascade',
			# Hide unwanted original statuses
			'request': 'set null', 'booked': 'set null',
			'attended': 'set null'
		}
	)

	ths_check_in_time = fields.Datetime(string='Check-in Time', readonly=True, copy=False)
	ths_check_out_time = fields.Datetime(string='Check-out Time', readonly=True, copy=False)
	ths_cancellation_reason_id = fields.Many2one(
		'ths.medical.cancellation.reason',
		string='Cancellation Reason', copy=False)

	# --- Walk-in Flag ---
	is_walk_in = fields.Boolean(string="Walk-in", default=False, tracking=True,
									help="Check if this appointment was created for a walk-in patient.")

	# Link to the clinical encounter generated from this appointment
	encounter_id = fields.Many2one(
		'ths.medical.base.encounter', string='Daily Encounter',
		readonly=True, copy=False, index=True, ondelete='set null',
		help="Daily encounter container for all services")

	encounter_count = fields.Integer(compute='_compute_encounter_count', store=False)

	is_resource_based_type = fields.Boolean(
		compute='_compute_is_resource_based_type', store=False
	)

	# --- Compute & Depends Methods ---
	@api.depends('appointment_type_id.schedule_based_on')
	def _compute_is_resource_based_type(self):
		for rec in self:
			rec.is_resource_based_type = rec.appointment_type_id.schedule_based_on == 'resources'

	@api.depends('appointment_type_id.resource_ids', 'appointment_type_id.schedule_based_on')
	def _compute_ar_domains(self):
		for rec in self:
			domain_pract = "[('resource_category', '=', 'practitioner')]"
			domain_loc = "[('resource_category', '=', 'location')]"

			if rec.appointment_type_id and rec.appointment_type_id.schedule_based_on == 'resources':
				ids_str = str(rec.appointment_type_id.resource_ids.ids)
				domain_pract = "[('resource_category', '=', 'practitioner'), ('id', 'in', %s)]" % ids_str
				domain_loc = "[('resource_category', '=', 'location'), ('id', 'in', %s)]" % ids_str

			rec.practitioner_id_domain = domain_pract
			rec.room_id_domain = domain_loc

	@api.depends('resource_ids')
	def _compute_appointment_ars(self):
		for rec in self:
			practitioner = None
			location = None
			for res in rec.resource_ids:
				if res.resource_category == 'practitioner' and not practitioner:
					practitioner = res
				elif res.resource_category == 'location' and not location:
					location = res

			rec.practitioner_id = practitioner
			rec.room_id = location

	@api.model
	def default_get(self, fields_list):
		"""
		Handles gantt context properly and let inverse methods do the work
		"""
		res = super().default_get(fields_list)

		# Get appointment type from context
		ctx_appointment_type_id = self.env.context.get('default_appointment_type_id')
		if ctx_appointment_type_id and 'appointment_type_id' in fields_list:
			res['appointment_type_id'] = ctx_appointment_type_id

		# Gantt sets default_resource_ids, we use resource_ids (computed field with inverse)
		ctx_resource_ids = self.env.context.get('default_resource_ids', [])
		# Store our partner_ids before appointment module interferes
		# our_partner_ids = res.get('partner_ids', [])

		# If we have vet-specific partners, preserve them
		if self.env.context.get('default_patient_ids'):
			# Don't let appointment module override our partner_ids
			pass

		if ctx_resource_ids and 'resource_ids' in fields_list:
			# Set resource_ids - this will trigger inverse method automatically
			res['resource_ids'] = [Command.set(ctx_resource_ids)]

			# The onchange will populate our custom fields from resource_ids
			if len(ctx_resource_ids) == 1:
				resource = self.env['appointment.resource'].browse(ctx_resource_ids[0]).exists()
				if resource:
					if resource.resource_category == 'practitioner' and 'practitioner_id' in fields_list:
						res['practitioner_id'] = resource.id
					elif resource.resource_category == 'location' and 'room_id' in fields_list:
						res['room_id'] = resource.id

		# Set default medical status
		if res.get('appointment_type_id') and 'appointment_status' in fields_list and not res.get('appointment_status'):
			res['appointment_status'] = 'draft'

		# For human medical: partner_ids = patients
		partner_ids = self.env.context.get('default_partner_ids') or []
		if partner_ids and 'patient_ids' in fields_list:
			res['patient_ids'] = [Command.set(partner_ids)]

		return res

	@api.onchange('practitioner_id', 'room_id')
	def _onchange_practitioner_or_room(self):
		selected_ids = []
		if self.practitioner_id:
			selected_ids.append(self.practitioner_id.id)
		if self.room_id:
			selected_ids.append(self.room_id.id)
		self.resource_ids = [Command.set(list(set(selected_ids)))]

		# This ensures the standard M2M field is updated whenever our specific AR selectors change
		if 'appointment_resource_ids' in self._fields:
			self.appointment_resource_ids = [Command.set(list(set(selected_ids)))]

	@api.onchange('patient_ids')
	def _onchange_patient_attendees(self):
		"""
		For base human medical: when patients change, update partner_ids
		"""
		if self.patient_ids:
			# In human medical, patients are the partners/customers
			self.partner_ids = [Command.set([p.id for p in self.patient_ids])]
		else:
			self.partner_ids = [Command.clear()]

	# --- Walk-in Partner Handling ---
	def _get_walkin_partner_type(self):
		""" Helper to safely get the Walk-in partner type """
		return self.env.ref('ths_medical_base.partner_type_walkin', raise_if_not_found=False).sudo()

	def _prepare_walkin_partner_vals(self, walkin_type_id):
		""" Prepare values for creating a walk-in partner """
		walkin_sequence = self.env.ref('ths_medical_base.seq_partner_ref_walkin', raise_if_not_found=False)
		sequence_val = "WALK-IN"  # Fallback name
		if walkin_sequence:
			try:
				sequence_val = walkin_sequence.sudo().next_by_id()
			except Exception as e:
				_logger.error(f"Failed to get next walk-in sequence value: {e}")

		return {
			'name': f"Walk-in Patient ({sequence_val})",
			'partner_type_id': walkin_type_id,
		}

	def _handle_walkin_partner(self, vals):
		""" Check if walk-in partner needs to be created """
		walkin_type = self._get_walkin_partner_type()
		if not walkin_type:
			_logger.error("Walk-in Partner Type not found. Cannot create walk-in partner.")
			return vals

		# Check conditions: walk-in flag is true, and no patient/partner is provided
		if vals.get('is_walk_in') and not vals.get('patient_ids') and not vals.get('partner_ids'):
			partner_vals = self._prepare_walkin_partner_vals(walkin_type.id)
			try:
				walkin_partner = self.env['res.partner'].sudo().create(partner_vals)
				# For human medical: patient = partner (same person)
				vals['patient_ids'] = [Command.set([walkin_partner.id])]
				vals['partner_ids'] = [Command.set([walkin_partner.id])]
			except Exception as e:
				raise UserError(_("Failed to create walk-in partner record: %s", e))
		return vals

	# --- Create Override ---
	@api.model_create_multi
	def create(self, vals_list):
		""" Override create to handle walk-in partner creation and set ARs and patient from context """
		processed_vals_list = []
		for vals in vals_list:
			vals = self._handle_walkin_partner(vals.copy())

			# For human medical: ensure consistency between partner_ids and patient_ids
			# if vals.get('partner_ids') and not vals.get('patient_ids'):
			#     # Extract IDs from Command operations
			#     partner_ids_val = vals['partner_ids']
			#     if isinstance(partner_ids_val, list) and partner_ids_val:
			#         ids = []
			#         for cmd in partner_ids_val:
			#             if isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
			#                 if cmd[0] == Command.SET:
			#                     ids.extend(cmd[2] if cmd[2] else [])
			#                 elif cmd[0] == Command.LINK:
			#                     ids.append(cmd[1])
			#         if ids:
			#             vals['patient_ids'] = [Command.set(ids)]

			vals["name"] = self.env["ir.sequence"].next_by_code("medical.appointment")
			processed_vals_list.append(vals)

		return super().create(processed_vals_list)

	# --- Write Override ---
	def write(self, vals):
		"""Override write to trigger actions when status changes via statusbar"""
		result = super().write(vals)
		# Handle walk-in before super to ensure partner_ids is set if needed
		if vals.get("is_walk_in") and not vals.get("patient_ids") and not self.patient_ids:
			vals = self._handle_walkin_partner(vals.copy())

		# If appointment status is being changed, trigger appropriate actions
		if 'appointment_status' in vals:
			for event in self:
				new_status = vals['appointment_status']

				# Trigger actions based on status change
				if new_status == 'checked_in':
					event._find_or_create_encounter()
				elif new_status == 'in_progress':
					if not event.encounter_id:
						event._find_or_create_encounter()
					if event.encounter_id and event.encounter_id.state == 'done':
						event.encounter_id.write({'state': 'in_progress'})

		# if 'patient_ids' not in vals:
		#     # Ensure patient_ids is always in sync with partner_ids
		#     for event in self:
		#         if event.partner_ids and not event.patient_ids:
		#             event.patient_ids = [Command.set(event.partner_ids.ids)]
		#         elif not event.partner_ids and event.patient_ids:
		#             event.partner_ids = [Command.clear()]

		return result

	# --- Encounter Count & Actions
	@api.depends('encounter_id')
	def _compute_encounter_count(self):
		for event in self:
			event.encounter_count = 1 if event.encounter_id else 0

	# --- Action Buttons ---
	def action_check_in(self):
		""" Set status to Checked In and record time. Trigger encounter creation. """
		now = fields.Datetime.now()
		for event in self:
			if event.appointment_status not in ('draft', 'confirmed'):
				raise UserError(_("Appointment must be Draft or Confirmed to Check In."))
			if event.appointment_status in ('completed', 'billed', 'cancelled_by_clinic', 'no_show'):
				raise UserError(_('You cannot check-in a completed or cancelled appointment.'))

			# Ensure patient/partner is set before check-in
			if not event.patient_ids or not event.partner_ids:
				raise UserError(_("Cannot check in appointment without a Patient assigned."))

			# Ensure practitioner is selected if medical appointment
			if event.appointment_type_id and event.appointment_type_id.schedule_based_on == 'resources' and not event.practitioner_id:
				raise UserError(
					_("Cannot check in: A Service Provider must be selected for this medical appointment type."))

			event.write({
				'appointment_status': 'checked_in',
				'ths_check_in_time': now
			})
			event._find_or_create_encounter()
		return True

	def action_start_consultation(self):
		""" Set status to In Progress. """
		for event in self:
			if event.appointment_status != 'checked_in':
				raise UserError(_("Patient must be Checked In before starting the consultation."))
			if not event.encounter_id:
				event._find_or_create_encounter()
			if not event.encounter_id:
				raise UserError(_("Cannot start consultation: Daily Encounter is missing."))

			event.write({'appointment_status': 'in_progress'})
		return True

	def action_complete_and_bill(self):
		""" Mark appointment and encounter as completed/ready for billing. """
		now = fields.Datetime.now()
		for event in self:
			if event.appointment_status not in ('checked_in', 'in_progress'):
				raise UserError(_("Appointment must be Checked In or In Progress to mark as Completed."))
			if not event.encounter_id:
				raise UserError(_("Cannot complete appointment: Corresponding Medical Encounter not found."))

			event.write({
				'appointment_status': 'completed',
				'ths_check_out_time': now
			})
		return True

	def action_cancel_appointment(self):
		""" Open wizard to select cancellation reason and set status. """
		# TODO: Implement wizard for reason selection. Needs a transient model.
		blame_reason = self.env['ths.medical.cancellation.reason'].search([('blame', '=', 'clinic')], limit=1)
		vals_to_write = {
			'appointment_status': 'cancelled_by_clinic',
			'ths_cancellation_reason_id': blame_reason.id if blame_reason else False
		}

		self.write(vals_to_write)
		return True

	def action_mark_no_show(self):
		""" Mark as No Show. """
		self.write({'appointment_status': 'no_show'})
		return True

	# --- Encounter Creation Logic ---
	def _find_or_create_encounter(self):
		"""Find or create daily encounter for this appointment"""
		self.ensure_one()

		patients = self.patient_ids
		primary_patient = patients[0] if patients else False

		if not primary_patient:
			raise UserError("Cannot create encounter: Patients must be set on the appointment.")

		encounter_date = self.start.date() if self.start else fields.Date.context_today(self)

		encounter = self.env['ths.medical.base.encounter']._find_or_create_daily_encounter(
			partner_id=primary_patient.id,
			patient_ids=patients.ids,
			encounter_date=encounter_date,
			practitioner_id=self.practitioner_id,
			room_id=self.room_id
		)

		self.encounter_id = encounter.id

		return encounter

	# --- Action to View Encounter ---
	def action_view_encounter(self):
		self.ensure_one()
		if not self.encounter_id:
			return False
		action = self.env['ir.actions.actions']._for_xml_id('ths_medical_base.action_medical_encounter')
		action['domain'] = [('id', '=', self.encounter_id.id)]
		action['res_id'] = self.encounter_id.id
		action['views'] = [(self.env.ref('ths_medical_base.view_medical_encounter_form').id, 'form')]
		return action

	@api.model
	def _cron_send_appointment_reminders(self):
		"""Send appointment reminders 24 hours before"""
		tomorrow = fields.Datetime.now() + timedelta(days=1)
		tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0)
		tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)

		appointments = self.search([
			('start', '>=', tomorrow_start),
			('start', '<=', tomorrow_end),
			('appointment_status', 'in', ['draft', 'confirmed']),
			('patient_ids', '!=', False),
		])

		template = self.env.ref('ths_medical_base.email_template_appointment_reminder', False)
		if not template:
			_logger.warning("Appointment reminder email template not found")
			return

		for appointment in appointments:
			try:
				template.send_mail(appointment.id, force_send=True)
				appointment.message_post(
					body=_("Reminder sent to %s") % appointment.partner_ids.name,
					message_type='notification'
				)
			except Exception as e:
				_logger.error("Failed to send reminder for appointment %s: %s", appointment.id, e)

# TODO: Add appointment recurring encounter linking
# TODO: Implement appointment-encounter sync validation
# TODO: Add appointment cancellation encounter cleanup
# TODO: Implement encounter-based appointment rescheduling
# TODO: Add appointment no-show encounter marking