from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataKesehatanWilayahMixin(models.AbstractModel):
    """Desa/kelurahan, kecamatan, dan puskesmas untuk data kesehatan per desa.

    Kecamatan dan puskesmas dicatat saat data dibuat (snapshot): bila desa dipindah
    kecamatan atau wilayah kerja puskesmas berubah, data lama tetap di tempat lamanya.
    """
    _name        = 'satu_data.kesehatan.wilayah.mixin'
    _description = 'Mixin Wilayah Data Kesehatan'

    # Tanpa check_company: company_id diturunkan dari desa_id (lihat rekap kependudukan).
    desa_id      = fields.Many2one(
        'satu_data.desa', string='Desa/Kelurahan', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('company_id', 'in', allowed_company_ids)]")
    kecamatan_id = fields.Many2one(
        'satu_data.kecamatan', string='Kecamatan', compute='_compute_wilayah',
        store=True, precompute=True, index=True, readonly=True,
        help='Kecamatan desa/kelurahan pada saat data ini dicatat.')
    puskesmas_id = fields.Many2one(
        'satu_data.faskes', string='Puskesmas', compute='_compute_wilayah',
        store=True, precompute=True, readonly=False, index=True, ondelete='restrict',
        tracking=True, domain="[('jenis', '=', 'puskesmas'), ('company_id', '=', company_id)]",
        help='Puskesmas wilayah kerja desa/kelurahan ini pada saat data dicatat. '
             'Terisi dari wilayah kerja puskesmas; bisa disesuaikan.')
    company_id   = fields.Many2one(related='desa_id.company_id', store=True, index=True,
                                   string='Wilayah (Kab/Kota)')
    sumber       = fields.Char('Sumber Data')

    @api.depends('desa_id')
    def _compute_wilayah(self):
        # Sengaja hanya bergantung pada desa_id (snapshot saat data dicatat).
        for rec in self:
            rec.kecamatan_id = rec.desa_id.kecamatan_id
            rec.puskesmas_id = rec.desa_id.sd_puskesmas_id

    @api.depends('desa_id.name', 'periode_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ' – '.join(filter(None, [rec.desa_id.name, rec.periode_id.name]))

    @api.constrains('puskesmas_id', 'desa_id')
    def _check_puskesmas(self):
        for rec in self.filtered('puskesmas_id'):
            if rec.puskesmas_id.jenis != 'puskesmas' or \
                    rec.puskesmas_id.company_id != rec.company_id:
                raise ValidationError(self.env._(
                    'Puskesmas harus puskesmas di wilayah (kab/kota) yang sama.'))

    def _cek_tidak_negatif(self, nama_field, pesan):
        for rec in self:
            if any(rec[f] < 0 for f in nama_field):
                raise ValidationError(pesan)
