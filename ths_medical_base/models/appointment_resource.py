# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AppointmentResource(models.Model):
    _inherit = 'appointment.resource'

    # This field helps categorize our medical resources within the appointment.resource model
    resource_category = fields.Selection([
        ('practitioner', 'Practitioner'),
        ('location', 'Location')
    ], string='Medical Category', index=True,
        help="Category for medical scheduling, distinguishing between practitioners and locations.")

    # Computed fields to easily access linked employee or room from appointment.resource
    # These assume that the underlying resource.resource record is correctly linked.
    employee_id = fields.Many2one(
        'hr.employee', string="Related Employee",
        store=True, readonly=True, index=True, copy=False
    )
    treatment_room_id = fields.Many2one(
        'ths.treatment.room', string="Related Room",
        related='resource_id.treatment_room_id', store=True, readonly=True, index=True
    )
    ths_department_id = fields.Many2one(
        'hr.department',
        compute='_compute_ths_department_id',
        string='Department (Smart Link)',
        store=True,
        readonly=True
    )

    @api.depends('resource_category', 'employee_id.department_id', 'treatment_room_id.department_id')
    def _compute_ths_department_id(self):
        for rec in self:
            if rec.resource_category == 'practitioner':
                rec.ths_department_id = rec.employee_id.department_id
            elif rec.resource_category == 'location':
                rec.ths_department_id = rec.treatment_room_id.department_id
            else:
                rec.ths_department_id = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override to ensure correct resource_type on the underlying resource.resource
        if we are creating an appointment.resource for a practitioner.
        The resource.mixin by default creates a 'material' resource.
        We also ensure the name is set correctly.
        """
        # Logic to ensure name consistency and correct resource_type for the underlying resource.resource
        for vals in vals_list:
            if vals.get('resource_id') and 'name' not in vals:
                resource = self.env['resource.resource'].browse(vals.get('resource_id'))
                if resource.exists():
                    vals['name'] = resource.name

            # If an employee_id is being passed, ensure name consistency if not already set
            elif vals.get('employee_id') and vals.get('resource_category') == 'practitioner' and 'name' not in vals:
                employee = self.env['hr.employee'].browse(vals.get('employee_id'))
                if employee.exists():
                    vals['name'] = employee.name

            # If a treatment_room_id is being passed (less direct, room object should be created first)
            # and category is location, ensure name consistency.
            # This case is usually handled by treatment_room.py setting resource_id and name.

        records = super(AppointmentResource, self).create(vals_list)

        for record in records:
            # Post-creation: Ensure resource_type of the linked resource.resource is correct.
            # The resource.mixin on appointment.resource creates a resource.resource if resource_id is not in vals.
            # Standard appointment.resource overrides _prepare_resource_values to default type to 'material'.
            if record.resource_category == 'practitioner':
                if record.resource_id:
                    if record.resource_id.resource_type != 'user':
                        record.resource_id.sudo().write({'resource_type': 'user'})
                    # If employee_id is set on appointment.resource, ensure resource_id is linked to it
                    if record.employee_id and record.resource_id.employee_id != record.employee_id:  # Standard resource.employee_id is O2M! This check isn't right.
                        # Instead, ensure resource.resource.user_id is linked if employee is a user
                        # or that hr.employee.resource_id points here.
                        # This part is complex due to resource.resource.employee_id being O2M.
                        # The hr_employee model should be responsible for setting its own hr.employee.resource_id
                        # to point to record.resource_id.
                        pass  # The link from hr.employee to resource.resource is managed on hr.employee.
                    # Sync name if needed
                    if record.employee_id and record.name != record.employee_id.name:
                        record.sudo().write({'name': record.employee_id.name})  # This updates resource.name too

            elif record.resource_category == 'location':
                if record.resource_id and record.resource_id.resource_type != 'material':
                    # This should not happen if it's for a room, as default is material.
                    _logger.warning(
                        f"AppointmentResource {record.name} for location has non-material resource type: {record.resource_id.resource_type}")
                if record.treatment_room_id and record.name != record.treatment_room_id.name:
                    record.sudo().write({'name': record.treatment_room_id.name})
        return records

    # Constraints or other logic can be added as needed
    @api.constrains('resource_category', 'employee_id', 'treatment_room_id', 'resource_id')
    def _check_medical_resource_consistency(self):
        for record in self:
            if record.resource_category == 'practitioner':
                if not record.employee_id:
                    raise ValidationError(_("A practitioner-type Appointment Resource must be linked to an Employee."))
                if record.treatment_room_id:
                    raise ValidationError(
                        _("A practitioner-type Appointment Resource should not be linked to a Treatment Room directly."))
                if record.resource_id and not record.resource_id.employee_id:  # Check if the linked hr.employee has this resource as its primary
                    # This check is hard because resource.resource.employee_id is O2M.
                    # We'd check if record.employee_id.resource_id == record.resource_id
                    if record.employee_id.resource_id != record.resource_id:
                        _logger.warning(
                            _("Practitioner Appointment Resource %s links to Employee %s, but that Employee's primary resource is %s (should be %s)."),
                            record.name, record.employee_id.name, record.employee_id.resource_id.name,
                            record.resource_id.name)


            elif record.resource_category == 'location':
                if not record.treatment_room_id:
                    raise ValidationError(_("A location-type Appointment Resource must be linked to a Treatment Room."))
                if record.employee_id:
                    raise ValidationError(
                        _("A location-type Appointment Resource should not be linked to an Employee directly."))
                if record.resource_id and record.resource_id.treatment_room_id != record.treatment_room_id:
                    _logger.warning(
                        _("Location Appointment Resource %s links to Room %s, but its underlying resource.resource links to room %s."),
                        record.name, record.treatment_room_id.name, record.resource_id.treatment_room_id.name)