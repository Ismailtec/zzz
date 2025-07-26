# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, tools
import logging

_logger = logging.getLogger(__name__)


class VetMedicalHistorySummary(models.Model):
	_name = 'vet.medical.history.summary'
	_description = 'Pet Medical History Summary'
	_auto = False  # This is a database view
	_order = 'last_visit_date desc, pet_id'

	# Basic Information
	pet_id = fields.Many2one('res.partner', string='Pet', readonly=True)
	owner_id = fields.Many2one('res.partner', string='Owner', readonly=True)
	pet_name = fields.Char(string='Pet Name', readonly=True)
	owner_name = fields.Char(string='Owner Name', readonly=True)
	species_name = fields.Char(string='Species', readonly=True)
	breed_name = fields.Char(string='Breed', readonly=True)

	# Encounter Statistics
	encounter_count = fields.Integer(string='Total Encounters', readonly=True)
	last_visit_date = fields.Date(string='Last Visit', readonly=True)
	first_visit_date = fields.Date(string='First Visit', readonly=True)
	total_spent = fields.Float(string='Total Spent', readonly=True)
	pending_amount = fields.Float(string='Pending Payments', readonly=True)

	# Service Statistics
	vaccination_count = fields.Integer(string='Vaccinations', readonly=True)
	expired_vaccinations = fields.Integer(string='Expired Vaccinations', readonly=True)
	upcoming_vaccinations = fields.Integer(string='Upcoming Vaccinations', readonly=True)
	boarding_count = fields.Integer(string='Boarding Stays', readonly=True)
	park_visit_count = fields.Integer(string='Park Visits', readonly=True)
	membership_count = fields.Integer(string='Active Memberships', readonly=True)
	appointment_count = fields.Integer(string='Total Appointments', readonly=True)

	# Last Service Dates
	last_vaccination_date = fields.Date(string='Last Vaccination', readonly=True)
	last_boarding_date = fields.Date(string='Last Boarding', readonly=True)
	last_park_visit_date = fields.Date(string='Last Park Visit', readonly=True)
	last_service_date = fields.Date(string='Last Service', readonly=True)

	# Health Indicators
	needs_vaccination = fields.Boolean(string='Needs Vaccination', readonly=True)
	overdue_vaccination = fields.Boolean(string='Overdue Vaccination', readonly=True)
	high_value_client = fields.Boolean(string='High Value Client', readonly=True)
	frequent_visitor = fields.Boolean(string='Frequent Visitor', readonly=True)

	# Computed Display Fields
	visit_frequency = fields.Char(string='Visit Frequency', readonly=True)
	health_status = fields.Char(string='Health Status', readonly=True)
	client_category = fields.Char(string='Client Category', readonly=True)

	def init(self):
		"""Create the database view with enhanced medical history analytics using proper joins.
		Computes financial sums from lines with proration for multi-pet lines."""
		tools.drop_view_if_exists(self.env.cr, self._table)
		self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT 
                    row_number() OVER (ORDER BY pet.id) AS id,

                    -- Basic Information
                    pet.id AS pet_id,
                    pet.pet_owner_id AS owner_id,
                    pet.name AS pet_name,
                    owner.name AS owner_name,
                    species.name AS species_name,
                    breed.name AS breed_name,

                    -- Encounter Statistics
                    COALESCE(enc_stats.encounter_count, 0) AS encounter_count,
                    enc_stats.last_visit_date,
                    enc_stats.first_visit_date,
                    COALESCE(fin_stats.total_spent, 0) AS total_spent,
                    COALESCE(fin_stats.pending_amount, 0) AS pending_amount,

                    -- Service Statistics
                    COALESCE(vacc_stats.vaccination_count, 0) AS vaccination_count,
                    COALESCE(vacc_stats.expired_count, 0) AS expired_vaccinations,
                    COALESCE(vacc_stats.upcoming_count, 0) AS upcoming_vaccinations,
                    COALESCE(board_stats.boarding_count, 0) AS boarding_count,
                    COALESCE(park_stats.park_visit_count, 0) AS park_visit_count,
                    COALESCE(memb_stats.membership_count, 0) AS membership_count,
                    COALESCE(appt_stats.appointment_count, 0) AS appointment_count,

                    -- Last Service Dates
                    vacc_stats.last_vacc_date AS last_vaccination_date,
                    board_stats.last_board_date AS last_boarding_date,
                    park_stats.last_park_date AS last_park_visit_date,
                    GREATEST(
                        COALESCE(enc_stats.last_visit_date, '1900-01-01'::date),
                        COALESCE(vacc_stats.last_vacc_date, '1900-01-01'::date),
                        COALESCE(board_stats.last_board_date, '1900-01-01'::date),
                        COALESCE(park_stats.last_park_date, '1900-01-01'::date),
                        COALESCE(appt_stats.last_apt_date, '1900-01-01'::date)
                    ) AS last_service_date,

                    -- Health Indicators
                    (COALESCE(vacc_stats.expired_count, 0) > 0 OR 
                     COALESCE(vacc_stats.upcoming_count, 0) > 0) AS needs_vaccination,
                    (COALESCE(vacc_stats.expired_count, 0) > 0) AS overdue_vaccination,
                    (COALESCE(fin_stats.total_spent, 0) > 5000) AS high_value_client,
                    (COALESCE(enc_stats.encounter_count, 0) > 10) AS frequent_visitor,

                    -- Display Categories
                    CASE 
                        WHEN COALESCE(enc_stats.encounter_count, 0) = 0 THEN 'No Visits'
                        WHEN enc_stats.last_visit_date > (CURRENT_DATE - INTERVAL '30 days') THEN 'Recent'
                        WHEN enc_stats.last_visit_date > (CURRENT_DATE - INTERVAL '90 days') THEN 'Regular'
                        WHEN enc_stats.last_visit_date > (CURRENT_DATE - INTERVAL '365 days') THEN 'Occasional'
                        ELSE 'Inactive'
                    END AS visit_frequency,

                    CASE 
                        WHEN COALESCE(vacc_stats.expired_count, 0) > 0 THEN 'Overdue Vaccinations'
                        WHEN COALESCE(vacc_stats.upcoming_count, 0) > 0 THEN 'Vaccinations Due Soon'
                        WHEN COALESCE(vacc_stats.vaccination_count, 0) > 0 THEN 'Up to Date'
                        ELSE 'No Vaccination Records'
                    END AS health_status,

                    CASE 
                        WHEN COALESCE(fin_stats.total_spent, 0) > 10000 THEN 'Platinum'
                        WHEN COALESCE(fin_stats.total_spent, 0) > 5000 THEN 'Gold'
                        WHEN COALESCE(fin_stats.total_spent, 0) > 1000 THEN 'Silver'
                        WHEN COALESCE(fin_stats.total_spent, 0) > 0 THEN 'Bronze'
                        ELSE 'New'
                    END AS client_category

                FROM res_partner pet
                LEFT JOIN res_partner owner ON owner.id = pet.pet_owner_id
                LEFT JOIN vet_species species ON species.id = pet.species_id
                LEFT JOIN vet_breed breed ON breed.id = pet.breed_id

                -- Encounter Base Statistics (counts and dates)
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        COUNT(DISTINCT e.id) AS encounter_count,
                        MAX(e.encounter_date) AS last_visit_date,
                        MIN(e.encounter_date) AS first_visit_date
                    FROM vet_encounter_header e
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = e.id
                    WHERE e.state IN ('in_progress', 'done')
                    GROUP BY rel.patient_id
                ) enc_stats ON enc_stats.pet_id = pet.id

                -- Financial Statistics from Lines (prorated for multi-pet)
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        SUM(l.sub_total / GREATEST((SELECT COUNT(*) FROM vet_encounter_mixin_patient_rel rel2 WHERE rel2.encounter_id = l.id), 1)) AS total_spent,
                        SUM(l.remaining_amount / GREATEST((SELECT COUNT(*) FROM vet_encounter_mixin_patient_rel rel2 WHERE rel2.encounter_id = l.id), 1)) AS pending_amount
                    FROM vet_encounter_line l
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = l.id
                    JOIN vet_encounter_header e ON e.id = l.encounter_id
                    WHERE e.state IN ('in_progress', 'done')
                    GROUP BY rel.patient_id
                ) fin_stats ON fin_stats.pet_id = pet.id

                -- Vaccination Statistics
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        COUNT(DISTINCT v.id) AS vaccination_count,
                        SUM(CASE WHEN v.is_expired = true THEN 1 ELSE 0 END) AS expired_count,
                        SUM(CASE WHEN v.expiry_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '30 days') THEN 1 ELSE 0 END) AS upcoming_count,
                        MAX(v.date) AS last_vacc_date
                    FROM vet_vaccination v
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = v.id
                    GROUP BY rel.patient_id
                ) vacc_stats ON vacc_stats.pet_id = pet.id

                -- Boarding Statistics
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        COUNT(DISTINCT b.id) AS boarding_count,
                        MAX(b.check_in_datetime::date) AS last_board_date
                    FROM vet_boarding_stay b
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = b.id
                    WHERE b.state != 'cancelled'
                    GROUP BY rel.patient_id
                ) board_stats ON board_stats.pet_id = pet.id

                -- Park Visit Statistics
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        COUNT(DISTINCT p.id) AS park_visit_count,
                        MAX(p.checkin_time::date) AS last_park_date
                    FROM vet_park_checkin p
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = p.id
                    WHERE p.state = 'checked_out'
                    GROUP BY rel.patient_id
                ) park_stats ON park_stats.pet_id = pet.id

                -- Membership Statistics
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        COUNT(DISTINCT m.id) AS membership_count
                    FROM vet_pet_membership m
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = m.id
                    WHERE m.state = 'active'
                    GROUP BY rel.patient_id
                ) memb_stats ON memb_stats.pet_id = pet.id

                -- Appointment Statistics
                LEFT JOIN (
                    SELECT 
                        rel.patient_id AS pet_id,
                        COUNT(DISTINCT c.id) AS appointment_count,
                        MAX(c.start::date) AS last_apt_date
                    FROM calendar_event c
                    JOIN vet_encounter_mixin_patient_rel rel ON rel.encounter_id = c.id
                    WHERE c.appointment_status IN ('completed', 'paid')
                    GROUP BY rel.patient_id
                ) appt_stats ON appt_stats.pet_id = pet.id

                WHERE pet.is_pet = TRUE
                  AND pet.active = TRUE
            )
        """)

	@api.model
	def get_summary_statistics(self):
		"""Get overall summary statistics for dashboard"""
		self.env.cr.execute("""
            SELECT COUNT(*)                                                                          as total_pets,
                   COUNT(CASE WHEN last_visit_date > (CURRENT_DATE - INTERVAL '30 days') THEN 1 END) as active_pets,
                   COUNT(CASE WHEN overdue_vaccination = true THEN 1 END)                            as overdue_vaccinations,
                   COUNT(CASE WHEN high_value_client = true THEN 1 END)                              as high_value_clients,
                   AVG(total_spent)                                                                  as avg_spent_per_pet,
                   SUM(pending_amount)                                                               as total_pending
            FROM vet_medical_history_summary
        """)

		result = self.env.cr.dictfetchone()
		return result if result else {}

	def action_view_pet_encounters(self):
		"""View all encounters for this pet"""
		self.ensure_one()
		return {
			'name': f'Medical History - {self.pet_name}',
			'type': 'ir.actions.act_window',
			'res_model': 'vet.encounter.header',
			'view_mode': 'list,form',
			'domain': [('patient_ids', 'in', [self.pet_id.id])],
			'context': {'search_default_groupby_date': 1},
		}

	def action_schedule_vaccination_reminder(self):
		"""Schedule vaccination reminder for this pet"""
		self.ensure_one()
		if not self.needs_vaccination:
			return {'type': 'ir.actions.act_window_close'}

		# Create activity reminder for vaccination
		self.pet_id.activity_schedule(
			'mail.mail_activity_data_todo',
			date_deadline=fields.Date.today() + timedelta(days=7),
			summary=f'Vaccination Reminder for {self.pet_name}',
			note=f'Pet {self.pet_name} needs vaccination update. '
				 f'Expired vaccinations: {self.expired_vaccinations}, '
				 f'Upcoming vaccinations: {self.upcoming_vaccinations}',
			user_id=self.env.user.id,
		)

		return {
			'type': 'ir.actions.client',
			'tag': 'display_notification',
			'params': {
				'message': f'Vaccination reminder scheduled for {self.pet_name}',
				'type': 'success',
			}
		}

	def action_view_owner_pets(self):
		"""View all pets for this owner"""
		self.ensure_one()
		return {
			'name': f'All Pets - {self.owner_name}',
			'type': 'ir.actions.act_window',
			'res_model': 'vet.medical.history.summary',
			'view_mode': 'list,form',
			'domain': [('owner_id', '=', self.owner_id.id)],
		}