from odoo import api, models
from odoo.exceptions import ValidationError


class SatuDataDesa(models.Model):
    _inherit = 'satu_data.desa'

    @api.constrains('company_id')
    def _check_company_kependudukan(self):
        # Data kependudukan menyimpan kecamatan saat dicatat; memindahkan desa ke
        # kab/kota lain akan membuat data lama menunjuk kecamatan company lain.
        Pdd = self.env['satu_data.kependudukan'].sudo()
        for rec in self:
            if Pdd.search_count([('desa_id', '=', rec.id),
                                 ('kecamatan_id.company_id', '!=', rec.company_id.id)], limit=1):
                raise ValidationError(self.env._(
                    'Desa/kelurahan %(desa)s sudah memiliki data kependudukan, sehingga '
                    'wilayah (kab/kota)-nya tidak bisa diubah.', desa=rec.name))
