# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Journal Entries Report',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Print Journal Entries pdf report.',
    'description': """
    journal entry
    print journal entry 
    journal entries
    print journal entry reports
    account journal entry reports
    journal reports
    account entry reports
""",
    'license': 'LGPL-3',
    'price': 000,
    'currency': 'USD',
    'author': 'Waleed Mohsen',
    'support': 'mohsen.waleed@gmail.com',
    'depends': ['base', 'account'],
    'data': [
        'report/report_journal_entry.xml',
    ],
    'installable': True,
    'auto_install': False,
    "images": ["static/description/main_screenshot.png"],
}
