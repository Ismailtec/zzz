/** @odoo-module */

import {Component, useState} from "@odoo/owl";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";

export class PetOrderSetupPopup extends Component {
    static template = "ths_medical_pos_vet.PetOrderSetupPopup";
    static components = {Dialog};

    static props = {
        title: {type: String, optional: true},
        // For NEW ORDER scenario (from partner_list_screen)
        partner_id: {type: Number, optional: true},
        partner_name: {type: String, optional: true},
        existing_encounter: {type: [Number, Boolean], optional: true},
        pets: {type: Array, optional: true},
        practitioners: {type: Array, optional: true},
        rooms: {type: Array, optional: true},
        selected_pets: {type: Array, optional: true},
        selected_practitioner: {type: [Number, Boolean], optional: true},
        selected_room: {type: [Number, Boolean], optional: true},
        // For EXISTING ORDER scenario (from product_screen)
        partner: {type: Object, optional: true},
        encounter: {type: [Object, Boolean], optional: true},
        preSelectedPets: {type: Array, optional: true},
        // Control behavior
        isNewOrder: {type: Boolean, optional: true},
        close: Function,
    };

    static defaultProps = {
        title: _t("Pet Order Setup"),
        pets: [],
        practitioners: [],
        rooms: [],
        selected_pets: [],
        preSelectedPets: [],
        selected_practitioner: false,
        selected_room: false,
        isNewOrder: false,
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");

        // Determine if this is a new order or existing order modification
        this.isNewOrder = this.props.isNewOrder ||
            (this.props.partner_id && !this.props.partner);

        // Get the partner object (either from props directly or by ID)
        this.partner = this.props.partner ||
            (this.props.partner_id ? this.pos.models["res.partner"]?.get(this.props.partner_id) : null);

        // Get available data based on scenario
        if (this.isNewOrder) {
            // NEW ORDER: Use data from backend call
            this.availablePets = this.props.pets || [];
            this.availablePractitioners = this.props.practitioners || [];
            this.availableRooms = this.props.rooms || [];
        } else {
            // EXISTING ORDER: Get data from preloaded models
            this.availablePets = this.getOwnerPets();
            this.availablePractitioners = this.pos.models["appointment.resource"]?.getAll().filter(r =>
                r.resource_category === 'practitioner' && r.active
            ) || [];
            this.availableRooms = this.pos.models["appointment.resource"]?.getAll().filter(r =>
                r.resource_category === 'location' && r.active
            ) || [];
        }

        // Initialize state based on scenario
        const initialPets = this.isNewOrder ?
            (this.props.selected_pets || []) :
            (this.props.preSelectedPets || []);

        const initialPractitioner = this.isNewOrder ?
            (this.props.selected_practitioner || false) :
            (this.props.encounter?.practitioner_id?.[0] || false);

        const initialRoom = this.isNewOrder ?
            (this.props.selected_room || false) :
            (this.props.encounter?.room_id?.[0] || false);

        this.state = useState({
            selectedPets: new Set(initialPets),
            selectedPractitioner: initialPractitioner,
            selectedRoom: initialRoom,
        });
    }

    getOwnerPets() {
        if (!this.partner) return [];
        const allPartners = this.pos.models["res.partner"]?.getAll() || [];
        return allPartners.filter(partner =>
            partner.pet_owner_id &&
            partner.pet_owner_id[0] === this.partner.id &&
            partner.active &&
            !partner.ths_deceased
        ).map(pet => this.pos.getPetWithSpecies(pet.id));
    }

    togglePetSelection(petId) {
        if (this.state.selectedPets.has(petId)) {
            this.state.selectedPets.delete(petId);
        } else {
            this.state.selectedPets.add(petId);
        }
    }

    isPetSelected(petId) {
        return this.state.selectedPets.has(petId);
    }

    setPractitioner(practitionerId) {
        this.state.selectedPractitioner = practitionerId;
    }

    setRoom(roomId) {
        this.state.selectedRoom = roomId;
    }

    async confirmSelection() {
        if (this.state.selectedPets.size === 0) {
            this.notification.add(_t("Please select at least one pet"), {type: 'warning'});
            return;
        }

        try {
            if (this.isNewOrder) {
                // NEW ORDER: Call backend to create/update encounter
                const result = await this.orm.call("pos.order", "_process_new_order_popup_result", [{
                    partner_id: this.props.partner_id,
                    selected_pets: Array.from(this.state.selectedPets),
                    selected_practitioner: this.state.selectedPractitioner,
                    selected_room: this.state.selectedRoom,
                }]);

                this.props.close({
                    confirmed: true,
                    payload: result,
                    skipped: false,
                    isNewOrder: true,
                });

            } else {
                // EXISTING ORDER: Format data for frontend use
                const selectedPetRecords = this.availablePets.filter(pet =>
                    this.state.selectedPets.has(pet.id)
                );

                const patient_ids = selectedPetRecords.map(pet => [pet.id, pet.name]);

                const practitioner_id = this.state.selectedPractitioner ?
                    [this.state.selectedPractitioner, this.getPractitionerName(this.state.selectedPractitioner)] :
                    null;

                const room_id = this.state.selectedRoom ?
                    [this.state.selectedRoom, this.getRoomName(this.state.selectedRoom)] :
                    null;

                const payload = {
                    patient_ids: patient_ids,
                    practitioner_id: practitioner_id,
                    room_id: room_id,
                    encounter_id: this.props.encounter?.id || false,
                };

                this.props.close({
                    confirmed: true,
                    payload: payload,
                    isNewOrder: false,
                });
            }

        } catch (error) {
            console.error("Error processing pet order setup:", error);
            this.notification.add(_t("Error setting up order: %s", error.message), {type: 'danger'});
        }
    }

    skipSetup() {
        this.props.close({
            confirmed: false,
            skipped: true,
        });
    }

    cancel() {
        this.props.close({
            confirmed: false,
            skipped: false,
        });
    }

    // Helper methods
    getSpeciesName(pet) {
        if (pet.species_id && Array.isArray(pet.species_id)) {
            return pet.species_id[1];
        }
        return '';
    }

    getPractitionerName(practitionerId) {
        const practitioner = this.availablePractitioners.find(p => p.id === practitionerId);
        return practitioner ? practitioner.name : '';
    }

    getRoomName(roomId) {
        const room = this.availableRooms.find(r => r.id === roomId);
        return room ? room.name : '';
    }

    getMembershipStatus(pet) {
        return this.pos.getPetMembershipStatus(pet.id).membership_status;
    }

    getSpeciesColor(pet) {
        return this.pos.getPetWithSpecies(pet.id).species_color_index || 0;
    }

    // Computed properties for template
    get partnerName() {
        return this.partner?.name || this.props.partner_name || 'Unknown Owner';
    }

    get encounterInfo() {
        if (this.isNewOrder) {
            return this.props.existing_encounter ?
                'Using existing encounter for today' :
                'Creating new encounter for today';
        } else {
            return this.props.encounter ?
                `Encounter: ${this.props.encounter.name}` :
                'New service session';
        }
    }

    get showSkipButton() {
        return this.isNewOrder; // Only show skip for new orders
    }
}

console.log("Vet POS: Consolidated PetOrderSetupPopup loaded");