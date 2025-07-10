# -*- coding: utf-8 -*-
{
	'name': 'Techouse Medical Veterinary',
	'version': '18.0.1.0.0',
	'category': 'Medical/Veterinary',
	'summary': 'Veterinary specific extensions for Techouse Medical modules.',
	'description': """ Adapts the Techouse Medical Base module for veterinary clinics.
                        - Defines "Pet" and "Pet Owner" partner types and relationships.
                        - Adds Pet-specific fields (Species, Breed, DOB, etc.) to the Partner model.
                        - Modifies Appointment and Encounter screens to handle Pet/Owner distinction. """,
	'author': 'Techouse Solutions / Ismail Abdelkhalik',
	'website': 'https://www.techouse.ae',
	'depends': [
		'ths_base',
		'ths_medical_base',  # Essential dependency
		'ths_hr',  # For ths_hr.employee
		'contacts',  # For res.partner
		'accountant',
	],
	'data': [
		'security/ir.model.access.csv',
		'data/ir_sequence.xml',
		'data/partner_type_data.xml',
		'data/product_sub_type_data.xml',
		'views/boarding.xml',
		'views/pending_pos_items.xml',
		'views/calendar_event.xml',
		'views/medical_encounter.xml',
		'views/medical_history.xml',
		'views/medical_summary.xml',
		'views/species.xml',
		'views/breed.xml',
		'views/vaccination.xml',
		'views/product.xml',
		'views/pet_membership.xml',
		'views/park.xml',
		'views/partner_type.xml',
		'views/res_partner.xml',
		'views/vet_encounter_reports.xml',
		'views/vet_menus.xml',
		'wizard/species_breed_import_view.xml',
	],
	'assets': {
		'web.assets_backend': [
			'ths_medical_vet/static/src/style.scss',
		],
	},
	'installable': True,
	'application': False,
	'auto_install': False,
	'license': 'OPL-1',
}