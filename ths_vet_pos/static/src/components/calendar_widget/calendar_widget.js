/** @odoo-module */
console.log("Loading: ths_medical_pos/static/src/components/calendar_widget/calendar_widget.js");

import { Component, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/store/pos_hook";

export class MedicalCalendarWidget extends Component {
    static template = "ths_medical_pos.MedicalCalendarWidget";
    static props = {};

    setup() {
        this.pos = usePos();
        this.calendarRef = useRef("calendar");

        onMounted(() => {
            this.initializeCalendar();
        });
    }

    async initializeCalendar() {
        if (window.FullCalendar && this.calendarRef.el) {
            const calendar = new window.FullCalendar.Calendar(this.calendarRef.el, {
                initialView: 'dayGridMonth',
                headerToolbar: {
                    left: 'prev,next today',
                    center: 'title',
                    right: 'dayGridMonth,timeGridWeek,timeGridDay'
                },
                events: async (info, successCallback, failureCallback) => {
                    try {
                        const events = await this.fetchEvents(info.start, info.end);
                        successCallback(events);
                    } catch (error) {
                        failureCallback(error);
                    }
                },
                eventClick: (info) => {
                    this.onEventClick(info.event);
                }
            });
            calendar.render();
        }
    }

    async fetchEvents(start, end) {
        const domain = [
            ['start', '>=', start.toISOString()],
            ['stop', '<=', end.toISOString()],
            ['patient_ids', '!=', false]  // Changed from patient_ids to patient_ids
        ];

        const events = await this.env.services.orm.searchRead(
            'calendar.event',
            domain,
            ['name', 'start', 'stop', 'patient_ids', 'appointment_status'],  // Updated field name
            { limit: 100 }
        );

        return events.map(event => ({
            id: event.id,
            title: event.name,
            start: event.start,
            end: event.stop,
            color: this.getStatusColor(event.appointment_status),
            extendedProps: {
                patients: event.patient_ids,  // Now returns array of patient records
                status: event.appointment_status
            }
        }));
    }

    getStatusColor(status) {
        const colors = {
            'draft': '#6c757d',        // gray
            'confirmed': '#007bff',    // blue
            'checked_in': '#ffc107',   // yellow
            'in_progress': '#fd7e14',  // orange
            'completed': '#28a745',    // green
            'billed': '#20c997',       // teal
            'cancelled_by_patient': '#dc3545',  // red
            'cancelled_by_clinic': '#dc3545',   // red
            'no_show': '#6c757d'       // gray
        };
        return colors[status] || '#007bff';
    }

    onEventClick(event) {
        console.log("Appointment clicked:", event);
        // TODO: Show appointment details popup or navigate to appointment form
        // Can access patient info via event.extendedProps.patients
    }
}

registry.category("pos_widgets").add("MedicalCalendarWidget", MedicalCalendarWidget);