/** @odoo-module */

/**
 * IMPORTANT: This follows Odoo 18 OWL 3 patching methodology using @web/core/utils/patch.
 * This is the LATEST required approach for extending existing POS screens in Odoo 18.
 * The patch system allows extending components without breaking inheritance chains.
 */
import {patch} from "@web/core/utils/patch";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {PendingItemsButton} from "@ths_medical_pos/components/pending_items_button/pending_items_button";

/**
 * Patch ProductScreen to add medical functionality for base medical practices
 * Adds PendingItemsButton component to the ProductScreen interface
 */

patch(ProductScreen, {
    // REQUIRED: Components must be extended, not replaced
    components: {
        ...ProductScreen.components,
        PendingItemsButton,
    },

    setup() {
        super.setup();
        console.log("Medical POS: ProductScreen patched successfully with medical components");
    },

    // Helper method to get medical context from current order
    getMedicalContext() {
        const order = this.pos.get_order();
        return order ? order.medical_context || {} : {};
    },

    // Helper method to check if order has medical context
    hasMedicalContext() {
        const context = this.getMedicalContext();
        return !!(context.encounter_id || context.patient_ids?.length);
    },

    // Helper method to format medical context for display
    formatMedicalContextDisplay() {
        const context = this.getMedicalContext();
        const display = {
            encounter_name: context.encounter_name || '',
            patient_names: [],
            practitioner_name: '',
            room_name: ''
        };

        // Format patient names
        if (context.patient_ids) {
            display.patient_names = this.pos.formatPatientIds(context.patient_ids);
        }

        // Format practitioner name
        if (context.practitioner_id && Array.isArray(context.practitioner_id)) {
            display.practitioner_name = context.practitioner_id[1];
        }

        // Format room name
        if (context.room_id && Array.isArray(context.room_id)) {
            display.room_name = context.room_id[1];
        }

        return display;
    }
});

console.log("Medical POS: ProductScreen enhanced with base medical functionality");

    // TODO: Add encounter service history popup in POS
    // TODO: Implement encounter-based product recommendations
    // TODO: Add encounter payment plan selection in POS
    // TODO: Implement encounter insurance validation in POS
    // TODO: Add encounter mobile POS integration
    // TODO: Implement encounter offline mode support

