# -*- coding: utf-8 -*-

from odoo import models, fields, api
#from odoo.exceptions import UserError, ValidationError
import logging
import re  # For sanitizing names

_logger = logging.getLogger(__name__)


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    # -- Fields --
    code = fields.Char(string='Code', copy=False, index=True)  # Added Dept Code
    ths_sequence_id = fields.Many2one(  # Added Sequence Link
        'ir.sequence',
        string='Reference Sequence',
        copy=False,
        readonly=True,
        help="Sequence related to this department (based on code)."
    )
    # Link to the department's specific inventory location
    ths_inv_location_id = fields.Many2one(
        'stock.location',
        string='Inv. Location',  # Shorter label
        copy=False,
        readonly=True,
        help="Internal inventory location associated with this department."
    )
    # Link to the department's specific analytic account
    ths_analytic_acc_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',  # Standard label is fine
        copy=False,
        readonly=True,
        help="Analytic account associated with this department."
    )
    ths_transfer_operation_id = fields.Many2one(
        'stock.picking.type',
        string='Transfer Operation',
        copy=False,
        readonly=True,
        help="Internal transfer operation type associated with this department."
    )

    # -- SQL Constraints --
    _sql_constraints = [
        ('code_company_uniq', 'unique (code, company_id)', 'Department Code must be unique per company!'),
    ]

    # -- Overrides --
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to automatically create sequence, location and analytic account."""
        departments = super(HrDepartment, self).create(vals_list)
        for department in departments:
            try:
                # Use sudo() for cross-model creation/linking consistency
                department.sudo()._create_department_sequence_if_needed()
                department.sudo()._create_department_location_if_needed()
                department.sudo()._create_department_transfer_operation_if_needed()
                department.sudo()._create_department_analytic_account_if_needed()
            except Exception as e:
                _logger.error(
                    f"Error during post-creation sync for new department {department.name} (ID: {department.id}): {e}")
                # Don't block department creation, just log the error
        return departments

    def write(self, vals):
        """Override write to update sequence/location/analytic/operation account if code/name changes."""
        # Store original values before write
        originals = {
            dept.id: {
                'name': dept.name,
                'code': dept.code,
                'sequence': dept.ths_sequence_id,
                'location': dept.ths_inv_location_id,
                'analytic': dept.ths_analytic_acc_id,
                'operation': dept.ths_transfer_operation_id
            }
            for dept in self
        } if 'name' in vals or 'code' in vals else {}

        res = super(HrDepartment, self).write(vals)

        if 'name' in vals or 'code' in vals:
            for dept in self:
                original = originals.get(dept.id, {})
                try:
                    # Update other records if name or code changed and they exist
                    if 'name' in vals or 'code' in vals:
                        if original.get('location'):
                            dept._update_department_location()
                        if original.get('analytic'):
                            dept._update_department_analytic_account()
                        if original.get('operation'):
                            dept._update_transfer_operation()
                        if original.get('sequence'):
                            dept._update_department_sequence()

                except Exception as e:
                    _logger.error("Failed to update department %s: %s", dept.id, str(e))

        return res

    # -- Update Methods --
    def _update_department_sequence(self):
        """Update existing sequence"""
        self.ensure_one()
        if not self.ths_sequence_id or not self.code:
            _logger.debug("Skipping sequence update - missing sequence or code")
            return

        # Calculate new values
        sanitized_code = self._sanitize_code(self.code)
        new_prefix = f"{sanitized_code}-"
        new_name = f"Department Sequence - {self.name or sanitized_code}"
        sequence_code = f'hr.department.seq.{sanitized_code}'

        # Determine what needs updating
        update_vals = {}
        if self.ths_sequence_id.prefix != new_prefix:
            update_vals['prefix'] = new_prefix
        if self.ths_sequence_id.name != new_name:
            update_vals['name'] = new_name
        if self.ths_sequence_id.code != sequence_code:
            update_vals['code'] = sequence_code

        # Apply updates if needed
        if update_vals:
            try:
                self.ths_sequence_id.sudo().write(update_vals)
                _logger.info("Updated sequence ID %s with values: %s",
                             self.ths_sequence_id.id, update_vals)
            except Exception as e:
                _logger.error("Failed to update sequence %s: %s",
                              self.ths_sequence_id.id, str(e))
                raise
        else:
            _logger.debug("No sequence updates needed for %s", self.code)

    def _update_department_location(self):
        """Update existing location"""
        self.ensure_one()
        if not self.ths_inv_location_id or not self.name:
            return

        new_name = self._sanitize_name(self.name)
        if self.ths_inv_location_id.name != new_name:
            self.ths_inv_location_id.sudo().write({
                'name': new_name
            })
            _logger.info("Updated location ID %s", self.ths_inv_location_id.id)

    def _update_department_analytic_account(self):
        """Update existing analytic account"""
        self.ensure_one()
        if not self.ths_analytic_acc_id or not self.name:
            return

        update_vals = {}
        if self.ths_analytic_acc_id.name != self.name:
            update_vals['name'] = self.name
        if self.code and self.ths_analytic_acc_id.code != self.code:
            update_vals['code'] = self.code

        if update_vals:
            self.ths_analytic_acc_id.sudo().write(update_vals)
            _logger.info("Updated analytic account ID %s", self.ths_analytic_acc_id.id)

    def _update_transfer_operation(self):
        """Update existing transfer operation"""
        self.ensure_one()
        if not self.ths_transfer_operation_id or not self.name:
            return

        new_name = f"{self.name} Internal Transfer from Main"
        if self.ths_transfer_operation_id.name != new_name:
            self.ths_transfer_operation_id.sudo().write({
                'name': new_name
            })
            _logger.info("Updated operation ID %s", self.ths_transfer_operation_id.id)

    # -- Helper Methods --
    @staticmethod
    def _sanitize_name(name):
        """ Sanitize department name for use in related records. """
        name = (name or '').strip()
        return name or 'unnamed-dept'

    @staticmethod
    def _sanitize_code(code):
        """ Sanitize department code. """
        code = (code or '').strip().upper()
        # Remove spaces and potentially problematic characters for sequence code
        code = re.sub(r'\s+', '_', code)
        code = re.sub(r'[^A-Z0-9_]+', '', code)
        return code or 'UNCODED'

    def _conditional_create_missing_items(self):
        """Conditionally triggers creation when both name/code are set."""
        for dept in self:
            if dept.name and dept.code:  # Only if both fields are set
                # Use sudo and skip_auto_create to prevent recursion
                dept.sudo().with_context(skip_auto_create=True).action_create_missing_items()

    def _get_department_parent_location(self):
        """ Helper to get the parent 'Departments' view location. """
        parent_loc = self.sudo().env.ref('ths_hr.ths_stock_location_departments_view', raise_if_not_found=False)
        if not parent_loc:
            _logger.error("Parent location 'Departments' (ths_hr.ths_loc_view_departments) not found.")
        return parent_loc

    def _get_department_analytic_plan(self):
        """ Helper to get the parent 'Departments' analytic plan. """
        analytic_plan = self.sudo().env.ref('ths_hr.ths_analytic_plan_departments', raise_if_not_found=False)
        if not analytic_plan:
            _logger.error("Analytic plan 'Departments' (ths_hr.ths_analytic_plan_departments) not found.")
        return analytic_plan

    def _create_department_sequence_if_needed(self):
        """ Creates or links an ir.sequence based on the department code. """
        if not self.env.context.get('force_create_missing') and not (self.name and self.code):
            return
        self.ensure_one()
        Sequence = self.env['ir.sequence']
        if not self.code:
            _logger.warning(f"Dept {self.id} ({self.name}): No code set, cannot create/link sequence.")
            if self.ths_sequence_id:  # Unlink if code is removed
                self.write({'ths_sequence_id': False})
            return

        sanitized_code = self._sanitize_code(self.code)
        sequence_code = f'hr.department.seq.{sanitized_code}'  # Unique code for the sequence record
        company_id = self.company_id.id or self.env.company.id

        # Search for existing sequence
        existing_sequence = Sequence.sudo().search([
            ('code', '=', sequence_code),
            ('company_id', '=', company_id)
        ], limit=1)

        sequence_to_link = False
        if existing_sequence:
            _logger.info(f"Dept {self.id}: Found existing sequence '{sequence_code}' (ID: {existing_sequence.id}).")
            sequence_to_link = existing_sequence
            # Optional: Update prefix if code changed but sequence existed?
            expected_prefix = f"{sanitized_code}-"
            expected_name = f"Department Sequence - {self.name or sanitized_code}"
            vals_to_write = {}
            if sequence_to_link.prefix != expected_prefix: vals_to_write['prefix'] = expected_prefix
            if sequence_to_link.name != expected_name: vals_to_write['name'] = expected_name
            if vals_to_write:
                try:
                    sequence_to_link.sudo().write(vals_to_write)
                except Exception as e:
                    _logger.warning(f"Dept {self.id}: Failed to update existing sequence details: {e}")
        else:
            # Create new sequence
            seq_vals = {
                'name': f"Department Sequence - {self.name or sanitized_code}",
                'code': sequence_code,
                'prefix': f"{sanitized_code}-",
                'padding': 4,
                'company_id': company_id,
                'implementation': 'no_gap',
            }
            try:
                new_sequence = Sequence.sudo().create(seq_vals)
                sequence_to_link = new_sequence
                _logger.info(f"Dept {self.id}: Created sequence '{new_sequence.name}' (ID: {new_sequence.id}).")
            except Exception as e:
                _logger.error(f"Dept {self.id}: Failed to create sequence for code '{sanitized_code}': {e}")

        # Link the sequence if found/created and different from current
        if sequence_to_link and self.ths_sequence_id != sequence_to_link:
            self.write({'ths_sequence_id': sequence_to_link.id})
        elif not sequence_to_link and self.ths_sequence_id:
            # Unlink if sequence couldn't be found/created (e.g., error)
            self.write({'ths_sequence_id': False})

    def _create_department_location_if_needed(self):
        """Creates an internal stock location for the department if it doesn't exist."""
        if self.env.context.get('skip_auto_create'):
            return
        self.ensure_one()

        if self.ths_inv_location_id:
            _logger.debug("Location already exists for %s (ID: %s)", self.name, self.ths_inv_location_id.id)
            return

        if not self.name:
            _logger.warning("Skipping location creation - no department name")
            return

        _logger.info("Creating location for department %s", self.name)
        try:
            location = self.env['stock.location'].sudo().create({
                'name': self._sanitize_name(self.name),
                'location_id': self._get_department_parent_location().id,
                'usage': 'inventory',
                'company_id': self.company_id.id
            })
            self.ths_inv_location_id = location
            _logger.info("Successfully created location ID %s", location.id)
        except Exception as e:
            _logger.error("Failed to create location: %s", str(e))
            raise

    def _create_department_transfer_operation_if_needed(self):
        """Creates an internal transfer operation type for the department if it doesn't exist."""
        if self.env.context.get('skip_auto_create'):
            return

        self.ensure_one()
        PickingType = self.env['stock.picking.type']

        # Your existing checks
        if self.ths_transfer_operation_id or not self.ths_inv_location_id:
            _logger.debug("Skipping operation: %s",
                          "Already exists" if self.ths_transfer_operation_id
                          else "No location available")
            return

        dept_name = self._sanitize_name(self.name)
        company_id = self.company_id.id or self.env.company.id

        # Your existing sequence logic
        sequence_code = f"stock.picking.type.intr.{self._sanitize_code(self.code or 'DEPT')}"
        sequence = self.env['ir.sequence'].sudo().search([
            ('code', '=', sequence_code),
            ('company_id', '=', company_id)
        ], limit=1)

        prefix = f"INTR/{self.code or 'DEPT'}/%(year)s%(month)s%(day)s"
        if not sequence:
            sequence_vals = {
                'name': f"Internal Transfer {dept_name} Sequence",
                'code': sequence_code,
                'prefix': prefix,
                'padding': 2,
                'company_id': company_id,
                'implementation': 'no_gap',
            }
            sequence = self.env['ir.sequence'].sudo().create(sequence_vals)
            _logger.info("Created new sequence ID %s for %s", sequence.id, dept_name)

        # Your existing operation creation
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company_id)], limit=1)
        if not warehouse:
            _logger.error("No warehouse found for company %s", company_id)
            return

        operation_vals = {
            'name': f"{dept_name} Internal Transfer from Main",
            'sequence_id': sequence.id,
            'code': 'internal',
            'warehouse_id': warehouse.id,
            'use_create_lots': False,
            'use_existing_lots': True,
            'default_location_src_id': self.env.ref('stock.stock_location_stock').id,
            'default_location_dest_id': self.ths_inv_location_id.id,
            'company_id': company_id,
            'sequence_code': 'INTR',
            'show_operations': True,
        }

        try:
            new_operation = PickingType.sudo().create(operation_vals)
            self.write({'ths_transfer_operation_id': new_operation.id})
            _logger.info("Created transfer operation ID %s for %s",
                         new_operation.id, dept_name)
        except Exception as e:
            _logger.error("Failed to create operation for %s: %s", dept_name, str(e))
            raise

    def _create_department_analytic_account_if_needed(self):
        """Creates an analytic account for the department if it doesn't exist."""
        if self.env.context.get('skip_auto_create'):
            return
        self.ensure_one()

        if self.ths_analytic_acc_id:
            _logger.debug("Analytic account already exists for %s (ID: %s)",
                          self.name, self.ths_analytic_acc_id.id)
            return

        if not self.name:
            _logger.warning("Skipping analytic account creation - no department name")
            return

        _logger.info("Creating analytic account for %s", self.name)
        try:
            analytic_account = self.env['account.analytic.account'].sudo().create({
                'name': self.name,
                'code': self.code,
                'plan_id': self._get_department_analytic_plan().id,
                'company_id': self.company_id.id
            })
            self.ths_analytic_acc_id = analytic_account
            _logger.info("Successfully created analytic account ID %s", analytic_account.id)
        except Exception as e:
            _logger.error("Failed to create analytic account: %s", str(e))
            raise

    # -- Action for Retroactive Creation --
    def action_create_missing_items(self):
        """Single method to handle all missing item creation"""
        # Allow forcing through context for automatic triggers
        if not self.env.context.get('force_create_missing') and not self.env.context.get('active_ids'):
            self = self.filtered(lambda d: d.name and d.code)  # Manual calls require both fields

        _logger.info(f"Starting creation process for {len(self)} departments")

        for dept in self:
            try:
                # Sequence depends on code
                if dept.code or self.env.context.get('force_create_missing'):
                    dept._create_department_sequence_if_needed()

                # Location/Operation/Analytic depend on name
                if dept.name or self.env.context.get('force_create_missing'):
                    dept._create_department_location_if_needed()
                    dept._create_department_transfer_operation_if_needed()
                    dept._create_department_analytic_account_if_needed()

            except Exception as e:
                _logger.error(f"Failed to process department {dept.id}: {e}")
                continue
