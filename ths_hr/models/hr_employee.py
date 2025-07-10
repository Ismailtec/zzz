# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import re

# Import the external translate library with error handling
try:
	from translate import Translator
except ImportError:
	# This will stop Odoo from loading if the library is missing
	raise ImportError(
		'This module needs translate to automatically write word in arabic. '
		'Please install translate on your system. (sudo pip3 install translate)')

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
	_inherit = ['hr.employee']

	# --- Added Arabic Name Field ---
	name_ar = fields.Char("Name (Arabic)", store=True, copy=True)

	# --- Selection Field Extension ---
	employee_type = fields.Selection(
		selection_add=[
			('part_time', 'Part Time'),
			('external_employee', 'External Employee')
		],
		ondelete={'part_time': 'set default', 'external_employee': 'set default'}
	)
	gender = fields.Selection([
		('male', 'Male'),
		('female', 'Female'),
	], string='Gender')

	# -- Core Employee Fields --
	ths_dob = fields.Date(string='Date of Birth')
	ths_gov_id = fields.Char(string='ID Number', help="National Identifier (ID)", readonly=False, copy=False,
							 store=True)

	# -- Custom Fields --
	ths_inv_loss_loc_id = fields.Many2one(
		'stock.location', string='Inv. Loss Location', copy=False, readonly=True,
		help="Inventory loss location specifically for this employee."
	)
	ths_analytic_acc_id = fields.Many2one(
		'account.analytic.account', string='Analytic Account', copy=False, readonly=True,
		help="Analytic account associated with this employee."
	)

	# -- Static Methods --
	@staticmethod
	def _sanitize_name(name):
		""" Sanitize employee name for use in related records. """
		name = (name or '').strip()
		name = re.sub(r'[\\/:*?"<>|]+', '-', name)
		return name or 'unnamed-employee'

	# --- Onchange for Translation ---
	@api.onchange('name')
	def onchange_name_translate(self):
		"""Translates the English name to Arabic on change."""
		if self.name:
			# Translator is guaranteed to be imported due to raise ImportError above
			try:
				translator = Translator(to_lang="ar")
				self.name_ar = translator.translate(self.name)
			except Exception as e:
				_logger.error(f"Failed to translate name '{self.name}' to Arabic: {e}")
		else:
			self.name_ar = False

	# -- Overrides --
	@api.model_create_multi
	def create(self, vals_list):
		"""Override create to trigger related record creation after employee is created."""
		employees = super(HrEmployee, self.with_context(in_employee_create=True)).create(vals_list)
		for employee in employees:
			try:
				employee.sudo()._trigger_related_creation_or_update()
			except Exception as e:
				_logger.error(
					f"Error during post-creation sync for new employee {employee.name} (ID: {employee.id}): {e}")
		return employees

	def write(self, vals):
		"""Override write to update related records if relevant fields change."""
		tracked_fields = ['name', 'name_ar', 'department_id', 'work_contact_id', 'employee_type', 'gender',
						  'work_email', 'work_phone', 'mobile_phone', 'job_title', 'country_id', 'image_1920',
						  'ths_dob', 'ths_gov_id', 'category_ids', 'private_country_id']
		originals = {}
		if any(field in vals for field in tracked_fields):
			originals = {
				emp.id: {
					'name': emp.name,
					'name_ar': emp.name_ar,
					'dept_id': emp.department_id.id if emp.department_id else None,
					'dept_code': emp.department_id.code if emp.department_id else None,
					'work_contact_id': emp.work_contact_id.id if emp.work_contact_id else None,
					'employee_type': emp.employee_type,
					'gender': emp.gender,
					'work_phone': emp.work_phone,
					'mobile_phone': emp.mobile_phone,
					'function': emp.job_title,
					'ths_nationality': emp.country_id.id if emp.country_id else None,
					'partner_type_id': emp.work_contact_id.partner_type_id.id if emp.work_contact_id else None,
					'image_1920': emp.image_1920,
					'ths_dob': emp.birthday,
					'ths_gov_id': emp.identification_id,
					'partner_address_country': emp.private_country_id.id if emp.private_country_id else None,
				} for emp in self
			}

		res = super(HrEmployee, self).write(vals)

		for employee in self:
			original = originals.get(employee.id)
			if original and not self.env.context.get('in_employee_create'):
				needs_trigger = False
				for field in tracked_fields:
					if field in ['department_id', 'work_contact_id', 'country_id']:
						original_key = field.replace('_id', '') if field.endswith('_id') else field
						original_id = original.get(original_key)
						current_record = getattr(employee, field)
						current_id = current_record.id if current_record else None
						if field in vals and current_id != original_id:
							needs_trigger = True
							break
					elif field == 'image_1920' and field in vals:
						needs_trigger = True
						break
					elif field in vals and getattr(employee, field) != original.get(field):
						needs_trigger = True
						break
				if not needs_trigger and 'department_id' in vals:
					dept_code_after = employee.department_id.code if employee.department_id else None
					if dept_code_after != original.get('dept_code'):
						needs_trigger = True

				if needs_trigger:
					try:
						employee.sudo()._trigger_related_creation_or_update(original_values=original)
					except Exception as e:
						_logger.error(
							f"Error during post-update sync for employee {employee.name} (ID: {employee.id}): {e}")
		return res

	# -- Trigger Method --
	def _trigger_related_creation_or_update(self, original_values=None):
		"""Central function to orchestrate related record logic."""
		self.ensure_one()
		original_values = original_values or {}

		# Sync Partner Type, Ref, and Common Fields
		self._sync_work_partner_details()

		# Location (depends on name, department)
		self._create_or_update_employee_location(original_values)

		# Analytic Account (depends on name, department code)
		self._create_or_update_employee_analytic_account(original_values)

	# -- Partner Sync Method --
	def _sync_work_partner_details(self):
		""" Set Partner Type, Ref, and common fields on the work_contact_id partner.
		FIXED: Employee ALWAYS overrides partner values.
		"""
		self.ensure_one()
		work_partner = self.work_contact_id

		if not work_partner:
			_logger.debug(f"Emp {self.id} ({self.name}): No work contact partner. Skipping partner sync.")
			return

		partner_vals_to_write = {}
		target_partner_type = None

		# --- 1. Determine Target Partner Type based on employee_type ---
		partner_type_mapping = {
			'employee': 'ths_hr.partner_type_employee',
			'part_time': 'ths_hr.partner_type_part_time_employee',
			'external_employee': 'ths_hr.partner_type_external_employee',
		}
		target_partner_type_xmlid = partner_type_mapping.get(self.employee_type,
															 'ths_hr.partner_type_employee')  # Fallback to default

		try:
			target_partner_type = self.sudo().env.ref(target_partner_type_xmlid)
		except ValueError:
			_logger.error(
				f"Partner Type XML ID '{target_partner_type_xmlid}' not found. Cannot set partner type for {work_partner.name}.")
			target_partner_type = None

		# --- 2. Sync Partner Type ---
		if target_partner_type and work_partner.partner_type_id != target_partner_type:
			partner_vals_to_write['partner_type_id'] = target_partner_type.id
			type_is_changing = True
		else:
			type_is_changing = False

		# --- 3. Sync Employee Backlink ---
		if hasattr(work_partner, 'ths_employee_id') and work_partner.ths_employee_id != self:
			partner_vals_to_write['ths_employee_id'] = self.id

		# --- 3.1 Sync Partner Title for Doctor or Pharmacist ---
		if self.employee_type in ('doctor', 'pharmacist'):
			doctor_title = self.sudo().env.ref('base.res_partner_title_doctor', raise_if_not_found=False)
			if doctor_title:
				if work_partner.title != doctor_title:
					partner_vals_to_write['title'] = doctor_title.id
					_logger.debug(
						f"Emp {self.id}: Setting partner title to 'Doctor' for employee_type '{self.employee_type}'.")
			else:
				_logger.warning(
					f"Emp {self.id}: Title 'base.res_partner_title_doctor' not found. Skipping title update for {work_partner.name}."
				)
		elif self.gender:  # Only set title based on gender if employee_type is not doctor/pharmacist and gender is set
			title_xml_id = 'base.res_partner_title_mister' if self.gender == 'male' else 'base.res_partner_title_madam'
			gender_title = self.sudo().env.ref(title_xml_id)
			if gender_title and work_partner.title != gender_title:
				partner_vals_to_write['title'] = gender_title.id
				_logger.debug(
					f"Emp {self.id}: Setting partner title to '{gender_title.name}' for gender '{self.gender}'.")

		# --- 4. Employee ALWAYS Overrides Partner Values ---
		# Basic fields - always sync regardless of current partner values
		if self.name:  # Only sync if employee has a name
			partner_vals_to_write['name'] = self.name
		if hasattr(work_partner, 'name_ar'):
			partner_vals_to_write['name_ar'] = self.name_ar or False
		if hasattr(work_partner, 'gender'):
			partner_vals_to_write['gender'] = self.gender or False
		if hasattr(work_partner, 'ths_dob'):
			partner_vals_to_write['ths_dob'] = self.birthday or False
		if hasattr(work_partner, 'ths_gov_id'):
			partner_vals_to_write['ths_gov_id'] = self.identification_id or False
		if hasattr(work_partner, 'ths_nationality'):
			partner_vals_to_write['ths_nationality'] = self.country_id.id or False

		# Contact fields
		partner_vals_to_write['email'] = self.work_email or False
		partner_vals_to_write['phone'] = self.work_phone or False
		partner_vals_to_write['mobile'] = self.mobile_phone or False
		partner_vals_to_write['function'] = self.job_title or False
		partner_vals_to_write['country_id'] = self.country_id.id if self.country_id else False
		partner_vals_to_write['image_1920'] = self.image_1920 or False
		partner_vals_to_write['ths_dob'] = self.birthday or False
		partner_vals_to_write['ths_gov_id'] = self.identification_id or False
		partner_vals_to_write['ths_nationality'] = self.country_id.id or False

		# --- 5. Sync Partner Reference ('ref') ---
		is_target_employee_type = target_partner_type and target_partner_type.id in (
			self.env.ref('ths_hr.partner_type_employee', raise_if_not_found=False).id,
			self.env.ref('ths_hr.partner_type_part_time_employee', raise_if_not_found=False).id,
			self.env.ref('ths_hr.partner_type_external_employee', raise_if_not_found=False).id
		)

		if is_target_employee_type:
			employee_sequence = self.sudo().env.ref('ths_hr.seq_partner_ref_employee', raise_if_not_found=False)
			if employee_sequence:
				try:
					# Update ref if type just changed OR if ref is currently empty
					if type_is_changing or not work_partner.ref:
						new_ref = employee_sequence.sudo().next_by_id()
						if new_ref and work_partner.ref != new_ref:
							partner_vals_to_write['ref'] = new_ref
							_logger.debug(f"Emp {self.id}: Setting partner ref to '{new_ref}' from employee sequence.")
				except Exception as e:
					_logger.error(f"Emp {self.id}: Failed to get next sequence for employee ref: {e}")
			else:
				_logger.warning("Sequence 'ths_hr.seq_partner_ref_employee' not found. Cannot set partner ref.")

		# --- 6. Write changes to Partner ---
		if partner_vals_to_write:
			try:
				work_partner.sudo().write(partner_vals_to_write)
				_logger.debug(
					f"Emp {self.id}: Synced work partner '{work_partner.name}' (ID: {work_partner.id}) with values: {partner_vals_to_write}")
			except Exception as e:
				_logger.error(
					f"Emp {self.id}: Failed to sync work partner {work_partner.name} (ID: {work_partner.id}): {e}")

	# -- Location Methods --
	def _create_or_update_employee_location(self, original_values=None):
		self.ensure_one()
		original_values = original_values or {}
		name_before = original_values.get('name')
		dept_before = original_values.get('dept_id')
		name_after = self.name
		dept_after = self.department_id.id if self.department_id else None
		if not self.ths_inv_loss_loc_id:
			self._create_employee_location_if_needed()
		elif name_after != name_before or dept_after != dept_before:
			self._update_employee_location(original_values)

	def _create_employee_location_if_needed(self):
		self.ensure_one()
		Location = self.env['stock.location']
		if self.ths_inv_loss_loc_id: return
		if not self.name: return
		parent_location = self._get_employee_department_location()
		if not parent_location: return
		loc_name = f"{self._sanitize_name(self.name)} - Location"
		company_id = self.company_id.id or self.env.company.id
		existing_location = Location.sudo().search(
			[('name', '=', loc_name), ('location_id', '=', parent_location.id), ('usage', '=', 'inventory'),
			 ('company_id', '=', company_id)], limit=1)
		if existing_location: self.sudo().write({'ths_inv_loss_loc_id': existing_location.id}); return
		loc_vals = {'name': loc_name, 'usage': 'inventory', 'location_id': parent_location.id, 'company_id': company_id}
		try:
			new_location = Location.sudo().create([loc_vals])
			self.sudo().write({'ths_inv_loss_loc_id': new_location.id})
			_logger.debug(f"Emp {self.id}: Created location '{new_location.name}' (ID: {new_location.id})")
		except Exception as e:
			_logger.error(f"Emp {self.id}: Failed to create location '{loc_name}': {e}")

	def _update_employee_location(self, original_values=None):
		self.ensure_one()
		original_values = original_values or {}
		if not self.ths_inv_loss_loc_id: return
		current_loc = self.ths_inv_loss_loc_id
		vals_to_write = {}
		name_before = original_values.get('name')
		name_after = self.name
		if name_after != name_before and name_after:
			new_loc_name = f"{self._sanitize_name(name_after)} - Location"
			if current_loc.name != new_loc_name: vals_to_write['name'] = new_loc_name
		dept_before = original_values.get('dept_id')
		dept_after = self.department_id.id if self.department_id else None
		if dept_after != dept_before:
			new_parent_location = self._get_employee_department_location()
			if new_parent_location and current_loc.location_id != new_parent_location: vals_to_write[
				'location_id'] = new_parent_location.id
		if vals_to_write:
			try:
				current_loc.sudo().write(vals_to_write)
				_logger.debug("Emp %s: Updated location ID %s with values: %s", self.id, current_loc.id, vals_to_write)
			except Exception as e:
				_logger.error("Emp %s: Failed to update location %s: %s", self.id, current_loc.id, str(e))

	# -- Analytic Account Methods --
	def _create_or_update_employee_analytic_account(self, original_values=None):
		self.ensure_one()
		original_values = original_values or {}
		name_before = original_values.get('name')
		dept_code_before = original_values.get('dept_code')
		name_after = self.name
		dept_code_after = self.department_id.code if self.department_id else None
		if not self.ths_analytic_acc_id:
			self._create_employee_analytic_account_if_needed()
		elif name_after != name_before or dept_code_after != dept_code_before:
			self._update_employee_analytic_account_name()

	def _create_employee_analytic_account_if_needed(self):
		self.ensure_one()
		AnalyticAccount = self.env['account.analytic.account']
		if self.ths_analytic_acc_id: return
		if not self.name: return
		analytic_plan = self._get_employee_analytic_plan()
		if not analytic_plan: return
		dept_code = self.department_id.code if self.department_id else 'NODEP'
		acc_name = f"{dept_code} - {self._sanitize_name(self.name)}"
		company_id = self.company_id.id or self.env.company.id
		existing_account = AnalyticAccount.sudo().search(
			[('name', '=', acc_name), ('plan_id', '=', analytic_plan.id), ('company_id', '=', company_id)], limit=1)
		if existing_account: self.sudo().write({'ths_analytic_acc_id': existing_account.id}); return
		acc_vals = {'name': acc_name, 'plan_id': analytic_plan.id, 'company_id': company_id}
		try:
			new_account = AnalyticAccount.sudo().create([acc_vals])
			self.sudo().write({'ths_analytic_acc_id': new_account.id})
			_logger.debug(f"Emp {self.id}: Created analytic account '{new_account.name}' (ID: {new_account.id})")
		except Exception as e:
			_logger.error(f"Emp {self.id}: Failed to create analytic account '{acc_name}': {e}")

	def _update_employee_analytic_account_name(self):
		self.ensure_one()
		if not self.ths_analytic_acc_id or not self.name: return
		current_acc = self.ths_analytic_acc_id
		dept_code = self.department_id.code if self.department_id else 'NODEP'
		new_name = f"{dept_code} - {self._sanitize_name(self.name)}"
		if current_acc.name != new_name:
			try:
				current_acc.sudo().write({'name': new_name})
				_logger.debug("Emp %s: Updated analytic account name for ID %s to '%s'", self.id, current_acc.id,
							  new_name)
			except Exception as e:
				_logger.error("Emp %s: Failed to update analytic account name for %s: %s", self.id, current_acc.id,
							  str(e))

	# -- Helper Methods --
	def _get_employee_department_location(self):
		if not self.department_id:
			_logger.debug(f"Emp {self.id}: No department set. Using fallback parent location.")
			fallback_parent = self.sudo().env.ref('ths_hr.ths_stock_location_departments_view',
												  raise_if_not_found=False)
			if not fallback_parent: _logger.error(
				"Fallback parent location 'ths_hr.ths_stock_location_departments_view' not found."); return False
			return fallback_parent
		if not self.department_id.ths_inv_location_id:
			try:
				self.department_id.sudo()._create_department_location_if_needed()
				self.department_id.invalidate_recordset(['ths_inv_location_id'])
				if not self.department_id.ths_inv_location_id: raise ValidationError(
					_("Department '%s' location could not be created/found.", self.department_id.display_name))
			except Exception as e:
				_logger.error(
					f"Failed to ensure department location for {self.department_id.name}: {e}")
				raise UserError(
					_("Could not determine the parent location for department '%s'. Please check the department configuration.",
					  self.department_id.display_name)) from e
		return self.department_id.ths_inv_location_id

	def _get_employee_analytic_plan(self):
		analytic_plan = self.sudo().env.ref('ths_hr.ths_analytic_plan_employees', raise_if_not_found=False)
		if not analytic_plan: _logger.error(
			"Analytic plan 'Employees' (ths_hr.ths_analytic_plan_employees) not found."); raise UserError(
			_("The 'Employees' Analytic Plan (ths_hr.ths_analytic_plan_employees) is missing. Please ensure the ths_hr module data is loaded correctly."))
		return analytic_plan

	# -- Action for Retroactive Creation --
	def action_create_missing_emp_locations_accounts(self):
		employees_to_process = self.sudo()
		if not self and self.env.context.get('active_model') == 'hr.employee' and self.env.context.get('active_ids'):
			employees_to_process = self.sudo().browse(self.env.context['active_ids'])
		elif not self:
			employees_to_process = self.sudo().search([])
		_logger.info(
			f"Starting retroactive creation/linking for {len(employees_to_process)} employees.")
		count_loc = 0
		count_acc = 0
		processed_ids = set()
		errors = []
		for employee in employees_to_process:
			if employee.id in processed_ids: continue
			processed_ids.add(employee.id)
			try:
				employee._trigger_related_creation_or_update()
				if employee.ths_inv_loss_loc_id: count_loc += 1
				if employee.ths_analytic_acc_id: count_acc += 1
			except Exception as e:
				_logger.error(
					f"Retroactive: Error processing employee {employee.name} (ID: {employee.id}): {e}")
				errors.append(
					f"Employee {employee.name}: {e}")
		_logger.info(
			f"Retroactive processing finished. Employees checked: {len(processed_ids)}. Locations linked: {count_loc}. Accounts linked: {count_acc}.")
		message = _("Checked %s employees. Loss Locations created/linked: %s. Analytic Accounts created/linked: %s.",
					len(processed_ids), count_loc, count_acc)
		if errors: message += _("\nErrors encountered:\n%s", "\n".join(errors))
		if self.env.context.get('active_model') == 'hr.employee': return {'type': 'ir.actions.client',
																		  'tag': 'display_notification',
																		  'params': {'title': _("Processing Complete"),
																					 'message': message,
																					 'sticky': bool(errors),
																					 'type': 'warning' if errors else 'info'}}
		return True

# TODO: Add bulk update functionality for employee data
# TODO: Add audit trail for partner sync operations
# TODO: Add validation for duplicate employee references