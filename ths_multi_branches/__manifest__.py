# -*- coding: utf-8 -*-
{
	'name': 'Techouse Multi Branches Management',
	'version': '18.0.1.0.0',
	'author': 'Techouse Solutions / Ismail Abdelkhalik',
	'website': 'https://www.techouse.ae',
	'category': 'Accounting',
	'summary': 'Core customizations and fixes by Techouse Solutions',
	'description': """
        Techouse Multi Branches Management for Odoo 18
        ==============================================

        This module changes 'Company' field labels to 'Branch' across key accounting models and reports:

        **Features:**
        - Updates company_id field labels to 'Branch' in invoices and payments
        - Modifies all customer-facing accounting views
        - Updates all accounting reports (Balance Sheet, P&L, Cash Flow, etc.)
        - Maintains full Odoo standard multi-company functionality
        - Supports all dynamic reports with JS filters
        - Compatible with all standard Odoo accounting workflows

        **Affected Models:**
        - Customer Invoices (account.move)
        - Customer Payments (account.payment)
        - Related accounting transactions

        **Updated Reports:**
        - Balance Sheet
        - Profit and Loss Statement
        - Cash Flow Statement
        - Executive Summary
        - Tax Return
        - General Ledger
        - Trial Balance
        - Journal Audit
        - Invoice Analysis
        - Analytic Reports
        - Budget Reports
        - All reports with JS filters

        **Technical Notes:**
        - Only changes field strings, preserves all standard functionality
        - No impact on existing data or workflows
        - Fully compatible with Odoo's native multi-company features
        - Maintains proper access rights and security rules
    """,
	'depends': ['account', 'base'],
	'data': [
		'views/all_views.xml',
	],
	'installable': True,
	'application': True,
	'auto_install': False,
	'license': 'OPL-1',
}