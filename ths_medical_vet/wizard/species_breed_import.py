# -*- coding: utf-8 -*-

from odoo import models, fields, _
from odoo.exceptions import UserError
import base64
import csv
import io


class SpeciesBreedImportWizard(models.TransientModel):
    _name = 'vet.species.breed.import.wizard'
    _description = 'Import Species and Breeds'

    import_type = fields.Selection([
        ('species', 'Species'),
        ('breed', 'Breeds')
    ], string='Import Type', required=True, default='species')

    file = fields.Binary(string='CSV File', required=True)
    filename = fields.Char(string='Filename')
    delimiter = fields.Selection([
        (',', 'Comma'),
        (';', 'Semicolon'),
        ('|', 'Pipe'),
        ('\t', 'Tab')
    ], string='Delimiter', default=',', required=True)

    sample_data = fields.Text(
        string='Sample Data',
        readonly=True,
        default="""Species Import Format:
name
Dog
Cat
Bird

Breed Import Format (requires species):
name,species
Labrador Retriever,Dog
Persian,Cat
Canary,Bird"""
    )

    import_summary = fields.Text(string='Import Summary', readonly=True)

    def action_import(self):
        """Import species or breeds from CSV"""
        self.ensure_one()

        if not self.file:
            raise UserError(_("Please upload a file."))

        # Decode file
        try:
            csv_data = base64.b64decode(self.file)
            file_input = io.StringIO(csv_data.decode('utf-8'))
            reader = csv.DictReader(file_input, delimiter=self.delimiter)
        except Exception as e:
            raise UserError(_("Error reading file: %s") % str(e))

        if self.import_type == 'species':
            result = self._import_species(reader)
        else:
            result = self._import_breeds(reader)

        self.import_summary = result

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def _import_species(self, reader):
        """Import species records"""
        Species = self.env['ths.species']
        created = 0
        skipped = 0
        errors = []

        for row_num, row in enumerate(reader, start=2):
            try:
                name = row.get('name', '').strip()
                if not name:
                    errors.append(_("Row %d: Empty name") % row_num)
                    continue

                # Check if exists
                existing = Species.search([('name', '=ilike', name)], limit=1)
                if existing:
                    skipped += 1
                    continue

                # Create
                Species.create({'name': name})
                created += 1

            except Exception as e:
                errors.append(_("Row %d: %s") % (row_num, str(e)))

        summary = _("Import Complete!\n")
        summary += _("Created: %d species\n") % created
        summary += _("Skipped: %d (already exist)\n") % skipped
        if errors:
            summary += _("\nErrors:\n") + "\n".join(errors[:10])
            if len(errors) > 10:
                summary += _("\n... and %d more errors") % (len(errors) - 10)

        return summary

    def _import_breeds(self, reader):
        """Import breed records"""
        Breed = self.env['ths.breed']
        Species = self.env['ths.species']
        created = 0
        skipped = 0
        errors = []

        # Cache species for performance
        species_map = {s.name.lower(): s.id for s in Species.search([])}

        for row_num, row in enumerate(reader, start=2):
            try:
                name = row.get('name', '').strip()
                species_name = row.get('species', '').strip()

                if not name:
                    errors.append(_("Row %d: Empty breed name") % row_num)
                    continue

                # Check if breed exists
                existing = Breed.search([('name', '=ilike', name)], limit=1)
                if existing:
                    skipped += 1
                    continue

                # Validate species if provided
                breed_vals = {'name': name}
                if species_name:
                    species_id = species_map.get(species_name.lower())
                    if not species_id:
                        errors.append(
                            _("Row %d: Unknown species '%s'") % (row_num, species_name)
                        )
                        continue
                    # Note: Add species_id to breed if you add species relation to breed model

                # Create breed
                Breed.create(breed_vals)
                created += 1

            except Exception as e:
                errors.append(_("Row %d: %s") % (row_num, str(e)))

        summary = _("Import Complete!\n")
        summary += _("Created: %d breeds\n") % created
        summary += _("Skipped: %d (already exist)\n") % skipped
        if errors:
            summary += _("\nErrors:\n") + "\n".join(errors[:10])
            if len(errors) > 10:
                summary += _("\n... and %d more errors") % (len(errors) - 10)

        return summary

    def action_download_template(self):
        """Download CSV template"""
        self.ensure_one()

        if self.import_type == 'species':
            content = "name\nDog\nCat\nBird\nRabbit\nHamster"
            filename = "species_template.csv"
        else:
            content = "name,species\nLabrador Retriever,Dog\nGerman Shepherd,Dog\nPersian,Cat\nSiamese,Cat"
            filename = "breeds_template.csv"

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(content.encode('utf-8')),
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
