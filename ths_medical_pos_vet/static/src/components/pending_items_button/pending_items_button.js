/** @odoo-module */

import {patch} from "@web/core/utils/patch";
import {PendingItemsButton} from "@ths_medical_pos/components/pending_items_button/pending_items_button";
import {_t} from "@web/core/l10n/translation";
import {makeAwaitable} from "@point_of_sale/app/store/make_awaitable_dialog";
import {PendingItemsListPopup} from "@ths_medical_pos/popups/pending_items_list_popup";

/**
 * IMPORTANT: This follows Odoo 18 OWL 3 component patching methodology.
 * This is the LATEST approach for extending existing components in veterinary modules.
 * Patches allow extending base medical functionality with vet-specific features.
 *
 * Veterinary-specific extension of PendingItemsButton
 * Extends base medical functionality to handle Pet/Owner relationships
 * Adds veterinary-specific UI adaptations and filtering logic
 */
patch(PendingItemsButton.prototype, {
    /**
     * Override onClick method to add veterinary-specific behavior
     * Enhanced to work with the updated base medical functionality
     * Adds Pet/Owner context for veterinary practices
     */
    async onClick() {
        console.log("Vet POS: Pending Items Button Clicked - Enhanced for Veterinary");

        const order = this.pos.get_order();
        if (!order) {
            console.error("No active order found");
            this.notification.add(
                _t('No active order found. Please try again.'),
                {type: 'danger', sticky: false, duration: 3000}
            );
            return;
        }

        const client = order.get_partner(); // This is the Pet Owner in vet context

        let popupTitle = _t('Pending Medical Items (All Pets)');
        let pendingItems = [];

        // Veterinary-specific filtering: Filter by Pet Owner if selected
        if (client?.id) {
            console.log(`Vet POS: Filtering pending items for Pet Owner: ${client.name} (ID: ${client.id})`);
            // Use the enhanced vet method for filtering
            pendingItems = this.pos.getPendingItems(client.id);
            popupTitle = _t("Pending Items for %(ownerName)s's Pets", {ownerName: client.name});
        } else {
            console.log("Vet POS: No Pet Owner selected, fetching all pending items for all pets.");
            pendingItems = this.pos.getPendingItems();
        }

        try {
            if (pendingItems && pendingItems.length > 0) {
                console.log('Vet POS: Opening PendingItemsListPopup with veterinary adaptations');

                // Use the imported PendingItemsListPopup from base module
                const payload = await makeAwaitable(this.dialog, PendingItemsListPopup, {
                    title: popupTitle, // Veterinary-specific title
                    items: pendingItems,
                });

                console.log("Vet POS: Popup opened successfully with veterinary adaptations");
            } else {
                // Veterinary-specific no-items message
                let message;
                if (client) {
                    message = _t('No pending medical items found for %(ownerName)s\'s pets.', {ownerName: client.name});
                } else {
                    message = _t('No pending medical items found for any pets. Note: Select a pet owner to filter items for specific pets.');
                }

                this.notification.add(message, {
                    type: 'info',
                    sticky: false,
                    duration: 4000
                });
            }

        } catch (error) {
            console.error("Vet POS: Error fetching or showing pending medical items:", error);

            // Enhanced error handling with veterinary context
            let errorMessage;
            if (error.message && error.message.includes('timeout')) {
                errorMessage = _t('Request timeout. Please check your connection and try again.');
            } else if (error.message && error.message.includes('permission')) {
                errorMessage = _t('Access denied. Please check your permissions for veterinary records.');
            } else {
                errorMessage = _t('Error fetching pending veterinary items: %(error)s', {error: error.message || 'Unknown error'});
            }

            this.notification.add(errorMessage, {type: 'danger', sticky: true});
        }
    }
});

// NOTE: No additional registry registration needed - this patches the existing component
// The base component is already registered in ths_medical_pos module

// TODO: Add vet-specific encounter filtering options
// TODO: Implement pet species-based service recommendations
// TODO: Add multi-pet family discount integration
// TODO: Implement vaccination status warnings in POS
// TODO: Consider adding pet health status indicators in the pending items display

console.log("Loaded vet button patch - compatible with updated base module:", "pending_items_button.js");