# Kuwait Address Full (ths_l10n_kw_address_full) for Odoo 18

## Summary

This module, developed by Techouse Solutions, provides comprehensive address localization for Kuwait. It re-purposes standard Odoo address fields to align with Kuwait's geographical hierarchy of Governorates and Areas/Districts, populates essential data, and customizes address entry and display for local compliance and usability.

## Key Features

**1. Kuwaiti Geographical Data Integration:**
   - **Governorates:** Populates all 6 Kuwaiti Governorates (`محافظة`) into Odoo's standard `res.country.state` model.
   - **Areas/Districts:** Introduces a new `res.country.area` model to manage the detailed areas (like Jabriya, Salmiya) within each Governorate.
   - **Extensive Data:** Includes an extensive initial list of common Areas/Districts for all Kuwaiti Governorates, making setup faster.

**2. Smart Address Field Management:**
   - **Re-purposed 'City' Field:** The standard `city` field on `res.partner` (and related address forms) is transformed from a free-text `Char` field into a `Many2one` dropdown linked to the new `res.country.area` model. This allows for controlled, selectable Area/District entries.
   - **Dynamic Filtering:** 'Area / District' options are dynamically filtered in the dropdown based on the selected 'Governorate' (`state_id`) and 'Country' (`country_id`).
   - **Auto-Population:** Automatically sets the 'Governorate' and 'Country' fields when an 'Area / District' is selected, streamlining data entry.
   - **Coherent Data Flow:** Ensures 'Area / District' is cleared if the chosen 'Governorate' or 'Country' changes, maintaining data consistency.

**3. Customized Address Formatting & Display:**
   - **Local Address Format:** Modifies the default address display format for partners and reports to conform to Kuwaiti expectations:
     ```
     %(street)s
     %(street2)s
     %(city)s %(state_code)s
     %(country_name)s
     ```
     This will typically render as: `[Street]`, `[Street2]`, `[Area/District] [Governorate Code]`, `[Country Name]`.
   - **Hidden Zip Code:** The 'Zip' (Postal Code) field is hidden from address entry forms, as it is not commonly used for specific street addresses in Kuwait.
   - **Backend Visibility:** Adds an 'Areas / Districts' column to the 'States' tab within the Country configuration form (`Settings -> General Settings -> Countries`), allowing administrators to easily view and manage areas associated with each Governorate.

## Dependencies

This module depends only on the following standard Odoo module:
* `base` (for core address models `res.country`, `res.country.state`, `res.partner`)

## Installation

1.  Copy the `ths_l10n_kw_address_full` module folder into your Odoo addons directory.
2.  Restart the Odoo server process (e.g., `sudo systemctl restart odoo`).
3.  Log in to your Odoo instance with administrator rights.
4.  Activate Developer Mode (Settings -> General Settings -> Activate the developer mode).
5.  Navigate to the "Apps" menu.
6.  Click "Update Apps List" in the Apps menu (top bar).
7.  Remove the default "Apps" filter and search for "Kuwait Address Full".
8.  Click the "Install" button on the `Kuwait Address Full` module card.

## Configuration & Usage

* **Partner Addresses:** When creating or editing a partner's address, you will now:
    1.  Select `Kuwait` as the `Country`.
    2.  Choose the `Governorate` from the `State` dropdown.
    3.  Select the specific `Area / District` from the `City` dropdown. The options in the `City` dropdown will automatically filter based on the selected `Governorate`.
* **Managing Areas:** Administrators can manage (`create`, `edit`, `delete`) Area/District records by navigating to `Settings -> Technical -> Database Structure -> Countries -> Areas / Districts`.
* **Viewing Areas by Governorate:** To see which Areas belong to each Governorate, go to `Settings -> General Settings -> Countries`. Open the `United Arab Emirates` record, and then navigate to the 'States' tab. You will see a new column listing the 'Areas / Districts' associated with each Emirate.

## Author & Support

* **Author:** Techouse Solutions / Ismail Abdelkhalik
* **Website:** [https://www.techouse.ae](https://www.techouse.ae)
* **Support:** info@techouse.ae