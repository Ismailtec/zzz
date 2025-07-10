# -*- coding: utf-8 -*-

from odoo import models, fields, api
#from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ResourceResource(models.Model):
    """ Inherit resource.resource to link back to Treatment Room. """
    _inherit = 'resource.resource'

    # Link back to the treatment room (set by treatment_room logic)
    # This allows finding the room from the resource if needed
    treatment_room_id = fields.Many2one(
        'ths.treatment.room', string='Treatment Room', ondelete='set null', index=True,
        help="Treatment room associated with this resource (if resource_type is 'material')."
    )

    # For calendar/gantt views
    calendar_start = fields.Datetime('Start Date', compute='_compute_calendar_fields')
    calendar_stop = fields.Datetime('End Date', compute='_compute_calendar_fields')
    # To link resources back to their appointment types
    appointment_type_id = fields.Many2one('appointment.type', string='Appointment Type',
                                          compute='_compute_appointment_type')

    @api.depends('employee_id', 'treatment_room_id')
    def _compute_appointment_type(self):
        """Compute the appointment type this resource belongs to"""
        for resource in self:
            # Check for medical practitioners
            if resource.employee_id and resource.employee_id.is_medical:
                appointment_type = self.env['appointment.type'].search([
                    ('practitioner_ids', 'in', resource.id),
                    ('schedule_based_on', '=', 'resources')
                ], limit=1)
                resource.appointment_type_id = appointment_type.id if appointment_type else False
                continue

            # Check for treatment rooms
            if resource.treatment_room_id:
                appointment_type = self.env['appointment.type'].search([
                    ('location_ids', 'in', resource.id),
                    ('schedule_based_on', '=', 'resources')
                ], limit=1)
                resource.appointment_type_id = appointment_type.id if appointment_type else False
                continue

            # Default case
            resource.appointment_type_id = False

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
