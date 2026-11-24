from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataDesa(models.Model):
    _inherit = 'satu_data.desa'

    sd_sekolah_ids = fields.One2many('satu_data.sekolah', 'desa_id', string='Satuan Pendidikan')

    @api.constrains('company_id')
    def _check_company_pendidikan(self):
        # Data usia sekolah menyimpan kecamatan saat dicatat; memindahkan desa ke kab/kota lain
        # merusaknya.
        Usia = self.env['satu_data.pendidikan.usia_sekolah'].sudo()
        for rec in self:
            if Usia.search_count([('desa_id', '=', rec.id),
                                  ('kecamatan_id.company_id', '!=', rec.company_id.id)], limit=1):
                raise ValidationError(self.env._(
                    'Desa/kelurahan %(desa)s sudah punya data penduduk usia sekolah, sehingga '
                    'wilayah (kab/kota)-nya tidak bisa diubah.', desa=rec.name))
