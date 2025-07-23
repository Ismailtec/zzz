# -*- coding: utf-8 -*-
{
    'name': 'Techouse Medical POS Integration',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale/Medical',
    'summary': 'Integrates medical encounters and billing with Point of Sale.',
    'description': '''
        Medical Point of Sale Extension
        ==============================
        
        This module extends the Odoo 18 Point of Sale application to support medical practices:
        
        Features:
        - Appointment management directly from POS
        - Patient management integration
        - Pending medical items handling
        - Medical practitioner assignment
        - Treatment room booking
        - Commission tracking for medical services
        
        Technical Implementation:
        - Built with OWL 3 framework
        - Follows Odoo 18 POS standards
        - Responsive design for mobile and tablet use
        - Real-time appointment calendar integration
    ''',
    'author': 'Techouse Solutions / Ismail Abdelkhalik',
    'website': 'https://www.techouse.ae',
    'depends': [
        'point_of_sale',
        'ths_medical_base',  # Depends on the medical base for encounter/pending items
        'ths_hr',  # Needed for hr.employee (practitioner) access
        'calendar',
        'hr',
        'resource',
        'contacts',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Views
        'views/medical_encounter.xml',
        # # Data
        #
        # # Assets
        #'static/src/xml/assets.xml',
    ],

    'assets': {
        'point_of_sale._assets_pos': [
	        #1. Data helpers (load first - provides utility functions)
	        'ths_medical_pos/static/src/js/pos_data_helpers.js',

	        # 2. Base popup components (no dependencies)
	        'ths_medical_pos/static/src/popups/pending_items_list_popup.js',
	        'ths_medical_pos/static/src/popups/pending_items_list_popup.xml',
	        'ths_medical_pos/static/src/popups/encounter_selection_popup.js',
	        'ths_medical_pos/static/src/popups/encounter_selection_popup.xml',

	        # 3. Button components (depends on popups)
	        'ths_medical_pos/static/src/components/pending_items_button/pending_items_button.js',
	        'ths_medical_pos/static/src/components/pending_items_button/pending_items_button.xml',

	        # 4. Control buttons encounter functionality
	        'ths_medical_pos/static/src/screens/product_screen/control_buttons_encounter.js',
	        'ths_medical_pos/static/src/screens/product_screen/control_buttons_encounter.xml',

	        # 5. Screen enhancements and patches
	        'ths_medical_pos/static/src/screens/partner_list_screen/partner_list_screen.js',
	        'ths_medical_pos/static/src/screens/partner_list_screen/partner_list_screen.xml',

	        # 6. Product screen enhancements
	        'ths_medical_pos/static/src/screens/product_screen/product_screen.js',
	        'ths_medical_pos/static/src/screens/product_screen/product_screen.xml',

	        # 7. Appointment screen functionality
	        'ths_medical_pos/static/src/screens/appointment_screen/appointment_screen.js',
	        'ths_medical_pos/static/src/screens/appointment_screen/appointment_screen.xml',

	        # 8. Styling (load last)
	        'ths_medical_pos/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OPL-1',
}
