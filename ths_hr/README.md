# Techouse HR Enhancements (ths_hr) for Odoo 18

## Summary

This module, developed by Techouse Solutions, enhances Odoo 18's Human Resources application by integrating it with Inventory Locations and Analytic Accounting. It automatically creates and links department/employee-specific locations and analytic accounts, adds department codes/sequences, extends employee type options, and provides related UI fields and security groups.

**Requires the 'Techouse Base' (`ths_base`) module to be installed first.**

## Key Features

* **Partner Type Integration:**
    * Adds an `is_employee` flag to the `ths.partner.type` model (defined in `ths_base`).
    * Creates an "Employee" `ths.partner.type` via data file.
    * Automatically sets the linked partner's type to "Employee" upon employee creation, triggering reference generation (via `ths_base`).
* **Department Enhancements:**
    * Adds a `code` field to Departments.
    * Adds a linked `ir.sequence` field (`ths_sequence_id`).
    * Automatically creates/links a sequence based on the department `code`.
    * Automatically creates/links a dedicated internal inventory location (`ths_inv_location_id`) under a parent "Departments" view location.
    * Automatically creates/links a dedicated analytic account (`ths_analytic_acc_id`) under a parent "Departments" analytic group.
* **Employee Enhancements:**
    * Adds "Part Time" and "External Contractor" options to the standard `employee_type` selection field.
    * Automatically creates/links a dedicated inventory *loss* location (`ths_inv_loss_loc_id`) nested under the employee's department location.
    * Automatically creates/links a dedicated analytic account (`ths_analytic_acc_id`) nested under the employee's department analytic account.
    * Handles updates to location/analytic account links if the employee's department changes.
* **Automation & Maintenance:**
    * Provides retroactive actions (buttons on list views for managers) to create/link missing sequences, locations, and analytic accounts for existing Departments and Employees.
* **Security:**
    * Defines "HR User (Techouse)" and "HR Manager (Techouse)" groups, inheriting from standard Odoo HR groups, for controlling access to features and actions.
* **UI:**
    * Adds relevant fields to Department and Employee forms and list views.
    * Adds useful filters and group-by options to Department and Employee list/search views.

## Dependencies

* **`ths_base`**: Essential for `ths.partner.type` and potentially other base features.
* `hr`
* `stock`
* `account`
* `analytic`

## Installation

1.  Ensure the `ths_base` module is already installed.
2.  Copy the `ths_hr` module folder into your Odoo addons directory.
3.  Restart the Odoo server process.
4.  Log in to Odoo as an administrator.
5.  Activate Developer Mode.
6.  Navigate to the "Apps" menu.
7.  Click "Update Apps List".
8.  Search for "Techouse HR Enhancements" and click "Install".

## Configuration

* No specific configuration is required for this module itself, but ensure parent locations/groups from data files are created correctly.
* Assign users to standard Odoo HR groups (`Human Resources / Employee` or `Human Resources / Administrator`) to grant access via the custom implied groups.

## Usage

* **Departments:** When creating/editing departments, fill in the `Code` field. The sequence, location, and analytic account will be automatically created/linked.
* **Employees:** When creating employees, the linked partner type will be set to "Employee", and the loss location/analytic account will be created/linked automatically based on their department. The `employee_type` field includes the new options. Check "Medical Staff" if applicable.
* **Retroactive Actions:** If needed, select existing departments or employees in their list views and use the "Create Missing Items" button (under the Action menu if not on header) to generate associated records.

## Author & Support

* **Author:** Techouse Solutions / Ismail Abdelkhalik
* **Website:** [https://www.techouse.ae](https://www.techouse.ae)
* **Support:** info@techouse.ae