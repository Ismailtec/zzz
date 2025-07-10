# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
#from odoo.osv import expression
import json
import logging

_logger = logging.getLogger(__name__)


class AppointmentType(models.Model):
    _inherit = 'appointment.type'

    department_ids = fields.Many2many(
        'hr.department',
        'appointment_type_hr_department_rel',
        'appointment_type_id',
        'department_id',
        string='Departments',
        domain="[('is_medical_dep', '=', True)]",
        help="Departments whose staff and rooms can be booked for this appointment type."
    )

    practitioner_ids = fields.Many2many(
        'appointment.resource',
        string='Service Providers (from Resources)',
        compute='_compute_filtered_medical_resources',
        readonly=True,
        store=False,
        help="View of service providers (Appointment Resources with category 'practitioner') from the main 'Resources' list."
    )

    location_ids = fields.Many2many(
        'appointment.resource',
        string='Rooms (from Resources)',
        compute='_compute_filtered_medical_resources',
        readonly=True,
        store=False,
        help="View of rooms (Appointment Resources with category 'location') from the main 'Resources' list."
    )

    ths_source_department_id = fields.Many2one(
        'hr.department',
        string='Source Department',
        copy=False,
        index=True,
        ondelete='set null',
        help="Department that auto-generated this appointment type, if applicable.",
    )

    resource_domain_char = fields.Char(
        compute='_compute_resource_domain',
        string='Resource Selection Domain',
        store=False,
    )

    # Computed fields for smart buttons
    practitioner_count = fields.Integer(compute='_compute_counts', string='Service Provider Count')
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
        return super().create(vals_list)

    def write(self, vals):
        """Handle schedule type changes"""
        # Clear staff when switching to resources
        if vals.get('schedule_based_on') == 'resources':
            vals['staff_user_ids'] = [(5, 0, 0)]
        # Clear resources when switching away from resources
        elif 'schedule_based_on' in vals and vals.get('schedule_based_on') != 'resources':
            vals['resource_ids'] = [(5, 0, 0)]
            vals['department_ids'] = [(5, 0, 0)]

        res = super().write(vals)

        # Re-populate resources if departments changed
        if 'department_ids' in vals and self.filtered(lambda r: r.schedule_based_on == 'resources'):
            for record in self:
                if record.schedule_based_on == 'resources':
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
