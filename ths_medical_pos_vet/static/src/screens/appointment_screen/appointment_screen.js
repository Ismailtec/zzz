/** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {PosStore} from "@point_of_sale/app/store/pos_store";
import {_t} from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async setup(...args) {
        await super.setup(...args);
    },

    async payAppointment(appointmentId, ownerId, petIds, practitionerId, encounterId) {
        try {
            const order = this.pos.get_order();
            const appointment = this.models["calendar.event"].get(appointmentId);
            if (!appointment) {
                this.notification.add(_t("Appointment not found"), {type: 'warning'});
                return;
            }

            const encounter = this.models["ths.medical.base.encounter"].find(e => e.id === encounterId) ||
                await this.data.call("ths.medical.base.encounter", "_find_or_create_daily_encounter", [
                    ownerId, petIds || [], new Date().toISOString().split('T')[0], practitionerId || false, appointment.room_id?.[0] || false
                ]);

            order.set_partner(this.models["res.partner"].get(ownerId));
            order.medical_context = {
                encounter_id: encounter.id,
                encounter_name: encounter.name || 'New Encounter',
                pet_owner_id: ownerId,
                patient_ids: encounter.patient_ids?.map(p => [p.id, p.name, p.species_id ? [p.species_id.id, p.species_id.name] : false]) || [],
                practitioner_id: encounter.practitioner_id ? [encounter.practitioner_id.id, encounter.practitioner_id.name] : false,
                room_id: encounter.room_id ? [encounter.room_id.id, encounter.room_id.name] : false,
            };

            order.patient_ids = order.medical_context.patient_ids;
            order.practitioner_id = order.medical_context.practitioner_id;
            order.room_id = order.medical_context.room_id;
            order.encounter_id = encounter.id;
            order.pet_owner_id = ownerId;

            const pendingItems = this.getPendingItems(ownerId);
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
            this.notification.add(_t("Order populated with veterinary encounter data"), {type: 'success'});
        } catch (error) {
            console.error("Vet POS: Error paying appointment:", error);
            this.notification.add(_t("Error processing payment: %s", error.message), {type: 'danger'});
        }
    },

    async handlePetOrderSetupPopupResult(result) {
        if (!result.confirmed) {
            if (result.skipped) {
                this.notification.add(_t("Order setup skipped"), {type: 'info'});
            }
            return;
        }

        const order = this.pos.get_order();
        const payload = result.payload;

        order.set_partner(this.models["res.partner"].get(payload.pet_owner_id || payload.partner?.id || payload.partner_id));
        order.medical_context = {
            encounter_id: payload.encounter_id,
            encounter_name: payload.encounter_name,
            pet_owner_id: payload.pet_owner_id || payload.partner?.id || payload.partner_id,
            patient_ids: payload.patient_ids.map(p => [p[0], p[1], p[2] || false]),
            practitioner_id: payload.practitioner_id || false,
            room_id: payload.room_id || false,
        };

        order.patient_ids = order.medical_context.patient_ids;
        order.practitioner_id = order.medical_context.practitioner_id;
        order.room_id = order.medical_context.room_id;
        order.encounter_id = payload.encounter_id;
        order.pet_owner_id = payload.pet_owner_id || payload.partner?.id || payload.partner_id;

        const pendingItems = this.getPendingItems(payload.pet_owner_id || payload.partner?.id || payload.partner_id);
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
        this.notification.add(_t("Order populated with pet order setup data"), {type: 'success'});
    }
});