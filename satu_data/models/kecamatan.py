from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataKecamatan(models.Model):
    _name             = 'satu_data.kecamatan'
    _description      = 'Kecamatan'
    _inherit          = ['satu_data.geojson.mixin']
    _order            = 'kode, name'
    _rec_names_search = ['name', 'kode']
    _check_company_auto = True

    kode       = fields.Char('Kode', required=True, index=True)
    name       = fields.Char('Nama Kecamatan', required=True)
    active     = fields.Boolean('Aktif', default=True)
    # Induk kecamatan adalah wilayah kabupaten/kota yang diwakili company.
    company_id = fields.Many2one(
        'res.company', string='Wilayah (Kab/Kota)', required=True, index=True,
        default=lambda self: self.env.company, ondelete='restrict',
    )
    desa_ids    = fields.One2many('satu_data.desa', 'kecamatan_id', string='Desa/Kelurahan')
    jumlah_desa = fields.Integer('Jumlah Desa/Kel.', compute='_compute_jumlah_desa')
    luas_km2    = fields.Float('Luas (km²)', digits=(12, 2), compute='_compute_luas_km2',
                               help='Jumlah luas desa/kelurahan aktif di kecamatan ini.')

    _kode_company_uniq = models.Constraint(
        'UNIQUE(company_id, kode)',
        'Kode kecamatan sudah dipakai di wilayah ini.',
    )

    @api.depends('desa_ids')
    def _compute_jumlah_desa(self):
        tersimpan = self.filtered('id')  # record baru (NewId) bernilai False
        hasil = dict(self.env['satu_data.desa']._read_group(
            [('kecamatan_id', 'in', tersimpan.ids)], ['kecamatan_id'], ['__count'],
        )) if tersimpan else {}
        for rec in self:
            rec.jumlah_desa = hasil.get(rec, 0) if rec.id else len(rec.desa_ids)

    @api.depends('desa_ids.luas_km2')
    def _compute_luas_km2(self):
        for rec in self:
            rec.luas_km2 = sum(rec.desa_ids.mapped('luas_km2'))

    @api.constrains('company_id')
    def _check_company_desa(self):
        for rec in self:
            desa = rec.with_context(active_test=False).desa_ids
            if desa.filtered(lambda d: d.company_id != rec.company_id):
                raise ValidationError(self.env._(
                    'Wilayah (kab/kota) kecamatan %(kec)s tidak bisa diubah karena masih '
                    'memiliki desa/kelurahan di wilayah lama.', kec=rec.name))
