/** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {PosStore} from "@point_of_sale/app/store/pos_store";
import {_t} from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        console.log("Medical POS Store: Setup completed with appointment support");
    },

    async manageMedicalAppointments() {
        console.log("Medical POS: Opening gantt view");
        this.orderToTransferUuid = null;
        this.showScreen("ActionScreen", {actionName: "ManageMedicalAppointments"});

        try {
            const action = await this.data.call("calendar.event", "action_open_medical_gantt_view", [false], {
                context: {
                    'default_appointment_status': 'draft',
                    'appointment_booking_gantt_show_all_resources': true,
                    'active_model': 'appointment.type',
                    'default_partner_ids': this.pos.get_order()?.get_partner()?.id ? [this.pos.get_order().get_partner().id] : [],
                },
            });
            await this.action.doAction(action);
            console.log("Medical POS: Opened gantt view");
        } catch (error) {
            console.error("Medical POS: Error opening gantt view:", error);
            this.notification?.add(_t("Error opening appointments view."), {type: 'danger'});
        }
    },

    getDailyAppointments(date = null) {
        const appointments = this.models["calendar.event"]?.getAll() || [];
        if (!date) date = new Date().toISOString().split('T')[0];

        return appointments.filter(appointment => {
            if (!appointment.start) return false;
            const appointmentDate = new Date(appointment.start).toISOString().split('T')[0];
            return appointmentDate === date &&
                appointment.appointment_status !== 'cancelled_by_patient' &&
                appointment.appointment_status !== 'cancelled_by_clinic';
        }).map(appointment => ({
            id: appointment.id,
            name: appointment.name || 'Unnamed Appointment',
            start_time: new Date(appointment.start).toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'}),
            partner_name: Array.isArray(appointment.partner_ids) ? appointment.partner_ids[0]?.[1] : 'Unknown',
            practitioner_name: Array.isArray(appointment.practitioner_id) ? appointment.practitioner_id[1] : 'No Practitioner',
            room_name: Array.isArray(appointment.room_id) ? appointment.room_id[1] : 'No Room',
            status: appointment.appointment_status || 'draft',
            encounter_id: Array.isArray(appointment.encounter_id) ? appointment.encounter_id[0] : appointment.encounter_id,
            patient_names: this.pos.formatPatientIds(appointment.patient_ids || []),
        })).sort((a, b) => a.start_time.localeCompare(b.start_time));
    },

    async payAppointment(appointmentId, partnerId, patientIds, practitionerId, encounterId) {
        try {
            const order = this.pos.get_order();
            const appointment = this.models["calendar.event"].get(appointmentId);
            if (!appointment) {
                this.notification.add(_t("Appointment not found"), {type: 'warning'});
                return;
            }

            // Fetch or create encounter
            const encounter = this.models["ths.medical.base.encounter"].find(e => e.id === encounterId) ||
                await this.data.call("ths.medical.base.encounter", "_find_or_create_daily_encounter", [
                    partnerId,
                    patientIds,
                    new Date().toISOString().split('T')[0],
                    practitionerId || false,
                    appointment.room_id || false
                ]);

            order.set_partner(this.models["res.partner"].get(partnerId));
            order.medical_context = {
                encounter_id: encounter.id,
                encounter_name: encounter.name || 'New Encounter',
                patient_ids: encounter.patient_ids.map(p => [p.id, p.name]),
                practitioner_id: encounter.practitioner_id ? [encounter.practitioner_id.id, encounter.practitioner_id.name] : false,
                room_id: encounter.room_id ? [encounter.room_id.id, encounter.room_id.name] : false,
            };

            order.patient_ids = order.medical_context.patient_ids;
            order.practitioner_id = order.medical_context.practitioner_id;
            order.room_id = order.medical_context.room_id;
            order.encounter_id = encounter.id;

            const pendingItems = this.pos.getPendingItems(partnerId);
            for (const item of pendingItems) {
                order.addProduct(this.models["product.product"].get(item.product_id[0]), {
                    quantity: item.quantity,
                    price: item.product_id[1].lst_price,
                    extras: {
                        ths_pending_item_id: item.id,
                        patient_ids: item.patient_ids,
                        practitioner_id: item.practitioner_id,
                        room_id: item.room_id,
                        discount: item.discount || 0.0,
                    },
                });
            }

            this.showScreen("ProductScreen");
            this.notification.add(_t("Order populated with encounter data"), {type: 'success'});
        } catch (error) {
            console.error("Medical POS: Error paying appointment:", error);
            this.notification?.add(_t("Error processing payment: %s", error.message), {type: 'danger'});
        }
    }
});