/** @odoo-module **/

import {registry} from "@web/core/registry";
import {Dialog} from "@web/core/dialog/dialog";
import {Component} from "@odoo/owl";
import {usePos} from "@point_of_sale/app/store/pos_hook";

export class EncounterSelectionPopup extends Component {
    static template = "ths_medical_pos.EncounterSelectionPopup";
    static components = {Dialog};

    static props = {
        title: {type: String, optional: true},
        encounters: {type: Array, optional: true},
        close: Function,
    };

    setup() {
        // Access the POS service using OWL 3 composable
        this.pos = usePos();
    }

    confirmSelection(encounter) {
        console.log("Encounter selected:", encounter);

        // Get partner from preloaded data
        const partnerId = Array.isArray(encounter.partner_id) ? encounter.partner_id[0] : encounter.partner_id;
        const partner = this.pos.models["res.partner"]?.get(partnerId) || null;

        console.log("Resolved partner:", partner);

        // Format encounter data for payload - BASE MEDICAL ONLY
        const payload = {
            partner,
            encounter_id: encounter.id,
            encounter_name: encounter.name,
            patient_ids: encounter.patient_ids || [],
            practitioner_id: encounter.practitioner_id || null,
            room_id: encounter.room_id || null,
        };

        this.props.close({
            confirmed: true,
            payload: payload,
        });
    }

    cancel() {
        this.props.close({confirmed: false});
    }
}

registry.category("pos_popup").add("ths_medical_pos.EncounterSelectionPopup", EncounterSelectionPopup);

console.log("POS: Base EncounterSelectionPopup loaded");