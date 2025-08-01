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
                practitioner_department: null,
                encounter_line_ids: [],
                company_currency: 'KWD',
                global_discount_type: 'percent',
                global_discount_rate: 0.0
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
            practitionerDepartment: {},
            sourceModel: 'manual_pos',
            isProcessingPayment: false,
            paymentCompleted: false,
            searchProductWord: '',
            scanning: false,
            searchResults: [],
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
                    ["id", "name", "partner_id", "patient_ids", "practitioner_id", "room_id", "practitioner_department",
                        "encounter_line_ids", "company_currency"]
                );
                const encounter_data = data[0];
                this.state.encounter = {...this.state.encounter, ...encounter_data};

                this.state.globalDiscountType = encounter_data.global_discount_type || 'percent';
                this.state.globalDiscount = encounter_data.global_discount_rate || 0;
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
                const patientIds = this.state.encounter.patient_ids.map(p => Array.isArray(p) ? p[0] : p);
                this.state.availablePatients = await this.orm.read("res.partner", patientIds, ["id", "name"]);
            }

            // Load all practitioners - don't filter by department here
            this.state.availablePractitioners = await this.orm.call(
                "appointment.resource",
                "search_read",
                [[['resource_category', '=', 'practitioner'], ['active', '=', true]],
                    ["id", "name"]]
            );

            // Load rooms - filter by practitioner_department if practitioner is selected
            // let roomDomain = [['resource_category', '=', 'location'], ['active', '=', true]];
            // if (this.state.encounter.practitioner_department) {
            //     roomDomain.push(['ths_department_id', '=', this.state.encounter.practitioner_department[0]]);
            // }

            this.state.availableRooms = await this.orm.call(
                "appointment.resource",
                "search_read",
                [[['resource_category', '=', 'location'], ['active', '=', true]],
                    ["id", "name"]]
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
                    ["product_id", "qty", "unit_price", "remaining_amount", "practitioner_id", "room_id", "patient_ids",
                        "discount", "payment_status", 'remaining_amount', 'practitioner_department']
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
                        price: line.unit_price,
                        qty: line.qty,
                        discount: (line.discount || 0) * 100,
                        remaining_amount: line.remaining_amount,
                        isExisting: true,
                        practitioner: practitionerName,
                        practitioner_id: line.practitioner_id ? line.practitioner_id[0] : null,
                        room: roomName,
                        room_id: line.room_id ? line.room_id[0] : null,
                        practitioner_department: line.practitioner_department ? line.practitioner_department[0] : null,
                        patients: patientNames,
                        patient_ids: line.patient_ids || [],
                        sourceModel: 'manual_pos',
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
                source_model: this.props.sourceModel,
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
        if (item.isGlobalDiscount) {
            return item.price; // Already negative
        }

        const lineTotal = item.price * item.qty;
        const discountAmount = lineTotal * ((item.discount / 100) || 0);
        return lineTotal - discountAmount;
    }

    updateCartTotal() {
        this.state.cartTotal = this.state.cartItems.reduce((total, item) => {
            return total + this.getLineTotal(item);
        }, 0);
        this.state.cartTotal = Math.max(0, this.state.cartTotal);
    }

    async updateGlobalDiscount(discount) {
        this.state.globalDiscount = parseFloat(discount) || 0;

        // Remove existing global discount line from cart
        this.removeGlobalDiscountFromCart();

        // Add new global discount line if discount > 0
        if (this.state.globalDiscount > 0) {
            await this.addGlobalDiscountToCart();
        }

        // Update cart total
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
        // Get actual product ID from xmlid
        try {
            const discountProducts = await this.orm.call("product.product", "search_read", [
                [['default_code', '=', 'DISC']],
                ['id', 'name', 'default_code']
            ]);

            if (!discountProducts.length) {
                this.notification.add(_t("Global discount product not found"), {type: "warning"});
                return;
            }

            const discountProduct = discountProducts[0];

            // Calculate discount amount
            const regularItems = this.state.cartItems.filter(item => !item.isGlobalDiscount);
            const subtotal = regularItems.reduce((total, item) => total + this.getLineTotal(item), 0);

            let discountAmount;
            if (this.state.globalDiscountType === 'percent') {
                discountAmount = subtotal * (this.state.globalDiscount / 100);
            } else {
                discountAmount = Math.min(this.state.globalDiscount, subtotal);
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

    selectPaymentMethod(method) {
        this.state.selectedPaymentMethod = method;
    }

    formatCurrency(amount) {
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
        // If no practitioner selected, return all rooms
        if (!practitionerId) {
            return this.state.availableRooms;
        }

        // If practitioner is selected but no department info, return all rooms
        if (!this.state.encounter.practitioner_department || !this.state.encounter.practitioner_department[0]) {
            return this.state.availableRooms;
        }

        // Return rooms filtered by the current practitioner's department
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

        if (!this.state.selectedPaymentMethod) {
            this.notification.add(_t("Please select a payment method"), {type: "warning"});
            return;
        }
        if (!this.state.cartItems.length) {
            this.notification.add(_t("Cart is empty"), {type: "warning"});
            return;
        }

        this.state.isProcessingPayment = true;

        try {
            // STEP 1: Sync all cart changes to encounter lines BEFORE payment
            await this.syncCartToEncounterLines();

            // STEP 3: Get line IDs to process (including updated discount values)
            const selectedLineIds = await this.getProcessableLineIds();

            // STEP 4: Process payment
            const result = await this.orm.call("vet.encounter.header", "process_payment_kanban_ui",
                [this.state.encounter.id], {
                    payment_method_id: this.state.selectedPaymentMethod.id,
                    selected_line_ids: selectedLineIds,
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
                    },  // Required by dialog
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
        // Sync all cart changes to encounter lines before payment"
        try {
            // Update existing lines with current cart values
            for (const item of this.state.cartItems) {
                if (item.isExisting && item.encounter_line_id) {
                    await this.orm.write("vet.encounter.line", [item.encounter_line_id], {
                        'qty': item.qty,
                        'discount': (item.discount || 0) / 100,
                        'practitioner_id': item.practitioner_id || false,
                        'room_id': item.room_id || false,
                        'patient_ids': [[6, 0, item.patient_ids || []]],
                        'source_model': 'manual_pos',
                    });
                }
            }

            // Add new items - source_model will be set in add_product_to_encounter_kanban
            const newItems = this.state.cartItems.filter(item => !item.isExisting);
            for (const item of newItems) {
                await this.orm.call("vet.encounter.header", "add_product_to_encounter_kanban",
                    [this.state.encounter.id], {
                        product_id: item.product_id,
                        qty: item.qty,
                        patient_ids: item.patient_ids || [],
                        discount: (item.discount || 0) / 100,
                        practitioner_id: item.practitioner_id,
                        room_id: item.room_id,
                    });
            }
        } catch (error) {
            throw new Error("Failed to sync cart to encounter lines: " + error.message);
        }
    }

    async getProcessableLineIds() {
        // Get line IDs that should be processed for payment
        try {
            const encounterLines = await this.orm.call("vet.encounter.line", "search_read", [
                [
                    ['encounter_id', '=', this.state.encounter.id],
                    ['payment_status', 'in', ['pending', 'partial']],
                    ['remaining_amount', '>', 0]
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
            this.closeInterface();
        } catch (error) {
            console.error("Print error:", error);
            this.notification.add(_t("Error printing invoice"), {type: "warning"});
            this.closeInterface();
        }
    }

    startNewOrder() {
        // Reload the encounter form to start fresh
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'vet.encounter.header',
            res_id: this.state.encounter.id,
            view_mode: 'form',
            target: 'current'
        });
    }

    closeInterface() {
        this.action.doAction({type: 'ir.actions.act_window_close'});
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
            this.state.searchResults = [];
            return;
        }

        try {
            this.state.searchResults = await this.orm.call("product.product", "search_read", [
                ['|', ['name', 'ilike', searchWord], ['default_code', 'ilike', searchWord],
                    ['sale_ok', '=', true], ['active', '=', true]],
                ['id', 'name', 'default_code', 'lst_price', 'barcode', 'image_128'],
                0, 10
            ]);
        } catch (error) {
            if (error.name === 'RPCError') {
                console.error("RPC Search error:", error.message);
            } else {
                console.error("Unexpected search error:", error);
            }
            this.state.searchResults = [];
        }
    }

    onSearchInputChange(event) {
        const searchWord = event.target.value;
        this.state.searchProductWord = searchWord;
        this.onSearchProducts(searchWord);
    }

    clearSearch() {
        this.state.searchProductWord = '';
        this.state.searchResults = [];
    }
}

registry.category("actions").add("vet_pos_interface_action", VetPosClientAction);