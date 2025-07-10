# -*- coding: utf-8 -*-

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
	_inherit = 'res.partner'

	@api.model
	def _load_pos_data_domain(self, data):
		domain = super()._load_pos_data_domain(data)
		domain += [
			('active', '=', True),
			'|',
			('partner_type_id.is_customer', '=', True),
			('partner_type_id.is_patient', '=', True),
		]
		return domain

	@api.model
	def _load_pos_data_fields(self, config_id):
		base_fields = super()._load_pos_data_fields(config_id)
		return base_fields + ['partner_type_id']

	def _load_pos_data(self, data):
		result = super()._load_pos_data(data)
		result['fields'] = list(set(result['fields'] + ['partner_type_id']))
		return result

	def _trigger_pos_sync(self, operation='update'):
		"""Trigger POS sync for partner updates"""
		# IMPORTANT: Add this guard. If self is empty, there are no records to sync.
		if not self:
			return

		PosSession = self.env['pos.session']

		if self._name in PosSession.CRITICAL_MODELS:
			try:
				active_sessions = PosSession.search([('state', '=', 'opened')])

				current_data = []
				if operation != 'delete':
					fields_to_sync = self._load_pos_data_fields(False)
					current_data = self.read(fields_to_sync)
				else:
					current_data = [{'id': record_id} for record_id in self.ids]

				for session in active_sessions:
					channel = 'pos.sync.channel' #(self._cr.dbname, 'pos.session', session.id)
					self.env['bus.bus']._sendone(
						channel,
						'critical_update',
						{
							'type': 'critical_update',
							'model': self._name,
							'operation': operation,
							'records': current_data
						}
					)
					_logger.info(f"POS Sync - Data sent to bus for res.partner (action: {operation}, IDs: {self.ids})")
			except Exception as e:
				_logger.error(f"Error triggering POS sync for {self._name} (IDs: {self.ids}): {e}")

	@api.model_create_multi
	def create(self, vals_list):
		"""Override create to trigger sync"""
		records = super().create(vals_list)
		records._trigger_pos_sync('create')
		return records

	def write(self, vals):
		"""Override write to trigger sync"""
		result = super().write(vals)
		self._trigger_pos_sync('update')
		return result

	def unlink(self):
		"""Override unlink to trigger sync"""
		self._trigger_pos_sync('delete')
		return super().unlink()

# def action_view_pos_order(self):
#     """  This function returns an action that displays the pos orders from partner.  """
#     action = self.env['ir.actions.act_window']._for_xml_id('point_of_sale.action_pos_pos_form')
#     if self.is_company:
#         action['domain'] = [('partner_id.commercial_partner_id', '=', self.id)]
#     else:
#         action['domain'] = [('partner_id', '=', self.id)]
#     return action
#
# def open_commercial_entity(self):
#     return {
#         **super().open_commercial_entity(),
#         **({'target': 'new'} if self.env.context.get('target') == 'new' else {}),
#     }