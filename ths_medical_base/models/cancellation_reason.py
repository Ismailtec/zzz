# -*- coding: utf-8 -*-
from odoo import models, fields


class ThsMedicalCancellationReason(models.Model):
    _name = 'ths.medical.cancellation.reason'
    _description = 'Appointment Cancellation Reason'
    _order = 'name'

    name = fields.Char(string='Reason', required=True, translate=True)
    description = fields.Text(string='Description')
    blame = fields.Selection([
        ('patient', 'Patient'),
        ('clinic', 'Clinic'),
        ('other', 'Other'),
    ], string='Blame', default='patient')
    active = fields.Boolean(default=True)
