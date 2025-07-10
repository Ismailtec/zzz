# Techouse Base (ths_base) for Odoo 18

## Summary

This module, developed by Techouse Solutions, provides core enhancements for Odoo 18, focusing on improved control over transaction dates (Effective Date), flexible vendor selection for purchasing, extended landed cost management features, and UI adjustments for better usability.

## Key Features

**1. Effective Date Control:**
   - Adds an "Effective Date" field (`ths_effective_date`) to Purchase Orders, Receipts/Transfers, Scraps, Inventory Adjustments, and Landed Costs.
   - Allows users to specify a date different from the transaction processing date.
   - Ensures that related Stock Moves and Journal Entries correctly use this Effective Date.
   - Includes logic to handle potential date resets during Odoo's standard processing.

**2. Enhanced Vendor Selection for Replenishment:**
   - Adds a "Priority" checkbox (`ths_manual_priority_vendor`) to vendor pricelists (supplierinfo).
   - Modifies the logic (`_select_seller`) used during replenishment (manual or automatic):
     - If a vendor is marked as "Priority" and has sequence 0 or 1, they are selected.
     - Otherwise, the system selects the valid vendor with the **lowest price**.
   - Allows manual override while defaulting to cost-effective purchasing.
   - Sorts vendor list view by price ascending by default.

**3. Improved Landed Cost Workflow:**
   - Adds "Effective Date" (`ths_effective_date`) for accurate accounting date control.
   - Links Landed Costs to Purchase Orders (`purchase_order_id`).
   - Provides dynamic filtering for Vendor Bills and Receipts based on the selected PO.
   - Autopopulates PO/Receipts/Cost Lines when creating LCs or selecting linked documents.
   - Includes a safe "Cancel" (Reversal) action that creates a reversing LC entry, maintaining audit trail.
   - Adds smart buttons on POs, Bills, and Receipts to easily navigate to related Landed Costs.
   - Automatically creates/updates a draft Landed Cost based on PO confirmation or Bill posting (populating cost lines from products marked as landed costs).

**4. Global "Hide Taxes" Option:**
   - Adds a global configuration setting (Accounting Settings) to hide tax-related columns (`Taxes`, `Tax Tags`) by default on Purchase Order, Sales Order, and Invoice/Bill lines.
   - Simplifies the interface for users who don't frequently interact with taxes on line items.
   - *(Note: Report modifications based on this setting are included but may require further fixes).*

**5. Other Enhancements:**
   - Adds a "Product Brand" field to products.
   - Includes code for AVCO cost recalculation (manual trigger button currently commented out).
   - Minor UI adjustments (optional columns, field labels, view layouts).

## Dependencies

This module depends on the following standard Odoo modules:
* `base`
* `mail`
* `account`
* `stock`
* `stock_account`
* `sale_stock`
* `sale_management`
* `purchase`
* `purchase_stock`
* `stock_landed_costs`

## Installation

1.  Copy the `ths_base` module folder into your Odoo addons directory.
2.  Restart the Odoo server process (e.g., `sudo systemctl restart odoo`).
3.  Log in to your Odoo instance with administrator rights.
4.  Activate Developer Mode (Settings -> General Settings -> Activate the developer mode).
5.  Navigate to the "Apps" menu.
6.  Click "Update Apps List" in the Apps menu (top bar).
7.  Remove the default "Apps" filter and search for "Techouse Base".
8.  Click the "Install" button on the `ths_base` module card.

## Configuration

* **Hide Taxes:** Go to Accounting -> Configuration -> Settings. Locate the "Hide Taxes" option under the Taxes section and check/uncheck it as desired. Apply changes.
* **Vendor Priority:** On a Product's "Purchase" tab, edit the Vendor lines. Check the "Priority" box and set the Sequence to 0 or 1 for a vendor you want to manually prioritize for replenishment, overriding the lowest price logic.

## Usage

* **Effective Date:** When creating/processing POs, Receipts, Scraps, Adjustments, or Landed Costs, use the "Effective Date" field to control the date used for stock moves and accounting entries. If left blank, the standard Odoo date logic applies.
* **Replenishment:** Replenishment actions will automatically select the lowest-priced valid vendor unless a vendor is manually prioritized (see Configuration).
* **Landed Costs:**
    * Create LCs directly or link them via the PO/Bill fields.
    * Cost lines can be auto-populated from linked POs/Bills containing Landed Cost type products.
    * Use the "Cancel" button on a *Done* Landed Cost to create a reversal entry.
    * Use smart buttons on PO/Bill/Receipts to find related LCs.

## Author & Support

* **Author:** Techouse Solutions / Ismail Abdelkhalik
* **Website:** [https://www.techouse.ae](https://www.techouse.ae)
* **Support:** info@techouse.ae

