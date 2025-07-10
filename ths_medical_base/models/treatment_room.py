# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ThsTreatmentRoom(models.Model):
    """ Model for defining Treatment Rooms within medical departments. """
    _name = 'ths.treatment.room'
    _description = 'Treatment Room'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence asc, name asc'

    name = fields.Char(string='Room Name/Number', required=True)
    sequence = fields.Integer(string='Sequence', default=10)  # For ordering
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        required=True,
        tracking=True,
        # Domain to show only departments marked as medical
        domain="[('is_medical_dep', '=', True)]",
        help="Select the medical department this room belongs to."
    )
    # Link to employees who can use/work in this room
    medical_staff_ids = fields.Many2many(
        'hr.employee',
        'treatment_room_staff_rel',
        'room_id', 'employee_id',
        string='Allowed Medical Staff',
        domain="[('is_medical', '=', True), ('active', '=', True), ('department_id', '=', department_id)]",
        help="Select the medical staff members who are assigned to or can use this room."
    )
    # Flag for calendar integration
    add_to_calendar_resource = fields.Boolean(
        string="Add to Calendar Resource",
        default=False,
        tracking=True,
        copy=False,
        help="If checked, a corresponding Resource (and Appointment Resource) will be created/activated for scheduling."
    )
    # Link to the resource.resource model
    resource_id = fields.Many2one(
        'resource.resource', string='Resource',
        copy=False, readonly=True, ondelete='set null',
        help="The technical resource.resource record linked to this room."
    )
    appointment_resource_id = fields.Many2one(
        'appointment.resource', string="Appointment Resource Link",
        copy=False, readonly=True,
        help="Technical field linking to the appointment.resource record for this room."
    )
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company', string='Company',
        related='department_id.company_id', store=True, readonly=True)

    # --- Constraints ---
    _sql_constraints = [
        ('name_dept_uniq', 'unique (name, department_id)', 'Room name/number must be unique within its department!'),
    ]

    # --- Overrides ---
    @api.model_create_multi
    def create(self, vals_list):
        """ Override create to handle resource creation. """
        rooms = super(ThsTreatmentRoom, self).create(vals_list)
        for room in rooms:
            if room.add_to_calendar_resource:
                room.sudo()._create_or_activate_resources_for_appointment()
        return rooms

    def write(self, vals):
        """ Override write to handle resource activation/deactivation. """
        # Store previous state if add_to_calendar_resource changes
        prev_add_to_calendar = {}
        if 'add_to_calendar_resource' in vals:
            for room in self:
                prev_add_to_calendar[room.id] = room.add_to_calendar_resource

        res = super(ThsTreatmentRoom, self).write(vals)
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
        }

    def _prepare_appointment_resource_vals(self, resource_resource_rec):
        self.ensure_one()
        return {
            'name': self.name,
            'resource_id': resource_resource_rec.id,
            'resource_category': 'location',
            'active': True,
            'company_id': self.company_id.id or self.department_id.company_id.id or self.env.company.id,
            'capacity': 1,  # Default capacity for a room is 1, can be adjusted
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
                _logger.info(f"Created appointment.resource '{app_resource.name}' for room '{self.name}'.")
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
            if vals_to_update_ar:
                app_resource.sudo().write(vals_to_update_ar)
                _logger.info(f"Updated appointment.resource '{app_resource.name}' for room '{self.name}'.")

    def _deactivate_resources_for_appointment(self):
        """ Deactivates the linked resource. """
        self.ensure_one()
        if self.appointment_resource_id and self.appointment_resource_id.active:
            self.appointment_resource_id.sudo().write({'active': False})
            _logger.info(f"Deactivated appointment.resource for room '{self.name}'.")
        if self.resource_id and self.resource_id.active:
            self.resource_id.sudo().write({'active': False})
            _logger.info(f"Deactivated resource.resource for room '{self.name}'.")

        # Ensure existing unlink method correctly handles deactivation of resources if needed

    def unlink(self):
        for room in self:
            if room.appointment_resource_id or room.resource_id:
                # Consider deactivating instead of preventing unlink, or unlinking resources if not used elsewhere
                # For now, let's just log and allow un-link. Deactivation is handled by active flag or write method.
                _logger.info(
                    f"Room '{room.name}' being unlinked had resource links. They will be unlinked by ondelete='set null' or cascade if set.")
        return super(ThsTreatmentRoom, self).unlink()
