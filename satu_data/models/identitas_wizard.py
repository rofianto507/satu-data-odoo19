from odoo import api, fields, models
from odoo.exceptions import AccessError

from .res_company import JENIS_WILAYAH


class SatuDataIdentitasWizard(models.TransientModel):
    """Ubah identitas wilayah (nama, logo, jenis, kode) pada company aktif.

    Admin Satu Data tidak diberi hak tulis ke ``res.company`` (yang berarti bisa
    mengubah semua field company, termasuk mata uang dan induk company). Wizard
    ini hanya menulis field yang ada di ``FIELD_IDENTITAS``.
    """
    _name        = 'satu_data.identitas.wizard'
    _description = 'Identitas Wilayah'

    FIELD_IDENTITAS = ('name', 'logo', 'sd_jenis_wilayah', 'sd_kode_wilayah')

    company_id       = fields.Many2one('res.company', string='Wilayah', required=True,
                                       readonly=True, default=lambda self: self.env.company)
    name             = fields.Char('Nama Wilayah', required=True,
                                   default=lambda self: self.env.company.name)
    logo             = fields.Binary('Logo', default=lambda self: self.env.company.logo)
    sd_jenis_wilayah = fields.Selection(
        JENIS_WILAYAH, string='Jenis Wilayah', required=True,
        default=lambda self: self.env.company.sd_jenis_wilayah)
    sd_kode_wilayah  = fields.Char(
        'Kode Wilayah Kemendagri', default=lambda self: self.env.company.sd_kode_wilayah,
        help='Format NN.NN, contoh: 16.71.')
    carto_api_key    = fields.Char(
        'API Key CARTO',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'satu_data.carto_api_key') or False,
        help='Untuk peta dasar Positron dan Voyager. Daftar gratis di '
             'https://carto.com/basemaps/apikey. Berlaku untuk semua wilayah (company). '
             'Kosongkan untuk memakai peta dasar OpenStreetMap saja.')

    @api.model
    def action_buka(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      self.env._('Identitas Wilayah'),
            'res_model': self._name,
            'view_mode': 'form',
            'views':     [(False, 'form')],
            'target':    'new',
        }

    def action_simpan(self):
        self.ensure_one()
        if self.company_id not in self.env.user.company_ids:
            raise AccessError(self.env._('Anda tidak memiliki akses ke wilayah ini.'))
        nilai = {
            'name':             (self.name or '').strip(),
            'logo':             self.logo or False,
            'sd_jenis_wilayah': self.sd_jenis_wilayah,
            'sd_kode_wilayah':  (self.sd_kode_wilayah or '').strip() or False,
        }
        company = self.company_id.sudo()
        # Tulis hanya yang berubah (logo tidak perlu diunggah ulang bila sama).
        nilai = {k: v for k, v in nilai.items() if k in self.FIELD_IDENTITAS and company[k] != v}
        if nilai:
            # sudo terbatas pada field identitas; constraint format dan keunikan tetap berlaku.
            company.write(nilai)
        # Parameter sistem global; hanya key ini yang ditulis.
        self.env['ir.config_parameter'].sudo().set_param(
            'satu_data.carto_api_key', (self.carto_api_key or '').strip() or False)
        # Muat ulang halaman agar nama dan logo baru tampil di menu dan dashboard.
        return {'type': 'ir.actions.client', 'tag': 'reload'}
