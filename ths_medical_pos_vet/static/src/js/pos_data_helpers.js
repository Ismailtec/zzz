/** @odoo-module */

import {patch} from "@web/core/utils/patch";
import {PosStore} from "@point_of_sale/app/store/pos_store";

/**
 * Veterinary-specific extensions to base medical POS
 * Extends base functionality with pet/species/membership logic
 */

patch(PosStore.prototype, {

    // VET: Helper method to get pet with species info
    getPetWithSpecies(petId) {
        const pet = this.models["res.partner"]?.get(petId);
        if (!pet || !pet.species_id) return pet;

        const speciesId = Array.isArray(pet.species_id) ? pet.species_id[0] : pet.species_id;
        const species = this.models["ths.species"]?.get(speciesId);

        return {
            ...pet,
            species_info: species,
            display_name: species ? `${pet.name} (${species.name})` : pet.name,
            species_color_index: species ? species.color : 0
        };
    },

    // VET: Helper method to get membership status for pets
    getPetMembershipStatus(petId) {
        const memberships = this.models["vet.pet.membership"]?.getAll().filter(m =>
                m.patient_ids && m.patient_ids.some(p => {
                    // Handle both formats: [{id: x, name: y}, ...] and [[id, name], ...]
                    if (Array.isArray(p) && p.length >= 2) {
                        return p[0] === petId; // [id, name] format
                    } else if (p && typeof p === 'object' && p.id) {
                        return p.id === petId; // {id: x, name: y} format
                    }
                    return false;
                })
        ) || [];

        // Find active membership
        const activeMembership = memberships.find(m =>
            m.state === 'running' && m.is_paid === true
        );

        return {
            has_membership: !!activeMembership,
            membership_status: activeMembership ? 'active' : 'none',
            membership_data: activeMembership || null
        };
    },

    // VET: Helper method to get park checkin status
    getParkCheckinStatus(petId) {
        const parkCheckins = this.models["park.checkin"]?.getAll().filter(checkin =>
                checkin.patient_ids && checkin.patient_ids.some(p => {
                    // Handle both formats
                    if (Array.isArray(p) && p.length >= 2) {
                        return p[0] === petId; // [id, name] format
                    } else if (p && typeof p === 'object' && p.id) {
                        return p.id === petId; // {id: x, name: y} format
                    }
                    return false;
                }) && checkin.state === 'checked_in'
        ) || [];

        return {
            is_in_park: parkCheckins.length > 0,
            checkin_data: parkCheckins[0] || null
        };
    },

    // VET: Enhanced pending items filtering for vet context
    getPendingItems(partnerId = null) {
        const allItems = this.models["ths.pending.pos.item"]?.getAll() || [];

        if (partnerId) {
            // In vet context, partner_id is the pet owner
            return allItems.filter(item =>
                item.state === 'pending' &&
                item.partner_id && item.partner_id[0] === partnerId
            );
        }

        return allItems.filter(item => item.state === 'pending');
    },

    // VET: Helper method to get Odoo standard color class from species color index
    getSpeciesColorClass(speciesColorIndex) {
        // Use Odoo's standard color system (o_tag_color_X classes)
        return `o_tag_color_${speciesColorIndex || 0}`;
    },

    // VET: Format patient IDs for veterinary display (shows species)
    formatPatientIds(patientIds) {
        if (!patientIds || !Array.isArray(patientIds)) {
            return [];
        }

        return patientIds.map(patient => {
            let petName = 'Unknown Pet';
            let petId = null;

            // Extract pet info from different formats
            if (Array.isArray(patient) && patient.length >= 2) {
                petId = patient[0];
                petName = patient[1]; // [id, name] format
            } else if (patient && typeof patient === 'object') {
                petId = patient.id;
                petName = patient.name; // {id: x, name: y} format
            }

            // Get species info if available
            if (petId) {
                const pet = this.models["res.partner"]?.get(petId);
                if (pet && pet.species_id) {
                    const speciesId = Array.isArray(pet.species_id) ?
                        pet.species_id[0] : pet.species_id;
                    const species = this.models["ths.species"]?.get(speciesId);
                    if (species) {
                        return `${petName} (${species.name})`;
                    }
                }
            }

            return petName;
        });
    }
});

console.log("Vet POS: Species and membership helpers loaded");