# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, _, Command
from odoo.exceptions import ValidationError, UserError
import json

import logging

_logger = logging.getLogger(__name__)


class AppointmentResource(models.Model):
	_inherit = 'appointment.resource'

	# This field helps categorize our medical resources within the appointment.resource model
	resource_category = fields.Selection([('practitioner', 'Practitioner'), ('location', 'Location')], string='Medical Category', index=True, required=True, default='practitioner',
										 help="Category for medical scheduling, distinguishing between practitioners and locations.")

	# These assume that the underlying resource.resource record is correctly linked.
	employee_id = fields.Many2one('hr.employee', string="Related Employee", store=True, readonly=True, index=True, copy=False)
	treatment_room_id = fields.Many2one('vet.treatment.room', string="Related Room", related='resource_id.treatment_room_id', store=True, readonly=True, index=True)
	ths_department_id = fields.Many2one('hr.department', compute='_compute_ths_department_id', string='Department (Smart Link)', store=True, readonly=True)
	medical_specialties = fields.Char(string="Medical Specialties", help="Specialties for this practitioner (e.g., Surgery, Dentistry)")
	room_capacity = fields.Integer(string="Room Capacity", default=1, help="Maximum number of simultaneous appointments for this resource")
	equipment_available = fields.Text(string="Available Equipment", help="Equipment available in this treatment room")

	@api.depends('resource_category', 'employee_id.department_id', 'treatment_room_id.department_id')
	def _compute_ths_department_id(self):
		"""Compute department based on resource category and linked entities"""
		for rec in self:
			if rec.resource_category == 'practitioner' and rec.employee_id:
				rec.ths_department_id = rec.employee_id.department_id
			elif rec.resource_category == 'location' and rec.treatment_room_id:
				rec.ths_department_id = rec.treatment_room_id.department_id
			else:
				rec.ths_department_id = False

	@api.model_create_multi
	def create(self, vals_list):
		"""Enhanced create to ensure proper resource setup and validation"""
		for vals in vals_list:
			# Ensure name consistency from linked resources
			if vals.get('resource_id') and 'name' not in vals:
				resource = self.env['resource.resource'].browse(vals.get('resource_id'))
				if resource.exists():
					vals['name'] = resource.name

			# Auto-populate name from employee for practitioners
			elif vals.get('employee_id') and vals.get('resource_category') == 'practitioner' and 'name' not in vals:
				employee = self.env['hr.employee'].browse(vals.get('employee_id'))
				if employee.exists():
					vals['name'] = employee.name

		records = super(AppointmentResource, self).create(vals_list)

		for record in records:
			# Ensure correct resource_type for underlying resource.resource
			if record.resource_category == 'practitioner' and record.resource_id:
				if record.resource_id.resource_type != 'user':
					record.resource_id.sudo().write({'resource_type': 'user'})

				# Sync employee information
				if record.employee_id and record.name != record.employee_id.name:
					record.sudo().write({'name': record.employee_id.name})

			elif record.resource_category == 'location' and record.resource_id:
				if record.resource_id.resource_type != 'material':
					_logger.warning(f"Location resource {record.name} has unexpected type: {record.resource_id.resource_type}")

				# Sync room information
				if record.treatment_room_id and record.name != record.treatment_room_id.name:
					record.sudo().write({'name': record.treatment_room_id.name})

		return records

	@api.constrains('resource_category', 'employee_id', 'treatment_room_id', 'resource_id')
	def _check_medical_resource_consistency(self):
		"""Validate resource consistency and relationships"""
		for record in self:
			if record.resource_category == 'practitioner':
				if not record.employee_id:
					raise ValidationError(_("A practitioner-type Appointment Resource must be linked to an Employee."))
				if record.treatment_room_id:
					raise ValidationError(_("A practitioner-type resource should not be linked to a Treatment Room."))

				# Validate employee is medical staff
				if record.employee_id and not record.employee_id.is_medical:
					raise ValidationError(_("Employee %s must be marked as Medical Staff to be used as a practitioner resource.") % record.employee_id.name)

			elif record.resource_category == 'location':
				if not record.treatment_room_id:
					raise ValidationError(_("A location-type Appointment Resource must be linked to a Treatment Room."))
				if record.employee_id:
					raise ValidationError(_("A location-type resource should not be linked to an Employee."))

	def name_get(self):
		"""Enhanced name display with category and department info"""
		result = []
		for record in self:
			name = record.name or ''
			if record.resource_category == 'practitioner' and record.ths_department_id:
				name = f"{name} ({record.ths_department_id.name})"
			elif record.resource_category == 'location' and record.ths_department_id:
				name = f"{name} - {record.ths_department_id.name}"
			result.append((record.id, name))
		return result


class AppointmentType(models.Model):
	_inherit = 'appointment.type'

	department_ids = fields.Many2many('hr.department', 'appointment_type_hr_department_rel', 'appointment_type_id', 'department_id', string='Departments',
									  domain="[('is_medical_dep', '=', True)]", help="Departments whose staff and rooms can be booked for this appointment type.")
	practitioner_ids = fields.Many2many('appointment.resource', string='Practitioners', compute='_compute_filtered_medical_resources', readonly=True, store=False,
										help="Practitioners available for this appointment type.")
	location_ids = fields.Many2many('appointment.resource', string='Treatment Rooms', compute='_compute_filtered_medical_resources', readonly=True, store=False,
									help="Treatment rooms available for this appointment type.")
	ths_source_department_id = fields.Many2one('hr.department', string='Source Department', copy=False, index=True, ondelete='set null',
											   help="Department that auto-generated this appointment type.")
	resource_domain_char = fields.Char(compute='_compute_resource_domain', string='Resource Selection Domain', store=False)
	default_duration_hours = fields.Float(string="Default Duration (Hours)", default=0.5, help="Default appointment duration in hours")
	requires_followup = fields.Boolean(string="Requires Follow-up", default=False, help="Automatically schedule follow-up for this appointment type")
	followup_days = fields.Integer(string="Follow-up Days", default=7, help="Days after appointment to schedule follow-up")
	medical_priority = fields.Selection([('low', 'Low Priority'), ('normal', 'Normal'), ('high', 'High Priority'), ('urgent', 'Urgent')], string="Medical Priority",
										default='normal', help="Default priority level for appointments of this type")

	# Computed fields for smart buttons
	practitioner_count = fields.Integer(compute='_compute_counts', string='Practitioner Count')
	location_count = fields.Integer(compute='_compute_counts', string='Room Count')

	@api.depends('practitioner_ids', 'location_ids')
	def _compute_counts(self):
		"""Compute counts for smart buttons"""
		for record in self:
			record.practitioner_count = len(record.practitioner_ids)
			record.location_count = len(record.location_ids)

	@api.depends('resource_ids', 'resource_ids.resource_category')
	def _compute_filtered_medical_resources(self):
		"""Filter resources by category for display"""
		for record in self:
			practitioners = record.resource_ids.filtered(lambda r: r.resource_category == 'practitioner')
			locations = record.resource_ids.filtered(lambda r: r.resource_category == 'location')
			record.practitioner_ids = [(6, 0, practitioners.ids)]
			record.location_ids = [(6, 0, locations.ids)]

	@api.depends('department_ids', 'schedule_based_on', 'resource_ids')
	def _compute_resource_domain(self):
		"""Computes the domain for the 'resource_ids' field selection"""
		for record in self:
			try:
				if record.schedule_based_on != 'resources':
					record.resource_domain_char = '[["id", "=", false]]'
					continue

				# Use helper method to build domain
				domain = self._get_medical_resource_domain(record.department_ids.ids)

				# Exclude already selected resources
				if record.resource_ids:
					domain.append(['id', 'not in', record.resource_ids.ids])

				# If no resources match, show empty domain
				if not self.env['appointment.resource'].search_count(domain):
					domain = [['id', '=', False]]

				record.resource_domain_char = json.dumps(domain)

			except Exception as e:
				_logger.error("Domain computation error for appointment type %s: %s", record.id, e)
				record.resource_domain_char = '[["id", "=", false]]'

	@api.model
	def _get_medical_resource_domain(self, department_ids=None):
		"""Helper to build consistent resource domains"""
		domain = [
			('active', '=', True),
			('resource_category', 'in', ['practitioner', 'location'])
		]

		if department_ids:
			domain.extend([
				'|',
				('employee_id.department_id', 'in', department_ids),
				('treatment_room_id.department_id', 'in', department_ids)
			])

		return domain

	@api.onchange('schedule_based_on', 'department_ids')
	def _onchange_department_or_schedule_type(self):
		"""Update resources when schedule type or departments change"""
		if self.schedule_based_on == 'resources':
			# Get matching resources using helper
			domain = self._get_medical_resource_domain(self.department_ids.ids)
			resources_to_set = self.env['appointment.resource'].search(domain)

			# Set resources
			self.resource_ids = [(6, 0, resources_to_set.ids)]

			# Ensure source department is in department list
			if self.ths_source_department_id and self.ths_source_department_id not in self.department_ids:
				self.department_ids = [(4, self.ths_source_department_id.id, 0)]
		else:
			# Clear medical fields when not resource-based
			self.department_ids = [(5, 0, 0)]
			self.resource_ids = [(5, 0, 0)]

	@api.onchange('department_ids', 'resource_ids', 'schedule_based_on')
	def _onchange_resource_ids_domain(self):
		"""Return domain for resource selection"""
		if self.schedule_based_on != 'resources':
			return {'domain': {'resource_ids': [('id', '=', False)]}}

		# Build domain using helper
		base_domain = self._get_medical_resource_domain(self.department_ids.ids)

		# Exclude already selected
		if self.resource_ids:
			base_domain.append(('id', 'not in', self.resource_ids.ids))

		# Check if any resources exist
		if not self.env['appointment.resource'].search_count(base_domain):
			base_domain = [('id', '=', False)]

		return {'domain': {'resource_ids': base_domain}}

	# CRUD overrides
	@api.model_create_multi
	def create(self, vals_list):
		"""Clear staff_user_ids when creating resource-based appointments"""
		for vals in vals_list:
			if vals.get('schedule_based_on') == 'resources':
				vals['staff_user_ids'] = [(5, 0, 0)]
				if 'appointment_duration' not in vals and 'default_duration_hours' in vals:
					vals['appointment_duration'] = vals['default_duration_hours']
		return super().create(vals_list)

	def write(self, vals):
		"""Handle schedule type changes and maintain consistency"""
		# Clear staff when switching to resources
		if vals.get('schedule_based_on') == 'resources':
			vals['staff_user_ids'] = [(5, 0, 0)]
		# Clear resources when switching away from resources
		elif 'schedule_based_on' in vals and vals.get('schedule_based_on') != 'resources':
			vals['resource_ids'] = [(5, 0, 0)]
			vals['department_ids'] = [(5, 0, 0)]

		res = super().write(vals)

		# Re-populate resources if departments changed
		if 'department_ids' in vals:
			for record in self.filtered(lambda r: r.schedule_based_on == 'resources'):
				record._onchange_department_or_schedule_type()

		return res

	# Helper methods
	def action_view_practitioners(self):
		"""View practitioners for this appointment type"""
		self.ensure_one()
		return {
			'name': _('Service Providers'),
			'type': 'ir.actions.act_window',
			'res_model': 'appointment.resource',
			'view_mode': 'list,form',
			'domain': [('id', 'in', self.practitioner_ids.ids)],
			'context': {'create': False}
		}

	def action_view_locations(self):
		"""View locations/rooms for this appointment type"""
		self.ensure_one()
		return {
			'name': _('Rooms'),
			'type': 'ir.actions.act_window',
			'res_model': 'appointment.resource',
			'view_mode': 'list,form',
			'domain': [('id', 'in', self.location_ids.ids)],
			'context': {'create': False}
		}


class ResourceResource(models.Model):
	""" Inherit resource.resource to link back to Treatment Room. """
	_inherit = 'resource.resource'

	# Link back to the treatment room (set by treatment_room logic)
	# This allows finding the room from the resource if needed
	treatment_room_id = fields.Many2one('vet.treatment.room', string='Treatment Room', ondelete='set null', index=True, help="Treatment room associated with this resource.")

	# For calendar/gantt views
	calendar_start = fields.Datetime('Start Date', compute='_compute_calendar_fields')
	calendar_stop = fields.Datetime('End Date', compute='_compute_calendar_fields')
	# To link resources back to their appointment types
	appointment_type_id = fields.Many2one('appointment.type', string='Appointment Type', compute='_compute_appointment_type')

	medical_availability = fields.Selection([('available', 'Available'), ('busy', 'Busy'), ('maintenance', 'Under Maintenance'), ('offline', 'Offline')],
											string="Medical Availability", default='available', help="Current availability status for medical scheduling")

	@api.depends('employee_id', 'treatment_room_id')
	def _compute_appointment_type(self):
		"""Compute the appointment type this resource belongs to"""
		for resource in self:
			appointment_type = False
			# Check for medical practitioners
			if resource.employee_id and getattr(resource.employee_id, 'is_medical', False):
				appointment_type = self.env['appointment.type'].search([
					('resource_ids.resource_id', '=', resource.id),
					('schedule_based_on', '=', 'resources')
				], limit=1)

			# Check for treatment rooms
			elif resource.treatment_room_id:
				appointment_type = self.env['appointment.type'].search([
					('resource_ids.resource_id', '=', resource.id),
					('schedule_based_on', '=', 'resources')
				], limit=1)

			resource.appointment_type_id = appointment_type.id if appointment_type else False

	def _compute_calendar_fields(self):
		"""Compute fields for calendar/gantt views."""
		# Get working hours from resource calendar
		for resource in self:
			calendar = resource.calendar_id
			if not calendar:
				calendar = self.env.company.resource_calendar_id

			# Get calendar start/end based on company working hours
			current_date = fields.Datetime.now()
			start_dt = calendar.get_work_hours_count(current_date, current_date, compute_leaves=True)
			end_dt = calendar.get_work_hours_count(current_date, current_date, compute_leaves=True)

			resource.calendar_start = start_dt
			resource.calendar_stop = end_dt


class AppointmentCancelWizard(models.TransientModel):
	_name = 'appointment.cancel.wizard'
	_description = 'Appointment Cancellation Wizard'

	blame = fields.Selection([('patient', 'Patient'), ('clinic', 'Clinic'), ('other', 'Other')], string='Cancelled By', required=True, default='patient',
							 help="Who is responsible for this cancellation?")
	description = fields.Text(string='Cancellation Reason', required=True, help="e.g., Patient can't make it, Emergency surgery needed, etc.")
	event_ids = fields.Many2many('calendar.event', string='Appointments', default=lambda self: self.env.context.get('active_ids', []), readonly=True)
	reschedule_immediately = fields.Boolean(string='Reschedule Immediately', help="Open reschedule wizard after cancellation")
	notify_customer = fields.Boolean(string='Notify Customer', default=True, help="Send cancellation notification to customer")

	def action_confirm_cancel(self):
		"""Confirm cancellation with simplified logic"""
		self.ensure_one()
		if not self.event_ids:
			raise UserError(_("No appointments selected for cancellation."))

		for event in self.event_ids:
			if event.appointment_status in ('completed', 'paid', 'no_show'):
				raise UserError(_("Cannot cancel appointment %s: Already completed, paid, or marked as no-show.") % event.name)

		for event in self.event_ids:
			event.write({
				'appointment_status': 'cancelled',
				'cancellation_blame': self.blame,
				'cancellation_reason': self.description,
			})

			blame_display = dict(self._fields['blame'].selection)[self.blame]
			event.message_post(
				body=_("Appointment cancelled by: %s<br/>Reason: %s") % (
					blame_display,
					self.description
				),
				message_type='notification'
			)

			if self.notify_customer and event.pet_owner_id:
				# TODO: Implement customer notification
				pass

		if self.reschedule_immediately and len(self.event_ids) == 1:
			return {
				'type': 'ir.actions.act_window',
				'name': _('Reschedule Appointment'),
				'res_model': 'appointment.reschedule.wizard',
				'view_mode': 'form',
				'target': 'new',
				'context': {'default_event_id': self.event_ids[0].id}
			}

		return {'type': 'ir.actions.act_window_close'}


class AppointmentRescheduleWizard(models.TransientModel):
	_name = 'appointment.reschedule.wizard'
	_description = 'Appointment Reschedule Wizard'

	event_id = fields.Many2one('calendar.event', string='Appointment', required=True)
	new_start = fields.Datetime(string='New Start', required=True, default=fields.Datetime.now)
	new_stop = fields.Datetime(string='New Stop', required=True, default=lambda self: fields.Datetime.now() + timedelta(hours=0.5))
	new_practitioner_id = fields.Many2one('appointment.resource', string='New Practitioner', domain="[('resource_category', '=', 'practitioner')]")
	new_room_id = fields.Many2one('appointment.resource', string='New Room', domain="[('resource_category', '=', 'location')]")
	notes = fields.Text(string='Reschedule Notes')
	has_conflicts = fields.Boolean(string='Has Conflicts', compute='_compute_conflicts')
	conflict_details = fields.Text(string='Conflict Details', compute='_compute_conflicts')

	@api.model
	def default_get(self, fields_list):
		"""Pre-populate with current appointment details"""
		res = super().default_get(fields_list)
		event = self.env['calendar.event'].browse(self.env.context.get('default_event_id'))
		if event:
			res.update({
				'new_start': event.start,
				'new_stop': event.stop,
				'new_practitioner_id': event.practitioner_id.id if event.practitioner_id else False,
				'new_room_id': event.room_id.id if event.room_id else False,
			})
		return res

	@api.onchange('new_start')
	def _onchange_new_start(self):
		"""Auto-update end time when start time changes"""
		if self.new_start:
			# Default to 30 minutes duration
			self.new_stop = self.new_start + timedelta(minutes=30)

	@api.depends('new_start', 'new_stop', 'new_practitioner_id', 'new_room_id')
	def _compute_conflicts(self):
		"""Check for scheduling conflicts"""
		for wizard in self:
			conflicts = []

			if not wizard.new_start or not wizard.new_stop:
				wizard.has_conflicts = False
				wizard.conflict_details = ""
				continue

			# Check practitioner conflicts
			if wizard.new_practitioner_id:
				practitioner_conflicts = self.env['calendar.event'].search([
					('practitioner_id', '=', wizard.new_practitioner_id.id),
					('start', '<', wizard.new_stop),
					('stop', '>', wizard.new_start),
					('appointment_status', 'not in', ['cancelled', 'no_show']),
					('id', '!=', wizard.event_id.id)
				])
				if practitioner_conflicts:
					conflicts.append(f"Practitioner {wizard.new_practitioner_id.name} has {len(practitioner_conflicts)} conflicting appointments")

			# Check room conflicts
			if wizard.new_room_id:
				room_conflicts = self.env['calendar.event'].search([
					('room_id', '=', wizard.new_room_id.id),
					('start', '<', wizard.new_stop),
					('stop', '>', wizard.new_start),
					('appointment_status', 'not in', ['cancelled', 'no_show']),
					('id', '!=', wizard.event_id.id)
				])
				if room_conflicts:
					conflicts.append(f"Room {wizard.new_room_id.name} has {len(room_conflicts)} conflicting appointments")

			wizard.has_conflicts = bool(conflicts)
			wizard.conflict_details = "\n".join(conflicts) if conflicts else ""

	def action_confirm_reschedule(self):
		"""Confirm rescheduling with conflict warning"""
		self.ensure_one()

		if self.has_conflicts:
			# Could add a confirmation step here
			pass

		vals = {
			'start': self.new_start,
			'stop': self.new_stop,
		}

		if self.new_practitioner_id:
			vals['practitioner_id'] = self.new_practitioner_id.id
		if self.new_room_id:
			vals['room_id'] = self.new_room_id.id

		self.event_id.write(vals)
		self.event_id.message_post(
			body=_("Appointment rescheduled. Notes: %s") % (self.notes or 'None')
		)

		return {'type': 'ir.actions.act_window_close'}


class VetReasonVisit(models.Model):
	_name = 'vet.reason.visit'
	_description = 'Appointment Visit Reason'
	_order = 'sequence, name'

	name = fields.Char(string='Reason', required=True, translate=True)
	description = fields.Text(string='Description')
	category = fields.Selection([('routine', 'Routine Care'), ('emergency', 'Emergency'), ('followup', 'Follow-up'), ('vaccination', 'Vaccination'), ('surgery', 'Surgery'),
								 ('dental', 'Dental Care'), ('boarding', 'Boarding'), ('grooming', 'Grooming'), ('other', 'Other')], string='Category', default='routine')
	sequence = fields.Integer(string='Sequence', default=10)
	active = fields.Boolean(default=True)
	estimated_duration = fields.Float(string='Estimated Duration (Hours)', default=0.5)


class CalendarEvent(models.Model):
	""" Enhanced calendar event with comprehensive veterinary functionality. """
	_inherit = 'calendar.event'

	name = fields.Char(default="Draft Appointment")
	encounter_id = fields.Many2one('vet.encounter.header', string='Encounter', readonly=True, copy=False, index=True, ondelete='set null',
								   help="Encounter container for all services")
	pet_owner_id = fields.Many2one('res.partner', string='Pet Owner', domain="[('is_pet_owner', '=', True)]", required=True, index=True, tracking=True, store=True, readonly=False)
	patient_ids = fields.Many2many('res.partner', 'calendar_event_patient_rel', 'event_id', 'patient_id', string='Pets', index=True, tracking=True, store=True, readonly=False,
								   domain="[('is_pet', '=', True), ('pet_owner_id', '=?', pet_owner_id)]", help="Pets receiving veterinary care")
	# patient_ids_domain = fields.Char(compute='_compute_patient_domain',store=False)
	practitioner_id = fields.Many2one('appointment.resource', string='Service Provider', domain="[('resource_category', '=', 'practitioner')]", store=True, readonly=False,
									  tracking=True, help="Primary service provider for this appointment.")
	room_id = fields.Many2one('appointment.resource', string='Room', domain="[('resource_category', '=', 'location')]", store=True, readonly=False, tracking=True, copy=False,
							  help="Treatment room for this appointment.")
	practitioner_id_domain = fields.Char(compute='_compute_ar_domains')
	room_id_domain = fields.Char(compute='_compute_ar_domains')
	reason_for_visit = fields.Many2many('vet.reason.visit', string='Reason for Visit', store=True, copy=False, help="Medical reasons for this visit")
	appointment_status = fields.Selection(selection_add=[('completed', 'Completed'), ('paid', 'Paid')], ondelete={'completed': 'cascade', 'paid': 'cascade'})
	ths_check_in_time = fields.Datetime(string='Check-in Time', readonly=True, copy=False)
	ths_check_out_time = fields.Datetime(string='Check-out Time', readonly=True, copy=False)
	cancellation_blame = fields.Selection([('patient', 'Patient'), ('clinic', 'Clinic'), ('other', 'Other')], string='Cancelled By', copy=False,
										  help="Who cancelled this appointment")
	cancellation_reason = fields.Text(string='Cancellation Details', copy=False, help="Details about why the appointment was cancelled")
	is_emergency = fields.Boolean(string="Emergency", default=False, tracking=True, help="Emergency appointment requiring immediate attention")
	is_resource_based_type = fields.Boolean(compute='_compute_is_resource_based_type', store=False)
	# estimated_cost = fields.Monetary(string="Estimated Cost", currency_field='company_currency_id', help="Estimated cost for this appointment")
	actual_duration = fields.Float(string="Actual Duration (Hours)", compute='_compute_actual_duration', store=True, help="Actual appointment duration")

	# company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

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

	@api.depends('ths_check_in_time', 'ths_check_out_time')
	def _compute_actual_duration(self):
		"""Compute actual appointment duration based on check-in/out times"""
		for event in self:
			if event.ths_check_in_time and event.ths_check_out_time:
				duration = event.ths_check_out_time - event.ths_check_in_time
				event.actual_duration = duration.total_seconds() / 3600.0  # Convert to hours
			else:
				event.actual_duration = 0.0

	@api.onchange('pet_owner_id')
	def _onchange_pet_owner_populate_partners(self):
		"""When pet owner changes, populate partner_ids and handle pet selection logic"""
		if self.pet_owner_id:
			# Always populate partner_ids with pet owner
			self.partner_ids = [Command.set([self.pet_owner_id.id])]

			# Only do auto-selection if NO pets are selected
			if not self.patient_ids:
				# No pets selected - check if owner has exactly 1 pet and auto-select it
				pets = self.env['res.partner'].search([
					('is_pet', '=', True),
					('pet_owner_id', '=', self.pet_owner_id.id),
					('active', '=', True)
				])
				if len(pets) == 1:
					self.patient_ids = [Command.set([pets[0].id])]

			# If pets are already selected, clear them only if they don't belong to new owner
			elif any(p.pet_owner_id != self.pet_owner_id for p in self.patient_ids):
				self.patient_ids = [Command.clear()]

		# If pets DO belong to this owner, do nothing (keep the selection)

		else:
			# Clear partner_ids when no owner
			self.partner_ids = [Command.clear()]
			self.patient_ids = [Command.clear()]

	@api.onchange('patient_ids')
	def _onchange_patient_ids_set_owner(self):
		"""Auto-set pet_owner_id when pet is selected"""
		if self.patient_ids and not self.pet_owner_id:
			# Set owner from first pet
			first_pet = self.patient_ids[0]
			if first_pet.pet_owner_id:
				self.pet_owner_id = first_pet.pet_owner_id
				self.partner_ids = [Command.set([first_pet.pet_owner_id.id])]

	@api.onchange('user_id')
	def _onchange_user_id_preserve_partners(self):
		"""Prevent user_id changes from overriding our partner_ids"""
		if self.pet_owner_id:
			self.partner_ids = [Command.set([self.pet_owner_id.id])]

	@api.onchange('practitioner_id', 'room_id')
	def _onchange_practitioner_or_room(self):
		selected_ids = []
		if self.practitioner_id:
			selected_ids.append(self.practitioner_id.id)
		if self.room_id:
			selected_ids.append(self.room_id.id)
		self.resource_ids = [Command.set(list(set(selected_ids)))]

		# Also update appointment_resource_ids if it exists
		if hasattr(self, 'appointment_resource_ids'):
			self.appointment_resource_ids = [Command.set(selected_ids)]

	@api.model
	def default_get(self, fields_list):
		""" Handles encounter context and sets defaults from encounter """
		res = super().default_get(fields_list)

		# Get encounter_id from context
		encounter_id = self.env.context.get('default_encounter_id')
		if encounter_id:
			encounter = self.env['vet.encounter.header'].browse(encounter_id)
			if encounter.exists():
				res['encounter_id'] = encounter.id
				res['pet_owner_id'] = encounter.partner_id.id
				res['partner_ids'] = [(6, 0, [encounter.partner_id.id])]
				res['patient_ids'] = [(6, 0, encounter.patient_ids.ids)]
				res['practitioner_id'] = encounter.practitioner_id.id
				res['room_id'] = encounter.room_id.id

		# Handle other context (gantt, etc.) - existing logic
		ctx_appointment_type_id = self.env.context.get('default_appointment_type_id')
		if ctx_appointment_type_id and 'appointment_type_id' in fields_list:
			res['appointment_type_id'] = ctx_appointment_type_id

		# Gantt sets default_resource_ids
		ctx_resource_ids = self.env.context.get('default_resource_ids', [])
		if ctx_resource_ids and 'resource_ids' in fields_list:
			res['resource_ids'] = [(6, 0, ctx_resource_ids)]

			# Auto-populate practitioner/room from single resource
			if len(ctx_resource_ids) == 1:
				resource = self.env['appointment.resource'].browse(ctx_resource_ids[0]).exists()
				if resource:
					if resource.resource_category == 'practitioner' and 'practitioner_id' in fields_list:
						res['practitioner_id'] = resource.id
					elif resource.resource_category == 'location' and 'room_id' in fields_list:
						res['room_id'] = resource.id

		ctx_pet_owner_id = self.env.context.get('default_pet_owner_id')
		if ctx_pet_owner_id and 'pet_owner_id' in fields_list:
			res['pet_owner_id'] = ctx_pet_owner_id
			res['partner_ids'] = [(6, 0, [ctx_pet_owner_id])]

		ctx_practitioner_id = self.env.context.get('default_practitioner_id')
		if ctx_practitioner_id and 'practitioner_id' in fields_list:
			res['practitioner_id'] = ctx_practitioner_id

		# Room from context
		ctx_room_id = self.env.context.get('default_room_id')
		if ctx_room_id and 'room_id' in fields_list:
			res['room_id'] = ctx_room_id

		# Set default medical status
		if res.get('appointment_type_id') and 'appointment_status' in fields_list and not res.get('appointment_status'):
			res['appointment_status'] = 'request'

		return res

	# --- Encounter Creation Logic ---
	def _find_or_create_encounter(self):
		"""Find or create daily encounter for this appointment"""
		self.ensure_one()

		if not self.patient_ids:
			raise UserError("Cannot create encounter: Patients must be set on the appointment.")

		encounter_date = self.start.date() if self.start else fields.Date.context_today(self)

		encounter = self.env['vet.encounter.header']._find_or_create_daily_encounter(
			partner_id=self.pet_owner_id.id,
			patient_ids=self.patient_ids.ids,
			encounter_date=encounter_date,
			practitioner_id=self.practitioner_id if self.practitioner_id else False,
			room_id=self.room_id if self.room_id else False,
		)

		self.encounter_id = encounter.id
		return encounter

	# --- Create Override ---
	@api.model_create_multi
	def create(self, vals_list):
		""" Override create to set Sequence """
		processed_vals_list = []
		for vals in vals_list:
			vals["name"] = self.env["ir.sequence"].next_by_code("medical.appointment") or 'New Appointment'
			processed_vals_list.append(vals)

		return super().create(processed_vals_list)

	# --- Write Override ---
	def write(self, vals):
		"""Override write to trigger actions when status changes via statusbar"""
		result = super().write(vals)

		# If appointment status is being changed, trigger appropriate actions
		if 'appointment_status' in vals:
			for event in self:
				new_status = vals['appointment_status']

				# Trigger actions based on status change
				if new_status in ('attended', 'completed'):
					if not event.encounter_id:
						event._find_or_create_encounter()

					if event.encounter_id and event.encounter_id.state == 'done':
						event.encounter_id.write({'state': 'in_progress'})

		return result

	# --- Action Buttons ---
	def action_check_in(self):
		""" Set status to Checked In and record time. Trigger encounter creation. """
		now = fields.Datetime.now()
		for event in self:
			if event.appointment_status not in ('request', 'booked'):
				raise UserError(_("Appointment must be Request or Booked to Check In."))
			if event.appointment_status in ('completed', 'paid', 'cancelled', 'no_show'):
				raise UserError(_('You cannot check-in a completed, paid, or cancelled appointment.'))

			if not event.pet_owner_id:
				raise UserError(_("Cannot check in: Pet Owner must be assigned to the appointment."))

			if not event.patient_ids or not event.partner_ids:
				raise UserError(_("Cannot check in appointment without Pet Owner and Pet assigned."))

			if event.appointment_type_id and event.appointment_type_id.schedule_based_on == 'resources' and not event.practitioner_id:
				raise UserError(
					_("Cannot check in: A Service Provider must be selected for this medical appointment type."))

			event.write({
				'appointment_status': 'attended',
				'ths_check_in_time': now
			})

			event._find_or_create_encounter()

			event.message_post(
				body=_("Patient checked in at %s") % now.strftime('%Y-%m-%d %H:%M:%S'),
				message_type='notification'
			)
		return True

	def action_complete_and_bill(self):
		""" Mark appointment and encounter as completed/ready for billing. """
		now = fields.Datetime.now()
		for event in self:
			if event.appointment_status != 'attended':
				raise UserError(_("Appointment must be Checked In to mark as Completed."))
			if not event.encounter_id:
				raise UserError(_("Cannot complete: No encounter found for this appointment."))

			event.write({
				'appointment_status': 'completed',
				'ths_check_out_time': now
			})

			event.message_post(
				body=_("Appointment completed at %s") % now.strftime('%Y-%m-%d %H:%M:%S'),
				message_type='notification'
			)

		return True

	def action_cancel_appointment(self):
		"""Open wizard to select cancellation reason and set status"""
		self.ensure_one()
		return {
			'type': 'ir.actions.act_window',
			'name': _('Cancel Appointment'),
			'res_model': 'appointment.cancel.wizard',
			'view_mode': 'form',
			'target': 'new',
			'context': {'active_ids': self.ids},
		}

	def action_mark_no_show(self):
		""" Mark as No Show. """
		for event in self:
			if event.appointment_status not in ('request', 'booked'):
				raise UserError(_("Cannot mark as no-show: Invalid appointment status."))

		self.write({'appointment_status': 'no_show'})

		# Log no-show
		for event in self:
			event.message_post(
				body=_("Appointment marked as No Show"),
				message_type='notification'
			)

		return True

	# --- Action to View Encounter ---
	def action_view_encounter(self):
		"""View the daily encounter for this boarding stay"""
		self.ensure_one()
		if not self.encounter_id:
			return {}

		return {
			'name': _('Encounter'),
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
			'view_mode': 'form',
			'res_id': self.encounter_id.id,
			'target': 'current'
		}

	def action_reschedule(self):
		"""Open reschedule wizard"""
		return {
			'type': 'ir.actions.act_window',
			'name': _('Reschedule Appointment'),
			'res_model': 'appointment.reschedule.wizard',
			'view_mode': 'form',
			'target': 'new',
			'context': {'default_event_id': self.id}
		}

	@api.model
	def _cron_send_appointment_reminders(self):
		"""Send appointment reminders 24 hours before"""
		tomorrow = fields.Datetime.now() + timedelta(days=1)
		tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0)
		tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)

		appointments = self.search([
			('start', '>=', tomorrow_start),
			('start', '<=', tomorrow_end),
			('appointment_status', 'in', ['request', 'booked']),
			('pet_owner_id', '!=', False),
			('patient_ids', '!=', False),
		])

		template = self.env.ref('ths_vet_base.email_template_appointment_reminder', False)
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
# TODO: Add appointment cancellation encounter cleanup