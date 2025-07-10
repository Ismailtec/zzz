/** @odoo-module */
import {patch} from "@web/core/utils/patch";
import {ProductScreen} from "@point_of_sale/app/screens/product_screen/product_screen";
import {PetOrderSetupPopup} from "@ths_medical_pos_vet/popups/pet_order_setup_popup";
import {_t} from "@web/core/l10n/translation";

patch(ProductScreen.prototype, {
    async setup(...args) {
        await super.setup(...args);
    },

    async createParkCheckIn() {
        const order = this.pos.get_order();
        if (!order.get_partner()) {
            this.notification.add(_t("Please select a pet owner first"), {type: 'warning'});
            return;
        }

        const popupData = await this._openPetOrderSetupPopup(false);
        if (popupData && popupData.confirmed) {
            order.medical_context = {
                encounter_id: popupData.payload.encounter_id,
                encounter_name: popupData.payload.encounter_name,
                pet_owner_id: order.get_partner().id,
                patient_ids: popupData.payload.patient_ids,
                practitioner_id: popupData.payload.practitioner_id,
                room_id: popupData.payload.room_id,
            };
            order.patient_ids = popupData.payload.patient_ids;
            order.practitioner_id = popupData.payload.practitioner_id;
            order.room_id = popupData.payload.room_id;
            order.encounter_id = popupData.payload.encounter_id;
            order.pet_owner_id = order.get_partner().id;

            await this.orm.call("pos.order", "_link_to_park_checkin", [order.pos_order_id || 0]);
            this.notification.add(_t("Park check-in created"), {type: 'success'});
        }
    },

    async _openPetOrderSetupPopup(isNewOrder) {
        const order = this.pos.get_order();
        const partner = order.get_partner();
        const encounter = order.medical_context?.encounter_id ?
            this.pos.models["ths.medical.base.encounter"].get(order.medical_context.encounter_id) : null;

        return await this.popup.add(PetOrderSetupPopup, {
            title: isNewOrder ? _t("New Pet Order Setup") : _t("Edit Pet Order"),
            partner,
            encounter,
            preSelectedPets: order.patient_ids?.map(p => p[0]) || [],
            isNewOrder,
        });
    }
});