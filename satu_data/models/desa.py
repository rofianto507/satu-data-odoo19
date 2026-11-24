from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataDesa(models.Model):
    _name             = 'satu_data.desa'
    _description      = 'Desa/Kelurahan'
    _inherit          = ['satu_data.geojson.mixin']
    _order            = 'kode, name'
    _rec_names_search = ['name', 'kode']
    _check_company_auto = True

    kode         = fields.Char('Kode', required=True, index=True)
    name         = fields.Char('Nama Desa/Kelurahan', required=True)
    jenis        = fields.Selection([
        ('desa',      'Desa'),
        ('kelurahan', 'Kelurahan'),
    ], string='Jenis', required=True, default='desa')
    active       = fields.Boolean('Aktif', default=True)
    kecamatan_id = fields.Many2one(
        'satu_data.kecamatan', string='Kecamatan', required=True, index=True,
        ondelete='restrict', check_company=True,
    )
    company_id   = fields.Many2one(
        'res.company', string='Wilayah (Kab/Kota)', required=True, index=True,
        default=lambda self: self.env.company, ondelete='restrict',
    )
    luas_km2     = fields.Float(
        'Luas (km²)', digits=(12, 2),
        help='Opsional. Dipakai untuk menghitung kepadatan penduduk di semua periode.',
    )

    _kode_company_uniq = models.Constraint(
        'UNIQUE(company_id, kode)',
        'Kode desa/kelurahan sudah dipakai di wilayah ini.',
    )

    @api.depends('name', 'kecamatan_id.name')
    def _compute_display_name(self):
        # Nama desa bisa sama di dua kecamatan; sertakan kecamatan agar jelas.
        for rec in self:
            if rec.kecamatan_id:
                rec.display_name = f'{rec.name} ({rec.kecamatan_id.name})'
            else:
                rec.display_name = rec.name or ''

    @api.model
    def _sd_geometri_induk(self, kecamatan_id):
        # Editor peta: tampilkan batas kecamatan sebagai acuan.
        if not kecamatan_id:
            return None
        kecamatan = self.env['satu_data.kecamatan'].browse(int(kecamatan_id)).exists()
        return kecamatan._sd_geometri() if kecamatan else None

    @api.onchange('kecamatan_id')
    def _onchange_kecamatan_id(self):
        if self.kecamatan_id:
            self.company_id = self.kecamatan_id.company_id

    @api.constrains('luas_km2')
    def _check_luas(self):
        for rec in self:
            if rec.luas_km2 < 0:
                raise ValidationError(self.env._('Luas wilayah tidak boleh bernilai negatif.'))
