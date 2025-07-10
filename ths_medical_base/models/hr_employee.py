# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    """ Inherit Employee to add computed medical staff flag, calendar flag, and resource link. """
    _inherit = 'hr.employee'

    # --- Selection Field Extension (Medical Specific) ---
    # Adds medical roles to the existing selection from hr and ths_hr
    employee_type = fields.Selection(
        selection_add=[
            ('doctor', 'Doctor'),
            ('medical_staff', 'Medical Staff'),
            ('nurse', 'Nurse'),
            ('pharmacist', 'Pharmacist'),
        ],
        # Define ondelete behavior for these specific types
        ondelete={'doctor': 'set default', 'medical_staff': 'set default',
                  'nurse': 'set default', 'pharmacist': 'set default'}
    )

    # --- Custom Fields ---
    is_medical = fields.Boolean(
        string="Medical Staff",
        compute='_compute_is_medical',
        store=True,
        readonly=False,  # Allow manual override
        inverse='_inverse_is_medical',  # Needed for manual edits
        help="Automatically checked based on the default setting for the Employee Type. Can be manually overridden."
    )
    add_to_calendar = fields.Boolean(
        string="Add to Calendar Resource",
        default=False,
        tracking=True,
        copy=False,
        help="If checked, a corresponding Resource will be created/activated for use in calendar scheduling."
    )
    appointment_resource_id = fields.Many2one(
        'appointment.resource',
        string="Appointment Resource Link",
        copy=False,
        readonly=True,
        help="Technical field linking to the appointment.resource record for this practitioner."
    )

    # Standard resource_id field is used, no need to redefine.

    # -- Compute Method --
    @api.depends('employee_type')
    def _compute_is_medical(self):
        """ Compute default medical staff flag based on employee type configuration. """
        if not self.env.context.get('compute_triggered_by_type_change', False):
            # If not explicitly triggered by a type change in write(),
            # respect existing manual edits. Only compute if the value is currently unset.
            employees_to_compute = self.filtered(lambda emp: emp.is_medical is None or not emp.id)
            if not employees_to_compute:
                return  # Avoid overwriting manual edits unless type changes
        else:
            # If triggered by type change, recompute for all records in self
            employees_to_compute = self

        if not employees_to_compute:
            return  # Nothing to compute

        # Prepare mapping for efficiency
        config_recs = self.env['ths.hr.employee.type.config'].search([('active', '=', True)])
        type_key_to_medical_flag = {rec.employee_type_key: rec.is_medical for rec in config_recs}
        _logger.debug("Employee Type Config Map: %s", type_key_to_medical_flag)  # Debug log

        for employee in employees_to_compute:
            employee_type_key = employee.employee_type
            default_is_medical = type_key_to_medical_flag.get(employee_type_key, False)
            employee.is_medical = default_is_medical
            _logger.debug(
                f"Computed is_medical for Emp {employee.id} (Type: {employee_type_key}) -> {default_is_medical}")

    def _inverse_is_medical(self):
        """ Placeholder inverse method for manually editable computed field. """
        pass

    # -- Overrides --
    @api.model_create_multi
    def create(self, vals_list):
        """ Override create to handle resource creation. """
        # is_medical will be computed automatically after creation
        employees = super(HrEmployee, self).create(vals_list)
        for employee in employees:
            if employee.add_to_calendar and employee.is_medical:
                employee.sudo()._create_or_activate_resources_for_appointment()
        return employees

    def write(self, vals):
        """ Override write to handle resource activation/deactivation and trigger recompute. """
        # Store previous state if add_to_calendar or is_medical changes
        prev_state = {}
        if 'add_to_calendar' in vals or 'is_medical' in vals:
            for employee in self:
                prev_state[employee.id] = (employee.add_to_calendar, employee.is_medical)

        res = super(HrEmployee, self).write(vals)

        for employee in self:
            current_add_to_calendar = employee.add_to_calendar
            current_is_medical = employee.is_medical

            handle_resource = False
            if 'add_to_calendar' in vals or 'is_medical' in vals:
                # If either relevant flag changed, re-evaluate
                original_add, original_medical = prev_state.get(employee.id, (None, None))
                if (original_add != current_add_to_calendar) or \
                        (original_medical != current_is_medical):
                    handle_resource = True
            elif 'name' in vals and employee.appointment_resource_id:  # If name changed, update related resources
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
            'employee_id': self.id,  # This field on resource.resource is O2M, so this writes to the M2O on hr.employee
            # This specific assignment might not be how Odoo expects to link them if resource.employee_id is O2M.
            # The link is primarily hr.employee.resource_id = M2O.
            # For resource.resource.employee_id (O2M), it would be populated by hr.employee's inverse 'resource_id'.
            # So, we don't set resource.resource.employee_id here. It's set by the inverse.
        }

    def _prepare_appointment_resource_vals(self, resource_resource_rec):
        """ Prepare values for creating an appointment.resource record """
        self.ensure_one()
        return {
            'name': self.name,
            'resource_id': resource_resource_rec.id,
            'resource_category': 'practitioner',
            'employee_id': self.id,
            'active': True,  # appointment.resource active state linked to resource_id.active
            'company_id': self.company_id.id or self.env.company.id,
            # Standard appointment.resource has company_id=False by default
            # capacity for a practitioner is typically 1
            'capacity': 1,
        }

    def _create_or_activate_resources_for_appointment(self):
        """
        Ensures a resource.resource (user type) and an appointment.resource (practitioner type)
        are created/activated and linked for this employee.
        """
        self.ensure_one()
        ResourceResource = self.env['resource.resource']
        AppointmentResource = self.env['appointment.resource']

        # 1. Ensure employee's own resource.resource exists (type 'user')
        employee_main_resource = self.resource_id
        if not employee_main_resource:
            rr_vals = self._prepare_resource_resource_vals()
            # Remove employee_id from rr_vals as it's handled by inverse from hr.employee.resource_id
            if 'employee_id' in rr_vals:  # Should not be there based on corrected _prepare_resource_resource_vals
                del rr_vals['employee_id']
            employee_main_resource = ResourceResource.sudo().create(rr_vals)
            self.sudo().write({'resource_id': employee_main_resource.id})  # This sets hr.employee.resource_id
            _logger.info(f"Created resource.resource '{employee_main_resource.name}' for employee '{self.name}'.")
        else:
            vals_to_update_rr = {}
            if not employee_main_resource.active: vals_to_update_rr['active'] = True
            if employee_main_resource.resource_type != 'user': vals_to_update_rr['resource_type'] = 'user'
            if employee_main_resource.name != self.name: vals_to_update_rr['name'] = self.name
            # Ensure the resource.resource.employee_id (O2M) correctly lists this employee via inverse.
            # This is usually automatic if hr.employee.resource_id (M2O) is set.
            if vals_to_update_rr:
                employee_main_resource.sudo().write(vals_to_update_rr)

        # 2. Ensure appointment.resource exists for this employee
        app_resource = self.appointment_resource_id
        if not app_resource:
            # Check if an appointment.resource already exists for THIS employee
            # (not just for the resource_id, as resource_id might be shared if not careful, though should be 1-1 here)
            app_resource = AppointmentResource.sudo().search([
                ('employee_id', '=', self.id),
                ('resource_category', '=', 'practitioner')
            ], limit=1)

            if not app_resource:  # Still not found, try by resource_id (less specific but a fallback)
                app_resource = AppointmentResource.sudo().search([
                    ('resource_id', '=', employee_main_resource.id),
                    ('resource_category', '=', 'practitioner')  # Ensure it's a practitioner type if found
                ], limit=1)

            if app_resource:  # Found an existing one
                self.sudo().write({'appointment_resource_id': app_resource.id})
                # Ensure it's correctly linked and configured
                update_vals_ar = {'employee_id': self.id, 'resource_id': employee_main_resource.id,
                                  'resource_category': 'practitioner'}
                if app_resource.name != self.name: update_vals_ar['name'] = self.name
                if not app_resource.active: update_vals_ar['active'] = True
                app_resource.sudo().write(update_vals_ar)

            else:  # Create a new appointment.resource
                ar_vals = self._prepare_appointment_resource_vals(employee_main_resource)
                app_resource = AppointmentResource.sudo().create(ar_vals)
                self.sudo().write({'appointment_resource_id': app_resource.id})
                _logger.info(f"Created appointment.resource '{app_resource.name}' for employee '{self.name}'.")
        else:  # app_resource (self.appointment_resource_id) exists
            vals_to_update_ar = {}
            if not app_resource.active: vals_to_update_ar['active'] = True
            if app_resource.resource_category != 'practitioner': vals_to_update_ar[
                'resource_category'] = 'practitioner'
            if app_resource.name != self.name: vals_to_update_ar['name'] = self.name
            if app_resource.employee_id != self: vals_to_update_ar['employee_id'] = self.id  # Ensure link
            if app_resource.resource_id != employee_main_resource: vals_to_update_ar[
                'resource_id'] = employee_main_resource.id  # Ensure link
            if vals_to_update_ar:
                app_resource.sudo().write(vals_to_update_ar)

        # Final check on underlying resource type for practitioner
        if app_resource and app_resource.resource_id and app_resource.resource_id.resource_type != 'user':
            app_resource.resource_id.sudo().write({'resource_type': 'user'})

    def _deactivate_resources_for_appointment(self):
        """ Deactivates linked resource.resource and appointment.resource. """
        self.ensure_one()
        if self.appointment_resource_id:
            if self.appointment_resource_id.active:
                self.appointment_resource_id.sudo().write({'active': False})  # This should deactivate resource_id too
                _logger.info(f"Deactivated appointment.resource for employee '{self.name}'.")
        # Deactivating resource_id will also deactivate appointment_resource if active is related.
        # Standard resource.mixin on appointment.resource makes its 'active' related to 'resource_id.active'.
        if self.resource_id and self.resource_id.active:
            self.resource_id.sudo().write({'active': False})
            _logger.info(f"Deactivated resource.resource for employee '{self.name}'.")
