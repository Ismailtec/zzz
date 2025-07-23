/** @odoo-module **/

import {ControlPanel} from "@web/search/control_panel/control_panel";
import {patch} from "@web/core/utils/patch";

patch(ControlPanel.prototype, {
    setup() {
        super.setup();
    },

    _onRefreshClick() {
        // Access the current view's model through the environment
        if (this.env.model && this.env.model.load) {
            // For most views (list, form, kanban, etc.)
            this.env.model.load();
        } else if (this.env.searchModel) {
            // Alternative: trigger search to refresh
            this.env.searchModel.search();
        } else {
            // Last resort: refresh the whole browser tab content
            window.location.reload();
        }
    }
});