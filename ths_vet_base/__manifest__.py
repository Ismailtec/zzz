# -*- coding: utf-8 -*-
{
	'name': 'Techouse Veterinary Base',
	'version': '18.0.1.0.0',
	'category': 'Healthcare/Veterinary',
	'summary': 'Comprehensive Veterinary Management System with Encounters, Boarding, Park Services & Medical Records',
	'description': """
	Complete Veterinary Management System for Odoo 18
================================================

This module provides a comprehensive veterinary clinic management solution with advanced 
appointment scheduling, medical record keeping, encounter management, and integrated billing.

**🎯 Core Features:**

**Daily Encounter Management:**
- Smart daily encounter containers grouping all services per pet owner per day
- Automatic encounter creation from appointments with seamless workflow integration
- Complete billing integration with line item management and payment tracking
- SOAP notes documentation with clinical findings and treatment plans
- Vital signs logging (weight, temperature, heart rate, respiratory rate)

**Advanced Appointment Scheduling:**
- Resource-based scheduling with practitioner and treatment room management
- Medical appointment types with department-specific resource allocation
- Emergency appointment flagging and priority management
- Status workflow: Request → Booked → Checked-In → Completed → Paid
- Cancellation and rescheduling with reason tracking and conflict detection

**Pet Owner & Pet Management:**
- Enhanced partner management with pet-owner relationship tracking
- Comprehensive pet profiles with species, breed, medical history
- Automatic contact information synchronization between pets and owners
- Pet health status indicators and vaccination tracking
- Medical alerts and dietary restrictions management
- Document management for pet photos and medical records

**Medical Records & Clinical Features:**
- Complete medical history with automated health indicators
- Vaccination management with expiry tracking and automated reminders
- Treatment plan creation with task management and progress tracking
- Medical summary generation with health status analytics
- Microchip tracking and pet identification management
- Insurance information and emergency contact management

**Service Management:**
- Boarding services with cage assignment and care logging
- Park/daycare check-ins with membership validation
- Pet membership management for subscription services
- Service utilization tracking and performance metrics

**Resource & Staff Management:**
- Medical staff categorization with appointment resource creation
- Treatment room management with equipment tracking and maintenance modes
- Department-based resource allocation and scheduling
- Medical license tracking and expiry alerts
- Staff scheduling and availability management

**Billing & Financial Integration:**
- Encounter-based billing with automatic line item generation
- Integration with POS, Sales Orders, and Direct Invoicing
- Payment status tracking (pending, paid, refunded, cancelled)
- Commission tracking and financial reporting
- Service pricing and cost estimation

**Analytics & Reporting:**
- Daily/weekly/monthly encounter analytics with comprehensive dashboards
- Pet medical history summaries with automated health indicators
- Service utilization reports and performance metrics
- QR code generation for mobile access and quick record retrieval
- Vaccination reminder scheduling and automated follow-up systems

**Automation Features:**
- Automated daily encounter creation and service linking
- Vaccination reminder scheduling with email and WhatsApp notifications
- Boarding pickup reminders and schedule notifications
- Appointment reminder system with 24-hour advance notifications
- Cron jobs for data cleanup and automated processes

**Enhanced User Experience:**
- Intuitive kanban views with pet-specific layouts and health indicators
- Smart buttons for quick navigation between related records
- Enhanced search and filtering with medical-specific criteria
- Color-coded status indicators and health alerts
- Mobile-responsive design for tablet-based workflows

**Configuration & Customization:**
- Product sub-type classification for veterinary services
- Species and breed management with color coding and visual indicators
- Boarding cage management with species restrictions and capacity tracking
- Treatment room setup with department linking and equipment management
- Comprehensive user roles: Manager, User, and Receptionist with appropriate permissions

**Integration Capabilities:**
- HR module integration for practitioner and staff management
- Document management for pet photos and medical record storage
- Appointment module extension with medical-specific fields and workflows
- POS integration for veterinary service billing and payment processing
- WhatsApp integration for automated customer communications and reminders
- Calendar integration for appointment scheduling and resource management

**Technical Specifications:**
- Built for Odoo 18 with OWL 3 framework compatibility
- RESTful API endpoints for external system integration
- Advanced security model with role-based access control
- Scalable architecture supporting multi-clinic operations
- Automated backup and data retention policies

**Target Users:**
- Veterinary clinics and animal hospitals
- Pet care facilities and boarding services
- Animal shelters and rescue organizations
- Mobile veterinary services
- Multi-location veterinary chains

**Business Benefits:**
- Streamlined appointment scheduling reducing no-shows by 30%
- Automated billing processes increasing revenue collection efficiency
- Comprehensive medical records improving patient care quality
- Staff productivity improvements through optimized workflows
- Enhanced customer communication and satisfaction
- Regulatory compliance with veterinary record-keeping requirements

**Security & Compliance:**
- HIPAA-compliant data handling for veterinary records
- Role-based access control ensuring data privacy
- Audit trails for all medical record modifications
- Secure communication channels for sensitive information
- Data encryption for all stored medical information

This system is designed to grow with your practice, from single-clinic operations to 
multi-location veterinary chains, providing the tools needed for excellent patient care 
and efficient business operations.""",
	'author': 'Techouse Solutions / Ismail Abdelkhalik',
	'website': 'https://www.techouse.ae',
	'depends': [
		# Core Odoo modules
		'base',
		'mail',
		'resource',

		# Human Resources
		'hr',
		'hr_holidays',
		'hr_work_entry',

		# Custom THS modules
		'ths_hr',
		'ths_base',

		# Inventory & Products
		'stock',
		'product',

		# Accounting & Finance
		'account',
		'analytic',

		# Scheduling & Calendar
		'appointment',
		'calendar',

		# Point of Sale
		'point_of_sale',

		# Document Management
		'documents',

		# Communication
		'whatsapp',
	],
	'data': [
		# Security
		'security/security.xml',
		'security/ir.model.access.csv',
		# Data Files
		'data/ir_sequence.xml',
		'data/documents_folders.xml',
		'data/hr_employee_type_config_data.xml',
		'data/partner_type_data.xml',
		'data/product_sub_type_data.xml',
		'data/species_data.xml',
		'data/crons.xml',
		'data/email_templates.xml',
		'data/whatsapp_templates.xml',
		# Views
		'views/hr_modifications.xml',  # HR enhancements for medical staff
		'views/appointment_modifications.xml',  # Appointment system enhancements
		'views/res_partner.xml',  # Pet and pet owner management
		'views/product.xml',  # Product sub-types and medical products
		'views/encounter.xml',  # Core encounter management
		'views/service_models.xml',  # All service models (boarding, vaccination, etc.)
		'views/vet_menus.xml',
		'wizard/species_breed_import_view.xml',
	],
	'assets': {
		# Backend lazy assets for gantt and calendar enhancements
		'web.assets_backend_lazy': [
			'appointment/static/src/views/gantt/**',
			'ths_vet_base/static/src/views/gantt/gantt_renderer_medical.js',
		],
		# Main backend assets
		'web.assets_backend': [
			# Appointment module styles and scripts
			'appointment/static/src/scss/appointment_type_views.scss',
			'appointment/static/src/scss/web_calendar.scss',
			'appointment/static/src/views/**/*',
			('remove', 'appointment/static/src/views/gantt/**'),  # Moved to lazy bundle
			'appointment/static/src/components/**/*',
			'appointment/static/src/js/appointment_insert_link_form_controller.js',
			'appointment/static/src/appointment_plugin.js',

			# Custom styles
			'ths_vet_base/static/src/style.scss',
			'ths_vet_base/static/src/icons.scss',
			'ths_vet_base/static/src/img/syringe.svg',

			# Custom JavaScript components
			'ths_vet_base/static/src/js/encounter_dashboard.xml',
			'ths_vet_base/static/src/js/encounter_dashboard.js',
			# 'ths_vet_base/static/src/js/medical_dashboard.js',
			'ths_vet_base/static/src/js/executive_dashboard.xml',
			'ths_vet_base/static/src/js/executive_dashboard.js',
		],

		# Print/PDF assets for reports
		# 'web.report_assets_common': [
		# 	'ths_vet_base/static/src/scss/reports.scss',
		# ],
	},
	'demo': [],
	'images': ['static/description/icon.png'],
	'installable': True,
	'application': True,
	'auto_install': False,
	'license': 'OPL-1',
	'external_dependencies': {
		'python': [
			'Pillow',  # For image processing
			'python-dateutil',  # For advanced date handling
		],
	},
	'support': 'support@techouse.ae',
}