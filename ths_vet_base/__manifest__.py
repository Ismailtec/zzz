# -*- coding: utf-8 -*-
{
    'name': 'Techouse Medical Base',
    'version': '18.0.1.0.0',
    'category': 'Hidden',
    'summary': 'Adds base medical-related flags to HR models.',
    'description': """Adds base models and logic for medical workflows:
                      - Medical flags for Employee Types and Employees.
                      - Product Sub Type classification system.
                      - Treatment Room management with resource linking.
                      - Daily Encounter grouping.
                      - Medical Encounter tracking linked to appointments.
                      - Pending POS Item model for billing bridge.
                      - Extends Calendar Event for medical context.
                    """,
    'author': 'Techouse Solutions / Ismail Abdelkhalik',
    'website': 'https://www.techouse.ae',
    'depends': [
        'hr',  # Dependency for hr.employee and hr.employee.type
        'base',
        'mail',
        'ths_hr',  # Dependency for potential future interactions or structure
        'ths_base',
        'hr',
        'hr_holidays',
        'hr_work_entry',
        'stock',
        'product',
        'account',
        'analytic',
        'appointment',
        'calendar',
        'resource',
        'point_of_sale',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Data Files
        'data/ir_sequence.xml',
        'data/hr_employee_type_config_data.xml',
        'data/partner_type_data.xml',
        'data/product_sub_type_data.xml',
        'data/appointment_reminder_cron.xml',
        'data/email_templates.xml',
        # Views
        'views/hr_employee.xml',  # Adds medical flag & calendar flag to Employee views
        'views/hr_employee_type_config.xml',
        'views/treatment_room.xml',  # New Treatment Room views
        'views/product_sub_type.xml',  # Views for the NEW sub-type model
        'views/medical_encounter.xml',  # New Encounter views
        'views/pending_pos_item.xml',  # New Pending POS Item views
        'views/medical_menus.xml',  # Menu for Treatment Rooms etc.
        'views/appointment_type.xml',
        'views/appointment_resource.xml',
        'views/product.xml',  # Adds sub-type field to Product views & domain logic
        'views/hr_department.xml',  # Adds medical flag to Department views
        'views/partner_type.xml',
        'views/calendar_event.xml',  # Inherited Calendar Event view
        'views/encounter_reports.xml',
    ],
    'assets': {
        # Move gantt extension to lazy bundle where gantt renderer lives
        'web.assets_backend_lazy': [
            'appointment/static/src/views/gantt/**',
            # Add our medical gantt extension AFTER appointment gantt files
            'ths_medical_base/static/src/views/gantt/gantt_renderer_medical.js',
        ],
        'web.assets_backend': [
            'appointment/static/src/scss/appointment_type_views.scss',
            'appointment/static/src/scss/web_calendar.scss',
            'appointment/static/src/views/**/*',
            # Remove gantt from main bundle since it's in lazy bundle
            ('remove', 'appointment/static/src/views/gantt/**'),
            'appointment/static/src/components/**/*',
            'appointment/static/src/js/appointment_insert_link_form_controller.js',
            'appointment/static/src/appointment_plugin.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OPL-1',
}
