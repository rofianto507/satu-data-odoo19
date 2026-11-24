import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

JENJANG = [
    ('paud', 'PAUD/TK/KB'),
    ('sd',   'SD'),
    ('mi',   'MI'),
    ('smp',  'SMP'),
    ('mts',  'MTs'),
    ('sma',  'SMA'),
    ('smk',  'SMK'),
    ('ma',   'MA'),
    ('slb',  'SLB'),
    ('pkbm', 'PKBM/Kesetaraan'),
    ('lain', 'Lainnya'),
]
# Pengelompokan untuk indikator (SD/MI, SMP/MTs, SMA/SMK/MA digabung).
KELOMPOK = [
    ('paud',       'PAUD/TK'),
    ('sd_mi',      'SD/MI'),
    ('smp_mts',    'SMP/MTs'),
    ('sma_smk_ma', 'SMA/SMK/MA'),
    ('lain',       'Lainnya'),
]
KELOMPOK_JENJANG = {
    'paud': 'paud', 'sd': 'sd_mi', 'mi': 'sd_mi', 'smp': 'smp_mts', 'mts': 'smp_mts',
    'sma': 'sma_smk_ma', 'smk': 'sma_smk_ma', 'ma': 'sma_smk_ma',
}
# Madrasah dibina Kementerian Agama; selebihnya Dinas Pendidikan. (RA = PAUD binaan Kemenag:
# ubah pembinanya secara manual.)
JENJANG_KEMENAG = ('mi', 'mts', 'ma')


class SatuDataSekolah(models.Model):
    """Satuan pendidikan (sekolah, madrasah, PAUD, dan sejenisnya) beserta lokasinya."""
    _name        = 'satu_data.sekolah'
    _description = 'Satuan Pendidikan'
    _inherit     = ['mail.thread']
    _order       = 'kecamatan_id, desa_id, jenjang, name'

    name       = fields.Char('Nama Satuan Pendidikan', required=True, tracking=True)
    npsn       = fields.Char('NPSN', tracking=True, index=True,
                             help='Nomor Pokok Sekolah Nasional (8 angka), bila ada.')
    jenjang    = fields.Selection(JENJANG, string='Jenjang', required=True, default='sd',
                                  tracking=True, index=True)
    kelompok   = fields.Selection(KELOMPOK, string='Kelompok Jenjang', compute='_compute_kelompok',
                                  store=True, precompute=True, index=True,
                                  help='SD dan MI dihitung bersama (SD/MI), demikian pula SMP/MTs '
                                       'dan SMA/SMK/MA.')
    status     = fields.Selection([('negeri', 'Negeri'), ('swasta', 'Swasta')], string='Status',
                                  required=True, default='negeri', tracking=True, index=True)
    pembina    = fields.Selection([
        ('disdik',  'Dinas Pendidikan'),
        ('kemenag', 'Kementerian Agama'),
    ], string='Pembina', compute='_compute_pembina', store=True, precompute=True,
        readonly=False, required=True, tracking=True, index=True,
        help='Terisi otomatis dari jenjang (madrasah = Kementerian Agama); bisa diubah, mis. RA.')
    akreditasi = fields.Selection([
        ('a', 'A'), ('b', 'B'), ('c', 'C'), ('belum', 'Belum/Tidak Terakreditasi'),
    ], string='Akreditasi', tracking=True)
    # Tanpa check_company: company_id diturunkan dari desa_id (lihat rekap kependudukan).
    desa_id    = fields.Many2one('satu_data.desa', string='Desa/Kelurahan', required=True,
                                 index=True, ondelete='restrict', tracking=True,
                                 domain="[('company_id', 'in', allowed_company_ids)]")
    kecamatan_id = fields.Many2one(related='desa_id.kecamatan_id', store=True, index=True,
                                   string='Kecamatan')
    company_id = fields.Many2one(related='desa_id.company_id', store=True, index=True,
                                 string='Wilayah (Kab/Kota)')
    alamat     = fields.Char('Alamat')
    telepon    = fields.Char('Telepon')
    latitude   = fields.Float('Lintang', digits=(10, 6))
    longitude  = fields.Float('Bujur', digits=(10, 6))
    active     = fields.Boolean(default=True)

    _npsn_company_uniq = models.Constraint(
        'UNIQUE(company_id, npsn)',
        'NPSN sudah dipakai satuan pendidikan lain di wilayah ini.',
    )

    @api.depends('jenjang')
    def _compute_kelompok(self):
        for rec in self:
            rec.kelompok = KELOMPOK_JENJANG.get(rec.jenjang, 'lain')

    @api.depends('jenjang')
    def _compute_pembina(self):
        for rec in self:
            rec.pembina = 'kemenag' if rec.jenjang in JENJANG_KEMENAG else 'disdik'

    @api.depends('name', 'npsn')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.name} ({rec.npsn})' if rec.npsn else rec.name or ''

    @api.constrains('npsn')
    def _check_npsn(self):
        for rec in self.filtered('npsn'):
            if not re.fullmatch(r'\d{8}', rec.npsn):
                raise ValidationError(self.env._('NPSN harus terdiri dari 8 angka.'))

    @api.constrains('latitude', 'longitude')
    def _check_koordinat(self):
        for rec in self:
            if not (-90 <= rec.latitude <= 90 and -180 <= rec.longitude <= 180):
                raise ValidationError(self.env._('Koordinat tidak valid.'))
