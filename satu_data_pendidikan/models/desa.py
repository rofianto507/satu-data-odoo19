from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataDesa(models.Model):
    _inherit = 'satu_data.desa'

    sd_sekolah_ids = fields.One2many('satu_data.sekolah', 'desa_id', string='Satuan Pendidikan')

    @api.constrains('company_id')
    def _check_company_pendidikan(self):
        # Data pendidikan menyimpan kecamatan saat dicatat; memindahkan desa ke kab/kota lain
        # merusaknya.
        Baris = [self.env[m].sudo() for m in ('satu_data.pendidikan.usia_sekolah',
                                              'satu_data.pendidikan.rekap')]
        for rec in self:
            if any(Model.search_count([
                    ('desa_id', '=', rec.id),
                    ('kecamatan_id.company_id', '!=', rec.company_id.id)], limit=1)
                    for Model in Baris):
                raise ValidationError(self.env._(
                    'Desa/kelurahan %(desa)s sudah punya data pendidikan, sehingga '
                    'wilayah (kab/kota)-nya tidak bisa diubah.', desa=rec.name))
