/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {AppointmentBookingGanttRenderer} from "@appointment/views/gantt/gantt_renderer";

/**
 * Medical extension of the Appointment Booking Gantt Renderer
 * Updated for human medical practice: patient = customer (same person)
 * Extends status handling for medical appointment statuses
 */
patch(AppointmentBookingGanttRenderer.prototype, {
    /**
     * @override
     * CLEANED UP: Handle only our medical appointment statuses with proper colors
     */
    enrichPill(pill) {
        const enrichedPill = super.enrichPill(pill);
        const {record} = pill;

        if (!record.appointment_type_id) {
            return enrichedPill;
        }

        const now = luxon.DateTime.now();
        let color = false;

        // Handle CLEANED UP appointment_status (only our medical statuses)
        if (!record.active) {
            color = false; // Archived
        } else {
            switch (record.appointment_status) {
                case 'draft':
                    color = 7; // light gray - draft state
                    break;
                case 'confirmed':
                    color = now.diff(record.start, ['minutes']).minutes > 15 ? 2 : 4; // orange if late, light blue if not
                    break;
                case 'checked_in':
                    color = 6; // yellow - patient is here
                    break;
                case 'in_progress':
                    color = 9; // dark blue - consultation ongoing
                    break;
                case 'completed':
                    color = 8; // light green - completed but not billed
                    break;
                case 'billed':
                    color = 10; // green - fully processed
                    break;
                case 'cancelled_by_patient':
                case 'cancelled_by_clinic':
                    color = 1; // red - cancelled
                    break;
                case 'no_show':
                    color = 1; // red - no show
                    break;
                // Legacy support for old statuses (will be migrated)
//                case 'booked':
//                case 'scheduled':
//                    color = now.diff(record.start, ['minutes']).minutes > 15 ? 2 : 4;
//                    break;
//                case 'attended':
//                    color = 10; // green - legacy status
//                    break;
//                case 'request':
//                    color = record.start < now ? 2 : 8; // orange if past, blue if future
//                    break;
                default:
                    color = 8; // default blue
            }
        }

        if (color) {
            enrichedPill.className += ` o_gantt_color_${color}`;
        }

        return enrichedPill;
    },

    /**
     * @override
     * Extended to handle medical field context in popover
     * Updated for human medical practice: patients are customers (same people)
     */
    async getPopoverProps(pill) {
        const popoverProps = await super.getPopoverProps(pill);
        const {record} = pill;

        // Handle Many2many field for patients display
        // For human medical: patients are the customers/billing entities
        let patientNames = '';
        if (record.patient_ids && Array.isArray(record.patient_ids)) {
            patientNames = record.patient_ids.map(patient =>
                Array.isArray(patient) ? patient[1] : patient.name || patient.toString()
            ).join(', ');
        }

        // Add medical-specific context for popover template
        Object.assign(popoverProps.context, {
            // Medical fields for popover display
            practitioner_name: record.practitioner_id ? record.practitioner_id[1] : '',
            ths_room_name: record.room_id ? record.room_id[1] : '',
            ths_patient_names: patientNames,  // Handle multiple patients
            // Status information
            medical_appointment: !!record.appointment_type_id,
            appointment_status_display: this._getStatusDisplayText(record.appointment_status),
            // Human medical context
            is_human_medical: true,  // Flag to indicate human medical context in templates
            // Encounter information
            encounter_id: record.encounter_id ? record.encounter_id[0] : false,
            // Add encounter status display
            encounter_status: record.encounter_id ? 'Linked' : 'Not Created',
            encounter_name: record.encounter_id ? record.encounter_id[1] : '',
            // POS integration
            pos_session_id: this.env.services.pos ? this.env.services.pos.session_id : false,
        });

        return popoverProps;
    },

    /**
     * CLEANED UP: Get display text for our medical appointment statuses only
     */
    _getStatusDisplayText(status) {
        const statusMap = {
            // Our clean medical statuses
            'draft': 'Draft',
            'confirmed': 'Confirmed',
            'checked_in': 'Checked In',
            'in_progress': 'In Progress',
            'completed': 'Completed',
            'billed': 'Billed',
            'cancelled_by_patient': 'Cancelled (Patient)',
            'cancelled_by_clinic': 'Cancelled (Clinic)',
            'no_show': 'No Show',
            // Legacy statuses (for backward compatibility during migration)
            //'request': 'Request (Legacy)',
            //'booked': 'Booked (Legacy)',
            //'scheduled': 'Scheduled (Legacy)',
            //'attended': 'Checked-In (Legacy)'
        };
        return statusMap[status] || status;
    },

    /**
     * @override
     * Extended popover buttons for medical appointments
     * Updated for human medical practice context
     */
    getPopoverButtons(record) {
        const buttons = super.getPopoverButtons(record);

        // Update the save button text based on medical context
        if (record.appointment_type_id && this.model.metaData.canEdit && record.appointment_status) {
            buttons[0].text = "Save Status & Close";
        }

        // 🔐 Only add Pay button if POS is available (not in backend)
        if (this.env.services?.pos) {
            buttons.push({
                text: "Pay",
                className: "btn-primary",
                action: () => this.handlePayButtonClick(record),
            });
        }

        return buttons;
    },

    /**
     * Helper method to format patient information for display
     * For human medical: patients are both service recipients and billing customers
     */
    _formatPatientInfo(patientIds) {
        if (!patientIds || !Array.isArray(patientIds) || patientIds.length === 0) {
            return 'No patients assigned';
        }

        const patientNames = patientIds.map(patient => {
            if (Array.isArray(patient) && patient.length > 1) {
                return patient[1]; // [id, name] format
            }
            return patient.name || patient.toString();
        });

        if (patientNames.length === 1) {
            return patientNames[0];
        } else if (patientNames.length <= 3) {
            return patientNames.join(', ');
        } else {
            return `${patientNames.slice(0, 2).join(', ')} and ${patientNames.length - 2} more`;
        }
    },

    /**
     * Handle Pay button click in gantt popover
     * Opens POS with pre-filled appointment data
     */
    handlePayButtonClick(appointmentData) {
        if (!this.env.services.pos) {
            console.warn('POS service not available');
            return;
        }

        // Pre-fill POS with appointment data
        const posData = {
            partner_id: appointmentData.partner_id,
            practitioner_id: appointmentData.practitioner_id,
            patient_ids: appointmentData.patient_ids,
            encounter_id: appointmentData.encounter_id,
            appointment_id: appointmentData.id,
        };

        // Navigate to POS with pre-filled data
        this.env.services.action.doAction({
            type: 'ir.actions.client',
            tag: 'point_of_sale.ui',
            context: {
                default_appointment_data: posData,
            }
        });
    }
});

// TODO: Add encounter status color coding in gantt pills
// TODO: Implement encounter service count display in gantt
// TODO: Add encounter payment status indicators
// TODO: Implement drag-and-drop encounter service reordering
// TODO: Add encounter duplication from gantt context menu