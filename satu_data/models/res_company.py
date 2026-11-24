import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Kode Kemendagri kabupaten/kota: 2 digit provinsi, titik, 2 digit kab/kota. Contoh: 16.71
KODE_WILAYAH_RE = re.compile(r'^\d{2}\.\d{2}$')

JENIS_WILAYAH = [
    ('kabupaten', 'Kabupaten'),
    ('kota',      'Kota'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Nama wilayah = name, logo wilayah = logo (field bawaan company).
    sd_jenis_wilayah = fields.Selection(JENIS_WILAYAH, string='Jenis Wilayah')
    sd_kode_wilayah = fields.Char(
        'Kode Wilayah Kemendagri',
        help='Kode kabupaten/kota menurut Kemendagri, format NN.NN (contoh: 16.71).',
    )

    _sd_kode_wilayah_uniq = models.Constraint(
        'UNIQUE(sd_kode_wilayah)',
        'Kode wilayah Kemendagri sudah dipakai company lain.',
    )

    @api.constrains('sd_kode_wilayah')
    def _check_sd_kode_wilayah(self):
        for company in self:
            kode = company.sd_kode_wilayah
            if kode and not KODE_WILAYAH_RE.match(kode):
                raise ValidationError(self.env._(
                    'Kode wilayah "%(kode)s" tidak sesuai format NN.NN (contoh: 16.71).',
                    kode=kode,
                ))
