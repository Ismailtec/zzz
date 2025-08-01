# -*- coding: utf-8 -*-
{
	'name': 'Techouse Base',
	'version': '18.0.1.0.0',
	'category': 'Base/Customization',
	'summary': 'Core customizations and fixes by Techouse Solutions',
	'description': """
Techouse Base (ths_base) for Odoo 18 introduces several core enhancements primarily focused on inventory and accounting date control, purchasing flexibility, landed cost management, and UI adjustments. Key features include an "Effective Date" field across Purchases, Inventory operations (Receipts, Scraps, Adjustments), and Landed Costs, allowing users to backdate transactions and ensure associated accounting entries reflect the chosen date. It modifies vendor selection for replenishment to prioritize manually flagged vendors or fallback to the lowest price. Landed cost workflow is improved with better linking to POs/Bills, automated creation/updates, and a safe reversal mechanism. Additionally, it adds a Product Brand field and provides a global configuration option to hide tax-related columns in various views and reports.
Detailed Feature List (User-Friendly)

    Global Settings:
        Adds an option in Accounting Settings to hide tax columns by default on Sales Orders, Purchase Orders, and Invoices/Bills lines.

    Product Setup:

        Adds a "Product Brand" field to the product form.
        Adds a "Priority" checkbox to the vendor list on the product's Purchase tab.
        Automatically sorts the vendor list by lowest price first by default.
        When replenishing stock, the system will choose the vendor marked as "Priority" (if sequence is 1), otherwise it selects the lowest priced vendor.

    Effective Date Feature:
        Adds an "Effective Date" field to Purchase Orders, Receipts/Transfers, Scraps, Inventory Adjustments, and Landed Costs.
        This date controls when the related inventory moves and accounting entries are recorded, allowing for backdating.
        The date set on a Purchase Order automatically flows to the linked Receipt and its inventory moves.

    Landed Cost Enhancements:
        Adds an "Effective Date" field to control the accounting date.
        Improves linking between Landed Costs and Purchase Orders.
        Automatically filters Vendor Bills and Receipts based on the selected Purchase Order.
        Can auto-fill related documents and cost lines when creating Landed Costs.
        Provides a safe "Cancel" button (replaces standard one) that creates a reversing entry for posted Landed Costs.
        Can automatically create or update a draft Landed Cost when a Purchase Order is confirmed or a Vendor Bill is posted (if they contain products designated as landed costs).

    Linking & Navigation:
        Adds a "Landed Costs" smart button to Vendor Bills, Purchase Orders, and Receipts for easy access to related records.

    Interface Adjustments:
        Conditionally hides tax columns in order/invoice lines based on the global setting.
        Makes the "Discount" column optional (can be hidden/shown) on order lines.
        Hides packaging-related fields on order lines by default.
        Adds the "Product Brand" field to the product form.
        Adds the "Priority" checkbox to the vendor list view.
        Adds the "Effective Date" field to relevant forms.
        Relocates the "Valuation Adjustments" section on the Landed Cost form for better flow.
        Adds the "Description" column to the Inventory Valuation report view.
        
    Reporting:
        Includes code intended to modify standard PDF reports (Sales Order, Purchase Order, Invoice) based on the "Hide Taxes" setting (marked as needing potential fixes).
    """,
	'author': 'Techouse Solutions / Ismail Abdelkhalik',
	'website': 'https://www.techouse.ae',
	'depends': [
		'base',
		'contacts',
		'mail',
		'account',
		'stock',
		'sale',
		'sale_management',
		'sale_stock',
		'spreadsheet_sale_management',
		'purchase',
		'purchase_stock',
		'stock_account',
		'stock_landed_costs',
		'product',
		'web',
		'web_chatter_position',
	],
	'data': [
		# Security files first
		'security/ir.model.access.csv',
		'security/security.xml',
		# Data files
		'data/ir_sequence.xml',
		'data/partner_type_data.xml',
		'data/global_discount_data.xml',
		# Views
		'views/partner_type.xml',
		'views/account_payment.xml',
		'views/purchase_order.xml',
		'views/sales_order.xml',
		'views/account_move.xml',
		'views/stock_picking.xml',
		'views/stock_quant.xml',
		'views/stock_scrap.xml',
		'views/stock_landed_cost.xml',
		'views/stock_valuation_layer.xml',
		'views/product.xml',
		'views/product_category.xml',
		'views/product_service.xml',
		'views/res_config.xml',
		'views/reports.xml',
		'views/invoice_report.xml',
		'views/res_partner.xml',
		'views/menus.xml',
	],
	'assets': {
		'web.assets_backend': [
			'ths_base/static/src/color_picker.scss',
			'ths_base/static/src/color_picker.js',
			'ths_base/static/src/base_enhancements.xml',
			'ths_base/static/src/base_enhancements.js',
		],
	},
	'installable': True,
	'application': True,
	'auto_install': False,
	'license': 'OPL-1',
}