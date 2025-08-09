# Techouse Multi Branches Management

## Overview

The **Techouse Multi Branches Management** module for Odoo 18 transforms the standard "Company" terminology to "Branch"
across all key accounting models, views, and reports. This module is perfect for organizations that prefer to think in
terms of branches rather than companies while maintaining full compatibility with Odoo's native multi-company
functionality.

## Features

### 🏢 **Core Model Updates**

- **Account Moves (Invoices)**: Changes `company_id` field label from "Company" to "Branch"
- **Account Payments**: Updates payment records to use "Branch" terminology
- **Account Move Lines**: Journal items now display "Branch" instead of "Company"
- **Accounting Journals**: Journal configurations show "Branch" field
- **Chart of Accounts**: Account configurations use "Branches" terminology

### 📊 **Comprehensive Report Coverage**

- **Balance Sheet** - Financial position by branch
- **Profit and Loss Statement** - P&L analysis per branch
- **Cash Flow Statement** - Cash movements by branch
- **Executive Summary** - High-level branch performance
- **General Ledger** - Detailed transactions by branch
- **Trial Balance** - Account balances per branch
- **Tax Return** - Tax reporting by branch
- **Journal Audit** - Audit trails with branch context
- **Invoice Analysis** - Customer invoice analytics by branch
- **Analytic Reports** - Project/cost center analysis by branch
- **Budget Reports** - Budget vs actual by branch
- **Aged Receivables/Payables** - Outstanding amounts by branch
- **Partner Ledger** - Customer/supplier statements by branch

### 🎯 **Advanced Features**

- **JS Filter Integration**: All dynamic reports with JavaScript filters support branch selection
- **Multi-Branch Views**: Enhanced group-by and filtering options in list views
- **Search Integration**: Branch-based search and filtering across all views
- **Report Actions**: Updated menu items and report actions
- **Template Updates**: Modified QWeb templates for consistent branch terminology

## Installation

1. **Download** the module and place it in your Odoo addons directory
2. **Update** the module list in Odoo
3. **Install** the module from Apps menu
4. **Restart** Odoo server if required

## Technical Details

### Dependencies

- `account` - Core accounting functionality
- `base` - Odoo base system

### Compatibility

- **Odoo Version**: 18.0
- **Python Version**: 3.8+
- **Edition**: Community and Enterprise
- **Database**: PostgreSQL

### Architecture

```
ths_multi_branches/
├── __manifest__.py          # Module configuration
├── models/
│   ├── __init__.py
│   └── all_models.py        # Model inheritance for field string updates
├── views/
│   └── all_views.xml        # View inheritance for UI updates
├── reports/
│   └── all_reports.xml      # Report updates and filter modifications
├── static/description/
│   └── index.html           # Module description page
└── README.md               # This file
```

## Usage

### Setting Up Branches

1. **Navigate** to Settings > Companies > Manage Companies
2. **Create** new companies that will serve as your branches
3. **Configure** each branch with appropriate settings
4. **Assign** users to their respective branches

### Working with Branch Data

The module automatically updates all relevant views and reports to display "Branch" instead of "Company". All existing
functionality remains the same:

- **Creating Invoices**: Select branch from dropdown (labeled as "Branch")
- **Processing Payments**: Branch context is maintained throughout payment workflow
- **Running Reports**: All reports now show branch-based filtering and grouping
- **Analyzing Data**: Use branch filters in dynamic reports and analytics

### Multi-Branch Operations

Users with access to multiple branches can:

- **Switch** between branches using the standard company switcher (now shows branches)
- **Filter** reports by specific branches or view consolidated data
- **Group** data by branch in list views and reports
- **Search** across branches using enhanced search filters

## Configuration

### User Access

Branch access is managed through the standard Odoo multi-company mechanism:

1. **User Settings**: Assign allowed branches to users
2. **Default Branch**: Set user's default working branch
3. **Access Rights**: Use standard security groups and rules

### Report Configuration

All reports support branch filtering out of the box. For custom reports:

1. **Enable** `filter_multi_company` on custom account reports
2. **Add** branch context to report actions
3. **Update** view inheritance if needed

## Customization

### Adding New Models


## Troubleshooting

### Common Issues

**Branch field not updating**: Clear browser cache and restart Odoo
**Report filters not showing**: Ensure user has multi-company access
**Data not filtering**: Check user's allowed companies/branches

### Debug Mode

Enable developer mode to:

- Inspect field definitions
- Check view inheritance
- Debug report configurations

## Support and Maintenance

### Updates

- Module follows Odoo 18 standards and coding guidelines
- Regular updates for new Odoo releases
- Backward compatibility maintained where possible

### Bug Reports

For issues or feature requests, contact:

- **Website**: [https://www.techouse.ae](https://www.techouse.ae)
- **Email**: info@techouse.ae

## License

This module is licensed under the Odoo Proprietary License v1.0 (OPL-1).

## Credits

**Developed by**: Techouse Solutions  
**Author**: Ismail Abdelkhalik  
**Website**: [https://www.techouse.ae](https://www.techouse.ae)

---

© 2024 Techouse Solutions. All rights reserved.