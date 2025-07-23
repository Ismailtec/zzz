# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ThsHrEmployeeTypeConfig(models.Model):
	""" Configuration model to map standard Employee Type (selection keys) to the 'Is Medical' flag. """
	_name = 'ths.hr.employee.type.config'
	_description = 'Employee Type Medical Configuration'
	_order = 'name'

	name = fields.Char(string='Employee Type', required=True, help="Employee type (e.g., 'Standard Employee', 'Part Time').")
	employee_type_key = fields.Char(string='Employee Type Key', required=True, index=True,
									help="The key used in hr.employee 'employee_type' selection field (e.g., 'employee', 'part_time')")
	is_medical = fields.Boolean(string="Is Default Medical Type?", default=False, help="Check this if employees selecting this type should be considered medical staff by default.")
	sequence = fields.Integer(string='Sequence', default=10)
	active = fields.Boolean(default=True)
	description = fields.Text(string='Description', help="Description of this employee type and its medical relevance")
	employee_count = fields.Integer(string='Employee Count', compute='_compute_employee_count', help="Number of employees currently using this type")

	_sql_constraints = [('employee_type_key_uniq', 'unique (employee_type_key)', "An entry for this Employee Type Key already exists!")]

	def _compute_employee_count(self):
		"""Compute number of employees using this type"""
		for config in self:
			config.employee_count = self.env['hr.employee'].search_count([
				('employee_type', '=', config.employee_type_key)
			])

	@api.constrains('employee_type_key')
	def _check_employee_type_key(self):
		"""Validate employee type key format"""
		for record in self:
			if not record.employee_type_key or not record.employee_type_key.strip():
				raise ValidationError(_("The Employee Type Key cannot be empty."))

			# Check for invalid characters
			if not record.employee_type_key.replace('_', '').replace('-', '').isalnum():
				raise ValidationError(_("Employee Type Key should only contain letters, numbers, underscores, and hyphens."))

	def action_view_employees(self):
		"""View employees using this type configuration"""
		self.ensure_one()
		return {
			'name': _('Employees: %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'hr.employee',
			'view_mode': 'list,form',
			'domain': [('employee_type', '=', self.employee_type_key)],
			'context': {'default_employee_type': self.employee_type_key}
		}


class HrDepartment(models.Model):
	_inherit = 'hr.department'

	is_medical_dep = fields.Boolean(string="Medical Department", default=False, tracking=True, help="Activate this if this is a Vet/Medical department (e.g., vet, lab, pharmacy).")
	medical_specialties = fields.Text(string="Medical Specialties", help="List of medical specialties offered by this department")
	department_head_medical = fields.Many2one('hr.employee', string="Medical Department Head", domain="[('department_id', '=', id), ('is_medical', '=', True)]",
											  help="Medical staff member who heads this department")

	medical_staff_count = fields.Integer(string='Medical Staff Count', compute='_compute_medical_stats', help="Number of medical staff in this department")
	treatment_room_count = fields.Integer(string='Treatment Rooms Count', compute='_compute_medical_stats', help="Number of treatment rooms in this department")
	appointment_type_count = fields.Integer(string='Appointment Types Count', compute='_compute_medical_stats', help="Number of appointment types for this department")

	@api.depends('member_ids.is_medical')
	def _compute_medical_stats(self):
		"""Compute medical-related statistics for the department"""
		for department in self:
			if department.is_medical_dep:
				# Count medical staff
				department.medical_staff_count = len(department.member_ids.filtered('is_medical'))

				# Count treatment rooms
				department.treatment_room_count = self.env['vet.treatment.room'].search_count([
					('department_id', '=', department.id)
				])

				# Count appointment types
				department.appointment_type_count = self.env['appointment.type'].search_count([
					('department_ids', 'in', department.id)
				])
			else:
				department.medical_staff_count = 0
				department.treatment_room_count = 0
				department.appointment_type_count = 0

	@api.model_create_multi
	def create(self, vals_list):
		"""Create department and handle medical appointment type creation"""
		departments = super(HrDepartment, self).create(vals_list)
		for department in departments.filtered(lambda d: d.is_medical_dep):
			department._create_or_update_medical_appointment_type()
		return departments

	def write(self, vals):
		"""Handle medical status changes and appointment type updates"""
		departments_becoming_non_medical = self.env['hr.department']
		if 'is_medical_dep' in vals and not vals['is_medical_dep']:
			departments_becoming_non_medical = self.filtered(lambda d: d.is_medical_dep)

		res = super(HrDepartment, self).write(vals)

		# Handle departments becoming non-medical
		for department in departments_becoming_non_medical:
			if not department.is_medical_dep:
				department._deactivate_medical_appointment_type()

		# Handle departments becoming medical or having name changes
		if ('is_medical_dep' in vals and vals.get('is_medical_dep')) or \
				('name' in vals and any(
					self.filtered(lambda d: d.id == record.id).is_medical_dep for record in self)):
			for department in self.filtered(lambda d: d.is_medical_dep):
				department._create_or_update_medical_appointment_type()

		return res

	def _get_default_appointment_type_values(self):
		"""Get default values for creating appointment types"""
		self.ensure_one()
		company_tz = self.company_id.resource_calendar_id.tz or self.env.company.resource_calendar_id.tz or self.env.user.tz or 'UTC'
		return {
			'appointment_duration': 0.5,
			'min_schedule_hours': 0.0,
			'max_schedule_days': 0,
			'min_cancellation_hours': 0.0,
			# 'category': 'anytime',
			'is_published': False,
			'appointment_tz': company_tz,
			'product_id': False,
			'assign_method': 'time_resource',
		}

	def _create_or_update_medical_appointment_type(self):
		self.ensure_one()
		if not self.is_medical_dep:
			return

		AppointmentType = self.env['appointment.type']
		AppointmentResource = self.env['appointment.resource']

		apt_type = AppointmentType.search([('ths_source_department_id', '=', self.id)], limit=1)
		apt_type_name = _("%s") % self.name

		# This assumes hr_employee.appointment_resource_id is populated correctly
		practitioner_resources = AppointmentResource.search([
			('employee_id.department_id', '=', self.id),
			('resource_category', '=', 'practitioner'),
			('active', '=', True)
		])

		# This assumes treatment_room.appointment_resource_id is populated correctly
		location_resources = AppointmentResource.search([
			('treatment_room_id.department_id', '=', self.id),
			('resource_category', '=', 'location'),
			('active', '=', True)
		])

		all_resources = practitioner_resources | location_resources

		common_values = {
			'name': apt_type_name,
			'ths_source_department_id': self.id,
			'department_ids': [(6, 0, [self.id])],  # Link this appointment type to the source department
			'schedule_based_on': 'resources',
			'active': True,
			'resource_ids': [(6, 0, all_resources.ids)],
		}

		if not apt_type:
			# _logger.info(
			# 	f"Creating appointment type '{apt_type_name}' for department '{self.name}'.")
			creation_values = self._get_default_appointment_type_values()
			creation_values.update(common_values)
			AppointmentType.create(creation_values)
		else:
			# _logger.info(
			# 	f"Updating appointment type for department '{self.name}'.")
			apt_type.write(common_values)

	def _deactivate_medical_appointment_type(self):
		"""Deactivate appointment types when department becomes non-medical"""
		self.ensure_one()
		apt_types = self.env['appointment.type'].search([('ths_source_department_id', '=', self.id)])
		if apt_types:
			# _logger.info(
			# 	f"Deactivating medical appointment types linked to department '{self.name}' (ID: {self.id}) as it's no longer medical.")
			apt_types.write({'active': False})

	def action_view_medical_staff(self):
		"""View medical staff in this department"""
		self.ensure_one()
		return {
			'name': _('Medical Staff - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'hr.employee',
			'view_mode': 'list,form',
			'domain': [('department_id', '=', self.id), ('is_medical', '=', True)],
			'context': {'default_department_id': self.id, 'default_is_medical': True}
		}

	def action_view_treatment_rooms(self):
		"""View treatment rooms in this department"""
		self.ensure_one()
		return {
			'name': _('Treatment Rooms - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'vet.treatment.room',
			'view_mode': 'list,form',
			'domain': [('department_id', '=', self.id)],
			'context': {'default_department_id': self.id}
		}

	def action_view_appointment_types(self):
		"""View appointment types for this department"""
		self.ensure_one()
		return {
			'name': _('Appointment Types - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'appointment.type',
			'view_mode': 'list,form',
			'domain': [('department_ids', 'in', self.id)],
			'context': {'default_department_ids': [(6, 0, [self.id])]}
		}


class VetTreatmentRoom(models.Model):
	""" Model for defining Treatment Rooms within medical departments. """
	_name = 'vet.treatment.room'
	_description = 'Treatment Room'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_order = 'sequence asc, name asc'

	name = fields.Char(string='Room Name/Number', required=True)
	sequence = fields.Integer(string='Sequence', default=10)
	department_id = fields.Many2one('hr.department', string='Department', required=True, tracking=True, domain="[('is_medical_dep', '=', True)]",
									help="Select the medical department this room belongs to.")
	# Link to employees who can use/work in this room
	medical_staff_ids = fields.Many2many('hr.employee', 'treatment_room_staff_rel', 'room_id', 'employee_id', string='Allowed Medical Staff',
										 domain="[('is_medical', '=', True), ('active', '=', True), ('department_id', '=', department_id)]",
										 help="Medical staff assigned to this room.")
	# Flag for calendar integration
	add_to_calendar_resource = fields.Boolean(string="Add to Calendar", default=False, tracking=True, copy=False, help="Create appointment resource for scheduling.")
	# Link to the resource.resource model
	resource_id = fields.Many2one('resource.resource', string='Resource', copy=False, readonly=True, ondelete='set null', help="Technical resource record for scheduling.")
	appointment_resource_id = fields.Many2one('appointment.resource', string="Appointment Resource", copy=False, readonly=True, help="Appointment resource for this room.")
	room_type = fields.Selection([('consultation', 'Consultation Room'), ('surgery', 'Surgery Room'), ('treatment', 'Treatment Room'), ('examination', 'Examination Room'),
								  ('isolation', 'Isolation Room'), ('recovery', 'Recovery Room'), ('diagnostic', 'Diagnostic Room'), ('dental', 'Dental Room'), ('other', 'Other')],
								 string='Room Type', default='consultation', tracking=True, help="Type of medical procedures this room is designed for")

	max_capacity = fields.Integer(string='Maximum Capacity', default=1, help="Maximum number of patients that can be treated simultaneously")
	equipment_available = fields.Text(string='Available Equipment', help="List of medical equipment available in this room")
	room_size = fields.Float(string='Room Size (m²)', help="Room size in square meters")
	active = fields.Boolean(string='Active', default=True)
	maintenance_mode = fields.Boolean(string='Under Maintenance', default=False, tracking=True, help="Mark room as unavailable due to maintenance")
	notes = fields.Text(string='Notes', help="Internal notes about this room")
	company_id = fields.Many2one('res.company', string='Company', related='department_id.company_id', store=True, readonly=True)
	appointment_count = fields.Integer(string='Appointment Count', compute='_compute_appointment_count', help="Number of appointments scheduled in this room")

	_sql_constraints = [('name_dept_uniq', 'unique (name, department_id)', 'Room name/number must be unique within its department!'),
						('max_capacity_positive', 'CHECK(max_capacity > 0)', 'Maximum capacity must be positive!'), ]

	def _compute_appointment_count(self):
		"""Compute number of appointments for this room"""
		for room in self:
			if room.appointment_resource_id:
				room.appointment_count = self.env['calendar.event'].search_count([
					('room_id', '=', room.appointment_resource_id.id)
				])
			else:
				room.appointment_count = 0

	@api.model_create_multi
	def create(self, vals_list):
		"""Create room and handle resource creation"""
		rooms = super(VetTreatmentRoom, self).create(vals_list)
		for room in rooms:
			if room.add_to_calendar_resource:
				room.sudo()._create_or_activate_resources_for_appointment()
		return rooms

	def write(self, vals):
		"""Handle resource changes when room properties change"""
		prev_add_to_calendar = {}
		if 'add_to_calendar_resource' in vals:
			for room in self:
				prev_add_to_calendar[room.id] = room.add_to_calendar_resource

		res = super(VetTreatmentRoom, self).write(vals)

		for room in self:
			handle_resource = False

			if 'add_to_calendar_resource' in vals:
				original_add = prev_add_to_calendar.get(room.id, None)
				if original_add != room.add_to_calendar_resource:
					handle_resource = True

			elif 'name' in vals and room.appointment_resource_id:  # If name changed, update related resources
				handle_resource = True

			if handle_resource:
				if room.add_to_calendar_resource:
					room.sudo()._create_or_activate_resources_for_appointment()
				else:
					room.sudo()._deactivate_resources_for_appointment()

		return res

	# --- Resource Handling Methods ---
	def _prepare_resource_resource_vals(self):
		self.ensure_one()
		return {
			'name': self.name,
			'resource_type': 'material',  # Rooms are material resources
			'company_id': self.company_id.id or self.department_id.company_id.id or self.env.company.id,
			'active': True,
			'treatment_room_id': self.id,  # Link back to this room
			'calendar_id': self.department_id.company_id.resource_calendar_id.id or self.env.company.resource_calendar_id.id,
		}

	def _prepare_appointment_resource_vals(self, resource_resource_rec):
		self.ensure_one()
		return {
			'name': self.name,
			'resource_id': resource_resource_rec.id,
			'resource_category': 'location',
			'active': True,
			'company_id': self.company_id.id or self.department_id.company_id.id or self.env.company.id,
			'capacity': self.max_capacity,
			'treatment_room_id': self.id,
		}

	def _create_or_activate_resources_for_appointment(self):
		""" Creates a new resource or activates an existing inactive one. """
		self.ensure_one()
		ResourceResource = self.env['resource.resource']
		AppointmentResource = self.env['appointment.resource']

		# 1. Ensure resource.resource exists
		room_resource = self.resource_id
		if not room_resource:
			rr_vals = self._prepare_resource_resource_vals()
			room_resource = ResourceResource.sudo().create(rr_vals)
			self.sudo().write({'resource_id': room_resource.id})
			_logger.info(f"Created resource.resource '{room_resource.name}' for room '{self.name}'.")
		else:
			vals_to_update_rr = {}
			if not room_resource.active:
				vals_to_update_rr['active'] = True
			if room_resource.resource_type != 'material':  # Ensure correct type
				vals_to_update_rr['resource_type'] = 'material'
			if room_resource.name != self.name:
				vals_to_update_rr['name'] = self.name
			if vals_to_update_rr:
				room_resource.sudo().write(vals_to_update_rr)
				_logger.info(f"Updated resource.resource '{room_resource.name}' for room '{self.name}'.")

		# 2. Ensure appointment.resource exists
		app_resource = self.appointment_resource_id
		if not app_resource:
			app_resource = AppointmentResource.sudo().search([('resource_id', '=', room_resource.id)], limit=1)
			if app_resource:
				self.sudo().write({'appointment_resource_id': app_resource.id})
			else:
				ar_vals = self._prepare_appointment_resource_vals(room_resource)
				app_resource = AppointmentResource.sudo().create(ar_vals)
				self.sudo().write({'appointment_resource_id': app_resource.id})
		# _logger.info(f"Created appointment.resource '{app_resource.name}' for room '{self.name}'.")
		else:
			vals_to_update_ar = {}
			if not app_resource.active:
				vals_to_update_ar['active'] = True
			if app_resource.resource_category != 'location':
				vals_to_update_ar['resource_category'] = 'location'
			if app_resource.name != self.name:
				vals_to_update_ar['name'] = self.name
			if app_resource.resource_id != room_resource:
				vals_to_update_ar['resource_id'] = room_resource.id
				if app_resource.capacity != self.max_capacity:
					vals_to_update_ar['capacity'] = self.max_capacity
			if vals_to_update_ar:
				app_resource.sudo().write(vals_to_update_ar)
		# _logger.info(f"Updated appointment.resource '{app_resource.name}' for room '{self.name}'.")

	def _deactivate_resources_for_appointment(self):
		""" Deactivates the linked resource. """
		self.ensure_one()
		if self.appointment_resource_id and self.appointment_resource_id.active:
			self.appointment_resource_id.sudo().write({'active': False})
		# _logger.info(f"Deactivated appointment.resource for room '{self.name}'.")
		if self.resource_id and self.resource_id.active:
			self.resource_id.sudo().write({'active': False})

	# _logger.info(f"Deactivated resource.resource for room '{self.name}'.")

	def action_view_appointments(self):
		"""View appointments scheduled in this room"""
		self.ensure_one()
		if not self.appointment_resource_id:
			return {}

		return {
			'name': _('Appointments - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'calendar.event',
			'view_mode': 'calendar,list,form',
			'domain': [('room_id', '=', self.appointment_resource_id.id)],
			'context': {'default_room_id': self.appointment_resource_id.id}
		}

	def action_toggle_maintenance(self):
		"""Toggle maintenance mode"""
		for room in self:
			room.maintenance_mode = not room.maintenance_mode
			if room.maintenance_mode:
				room.message_post(body=_("Room marked as under maintenance"))
			else:
				room.message_post(body=_("Room maintenance completed"))

	def unlink(self):
		"""Handle resource cleanup on deletion"""
		for room in self:
			if room.appointment_resource_id:
				_logger.info(f"Room '{room.name}' being deleted had appointment resource")
			if room.resource_id:
				_logger.info(f"Room '{room.name}' being deleted had resource")
		return super(VetTreatmentRoom, self).unlink()


class HrEmployee(models.Model):
	""" Inherit Employee to add computed medical staff flag, calendar flag, and resource link. """
	_inherit = 'hr.employee'

	# --- Selection Field Extension (Medical Specific) ---
	# Adds medical roles to the existing selection from hr and ths_hr
	employee_type = fields.Selection(selection_add=[('doctor', 'Doctor'), ('medical_staff', 'Medical Staff'), ('nurse', 'Nurse'), ('technician', 'Medical Technician'),
													('pharmacist', 'Pharmacist')],
									 ondelete={'doctor': 'set default', 'medical_staff': 'set default', 'nurse': 'set default', 'pharmacist': 'set default',
											   'technician': 'set default'})

	# --- Custom Fields ---
	is_medical = fields.Boolean(string="Medical Staff", compute='_compute_is_medical', store=True, readonly=False, inverse='_inverse_is_medical',
								help="Automatically checked based on the default setting for the Employee Type. Can be manually overridden.")
	add_to_calendar = fields.Boolean(string="Add to Calendar", default=False, tracking=True, copy=False, help="Create appointment resource for scheduling.")
	appointment_resource_id = fields.Many2one('appointment.resource', string="Appointment Resource", copy=False, readonly=True,
											  help="Appointment resource for this practitioner.")
	medical_specialties = fields.Text(string="Medical Specialties", help="Areas of medical specialization for this practitioner")
	medical_license_number = fields.Char(string="Medical License Number", help="Professional medical license number")
	medical_license_expiry = fields.Date(string="License Expiry Date", help="Expiry date of medical license")
	preferred_treatment_rooms = fields.Many2many('vet.treatment.room', 'employee_preferred_room_rel', 'employee_id', 'room_id',
												 string='Preferred Treatment Rooms', domain="[('department_id', '=', department_id), ('active', '=', True)]",
												 help="Treatment rooms this employee prefers to work in")
	appointment_count = fields.Integer(string='Appointment Count', compute='_compute_appointment_count', help="Number of appointments assigned to this practitioner")
	patient_count = fields.Integer(string='Patient Count', compute='_compute_patient_count', help="Number of unique patients treated by this practitioner")

	# -- Compute Method --
	@api.depends('employee_type')
	def _compute_is_medical(self):
		""" Compute default medical staff flag based on employee type configuration. """
		if not self.env.context.get('compute_triggered_by_type_change', False):
			employees_to_compute = self.filtered(lambda emp: not emp.id or emp.is_medical is None)
		else:
			employees_to_compute = self

		if not employees_to_compute:
			return

		# Prepare mapping for efficiency
		config_recs = self.env['ths.hr.employee.type.config'].search([('active', '=', True)])
		type_key_to_medical_flag = {rec.employee_type_key: rec.is_medical for rec in config_recs}
		# _logger.debug("Employee Type Config Map: %s", type_key_to_medical_flag)

		for employee in employees_to_compute:
			employee_type_key = employee.employee_type
			default_is_medical = type_key_to_medical_flag.get(employee_type_key, False)
			employee.is_medical = default_is_medical

	# _logger.debug(
	# 	f"Computed is_medical for Emp {employee.id} (Type: {employee_type_key}) -> {default_is_medical}")

	def _inverse_is_medical(self):
		""" Placeholder inverse method for manually editable computed field. """
		pass

	def _compute_appointment_count(self):
		"""Compute number of appointments for this practitioner"""
		for employee in self:
			if employee.appointment_resource_id:
				employee.appointment_count = self.env['calendar.event'].search_count([
					('practitioner_id', '=', employee.appointment_resource_id.id)
				])
			else:
				employee.appointment_count = 0

	def _compute_patient_count(self):
		"""Compute number of unique patients treated"""
		for employee in self:
			if employee.appointment_resource_id:
				appointments = self.env['calendar.event'].search([
					('practitioner_id', '=', employee.appointment_resource_id.id),
					('appointment_status', 'in', ['attended', 'completed', 'paid'])
				])
				unique_patients = set()
				for appointment in appointments:
					unique_patients.update(appointment.patient_ids.ids)
				employee.patient_count = len(unique_patients)
			else:
				employee.patient_count = 0

	# -- Overrides --
	@api.model_create_multi
	def create(self, vals_list):
		"""Handle resource creation on employee creation"""
		# is_medical will be computed automatically after creation
		employees = super(HrEmployee, self).create(vals_list)
		for employee in employees:
			if employee.add_to_calendar and employee.is_medical:
				employee.sudo()._create_or_activate_resources_for_appointment()
		return employees

	def write(self, vals):
		"""Handle resource changes when employee properties change"""
		# Store previous state if add_to_calendar or is_medical changes
		prev_state = {}
		if 'add_to_calendar' in vals or 'is_medical' in vals or 'employee_type' in vals:
			for employee in self:
				prev_state[employee.id] = (employee.add_to_calendar, employee.is_medical)

		# Trigger recompute if employee_type changed
		if 'employee_type' in vals:
			self = self.with_context(compute_triggered_by_type_change=True)

		res = super(HrEmployee, self).write(vals)

		for employee in self:
			current_add_to_calendar = employee.add_to_calendar
			current_is_medical = employee.is_medical

			handle_resource = False

			if 'add_to_calendar' in vals or 'is_medical' in vals or 'employee_type' in vals:
				original_add, original_medical = prev_state.get(employee.id, (None, None))
				if (original_add != current_add_to_calendar) or (original_medical != current_is_medical):
					handle_resource = True

			# Check if name changed and resource exists
			elif 'name' in vals and employee.appointment_resource_id:
				handle_resource = True

			if handle_resource:
				if current_add_to_calendar and current_is_medical:
					employee.sudo()._create_or_activate_resources_for_appointment()
				else:
					employee.sudo()._deactivate_resources_for_appointment()

			return res

	# -- Resource Handling Methods --
	def _prepare_resource_resource_vals(self):
		""" Prepare values for creating a resource.resource record. """
		self.ensure_one()
		return {
			'name': self.name,
			'resource_type': 'user',
			'user_id': self.user_id.id if self.user_id else None,
			'company_id': self.company_id.id or self.env.company.id,
			'active': True,
			'calendar_id': self.resource_calendar_id.id if self.resource_calendar_id else None,
			'employee_id': self.id,  # This field on resource.resource is O2M, so this writes to the M2O on hr.employee
		}

	def _prepare_appointment_resource_vals(self, resource_resource_rec):
		""" Prepare values for creating an appointment.resource record """
		self.ensure_one()
		return {
			'name': self.name,
			'resource_id': resource_resource_rec.id,
			'resource_category': 'practitioner',
			'employee_id': self.id,
			'active': True,
			'company_id': self.company_id.id or self.env.company.id,
			'capacity': 1,
			'medical_specialties': self.medical_specialties,
		}

	def _create_or_activate_resources_for_appointment(self):
		""" Ensures a resource.resource (user type) and an appointment.resource (practitioner type) are created/activated and linked for this employee. """
		self.ensure_one()
		ResourceResource = self.env['resource.resource']
		AppointmentResource = self.env['appointment.resource']

		# 1. Ensure employee's own resource.resource exists (type 'user')
		employee_main_resource = self.resource_id
		if not employee_main_resource:
			rr_vals = self._prepare_resource_resource_vals()
			# Remove employee_id from rr_vals as it's handled by inverse from hr.employee.resource_id
			if 'employee_id' in rr_vals:
				del rr_vals['employee_id']
			employee_main_resource = ResourceResource.sudo().create(rr_vals)
			self.sudo().write({'resource_id': employee_main_resource.id})
		# _logger.info(f"Created resource.resource '{employee_main_resource.name}' for employee '{self.name}'.")
		else:
			vals_to_update_rr = {}
			if not employee_main_resource.active: vals_to_update_rr['active'] = True
			if employee_main_resource.resource_type != 'user': vals_to_update_rr['resource_type'] = 'user'
			if employee_main_resource.name != self.name: vals_to_update_rr['name'] = self.name
			if vals_to_update_rr:
				employee_main_resource.sudo().write(vals_to_update_rr)

		# 2. Ensure appointment.resource exists for this employee
		app_resource = self.appointment_resource_id
		if not app_resource:
			# Check if an appointment.resource already exists for THIS employee
			app_resource = AppointmentResource.sudo().search([
				('employee_id', '=', self.id),
				('resource_category', '=', 'practitioner')
			], limit=1)

			if not app_resource:
				app_resource = AppointmentResource.sudo().search([
					('resource_id', '=', employee_main_resource.id),
					('resource_category', '=', 'practitioner')
				], limit=1)

			if app_resource:  # Found an existing one
				self.sudo().write({'appointment_resource_id': app_resource.id})
				update_vals_ar = {'employee_id': self.id, 'resource_id': employee_main_resource.id, 'resource_category': 'practitioner'}
				if app_resource.name != self.name: update_vals_ar['name'] = self.name
				if not app_resource.active: update_vals_ar['active'] = True
				app_resource.sudo().write(update_vals_ar)

			else:  # Create a new appointment.resource
				ar_vals = self._prepare_appointment_resource_vals(employee_main_resource)
				app_resource = AppointmentResource.sudo().create(ar_vals)
				self.sudo().write({'appointment_resource_id': app_resource.id})
		# _logger.info(f"Created appointment.resource '{app_resource.name}' for employee '{self.name}'.")
		else:
			vals_to_update_ar = {}
			if not app_resource.active: vals_to_update_ar['active'] = True
			if app_resource.resource_category != 'practitioner': vals_to_update_ar['resource_category'] = 'practitioner'
			if app_resource.name != self.name: vals_to_update_ar['name'] = self.name
			if app_resource.employee_id != self: vals_to_update_ar['employee_id'] = self.id
			if app_resource.resource_id != employee_main_resource: vals_to_update_ar['resource_id'] = employee_main_resource.id
			if vals_to_update_ar: app_resource.sudo().write(vals_to_update_ar)

		# Final check on underlying resource type for practitioner
		if app_resource and app_resource.resource_id and app_resource.resource_id.resource_type != 'user':
			app_resource.resource_id.sudo().write({'resource_type': 'user'})

	def _deactivate_resources_for_appointment(self):
		""" Deactivates linked resource.resource and appointment.resource. """
		self.ensure_one()
		if self.appointment_resource_id and self.appointment_resource_id.active:
			self.appointment_resource_id.sudo().write({'active': False})  # This should deactivate resource_id too
		# _logger.info(f"Deactivated appointment.resource for employee '{self.name}'.")
		# Deactivating resource_id will also deactivate appointment_resource if active is related.
		# Standard resource.mixin on appointment.resource makes its 'active' related to 'resource_id.active'.
		# if self.resource_id and self.resource_id.active:
		# 	self.resource_id.sudo().write({'active': False})
		# _logger.info(f"Deactivated resource.resource for employee '{self.name}'.")

	def action_view_appointments(self):
		"""View appointments assigned to this practitioner"""
		self.ensure_one()
		if not self.appointment_resource_id:
			return {}

		return {
			'name': _('Appointments - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'calendar.event',
			'view_mode': 'calendar,list,form',
			'domain': [('practitioner_id', '=', self.appointment_resource_id.id)],
			'context': {'default_practitioner_id': self.appointment_resource_id.id}
		}

	def action_view_patients(self):
		"""View patients treated by this practitioner"""
		self.ensure_one()
		if not self.appointment_resource_id:
			return {}

		# Get unique patients from appointments
		appointments = self.env['calendar.event'].search([
			('practitioner_id', '=', self.appointment_resource_id.id),
			('appointment_status', 'in', ['attended', 'completed', 'paid'])
		])
		patient_ids = set()
		for appointment in appointments:
			patient_ids.update(appointment.patient_ids.ids)

		return {
			'name': _('Patients - %s') % self.name,
			'type': 'ir.actions.act_window',
			'res_model': 'res.partner',
			'view_mode': 'list,form',
			'domain': [('id', 'in', list(patient_ids))],
		}

	@api.constrains('medical_license_expiry')
	def _check_license_expiry(self):
		"""Warn about expiring medical licenses"""
		for employee in self:
			if (employee.is_medical and employee.medical_license_expiry and
					employee.medical_license_expiry < fields.Date.today()):
				# Could create activity or send notification
				_logger.warning(f"Medical license expired for employee {employee.name}")

# TODO: Add medical shift scheduling integration
# TODO: Implement practitioner availability management
# TODO: Add medical license tracking
# TODO: Integrate with payroll for medical staff bonuses