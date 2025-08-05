/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Component, onWillStart, useState} from "@odoo/owl";
import {CompletionDialog} from "@ths_vet_base/pos_interface/completion_dialog";
import {useService} from "@web/core/utils/hooks";
import {scanBarcode} from "@web/core/barcode/barcode_dialog";
import {isBarcodeScannerSupported} from "@web/core/barcode/barcode_video_scanner";
import {_t} from "@web/core/l10n/translation";

class VetPosClientAction extends Component {
    static template = "ths_vet_base.PosInterface";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.isBarcodeScannerSupported = isBarcodeScannerSupported;

        this.state = useState({
            encounter: {
                id: null,
                name: '',
                partner_id: null,
                patient_ids: [],
                practitioner_id: null,
                room_id: null,
                encounter_line_ids: [],
                company_currency: 'KWD',
            },
            productsByCategory: {},
            paymentMethods: [],
            cartItems: [],
            selectedCategory: null,
            selectedPaymentMethods: [],
            cartTotal: 0,
            filteredProducts: [],
            isLoading: true,
            availablePatients: [],
            availablePractitioners: [],
            availableRooms: [],
            sourceModel: 'manual_pos',
            isProcessingPayment: false,
            paymentCompleted: false,
            searchProductWord: '',
            scanning: false,
            globalDiscount: 0,
            globalDiscountType: 'percent',
            paymentAmount: 0,
            customerCredit: 0,
            paymentDistribution: {credit: 0, remaining: 0, otherMethods: []},
            paymentAmountManuallySet: false,
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
                const encounter_data = data[0];
                if (encounter_data.patient_ids && encounter_data.patient_ids.length > 0) {
                    const patientIds = encounter_data.patient_ids.map(p => parseInt(Array.isArray(p) ? p[0] : p));
                    const patients = await this.orm.read("res.partner", patientIds, ["id", "name"]);
                    encounter_data.patient_ids = patients.map(p => [p.id, p.name]); // Ensure numeric IDs
                }
                this.state.encounter = {...this.state.encounter, ...encounter_data};
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
            if (this.state.encounter.partner_id) {
                try {
                    const creditInfo = await this.orm.call("res.partner", "get_credit_balance", [this.state.encounter.partner_id[0]]);
                    const availableCredit = creditInfo.available_credit || 0;

                    // Use the credit amount as-is (should be positive for available credit)
                    this.state.customerCredit = availableCredit;

                    console.log('Available credit from backend:', availableCredit);
                    console.log('Customer credit set to:', this.state.customerCredit);
                } catch (error) {
                    console.warn("Could not load credit balance:", error);
                    this.state.customerCredit = 0;
                }
            }

            const categories = Object.keys(this.state.productsByCategory);
            if (categories.length > 0) {
                this.selectCategory(categories[0]);
            }

            await this.loadAvailableResources();

            if (this.state.encounter.encounter_line_ids && this.state.encounter.encounter_line_ids.length > 0) {
                await this.loadExistingLines();
            }

            this.updateCartTotal();
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
                const patientIds = this.state.encounter.patient_ids.map(p => parseInt(Array.isArray(p) ? p[0] : p));
                this.state.availablePatients = await this.orm.read("res.partner", patientIds, ["id", "name"]);
                this.state.availablePatients = this.state.availablePatients.map(p => ({
                    id: parseInt(p.id),
                    name: p.name
                }));
            }

            this.state.availablePractitioners = await this.orm.call(
                "appointment.resource",
                "search_read",
                [[['resource_category', '=', 'practitioner'], ['active', '=', true]],
                    ["id", "name", "ths_department_id"]]
            );

            this.state.availableRooms = await this.orm.call(
                "appointment.resource",
                "search_read",
                [[['resource_category', '=', 'location'], ['active', '=', true]],
                    ["id", "name", "ths_department_id"]]
            );
        } catch (error) {
            console.error("Error loading resources:", error);
        }
    }

    getFilteredRoomsForHeader() {
        if (!this.state.encounter.practitioner_id || !this.state.encounter.practitioner_id[0]) {
            return this.state.availableRooms;
        }

        const practitioner = this.state.availablePractitioners.find(p => p.id === this.state.encounter.practitioner_id[0]);
        if (!practitioner || !practitioner.ths_department_id) {
            return this.state.availableRooms;
        }

        const practitionerDept = practitioner.ths_department_id[0];
        return this.state.availableRooms.filter(room =>
            !room.ths_department_id || room.ths_department_id[0] === practitionerDept
        );
    }

    getFilteredRoomsForLine(practitionerId) {
        if (!practitionerId) {
            return this.state.availableRooms;
        }

        const practitioner = this.state.availablePractitioners.find(p => p.id === practitionerId);
        if (!practitioner || !practitioner.ths_department_id) {
            return this.state.availableRooms;
        }

        const practitionerDept = practitioner.ths_department_id[0];
        return this.state.availableRooms.filter(room =>
            !room.ths_department_id || room.ths_department_id[0] === practitionerDept
        );
    }

    updateHeaderPractitioner(ev) {
        const practitionerId = parseInt(ev.target.value) || null;
        const oldPractitionerId = this.state.encounter.practitioner_id ? this.state.encounter.practitioner_id[0] : null;

        if (practitionerId) {
            const practitioner = this.state.availablePractitioners.find(p => p.id === practitionerId);
            this.state.encounter.practitioner_id = [practitioner.id, practitioner.name];

            const availableRooms = this.getFilteredRoomsForHeader();
            if (this.state.encounter.room_id && !availableRooms.find(r => r.id === this.state.encounter.room_id[0])) {
                this.state.encounter.room_id = null;
            }
        } else {
            this.state.encounter.practitioner_id = null;
            this.state.encounter.room_id = null;
        }

        if (oldPractitionerId !== (this.state.encounter.practitioner_id ? this.state.encounter.practitioner_id[0] : null)) {
            this.state.encounter.hasChanges = true;
        }

        this.updateNewItemsWithHeaderValues();
    }

    updateHeaderRoom(ev) {
        const roomId = parseInt(ev.target.value) || null;
        const oldRoomId = this.state.encounter.room_id ? this.state.encounter.room_id[0] : null;

        if (roomId) {
            const room = this.state.availableRooms.find(r => r.id === roomId);
            this.state.encounter.room_id = [room.id, room.name];
        } else {
            this.state.encounter.room_id = null;
        }

        if (oldRoomId !== (this.state.encounter.room_id ? this.state.encounter.room_id[0] : null)) {
            this.state.encounter.hasChanges = true;
        }

        this.updateNewItemsWithHeaderValues();
    }

    updateNewItemsWithHeaderValues() {
        this.state.cartItems.forEach(item => {
            if (!item.isExisting && !item.isGlobalDiscount) {
                // Update practitioner
                if (this.state.encounter.practitioner_id) {
                    item.practitioner_id = this.state.encounter.practitioner_id[0];
                    item.practitioner = this.state.encounter.practitioner_id[1];
                }
                // Update room
                if (this.state.encounter.room_id) {
                    item.room_id = this.state.encounter.room_id[0];
                    item.room = this.state.encounter.room_id[1];
                }
                // Update patients
                if (this.state.encounter.patient_ids) {
                    item.patient_ids = this.state.encounter.patient_ids.map(p => p[0]);
                    item.patients = this.state.encounter.patient_ids.map(p => p[1]);
                }
            }
        });
    }


    async loadExistingLines() {
        const lineIds = this.state.encounter.encounter_line_ids;
        if (lineIds && lineIds.length > 0) {
            try {
                const lines = await this.orm.call("vet.encounter.line", "search_read", [
                    [
                        ['id', 'in', lineIds],
                        ['payment_status', 'in', ['pending', 'partial']],
                        ['remaining_qty', '>', 0]
                    ],
                    ["id", "product_id", "qty", "unit_price", "remaining_qty", "practitioner_id", "room_id", "patient_ids",
                        "discount", "payment_status"]
                ]);

                for (const line of lines) {
                    const product = await this.orm.read("product.product", [line.product_id[0]], ["name", "default_code", "image_128"]);

                    let practitionerName = '';
                    let roomName = '';
                    let patientNames = [];
                    let patientIds = [];

                    if (line.patient_ids && line.patient_ids.length > 0) {
                        try {
                            const patients = await this.orm.read("res.partner", line.patient_ids, ["name"]);
                            patientNames = patients.map(p => p.name);
                            patientIds = line.patient_ids.map(id => parseInt(id));
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
                        price: line.unit_price,
                        qty: line.qty,
                        discount: (line.discount || 0) * 100,
                        remaining_qty: line.remaining_qty,
                        isExisting: true,
                        practitioner: practitionerName,
                        practitioner_id: line.practitioner_id ? line.practitioner_id[0] : null,
                        room: roomName,
                        room_id: line.room_id ? line.room_id[0] : null,
                        patients: patientNames,
                        patient_ids: patientIds,
                        sourceModel: 'manual_pos',
                        isGlobalDiscount: product[0].default_code === 'DISC'
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
        if (category === 'All') {
            this.state.filteredProducts = this.state.productsByCategory[category] || [];
        } else {
            this.state.filteredProducts = this.state.productsByCategory[category] || [];
        }
    }

    addToCart(product) {
        const existingItem = this.state.cartItems.find(item => item.product_id === product.id && !item.isExisting);
        if (existingItem) {
            existingItem.qty += 1;
        } else {
            const patientIds = this.state.encounter.patient_ids ?
                this.state.encounter.patient_ids.map(p => parseInt(Array.isArray(p) ? p[0] : p)).filter(id => !isNaN(id)) : [];

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
                patient_ids: patientIds,
                source_model: 'manual_pos',
                unsaved: true,
            });
        }
        this.updateCartTotal();
    }

    updateQuantity(itemId, change) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            const oldQty = item.qty;

            if (typeof change === 'number') {
                const newQty = item.qty + change;
                if (newQty >= 1) {
                    item.qty = newQty;
                }
            } else {
                const newQty = parseInt(change) || 1;
                if (newQty >= 1) {
                    item.qty = newQty;
                }
            }

            if (item.isExisting && oldQty !== item.qty) {
                item.hasChanges = true;
            }

            this.updateCartTotal();
        }
    }

    updatePrice(itemId, newPrice) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            const oldPrice = item.price;
            item.price = parseFloat(newPrice) || 0;

            if (item.isExisting && oldPrice !== item.price) {
                item.hasChanges = true;
            }

            this.updateCartTotal();
        }
    }

    async updateDiscount(itemId, newDiscount) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            const oldDiscount = item.discount;
            item.discount = parseFloat(newDiscount) || 0;

            if (item.isExisting && oldDiscount !== item.discount) {
                item.hasChanges = true;
            }

            // Auto-recalculate global discount if it exists
            if (this.state.globalDiscount > 0) {
                this.removeGlobalDiscountFromCart();
                await this.addGlobalDiscountToCart();
            }

            this.updateCartTotal();
        }
    }

    getLineTotal(item) {
        if (item.isGlobalDiscount) {
            return item.price; // Already negative
        }

        const lineTotal = item.price * item.qty;
        const discountAmount = lineTotal * ((item.discount / 100) || 0);
        return lineTotal - discountAmount;
    }

    updatePaymentAmount(amount) {
        this.state.paymentAmount = Math.min(parseFloat(amount) || 0, this.state.cartTotal);
        this.state.paymentAmountManuallySet = true;
        this.updatePaymentDistribution();
    }

    updateCartTotal() {
        this.state.cartTotal = this.state.cartItems.reduce((total, item) => {
            return total + this.getLineTotal(item);
        }, 0);
        this.state.cartTotal = Math.max(0, this.state.cartTotal);

        if (!this.state.paymentAmountManuallySet || this.state.paymentAmount > this.state.cartTotal) {
            this.state.paymentAmount = this.state.cartTotal;
            this.state.paymentAmountManuallySet = false;
        }

        this.updatePaymentDistribution();
    }

    updatePaymentDistribution() {
        const totalAmount = this.state.cartTotal;
        let remainingAmount = totalAmount;

        this.state.paymentDistribution = {
            credit: 0,
            remaining: totalAmount,
            otherMethods: []
        };

        const creditMethod = this.state.selectedPaymentMethods.find(m => m.is_credit);
        if (creditMethod && this.state.customerCredit > 0) {
            const creditUsed = Math.min(this.state.customerCredit, totalAmount);
            remainingAmount = Math.max(0, totalAmount - creditUsed);

            this.state.paymentDistribution = {
                credit: creditUsed,
                remaining: remainingAmount,
                otherMethods: this.state.selectedPaymentMethods.filter(m => !m.is_credit)
            };
        }

        // Only update payment amount if not manually set
        if (!this.state.paymentAmountManuallySet) {
            this.state.paymentAmount = this.state.paymentDistribution.remaining;
        }

        this.render();
    }

    getTotalDiscountAmount() {
        let totalDiscount = 0;

        this.state.cartItems.forEach(item => {
            if (item.isGlobalDiscount) {
                totalDiscount += Math.abs(item.price);
            } else {
                const lineTotal = item.price * item.qty;
                const lineDiscount = lineTotal * ((item.discount / 100) || 0);
                totalDiscount += lineDiscount;
            }
        });

        return totalDiscount;
    }

    async updateGlobalDiscount(discount) {
        const discountValue = parseFloat(discount);

        // Allow both positive and negative values
        if (isNaN(discountValue)) {
            this.state.globalDiscount = 0;
        } else {
            this.state.globalDiscount = Math.abs(discountValue);
        }

        this.removeGlobalDiscountFromCart();

        if (this.state.globalDiscount > 0) {
            await this.addGlobalDiscountToCart();
        }

        this.updateCartTotal();
    }

    async updateGlobalDiscountType(type) {
        this.state.globalDiscountType = type;
        this.state.globalDiscount = 0;

        // Remove any existing global discount line
        this.removeGlobalDiscountFromCart();
        this.updateCartTotal();

    }

    removeGlobalDiscountFromCart() {
        this.state.cartItems = this.state.cartItems.filter(item => !item.isGlobalDiscount);
    }

    async addGlobalDiscountToCart() {
        try {
            const xmlidRecord = await this.orm.call("ir.model.data", "search_read", [
                [['name', '=', 'product_global_discount'], ['module', '=', 'ths_base']],
                ["res_id"]
            ]);

            if (!xmlidRecord.length) {
                this.notification.add(_t("Global discount product not found"), {type: "warning"});
                return;
            }

            const discountProductId = xmlidRecord[0].res_id;
            const discountProducts = await this.orm.read("product.product", [discountProductId], ["id", "name", "default_code"]);

            if (!discountProducts.length) {
                this.notification.add(_t("Global discount product not found"), {type: "warning"});
                return;
            }

            const discountProduct = discountProducts[0];

            // Calculate on PRE-DISCOUNT subtotal (price * qty only)
            const regularItems = this.state.cartItems.filter(item => !item.isGlobalDiscount);
            const subtotal = regularItems.reduce((total, item) => total + (item.price * item.qty), 0);

            let discountAmount;
            if (this.state.globalDiscountType === 'percent') {
                discountAmount = Math.round((subtotal * (this.state.globalDiscount / 100)) * 1000) / 1000;
            } else {
                discountAmount = Math.min(this.state.globalDiscount, subtotal);
                discountAmount = Math.round(discountAmount * 1000) / 1000;
            }

            if (discountAmount > 0) {
                this.state.cartItems.push({
                    id: 'global_discount_line',
                    product_id: discountProduct.id,
                    name: `Global Discount (${this.state.globalDiscount.toFixed(3)}${this.state.globalDiscountType === 'percent' ? '%' : ' KWD'})`,
                    default_code: 'DISC',
                    price: -discountAmount,
                    qty: 1,
                    discount: 0,
                    isExisting: false,
                    isGlobalDiscount: true,
                    practitioner: '',
                    practitioner_id: null,
                    room: '',
                    room_id: null,
                    patients: [],
                    patient_ids: [],
                    sourceModel: 'manual_pos',
                });
            }
        } catch (error) {
            console.error("Error adding global discount:", error);
            this.notification.add(_t("Error adding global discount"), {type: "danger"});
        }
    }

    togglePaymentMethod(method) {
        if (method.is_credit) {
            const index = this.state.selectedPaymentMethods.findIndex(m => m.is_credit);
            if (index > -1) {
                this.state.selectedPaymentMethods.splice(index, 1);
            } else {
                this.state.selectedPaymentMethods.push(method);
            }
        } else {
            this.state.selectedPaymentMethods = this.state.selectedPaymentMethods.filter(m => m.is_credit);
            this.state.selectedPaymentMethods.push(method);
        }

        this.updatePaymentDistribution();
        this.render();
    }

    isPaymentMethodSelected(method) {
        return this.state.selectedPaymentMethods.some(m => m.id === method.id);
    }

    formatCurrency(amount, isDiscount = false) {
        if (isNaN(amount) || amount === null || amount === undefined) {
            return `${this.state.encounter.company_currency} 0.000`;
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
            if (isDiscount && amount > 0) {
                return `${currencyCode} -${amount.toFixed(decimals)}`;
            }

            const formatOptions = {
                style: 'currency',
                currency: currencyCode,
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals,
            };

            return new Intl.NumberFormat('en-KW', formatOptions).format(amount);
        } catch (error) {
            const sign = amount < 0 ? '-' : '';
            const absAmount = Math.abs(amount);
            return `${sign}${currencyCode} ${absAmount.toFixed(decimals)}`;
        }
    }


    updateLinePractitioner(ev) {
        const practitionerId = parseInt(ev.target.value) || null;
        // Find the item ID from the closest cart item container
        const cartItemElement = ev.target.closest('.cart-item-compact');
        const itemId = cartItemElement.querySelector('[data-item-id]')?.dataset.itemId;

        // Alternative way to get itemId if the above doesn't work
        if (!itemId) {
            // Find the item by matching the select element
            const item = this.state.cartItems.find(item => {
                const selectElement = cartItemElement.querySelector('select[t-att-value*="practitioner_id"]');
                return selectElement && selectElement.value === (item.practitioner_id || '');
            });
            if (item) {
                this.updateLinePractitionerById(item.id, practitionerId);
            }
            return;
        }

        this.updateLinePractitionerById(itemId, practitionerId);
    }

    updateLinePractitionerById(itemId, practitionerId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.practitioner_id = practitionerId;
            if (practitionerId) {
                const practitioner = this.state.availablePractitioners.find(p => p.id === practitionerId);
                item.practitioner = practitioner ? practitioner.name : '';

                // Clear room if it's not valid for the new practitioner
                const availableRooms = this.getFilteredRoomsForLine(practitionerId);
                if (item.room_id && !availableRooms.find(r => r.id === item.room_id)) {
                    item.room_id = null;
                    item.room = '';
                }
            } else {
                item.practitioner = '';
                item.room_id = null;
                item.room = '';
            }
        }
    }

    updateLineRoom(ev) {
        const roomId = parseInt(ev.target.value) || null;
        // Find the item ID from the closest cart item container
        const cartItemElement = ev.target.closest('.cart-item-compact');
        const itemId = cartItemElement.querySelector('[data-item-id]')?.dataset.itemId;

        // Alternative way to get itemId if the above doesn't work
        if (!itemId) {
            // Find the item by matching the select element
            const item = this.state.cartItems.find(item => {
                const selectElement = cartItemElement.querySelector('select[t-att-value*="room_id"]');
                return selectElement && selectElement.value === (item.room_id || '');
            });
            if (item) {
                this.updateLineRoomById(item.id, roomId);
            }
            return;
        }

        this.updateLineRoomById(itemId, roomId);
    }

    updateLineRoomById(itemId, roomId) {
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

    getHeaderPatientIds() {
        if (!this.state.encounter.patient_ids) return [];
        return this.state.encounter.patient_ids.map(p => {
            const id = Array.isArray(p) ? p[0] : p;
            return parseInt(id);
        }).filter(id => !isNaN(id));
    }

    isPatientSelectedInHeader(patientId) {
        return this.getHeaderPatientIds().includes(parseInt(patientId));
    }

    isPatientSelectedInLine(item, patientId) {
        if (!item.patient_ids) return false;
        return item.patient_ids.map(id => parseInt(id)).includes(parseInt(patientId));
    }

    togglePatientSelection(patientId) {
        if (!this.state.encounter.patient_ids) {
            this.state.encounter.patient_ids = [];
        }

        const numericPatientId = parseInt(patientId);
        const currentIds = this.getHeaderPatientIds();
        const patient = this.state.availablePatients.find(p => p.id === numericPatientId);

        if (currentIds.includes(numericPatientId)) {
            this.state.encounter.patient_ids = this.state.encounter.patient_ids.filter(p => {
                const id = Array.isArray(p) ? p[0] : p;
                return parseInt(id) !== numericPatientId;
            });
        } else if (patient) {
            this.state.encounter.patient_ids.push([patient.id, patient.name]);
        }

        this.state.encounter.hasChanges = true;
    }

    toggleLinePatient(itemId, patientId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            const numericPatientId = parseInt(patientId);

            if (!item.patient_ids) item.patient_ids = [];
            const currentIds = item.patient_ids.map(id => parseInt(id));

            if (currentIds.includes(numericPatientId)) {
                item.patient_ids = item.patient_ids.filter(id => parseInt(id) !== numericPatientId);
            } else {
                item.patient_ids.push(numericPatientId);
            }

            const selectedPatients = this.state.availablePatients.filter(p =>
                item.patient_ids.map(id => parseInt(id)).includes(p.id)
            );
            item.patients = selectedPatients.map(p => p.name);

            if (item.isExisting) {
                item.hasChanges = true;
            }
        }
    }

    clearLinePractitioner(itemId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.practitioner_id = null;
            item.practitioner = '';
            item.room_id = null;
            item.room = '';
        }
    }

    clearLineRoom(itemId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (item) {
            item.room_id = null;
            item.room = '';
        }
    }

    clearLinePatients(itemId) {
        this.updateLinePatients(itemId, []);
    }

    async removeFromCart(itemId) {
        const item = this.state.cartItems.find(i => i.id === itemId);
        if (!item) return;

        if (item.isExisting) {
            try {
                await this.orm.unlink("vet.encounter.line", [item.encounter_line_id]);
                this.notification.add(_t("Item deleted from encounter"), {type: "success"});
            } catch (error) {
                this.notification.add(_t("Error deleting item: ") + error.message, {type: "danger"});
                return;
            }
        }

        const index = this.state.cartItems.findIndex(i => i.id === itemId);
        if (index > -1) {
            this.state.cartItems.splice(index, 1);
            this.updateCartTotal();
        }
    }

    async processPayment() {
        if (this.state.isProcessingPayment || this.state.paymentCompleted) {
            this.notification.add(_t("Payment is already being processed"), {type: "warning"});
            return;
        }

        if (!this.state.selectedPaymentMethods.length) {
            this.notification.add(_t("Please select a payment method"), {type: "warning"});
            return;
        }
        if (!this.state.cartItems.length) {
            this.notification.add(_t("Cart is empty"), {type: "warning"});
            return;
        }

        this.state.isProcessingPayment = true;

        try {
            const syncResult = await this.syncCartToEncounterLines();
            if (!syncResult.success) {
                this.notification.add(_t("Error syncing cart: ") + syncResult.error, {type: "danger"});
                this.state.isProcessingPayment = false;
                return;
            }
            const selectedLineIds = await this.getProcessableLineIds();

            // Get primary payment method ID properly - FIXED ERROR HANDLING
            const primaryPaymentMethod = this.state.selectedPaymentMethods.find(m => !m.is_credit);

            if (!primaryPaymentMethod && this.state.paymentDistribution.remaining > 0) {
                this.notification.add(_t("A payment method is required for the remaining amount"), {type: "warning"});
                this.state.isProcessingPayment = false;
                return;
            }

            let paymentMethodId;
            if (primaryPaymentMethod) {
                paymentMethodId = primaryPaymentMethod.id;
            } else {
                // If fully covered by credit, use first available payment method as placeholder
                const fallbackMethod = this.state.paymentMethods.find(m => !m.is_credit);
                if (!fallbackMethod) {
                    this.notification.add(_t("No valid payment method available"), {type: "warning"});
                    this.state.isProcessingPayment = false;
                    return;
                }
                paymentMethodId = fallbackMethod.id;
            }

            const paymentAmount = this.state.paymentDistribution.remaining;
            const creditUsed = this.state.paymentDistribution.credit || 0;

            console.log('Payment method ID:', paymentMethodId, 'Payment amount:', paymentAmount, 'Credit used:', creditUsed);

            const result = await this.orm.call("vet.encounter.header", "process_payment_kanban_ui",
                [this.state.encounter.id], {
                    payment_method_id: paymentMethodId,
                    selected_line_ids: selectedLineIds,
                    payment_amount: paymentAmount,
                    credit_used: creditUsed,
                });

            if (result && result.success === true) {
                this.state.paymentCompleted = true;

                // Show completion dialog
                this.dialog.add(CompletionDialog, {
                    title: _t("Order Successfully Processed"),
                    message: result.message || _t("Payment processed successfully!"),
                    invoiceId: result.invoice_id,
                    onPrintInvoice: () => this.printInvoice(result.invoice_id),
                    onNewOrder: () => this.startNewOrder(),
                    onClose: () => this.closeInterface(),
                    close: () => {
                    },
                });
            } else {
                const errorMsg = result?.message || result?.error || "Payment processing failed";
                this.notification.add(_t("Error: ") + errorMsg, {type: "danger"});
                this.state.isProcessingPayment = false;
            }
        } catch (error) {
            console.error("Payment processing error:", error);
            this.notification.add(_t("Error processing payment: ") + error.message, {type: "danger"});
            this.state.isProcessingPayment = false;
        }
    }

    async syncCartToEncounterLines() {
        try {
            // Update existing lines with current cart values
            for (const item of this.state.cartItems) {
                if (item.isExisting && item.encounter_line_id) {
                    await this.orm.call("vet.encounter.header", "add_product_to_encounter_kanban",
                        [this.state.encounter.id], {
                            product_id: item.product_id,
                            qty: item.qty,
                            unit_price: item.price,
                            partner_id: this.state.partner_id,
                            patient_ids: item.patient_ids || [],
                            discount: (item.discount || 0) / 100,
                            practitioner_id: item.practitioner_id || false,
                            room_id: item.room_id || false,
                            line_id: item.encounter_line_id,
                        });
                }
            }

            // Add new items and sync back encounter_line_id
            const newItems = this.state.cartItems.filter(item => !item.isExisting);
            for (const item of newItems) {
                const existingLine = await this.orm.call("vet.encounter.line", "search_read", [
                    [
                        ['encounter_id', '=', this.state.encounter.id],
                        ['product_id', '=', item.product_id],
                        ['qty', '=', item.qty],
                        ['unit_price', '=', item.price],
                        ['payment_status', '=', 'pending']
                    ],
                    ['id']
                ]);

                if (existingLine.length === 0) {
                    const result = await this.orm.call("vet.encounter.header", "add_product_to_encounter_kanban",
                        [this.state.encounter.id], {
                            product_id: item.product_id,
                            qty: item.qty,
                            unit_price: item.price,
                            partner_id: this.state.partner_id,
                            patient_ids: item.patient_ids || [],
                            discount: (item.discount || 0) / 100,
                            practitioner_id: item.practitioner_id || false,
                            room_id: item.room_id || false,
                        });

                    // SYNC BACK: Update cart item with encounter_line_id
                    if (result && result.encounter_line_id) {
                        item.encounter_line_id = result.encounter_line_id;
                        item.isExisting = true;
                    }
                } else {
                    // Link to existing line
                    item.encounter_line_id = existingLine[0].id;
                    item.isExisting = true;
                }
            }
        } catch (error) {
            console.error("Failed to sync cart to encounter lines:", error);
            return {
                success: false,
                error: error.message || "Failed to sync cart to encounter lines"
            };
        }

        return {success: true};
    }

    async getProcessableLineIds() {
        // Get line IDs that should be processed for payment
        try {
            const encounterLines = await this.orm.call("vet.encounter.line", "search_read", [
                [
                    ['encounter_id', '=', this.state.encounter.id],
                    ['payment_status', 'in', ['pending', 'partial']],
                    ['remaining_qty', '>', 0]
                ],
                ['id']
            ]);

            return encounterLines.map(line => line.id);
        } catch (error) {
            throw new Error("Failed to get processable lines: " + error.message);
        }
    }

    async printInvoice(invoiceId) {
        try {
            await this.action.doAction({
                type: 'ir.actions.report',
                report_name: 'account.report_invoice',
                report_type: 'qweb-pdf',
                data: {'report_type': 'pdf'},
                context: {
                    'active_ids': [invoiceId],
                    'active_model': 'account.move',
                }
            });
            await this.closeInterface();
        } catch (error) {
            console.error("Print error:", error);
            this.notification.add(_t("Error printing invoice"), {type: "warning"});
            await this.closeInterface();
        }
    }

    async startNewOrder() {
        // Reload the encounter form to start fresh
        await this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'vet.encounter.header',
            res_id: this.state.encounter.id,
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'current'
        });
    }

    async closeInterface() {
        await this.action.doAction({type: 'ir.actions.act_window_close'});
    }

    // clearCartAndClose() {
    //     // Clear all cart data
    //     this.state.cartItems = [];
    //     this.state.globalDiscount = 0;
    //     this.state.globalDiscountAmount = 0;
    //     this.state.cartTotal = 0;
    //     this.state.selectedPaymentMethod = null;
    //     this.state.isProcessingPayment = false;
    //     this.state.paymentCompleted = true;
    //
    //     // Close the window after a short delay
    //     setTimeout(() => {
    //         window.close();
    //     }, 2000);
    // }

    async onClickScan() {
        if (!this.isBarcodeScannerSupported()) {
            this.notification.add(_t("Barcode scanner not supported"), {type: "warning"});
            return;
        }

        try {
            const result = await scanBarcode(this.env);
            if (result) {
                await this._barcodeProductAction(result);
            }
        } catch (error) {
            if (error.message !== "BarcodeScanningCancelled") {
                console.error("Barcode scan error:", error);
                this.notification.add(_t("Barcode scanning failed"), {type: "danger"});
            }
        }
    }

    async _barcodeProductAction(barcode) {
        try {
            const product = await this._getProductByBarcode(barcode);
            if (!product) {
                this.notification.add(_t("Product not found for barcode: ") + barcode, {type: "warning"});
                return;
            }
            this.addToCart(product);
            this.notification.add(_t("Product added: ") + product.name, {type: "success"});
        } catch (error) {
            console.error("Barcode product action error:", error);
            this.notification.add(_t("Error processing barcode"), {type: "danger"});
        }
    }

    async _getProductByBarcode(barcode) {
        try {
            // Search in current loaded products first
            for (const category of Object.values(this.state.productsByCategory)) {
                const product = category.find(p => p.barcode === barcode);
                if (product) {
                    return product;
                }
            }

            const products = await this.orm.call("product.product", "search_read", [
                [['barcode', '=', barcode], ['sale_ok', '=', true], ['active', '=', true]],
                ['id', 'name', 'default_code', 'lst_price', 'barcode', 'image_128']
            ]);

            return products.length > 0 ? products[0] : null;
        } catch (error) {
            if (error.name === 'RPCError') {
                console.error("RPC Barcode search error:", error.message);
            } else {
                console.error("Unexpected barcode search error:", error);
            }
            return null;
        }
    }

    async onSearchProducts(searchWord) {
        if (!searchWord || searchWord.length < 2) {
            // If no search, show current category
            if (this.state.selectedCategory) {
                this.state.filteredProducts = this.state.productsByCategory[this.state.selectedCategory] || [];
            }
            return;
        }

        try {
            // Show search results in main products area
            this.state.filteredProducts = await this.orm.call("product.product", "search_read", [
                ['|', ['name', 'ilike', searchWord], ['default_code', 'ilike', searchWord],
                    ['sale_ok', '=', true], ['active', '=', true]],
                ['id', 'name', 'default_code', 'lst_price', 'barcode', 'image_128'],
                0, 20
            ]);
            this.state.selectedCategory = null; // Clear category selection during search
        } catch (error) {
            console.error("Search error:", error);
            this.state.filteredProducts = [];
        }
    }

    async onSearchInputChange(event) {
        const searchWord = event.target.value;
        this.state.searchProductWord = searchWord;

        // await this.onSearchProducts(searchWord);
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.onSearchProducts(searchWord);
        }, 300);
    }

    clearSearch() {
        this.state.searchProductWord = '';

        console.log('Current category:', this.state.selectedCategory);
        console.log('Available categories:', Object.keys(this.state.productsByCategory));

        if (this.state.selectedCategory && this.state.productsByCategory[this.state.selectedCategory]) {
            this.state.filteredProducts = [...this.state.productsByCategory[this.state.selectedCategory]];
        } else {
            // Force fallback to "All" or first category
            const categories = Object.keys(this.state.productsByCategory);
            const allCategory = categories.find(cat => cat.toLowerCase() === 'all');
            const fallbackCategory = allCategory || categories[0];

            if (fallbackCategory) {
                this.selectCategory(fallbackCategory); // Use selectCategory method instead
            }
        }
    }

    async saveChanges() {
        if (!this.hasUnsavedChanges()) {
            this.notification.add(_t("No changes to save"), {type: "info"});
            return;
        }
        try {
            const validPatientIds = this.state.encounter.patient_ids
                ? this.state.encounter.patient_ids.map(p => Array.isArray(p) ? p[0] : p).filter(id => id !== null && id !== undefined)
                : [];

            await this.orm.write("vet.encounter.header", [this.state.encounter.id], {
                'practitioner_id': this.state.encounter.practitioner_id ? this.state.encounter.practitioner_id[0] : false,
                'room_id': this.state.encounter.room_id ? this.state.encounter.room_id[0] : false,
                'patient_ids': [[6, 0, validPatientIds]],
            });

            // Sync cart to encounter lines
            await this.syncCartToEncounterLines();

            // Clear change flags
            this.state.cartItems.forEach(item => {
                if (!item.isExisting) {
                    item.isExisting = true;
                }
                item.unsaved = false;
                item.hasChanges = false;
            });

            this.notification.add(_t("Changes saved successfully"), {type: "success"});
        } catch (error) {
            console.error("Save error:", error);
            this.notification.add(_t("Error saving changes: ") + error.message, {type: "danger"});
        }
    }

    hasUnsavedChanges() {
        return this.state.cartItems.some(item => !item.isExisting || item.unsaved || item.hasChanges) ||
            this.state.encounter.hasChanges;
    }

    // Add methods to VetPosClientAction:
    moveCartItemUp(itemId) {
        const index = this.state.cartItems.findIndex(item => item.id === itemId);
        if (index > 0) {
            const item = this.state.cartItems.splice(index, 1)[0];
            this.state.cartItems.splice(index - 1, 0, item);
        }
    }

    moveCartItemDown(itemId) {
        const index = this.state.cartItems.findIndex(item => item.id === itemId);
        if (index < this.state.cartItems.length - 1) {
            const item = this.state.cartItems.splice(index, 1)[0];
            this.state.cartItems.splice(index + 1, 0, item);
        }
    }
}

registry.category("actions").add("vet_pos_interface_action", VetPosClientAction);