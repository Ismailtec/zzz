# -*- coding: utf-8 -*-
{
    'name': 'Techouse Medical POS Veterinary',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale/Medical',
    'summary': 'Veterinary specific UI adaptations for Medical POS.',
    'description': """
Extends the Techouse Medical POS Integration for veterinary specifics.
- Adapts POS UI elements (e.g., pending item lists, customer selection) to display Pet/Owner information clearly.
- Handles fetching and potentially filtering data based on Pet/Owner context.
- (Future) Integrates with Membership module for displaying Park Management status.
    """,
    'author': 'Techouse Solutions / Ismail Abdelkhalik',
    'website': 'https://www.techouse.ae',
    'depends': [
		'ths_medical_vet',  # Core Vet data models and fields
        'ths_medical_pos',  # Core POS medical integration
    ],
    'data': [
        #'security/ir.model.access.csv',
		'reports/vet_order_summary.xml',
		'reports/vet_line_summary.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            # Odoo standard assets required for Gantt and calendar views
            'web_gantt/static/src/**/*',
            'appointment/static/src/views/gantt/**/*',
            'calendar/static/src/views/widgets/**/*',
            'calendar/static/src/views/calendar_form/**/*',
            # Patches should load after the original components they patch

	        # 1. CONSOLIDATED POPUP (loads first - standalone component)
	        'ths_medical_pos_vet/static/src/popups/pet_order_setup_popup.js',
	        'ths_medical_pos_vet/static/src/popups/pet_order_setup_popup.xml',

	        # 2. Pending items popup with vet-specific Pet/Owner split
	        'ths_medical_pos_vet/static/src/popups/pending_items_list_popup.xml',

	        # 3. Partner list screen vet extension
	        'ths_medical_pos_vet/static/src/screens/partner_list_screen/partner_list_screen.js',
	        'ths_medical_pos_vet/static/src/screens/partner_list_screen/partner_list_screen.xml',

	        # 4. Encounter selection popup vet extension
	        'ths_medical_pos_vet/static/src/popups/encounter_selection_popup.js',
	        'ths_medical_pos_vet/static/src/popups/encounter_selection_popup.xml',

	        # 5. Pending items button vet extension
	        'ths_medical_pos_vet/static/src/components/pending_items_button/pending_items_button.js',

	        # 6. Product screen vet extension
	        #'ths_medical_pos_vet/static/src/screens/product_screen/order_widget_pets.xml',
			'ths_medical_pos_vet/static/src/screens/product_screen/vet_order_widget.xml',
	        'ths_medical_pos_vet/static/src/screens/product_screen/product_screen.xml',
	        'ths_medical_pos_vet/static/src/screens/product_screen/product_screen.js',
			'ths_medical_pos_vet/static/src/screens/appointment_screen/appointment_screen.js',

	        # 7. Data helpers for vet functionality
	        'ths_medical_pos_vet/static/src/js/pos_data_helpers.js',

	        # 8. Vet-specific styling (extends base style.css)
	        'ths_medical_pos_vet/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'OPL-1',
}
