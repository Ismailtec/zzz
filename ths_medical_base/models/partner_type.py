# -*- coding: utf-8 -*-

from odoo import models, fields


class ThsPartnerType(models.Model):
    """ Inherit Partner Type to add HR-specific flags. """
    _inherit = 'ths.partner.type'

    is_patient = fields.Boolean(
        string="Patient",
        default=False,
        help="Check if this partner type specifically represents Patients."
    )