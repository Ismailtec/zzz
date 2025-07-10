# -*- coding: utf-8 -*-
{
	'name': "Kuwait Address Full",
	'summary': 'Comprehensive address localization for Kuwait with Governorates and Areas/Districts utilizing standard Odoo fields.',
	'description': """This module enhances Odoo's address management for Kuwait by:
        - Populating all 6 Kuwaiti Governorates as Odoo States (res.country.state).
        - Introducing a new 'Area/District' model (res.country.area) linked to Governorates.
        - Modifying the standard 'City' field on res.partner to be a selectable 'Area/District' dropdown, dynamically filtered by Governorate.
        - Auto-populating Governorate and Country when an Area/District is selected.
        - Auto-populating Area/District when Governorate is selected.
        - Customizing address formatting to display 'Area/District Governorate_Code Country_Name'.
        - Hiding the 'Zip' code field in common address views.
        - Adding a column to the Country's States tab to show associated Areas.

        **Note:** Contains an extensive list of Governorates and common Areas/Districts.
        Full data population for all granular areas might require additional entries.""",
	'author': 'Techouse Solutions / Ismail Abdelkhalik',
	'website': 'https://www.techouse.ae',
	'category': 'Localization/Addresses',
	'version': '1.0',
	'depends': ['base', 'contacts'],  # Depends only on 'base' for core address models
	'data': [
		'data/pre_migration.xml',
		'security/ir.model.access.csv',
		'data/res_country_state_kw_data.xml',
		'data/res_country_area_kw_data.xml',
		'data/res_currency_data.xml',
        'data/res_lang_data.xml',
		'views/res_country_area.xml',
		'views/company.xml',
		'views/res_partner.xml',
		'views/res_country.xml',  # New view for country form modification
	],
	'installable': True,
	'application': False,
	'auto_install': False,
	'license': 'LGPL-3',
}