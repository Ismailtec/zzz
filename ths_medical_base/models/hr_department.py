# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    is_medical_dep = fields.Boolean(
        string="Medical Department",
        default=False,
        tracking=True,
        help="Check this box if this is a medical-related department (e.g., clinic, lab, pharmacy)."
    )

    @api.model_create_multi
    def create(self, vals_list):
        departments = super(HrDepartment, self).create(vals_list)
        for department in departments.filtered(lambda d: d.is_medical_dep):
            department._create_or_update_medical_appointment_type()
        return departments

    def write(self, vals):
        departments_becoming_non_medical = self.env['hr.department']
        if 'is_medical_dep' in vals and not vals['is_medical_dep']:
            departments_becoming_non_medical = self.filtered(lambda d: d.is_medical_dep)

        res = super(HrDepartment, self).write(vals)

        for department in departments_becoming_non_medical:
            if not department.is_medical_dep:
                department._deactivate_medical_appointment_type()

        if ('is_medical_dep' in vals and vals.get('is_medical_dep')) or \
                ('name' in vals and any(
                    self.filtered(lambda d: d.id == record.id).is_medical_dep for record in self)):
            for department in self.filtered(lambda d: d.is_medical_dep):
                department._create_or_update_medical_appointment_type()
        return res

    def _get_default_appointment_type_values(self):
        self.ensure_one()
        company_tz = self.company_id.resource_calendar_id.tz or \
                     self.env.company.resource_calendar_id.tz or \
                     self.env.user.tz or \
                     'UTC'
        return {
            'appointment_duration': 0.5,
            'min_schedule_hours': 0.0,
            'max_schedule_days': 0,
            'min_cancellation_hours': 0.0,
            # 'category': 'anytime',
            'is_published': False,
            'appointment_tz': company_tz,
            'product_id': False,
        }

    def _create_or_update_medical_appointment_type(self):
        self.ensure_one()
        if not self.is_medical_dep:
            return

        AppointmentType = self.env['appointment.type']
        AppointmentResource = self.env['appointment.resource']

        apt_type = AppointmentType.search([('ths_source_department_id', '=', self.id)], limit=1)
        apt_type_name = _("%s") % self.name

        # Find APPOINTMENT.RESOURCE records for practitioners in this department
        # This assumes hr_employee.appointment_resource_id is populated correctly
        practitioner_appointment_resources = AppointmentResource.search([
            ('employee_id.department_id', '=', self.id),
            ('resource_category', '=', 'practitioner'),
            ('active', '=', True)
        ])

        # Find APPOINTMENT.RESOURCE records for locations in this department
        # This assumes treatment_room.appointment_resource_id is populated correctly
        location_appointment_resources = AppointmentResource.search([
            ('treatment_room_id.department_id', '=', self.id),
            ('resource_category', '=', 'location'),
            ('active', '=', True)
        ])

        all_relevant_appointment_resources = practitioner_appointment_resources | location_appointment_resources

        common_values = {
            'name': apt_type_name,
            'ths_source_department_id': self.id,
            'department_ids': [(6, 0, [self.id])],  # Link this appointment type to the source department
            'schedule_based_on': 'resources',
            'active': True,
            'resource_ids': [(6, 0, all_relevant_appointment_resources.ids)],
        }

        if not apt_type:
            _logger.info(
                f"Creating appointment type '{apt_type_name}' for department '{self.name}'.")
            creation_values = self._get_default_appointment_type_values()
            creation_values.update(common_values)
            AppointmentType.create(creation_values)
        else:
            _logger.info(
                f"Updating appointment type for department '{self.name}'.")
            apt_type.write(common_values)

    def _deactivate_medical_appointment_type(self):
        self.ensure_one()
        apt_types = self.env['appointment.type'].search([('ths_source_department_id', '=', self.id)])
        if apt_types:
            _logger.info(
                f"Deactivating medical appointment types linked to department '{self.name}' (ID: {self.id}) as it's no longer medical.")
            apt_types.write({'active': False})
