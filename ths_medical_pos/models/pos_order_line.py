# -*- coding: utf-8 -*-
from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


class PosOrderLine(models.Model):
	_inherit = 'pos.order.line'

	# Link back to the source pending item
	ths_pending_item_id = fields.Many2one(
		'ths.pending.pos.item',
		string='Source Pending Item',
		readonly=True,
		copy=False,
		help="The pending medical item that generated this POS line."
	)

	# For medical: patient = customer (same person receiving service and paying)
	patient_ids = fields.Many2many(
		'res.partner',
		'ths_pos_order_line_patient_rel',
		'pos_order_line_id',
		'patient_id',
		string='Patients',
		domain="[('partner_type_id.is_patient', '=', True)]",
		help="Patients who received this service."
	)

	practitioner_id = fields.Many2one(
		'appointment.resource',
		string='Provider',
		related='order_id.practitioner_id',
		readonly=True,
		copy=False,
		domain="[('resource_category', '=', 'practitioner')]",
		help="Medical staff member who provided this service/item."
	)
	room_id = fields.Many2one(
		'appointment.resource',
		string='Treatment Room',
		related='order_id.room_id',
		readonly=True,
		copy=False,
		ondelete='set null',
		index=True,
		domain="[('resource_category', '=', 'location')]",
		help="Treatment room associated with this service."
	)

	# Store specific commission rate for this line
	ths_commission_pct = fields.Float(
		string='Commission %',
		digits='Discount',
		readonly=True,
		copy=False,
		help="Specific commission percentage for the provider on this line."
	)

	encounter_id = fields.Many2one(
		'ths.medical.base.encounter',
		string='Daily Encounter',
		related='order_id.encounter_id',
		store=True,
		readonly=True,
		help="Daily encounter this line belongs to"
	)

	# --- MEDICAL CONSTRAINTS ---
	@api.constrains('patient_ids', 'order_id')
	def _check_human_medical_consistency(self):
		"""
		For medical: ensure patient is consistent with order customer
		Patient should be the same as the order's customer
		"""
		for line in self:
			if line.patient_ids and line.order_id.partner_id:
				# In medical, patients should be related to the billing customer
				# This is a warning rather than hard error for flexibility
				for patient in line.patient_ids:
					if patient != line.order_id.partner_id:
						_logger.warning(
							f"POS Line {line.id}: Patient '{patient.name}' differs from order customer '{line.order_id.partner_id.name}'. "
							f"This may be normal for family members or representatives."
						)

	# --- ONCHANGE METHODS FOR MEDICAL ---
	@api.onchange('ths_pending_item_id')
	def _onchange_pending_item_sync_data(self):
		"""When pending item is linked, sync relevant data for human medical context"""
		if self.ths_pending_item_id:
			item = self.ths_pending_item_id

			# For medical: sync patient data
			if item.patient_ids:
				self.patient_ids = item.patient_ids

			# Sync commission data
			if item.commission_pct:
				self.ths_commission_pct = item.commission_pct

	# REMOVED: _onchange_patient_check_consistency method as it was commented out and had issues

	# --- HELPER METHODS FOR MEDICAL ---
	def _get_medical_context_summary(self):
		"""Get a summary of medical context for this line (medical practice)"""
		self.ensure_one()
		summary_parts = []

		if self.patient_ids:
			patient_names = ', '.join(self.patient_ids.mapped('name'))
			summary_parts.append(f"Patients: {patient_names}")

		if self.practitioner_id:
			summary_parts.append(f"Provider: {self.practitioner_id.name}")

		if self.room_id:
			summary_parts.append(f"Room: {self.room_id.name}")

		if self.ths_commission_pct:
			summary_parts.append(f"Commission: {self.ths_commission_pct}%")

		if self.ths_pending_item_id:
			summary_parts.append(f"From Encounter: {self.ths_pending_item_id.encounter_id.name}")

		return " | ".join(summary_parts) if summary_parts else "No medical context"

	# --- REPORTING METHODS ---
	def _get_commission_amount(self):
		"""Calculate commission amount for this line"""
		self.ensure_one()
		if self.ths_commission_pct and self.price_subtotal:
			return (self.price_subtotal * self.ths_commission_pct) / 100.0
		return 0.0

	def _get_patient_info_for_reporting(self):
		"""Get patient information formatted for reporting"""
		self.ensure_one()
		if not self.patient_ids:
			return "No patients assigned"

		info_parts = []
		for patient in self.patient_ids:
			patient_info = [patient.name]
			if patient.ref:
				patient_info.append(f"File: {patient.ref}")
			if hasattr(patient, 'mobile') and patient.mobile:  # FIXED: Added hasattr check
				patient_info.append(f"Mobile: {patient.mobile}")
			info_parts.append(" • ".join(patient_info))

		return " | ".join(info_parts)

	# TODO: Add integration methods for future enhancements
	def _create_commission_line(self):
		"""Create commission line for this POS line (if commission module is installed)"""
		# TODO: This would be implemented by ths_medical_commission module
		pass

	def _update_patient_medical_file(self):
		"""Update patient's medical file with this service information"""
		# TODO: Future enhancement for medical record integration
		pass

	def get_appointment_context_data(self):
		"""Get appointment context data for POS line pre-filling"""
		self.ensure_one()

		# Try to get appointment data from encounter
		if self.encounter_id and self.encounter_id.appointment_ids:
			appointment = self.encounter_id.appointment_ids[0]  # Get first appointment
			return {
				'practitioner_id': appointment.practitioner_id.id if appointment.practitioner_id else False,
				'patient_ids': appointment.patient_ids.ids if appointment.patient_ids else [],
				'appointment_id': appointment.id,
			}

		return {}

	def apply_appointment_context(self, appointment_data):
		"""Apply appointment context data to POS line"""
		self.ensure_one()

		vals = {}
		if appointment_data.get('practitioner_id'):
			# Note: practitioner_id is related field, so this might not work directly
			# This would need to be set on the order level
			pass

		if appointment_data.get('patient_ids'):
			# Set patients for this line
			vals['patient_ids'] = [(6, 0, appointment_data['patient_ids'])]

		if vals:
			self.write(vals)

# TODO: Add line-level encounter service classification
# TODO: Implement encounter-based commission calculations
# TODO: Add encounter service bundling validation
# TODO: Implement encounter inventory allocation