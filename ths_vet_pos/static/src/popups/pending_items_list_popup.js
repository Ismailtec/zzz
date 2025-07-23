/** @odoo-module */

import {Component} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";

export class PendingItemsListPopup extends Component {
    constructor(...args) {
        console.log('PendingItemsListPopup: constructed with', args);
        super(...args);
    }

    static template = "ths_medical_pos.PendingItemsListPopup";
    static components = {Dialog};

    static props = {
        title: {type: String, optional: true},
        items: {type: Array, optional: true},
        close: Function,
        getPayload: {type: Function, optional: true},
    };

    static defaultProps = {
        title: _t("Pending Medical Items"),
        items: [],
    };

    setup() {
        console.log("PendingItemsListPopup: setup called");
        this.pos = usePos();
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    getProductById(productId) {
        try {
            // Use preloaded product data
            return this.pos.models["product.product"].get(productId);
        } catch (error) {
            console.error("Error accessing product by ID:", error);
            return null;
        }
    }

    async addProductToOrder(order, product, options = {}) {
        try {
            console.log("=== ERROR-FREE ODOO 18 ORDERLINE CREATION ===");
            console.log("Order lines before:", order.get_orderlines().length);

            const OrderLineModel = this.pos.models['pos.order.line'];
            // FIX A: Handle error without throwing locally caught exception
            if (!OrderLineModel) {
                console.error("pos.order.line model not found");
                return null;
            }

            // Prepare complete orderline data - keep what works
            const lineData = {
                order_id: order,
                product_id: product,
                qty: options.quantity || 1,
                price_unit: options.price || product.lst_price || 0,
                discount: options.discount || 0,
                // Add medical extras
                ...(options.extras || {})
            };

            console.log("Creating orderline with data:", lineData);

            // WORKING METHOD: Use only OrderLineModel.create()
            const newOrderline = OrderLineModel.create(lineData);
            console.log("Created orderline instance:", newOrderline);

            // Verify it was added correctly
            const linesAfter = order.get_orderlines();
            console.log("Order lines after create():", linesAfter.length);

            if (linesAfter.length > 0) {
                const lastLine = order.get_last_orderline();
                console.log("Last orderline:", lastLine);

                if (lastLine && lastLine.product_id && lastLine.product_id.id === product.id) {
                    console.log("✅ SUCCESS: Orderline automatically added to order by create()!");
                    return lastLine;
                }
            }

            // FIX A: Log error instead of throwing locally caught exception
            console.error("OrderLineModel.create() did not add line to order as expected");
            return null;

        } catch (error) {
            console.error("❌ ERROR in addProductToOrder:", error);
            return null;
        }
    }

    async setOrderlineNoteSafely(orderline, description) {
        if (!description || !orderline) {
            return;
        }

        try {
            // Method 1: Try direct property setting first (least reactive)
            if (orderline.note !== undefined) {
                orderline.note = description;
                console.log("✅ Set note via direct property");
                return;
            }

            // Method 2: Try setNote if available, with delay to avoid reactive conflicts
            if (typeof orderline.setNote === 'function') {
                setTimeout(() => {
                    try {
                        orderline.setNote(description);
                        console.log("✅ Set note via setNote (delayed)");
                    } catch (delayedError) {
                        console.log("⚠️ Delayed setNote failed:", delayedError.message);
                    }
                }, 100);
                return;
            }

            console.log("ℹ️ No note setting method available on orderline");

        } catch (error) {
            console.log("⚠️ Could not set note safely:", error.message);
        }
    }

    async addItemToOrder(item) {
        console.log("=== ADDING MEDICAL ITEM TO ORDER WITH ENCOUNTER INTEGRATION ===");
        console.log("Item:", item);

        const order = this.pos.get_order();

        // Extract product ID from the array format [id, name]
        const productId = Array.isArray(item.product_id) ? item.product_id[0] : item.product_id;
        const product = this.getProductById(productId);

        if (!product) {
            const productName = Array.isArray(item.product_id) ? item.product_id[1] : "Unknown";
            this.notification.add(
                _t("Product %s not found in POS", productName),
                {type: "danger"}
            );
            return;
        }

        // Check customer consistency
        const currentPartner = order.get_partner();
        const itemPartnerId = Array.isArray(item.partner_id) ? item.partner_id[0] : item.partner_id;

        if (currentPartner && currentPartner.id !== itemPartnerId) {
            const itemPartnerName = Array.isArray(item.partner_id) ? item.partner_id[1] : "Unknown";
            this.notification.add(
                _t("Item is for %s, current customer is %s. Proceeding anyway.",
                    itemPartnerName, currentPartner.name),
                {type: "warning"}
            );
        }

        try {
            const orderline = await this.addProductToOrder(order, product, {
                quantity: item.qty,
                price: item.price_unit,
                discount: item.discount || 0,
                extras: {
                    ths_pending_item_id: item.id,
                    patient_ids: Array.isArray(item.patient_ids) ? item.patient_ids[0]?.[0] : item.patient_ids,
                    provider_id: Array.isArray(item.practitioner_id) ? item.practitioner_id[0] : item.practitioner_id,
                    ths_commission_pct: item.commission_pct || 0,
                    encounter_id: Array.isArray(item.encounter_id) ? item.encounter_id[0] : item.encounter_id,
                },
            });

            // FIX A: Check result instead of throwing locally caught exception
            if (!orderline) {
                console.error("Failed to create orderline");
                this.notification.add(
                    _t("Could not add item to order: Failed to create order line"),
                    {type: "danger"}
                );
                return;
            }

            // Update order header with encounter data if not already set
            const encounterId = Array.isArray(item.encounter_id) ? item.encounter_id[0] : item.encounter_id;
            if (encounterId && !order.encounter_id) {
                order.encounter_id = encounterId;

                // Get encounter data from preloaded data
                const encounter = this.pos.models["ths.medical.base.encounter"]?.get(encounterId);
                if (encounter) {
                    order.patient_ids = encounter.patient_ids || [];
                    order.practitioner_id = encounter.practitioner_id || null;
                    order.room_id = encounter.room_id || null;
                }
            }

            await this.setOrderlineNoteSafely(orderline, item.description);

            console.log("⚠️ NOTE: Item will be marked as 'processed' only when order is paid/finalized");
            this.notification.add(_t("Item added to order and linked to encounter"), {type: "success"});

            // Remove from popup - update preloaded data
            this.pos.models["ths.pending.pos.item"]?.delete(item.id);
            const index = this.props.items.findIndex(i => i.id === item.id);
            if (index !== -1) {
                this.props.items.splice(index, 1);
            }

            // Close popup if empty
            if (!this.props.items.length) {
                this.props.close();
            }

        } catch (error) {
            console.error("❌ ERROR adding item to order:", error);
            this.notification.add(
                _t("Could not add item to order: %s", error.message || 'Unknown error'),
                {type: "danger"}
            );
        }
    }

    cancel() {
        this.props.close();
    }

    close() {
        this.props.close();
    }

    get itemsToShow() {
        return this.props.items;
    }

    formatCurrency(amount) {
        try {
            // FIX D: Ensure amount is properly typed
            const numAmount = parseFloat(String(amount || 0));

            // FIX B & C: Use proper Odoo 18 POS currency formatting
            if (this.pos && this.pos.currency) {
                const decimalPlaces = this.pos.currency.decimal_places || 2;
                const formattedAmount = numAmount.toFixed(decimalPlaces);
                const symbol = this.pos.currency.symbol || '';

                // Use Odoo's position setting if available
                if (this.pos.currency.position === 'before') {
                    return symbol + formattedAmount;
                } else {
                    return formattedAmount + symbol;
                }
            } else {
                // Fallback formatting
                return numAmount.toFixed(2);
            }
        } catch (error) {
            console.error("Error formatting currency:", error);
            // FIX D: Ensure proper type conversion
            return parseFloat(String(amount || 0)).toFixed(2);
        }
    }
}

console.log("Loaded pending_items_list_popup.js", "pending_items_list_popup.js");