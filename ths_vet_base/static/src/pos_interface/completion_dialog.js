/** @odoo-module **/

import {Component} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";

export class CompletionDialog extends Component {
    static template = "ths_vet_base.CompletionDialog";
    static components = {Dialog};

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    async onPrintInvoice() {
        try {
            if (this.props.invoiceId) {
                // Print invoice report
                await this.action.doAction({
                    type: 'ir.actions.report',
                    report_name: 'account.report_invoice',
                    report_type: 'qweb-pdf',
                    data: {
                        'report_type': 'pdf'
                    },
                    context: {
                        'active_ids': [this.props.invoiceId],
                        'active_model': 'account.move',
                    }
                });
            }
            this.props.close();
            this.props.onClose?.();
        } catch (error) {
            console.error("Print error:", error);
            this.notification.add(_t("Error printing invoice"), {type: "warning"});
            this.props.close();
            this.props.onClose?.();
        }
    }

    onNewOrder() {
        this.props.close();
        this.props.onNewOrder?.();
    }

    onCloseOnly() {
        this.props.close();
        this.props.onClose?.();
    }
}