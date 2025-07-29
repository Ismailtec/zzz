/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, useState, onWillStart} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {_t} from "@web/core/l10n/translation";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";

class VetPosClientAction extends Component {
    static template = "ths_vet_base.PosInterface";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.dialog = useService("dialog");

        this.state = useState({
            encounter: {
                id: null,
                name: '',
                partner_id: null,
                patient_ids: [],
                practitioner_id: null,
                room_id: null,
                encounter_line_ids: [],
                company_currency: 'KWD'
            },
            productsByCategory: {},
            paymentMethods: [],
            cartItems: [],
            selectedCategory: null,
            selectedPaymentMethod: null,
            cartTotal: 0,
            filteredProducts: [],
            isLoading: true,
            globalDiscount: 0,
            globalDiscountType: 'percent',
            availablePatients: [],
            availablePractitioners: [],
            availableRooms: [],
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            const encounterId = this.props.action?.context?.encounter_id;

            if (encounterId) {
                const data = await this.orm.read(
                    "vet.encounter.header",
                    [encounterId],
                    ["id", "name", "partner_id", "patient_ids", "practitioner_id", "room_id", "encounter_line_ids", "company_currency"]
                );
                this.state.encounter = {...this.state.encounter, ...data[0]};
            }

            this.state.productsByCategory = await this.orm.call(
                "vet.encounter.header",
                "get_products_by_category",
                []
            );

            this.state.paymentMethods = await this.orm.call(
                "vet.encounter.header",
                "get_payment_methods_kanban",
                []
            );

            const categories = Object.keys(this.state.productsByCategory);
            if (categories.length > 0) {
                this.selectCategory(categories[0]);
            }

            await this.loadAvailableResources();

            if (this.state.encounter.encounter_line_ids && this.state.encounter.encounter_line_ids.length > 0) {
                await this.loadExistingLines();
            }

            this.state.isLoading = false;
        } catch (error) {
            console.error("Error loading POS data:", error);
            this.notification.add(_t("Error loading data: ") + error.message, {type: "danger"});
            this.state.isLoading = false;
        }
    }

    async loadAvailableResources() {
        try {
            if (this.state.encounter.patient_ids && this.state.encounter.patient_ids.length > 0) {
                const patientIds = this.state.encounter.patient_ids.map(p => Array.isArray(p) ? p[0] : p);
                this.state.availablePatients = await this.orm.read("res.partner", patientIds, ["id", "name"]);
            }

            this.state.availablePractitioners = await this.orm.call(
                "appointment.resource",
                "search_read",
                [[['resource_category', '=', 'practitioner'], ['active', '=', true]]],
                {fields: ["id", "name", "ths_department_id"]}
            );

            this.state.availableRooms = await this.orm.call(
                "appointment.resource",
                "search_read",
                [[['resource_category', '=', 'location'], ['active', '=', true]]],
                {fields: ["id", "name", "ths_department_id"]}
            );

        } catch (error) {
            console.error("Error loading resources:", error);
        }
    }

    async loadExistingLines() {
        const lineIds = this.state.encounter.encounter_line_ids;
        if (lineIds && lineIds.length > 0) {
            try {
                const lines = await this.orm.call("vet.encounter.line", "search_read", [
                    [
                        ['id', 'in', lineIds],
                        ['payment_status', 'in', ['pending', 'partial']],
                        ['remaining_amount', '>', 0]
                    ],
                    ["product_id", "qty", "unit_price", "remaining_amount", "practitioner_id", "room_id", "patient_ids", "discount"]
                ]);

                for (const line of lines) {
                    const product = await this.orm.read("product.product", [line.product_id[0]], ["name", "default_code", "image_128"]);

                    let practitionerName = '';
                    let roomName = '';
                    let patientNames = [];

                    if (line.patient_ids && line.patient_ids.length > 0) {
                        try {
                            const patients = await this.orm.read("res.partner", line.patient_ids, ["name"]);
                            patientNames = patients.map(p => p.name);
                        } catch (error) {
                            console.warn("Could not load patients:", error);
                        }
                    }

                    if (line.practitioner_id && line.practitioner_id.length > 0) {
                        try {
                            const practitioner = await this.orm.read("appointment.resource", [line.practitioner_id[0]], ["name"]);
                            if (practitioner.length > 0) {
                                practitionerName = practitioner[0].name;
                            }
                        } catch (error) {
                            console.warn("Could not load practitioner:", error);
                        }
                    }

                    if (line.room_id && line.room_id.length > 0) {
                        try {
                            const room = await this.orm.read("appointment.resource", [line.room_id[0]], ["name"]);
                            if (room.length > 0) {
                                roomName = room[0].name;
                            }
                        } catch (error) {
                            console.warn("Could not load room:", error);
                        }
                    }

                    this.state.cartItems.push({
                        id: `existing_${line.id}`,
                        encounter_line_id: line.id,
                        product_id: line.product_id[0],
                        name: product[0].name,
                        default_code: product[0].default_code,
                        price: line.remaining_amount / line.qty,
                        qty: line.qty,
                        discount: (line.discount || 0) * 100,
                        isExisting: true,
                        practitioner: practitionerName,
                        practitioner_id: line.practitioner_id ? line.practitioner_id[0] : null,
                        room: roomName,
                        room_id: line.room_id ? line.room_id[0] : null,
                        patients: patientNames,
                        patient_ids: line.patient_ids || [],
                    });
                }
                this.updateCartTotal();
            } catch (error) {
                console.error("Error loading existing lines:", error);
                this.notification.add(_t("Error loading existing items: ") + error.message, {type: "warning"});
            }
        }
    }

    selectCategory(category) {
        this.state.selectedCategory = category;
        this.state.filteredProducts = this.state.productsByCategory[category] || [];
    }

    addToCart(product) {
        const existingItem = this.state.cartItems.find(item => item.product_id === product.id && !item.isExisting);
        if (existingItem) {
            existingItem.qty += 1;
        } else {
            this.state.cartItems.push({
                id: `new_${Date.now()}_${product.id}`,
                product_id: product.id,
                name: product.name,
                default_code: product.default_code,
                price: product.lst_price,
                qty: 1,
                discount: 0.0,
                isExisting: false,
                practitioner: this.state.encounter.practitioner_id ? this.state.encounter.practitioner_id[1] : '',
                practitioner_id: this.state.encounter.practitioner_id ? this.state.encounter.practitioner_id[0] : null,
                room: this.state.encounter.room_id ? this.state.encounter.room_id[1] : '',
                room_id: this.state.encounter.room_id ? this.state.encounter.room_id[0] : null,
                patients: this.state.encounter.patient_ids ? this.state.encounter.patient_ids.map(p => p[1]) : [],
                patient_ids: this.state.encounter.patient_ids ? this.state.encounter.patient_ids.map(p => p[0]) : [],
                unsaved: true,
            });
        }
        this.updateCartTotal();
    }

    updateQuantity(itemId, change) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            if (typeof change === 'number') {
                const newQty = item.qty + change;
                if (newQty >= 1) {
                    item.qty = newQty;
                    this.updateCartTotal();
                }
            } else {
                const newQty = parseInt(change) || 1;
                if (newQty >= 1) {
                    item.qty = newQty;
                    this.updateCartTotal();
                }
            }
        }
    }

    updatePrice(itemId, newPrice) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.price = parseFloat(newPrice) || 0;
            this.updateCartTotal();
        }
    }

    updateDiscount(itemId, newDiscount) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.discount = parseFloat(newDiscount) || 0;
            this.updateCartTotal();
        }
    }

    getLineTotal(item) {
        const lineTotal = item.price * item.qty;
        const discountAmount = lineTotal * ((item.discount / 100) || 0);
        return lineTotal - discountAmount;
    }

    updateCartTotal() {
        let subtotal = this.state.cartItems.reduce((total, item) => {
            return total + this.getLineTotal(item);
        }, 0);

        let globalDiscountAmount = 0;
        if (this.state.globalDiscount > 0) {
            if (this.state.globalDiscountType === 'percent') {
                globalDiscountAmount = subtotal * (this.state.globalDiscount / 100);
            } else {
                globalDiscountAmount = this.state.globalDiscount;
            }
        }

        this.state.cartTotal = subtotal - globalDiscountAmount;
    }

    updateGlobalDiscount(discount) {
        this.state.globalDiscount = parseFloat(discount) || 0;
        this.updateCartTotal();
    }

    updateGlobalDiscountType(type) {
        this.state.globalDiscountType = type;
        this.updateCartTotal();
    }

    selectPaymentMethod(method) {
        this.state.selectedPaymentMethod = method;
    }

    formatCurrency(amount) {
        if (isNaN(amount) || amount === null || amount === undefined) {
            return 'KWD 0.000';
        }

        let currencyCode = 'KWD';
        if (this.state.encounter.company_currency) {
            const currencyStr = this.state.encounter.company_currency.toString();
            if (currencyStr.includes(',')) {
                currencyCode = currencyStr.split(',')[1];
            } else {
                currencyCode = currencyStr;
            }
        }

        const decimals = currencyCode === 'KWD' ? 3 : 2;

        try {
            return new Intl.NumberFormat('en-KW', {
                style: 'currency',
                currency: currencyCode,
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals,
            }).format(amount);
        } catch (error) {
            return `${currencyCode} ${amount.toFixed(decimals)}`;
        }
    }

    getAvailableRoomsForPractitioner(practitionerId) {
        if (!practitionerId) {
            return this.state.availableRooms;
        }

        const practitioner = this.state.availablePractitioners.find(p => p.id === practitionerId);
        if (practitioner && practitioner.ths_department_id) {
            const departmentId = Array.isArray(practitioner.ths_department_id) ? practitioner.ths_department_id[0] : practitioner.ths_department_id;
            return this.state.availableRooms.filter(room => {
                if (!room.ths_department_id) return false;
                const roomDeptId = Array.isArray(room.ths_department_id) ? room.ths_department_id[0] : room.ths_department_id;
                return roomDeptId === departmentId;
            });
        }

        return this.state.availableRooms;
    }

    updateLinePractitioner(itemId, practitionerId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.practitioner_id = practitionerId;
            if (practitionerId) {
                const practitioner = this.state.availablePractitioners.find(p => p.id === practitionerId);
                item.practitioner = practitioner ? practitioner.name : '';

                const availableRooms = this.getAvailableRoomsForPractitioner(practitionerId);
                if (item.room_id && !availableRooms.find(r => r.id === item.room_id)) {
                    item.room_id = null;
                    item.room = '';
                }
            } else {
                item.practitioner = '';
            }
        }
    }

    updateLineRoom(itemId, roomId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.room_id = roomId;
            if (roomId) {
                const room = this.state.availableRooms.find(r => r.id === roomId);
                item.room = room ? room.name : '';
            } else {
                item.room = '';
            }
        }
    }

    updateLinePatients(itemId, patientIds) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.patient_ids = patientIds;
            if (patientIds.length > 0) {
                const selectedPatients = this.state.availablePatients.filter(p => patientIds.includes(p.id));
                item.patients = selectedPatients.map(p => p.name);
            } else {
                item.patients = [];
            }
        }
    }

    togglePatientSelection(patientId) {
        if (!this.state.encounter.patient_ids) {
            this.state.encounter.patient_ids = [];
        }

        const currentIds = this.state.encounter.patient_ids.map(p => Array.isArray(p) ? p[0] : p);
        const patient = this.state.availablePatients.find(p => p.id === patientId);

        if (currentIds.includes(patientId)) {
            this.state.encounter.patient_ids = this.state.encounter.patient_ids.filter(p => {
                const id = Array.isArray(p) ? p[0] : p;
                return id !== patientId;
            });
        } else if (patient) {
            this.state.encounter.patient_ids.push([patient.id, patient.name]);
        }
    }

    toggleLinePatient(itemId, patientId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            if (item.patient_ids.includes(patientId)) {
                item.patient_ids = item.patient_ids.filter(id => id !== patientId);
            } else {
                item.patient_ids.push(patientId);
            }

            const selectedPatients = this.state.availablePatients.filter(p => item.patient_ids.includes(p.id));
            item.patients = selectedPatients.map(p => p.name);
        }
    }

    clearLinePractitioner(itemId) {
        this.updateLinePractitioner(itemId, null);
    }

    clearLineRoom(itemId) {
        this.updateLineRoom(itemId, null);
    }

    clearLinePatients(itemId) {
        this.updateLinePatients(itemId, []);
    }

    async removeFromCart(itemId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (!item) return;

        if (item.isExisting) {
            const choice = await new Promise((resolve) => {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Remove Item"),
                    body: _t("Do you want to remove this item from the current order only, or delete it from the encounter entirely?"),
                    confirmLabel: _t("Remove from Order Only"),
                    cancelLabel: _t("Delete from Encounter"),
                    confirm: () => resolve("order"),
                    cancel: () => resolve("encounter"),
                });
            });

            if (choice === "encounter") {
                try {
                    await this.orm.unlink("vet.encounter.line", [item.encounter_line_id]);
                    this.notification.add(_t("Item deleted from encounter"), {type: "success"});
                } catch (error) {
                    this.notification.add(_t("Error deleting item: ") + error.message, {type: "danger"});
                    return;
                }
            }
        }

        const index = this.state.cartItems.findIndex(i => i.id === itemId);
        if (index > -1) {
            this.state.cartItems.splice(index, 1);
            this.updateCartTotal();
        }
    }

    async processPayment() {
        if (!this.state.selectedPaymentMethod) {
            this.notification.add(_t("Please select a payment method"), {type: "warning"});
            return;
        }
        if (!this.state.cartItems.length) {
            this.notification.add(_t("Cart is empty"), {type: "warning"});
            return;
        }

        try {
            console.log("Starting payment process...");

            const newItems = this.state.cartItems.filter(item => !item.isExisting);
            for (const item of newItems) {
                const patientIds = item.patient_ids?.length ? item.patient_ids : [];

                await this.orm.call("vet.encounter.header", "add_product_to_encounter_kanban", [this.state.encounter.id], {
                    product_id: item.product_id,
                    qty: item.qty,
                    patient_ids: patientIds,
                    discount: item.discount / 100 || 0.0,
                    practitioner_id: item.practitioner_id,
                    room_id: item.room_id,
                });
            }

            console.log("Processing payment...");

            const result = await this.orm.call("vet.encounter.header", "process_payment_kanban_ui", [this.state.encounter.id], {
                payment_method_id: this.state.selectedPaymentMethod.id,
            });

            console.log("Payment result:", result);

            // FIX #6: Handle result properly without throwing
            if (result && result.success === true) {
                this.notification.add(result.message || _t("Payment processed successfully!"), {type: "success"});
                setTimeout(() => {
                    window.close();
                }, 1500);
            } else {
                // Don't throw, just show notification
                const errorMsg = result?.message || result?.error || "Payment processing failed - unknown error";
                this.notification.add(_t("Error: ") + errorMsg, {type: "danger"});
            }
        } catch (error) {
            console.error("Payment processing error:", error);
            this.notification.add(_t("Error processing payment: ") + error.message, {type: "danger"});
        }
    }

    getGlobalDiscountAmount() {
        let subtotal = this.state.cartItems.reduce((total, item) => {
            return total + this.getLineTotal(item);
        }, 0);

        if (this.state.globalDiscount > 0) {
            if (this.state.globalDiscountType === 'percent') {
                return subtotal * (this.state.globalDiscount / 100);
            } else {
                return this.state.globalDiscount;
            }
        }
        return 0;
    }
}

registry.category("actions").add("vet_pos_interface_action", VetPosClientAction);