# -*- coding: utf-8 -*-

from odoo import models


class ResPartner(models.Model):
	_inherit = 'res.partner'

	def patient_name(self, field_name='patient_ids'):
		"""Return list of dicts with id and name for M2M field used in POS."""
		return [{
			'id': patient.id,
			'name': patient.name,
		} for patient in self[field_name]]