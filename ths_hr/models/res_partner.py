# -*- coding: utf-8 -*-

from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    """ Inherit res.partner to add a direct link back to the employee record. """
    _inherit = 'res.partner'

    # Direct link to the employee record associated with this partner
    # (Usually the partner created for the employee's home address)
    ths_employee_id = fields.Many2one(
        'hr.employee',
        string='Related Employee',
        copy=False,
        readonly=True,
        index=True,
        help="The employee record linked to this partner (often via Home Address)."
    )

    # Optional: Add constraint if needed, e.g., only one employee per partner?
    # _sql_constraints = [
    #    ('ths_employee_id_uniq', 'unique (ths_employee_id)', 'An employee can only be linked to one partner record directly!')
    # ]
    # Be careful with this constraint, consider edge cases (e.g., shared home address partner?).

    # --- Handle Employee Archive/Delete ---
    # If an employee is archived or deleted, we should clear the link on the partner
    # This requires inheriting hr.employee write/unlink, or using a related field with ondelete='set null' if possible,
    # but since the field is on res.partner, inheriting hr.employee is cleaner.

    # Note: Logic to clear this field when employee is archived/deleted
    # should be added in hr.employee write/unlink overrides if strict cleanup is needed.
    # Example (add to hr_employee.py in ths_hr):
    # def write(self, vals):
    #     if 'active' in vals and not vals['active']:
    #         # If archiving employee, clear link on partner
    #         partners = self.mapped('address_home_id').filtered(lambda p: p.ths_employee_id in self)
    #         if partners: partners.sudo().write({'ths_employee_id': False})
    #     return super(HrEmployee, self).write(vals)
    #
    # def unlink(self):
    #     # Clear link before unlinking
    #     partners = self.mapped('address_home_id').filtered(lambda p: p.ths_employee_id in self)
    #     if partners: partners.sudo().write({'ths_employee_id': False})
    #     return super(HrEmployee, self).unlink()
