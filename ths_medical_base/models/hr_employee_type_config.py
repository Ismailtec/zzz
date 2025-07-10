# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class ThsHrEmployeeTypeConfig(models.Model):
    """
    Configuration model to map standard Employee Type (selection keys)
    to the 'Is Medical' flag.
    """
    _name = 'ths.hr.employee.type.config'
    _description = 'Employee Type Medical Configuration'
    _order = 'name'

    name = fields.Char(
        string='Employee Type Label',
        required=True,
        help="User-friendly label for the employee type (e.g., 'Standard Employee', 'Part Time')."
    )
    employee_type_key = fields.Char(
        string='Employee Type Key',
        required=True,
        index=True,
        help="The technical key used in the hr.employee 'employee_type' selection field (e.g., 'employee', 'part_time'). Must match exactly."
    )
    is_medical = fields.Boolean(
        string="Is Default Medical Type?",
        default=False,
        help="Check this if employees selecting this type should be considered medical staff by default."
    )
    active = fields.Boolean(default=True)  # Allow archiving configurations

    _sql_constraints = [
        ('employee_type_key_uniq', 'unique (employee_type_key)',
         "An entry for this Employee Type Key already exists!")
    ]

    @api.constrains('employee_type_key')
    def _check_employee_type_key(self):
        """ Validate the key against the actual selection field if possible. """
        # This is tricky as the selection is extended in another module (ths_hr)
        # We'll do a basic check for empty string. A more robust check might involve
        # querying ir.model.fields, but that's complex.
        for record in self:
            if not record.employee_type_key or not record.employee_type_key.strip():
                raise ValidationError(_("The Employee Type Key cannot be empty."))
            # You could add regex checks here if needed