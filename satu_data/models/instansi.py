from odoo import api, fields, models
from odoo.exceptions import ValidationError

PERAN = [
    ('produsen',           'Produsen Data'),
    ('walidata',           'Walidata'),
    ('walidata_pendukung', 'Walidata Pendukung'),
    ('sekretariat',        'Sekretariat Satu Data'),
    ('pembina',            'Pembina Data'),
]
# Peran yang hanya boleh dipegang satu instansi per wilayah.
PERAN_TUNGGAL = ('walidata', 'sekretariat')


class SatuDataInstansi(models.Model):
    """Instansi dalam penyelenggaraan Satu Data daerah.

    Produsen Data (perangkat daerah penghasil data), Walidata (mis. Diskominfo:
    memeriksa dan menyebarluaskan data), Walidata Pendukung, Sekretariat Satu Data
    (mis. Bappeda: koordinator Forum Satu Data), atau Pembina Data (mis. BPS).
    """
    _name        = 'satu_data.instansi'
    _description = 'Instansi Satu Data'
    _order       = 'sequence, name'

    name       = fields.Char('Nama Instansi', required=True)
    singkatan  = fields.Char('Singkatan', help='Mis. Dinkes, Diskominfo.')
    kode       = fields.Char('Kode Instansi',
                             help='Kode instansi sesuai referensi yang berlaku (opsional).')
    jenis      = fields.Selection([
        ('opd',      'Perangkat Daerah'),
        ('vertikal', 'Instansi Vertikal'),
        ('lain',     'Lainnya'),
    ], string='Jenis', required=True, default='opd')
    peran      = fields.Selection(PERAN, string='Peran Satu Data', required=True,
                                  default='produsen',
        help='Walidata: memeriksa data dari Produsen Data dan menyebarluaskannya. '
             'Walidata Pendukung: membantu Walidata memeriksa data di bidangnya. '
             'Sekretariat Satu Data (mis. Bappeda): mengoordinasikan Forum Satu Data '
             'dan penyebarluasan data ke luar pemerintah daerah. '
             'Pembina Data: membina standar data dan metadata (mis. BPS).')
    urusan_ids = fields.Many2many('satu_data.urusan', string='Urusan Pemerintahan',
                                  help='Urusan yang menjadi kewenangan instansi ini.')
    company_id = fields.Many2one('res.company', string='Wilayah (Kab/Kota)', required=True,
                                 index=True, default=lambda self: self.env.company)
    sequence   = fields.Integer(default=10)
    active     = fields.Boolean(default=True)
    email      = fields.Char('Email')
    telepon    = fields.Char('Telepon')
    user_ids   = fields.One2many('res.users', 'sd_instansi_id', string='Petugas')
    data_ids   = fields.One2many('satu_data.data', 'instansi_id', string='Daftar Data')
    jumlah_data = fields.Integer('Jumlah Data', compute='_compute_jumlah_data')

    # Kinerja Produsen Data: ketepatan jadwal pemutakhiran (penilaian kualitas data)
    jumlah_pengajuan = fields.Integer('Pengajuan Dinilai', compute='_compute_kinerja',
                                      help='Pengajuan yang sudah pernah diajukan ke Walidata.')
    jumlah_tepat     = fields.Integer('Tepat Waktu', compute='_compute_kinerja')
    persen_tepat     = fields.Float('Ketepatan Waktu (%)', compute='_compute_kinerja',
                                    digits=(5, 1))

    _nama_company_uniq = models.Constraint(
        'UNIQUE(company_id, name)',
        'Nama instansi sudah dipakai di wilayah ini.',
    )

    def _compute_kinerja(self):
        hasil = self.env['satu_data.pengajuan'].sudo()._read_group(
            [('instansi_id', 'in', self.ids), ('ketepatan', '!=', False)],
            ['instansi_id', 'ketepatan'], ['__count'])
        hitung = {}
        for instansi, ketepatan, jumlah in hasil:
            hitung.setdefault(instansi.id, {})[ketepatan] = jumlah
        for rec in self:
            h = hitung.get(rec.id, {})
            total = sum(h.values())
            rec.jumlah_pengajuan = total
            rec.jumlah_tepat = h.get('tepat', 0)
            rec.persen_tepat = 100.0 * rec.jumlah_tepat / total if total else 0.0

    @api.depends('name', 'singkatan')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (f'{rec.singkatan} - {rec.name}' if rec.singkatan
                                else rec.name or '')

    def _compute_jumlah_data(self):
        hitung = dict(self.env['satu_data.data']._read_group(
            [('instansi_id', 'in', self.ids)], ['instansi_id'], ['__count']))
        for rec in self:
            rec.jumlah_data = hitung.get(rec, 0)

    @api.constrains('peran', 'company_id', 'active')
    def _check_satu_walidata(self):
        label = dict(PERAN)
        for rec in self.filtered(lambda r: r.peran in PERAN_TUNGGAL and r.active):
            if self.search_count([('id', '!=', rec.id), ('peran', '=', rec.peran),
                                  ('company_id', '=', rec.company_id.id)], limit=1):
                raise ValidationError(self.env._(
                    'Satu wilayah hanya boleh memiliki satu %(peran)s.', peran=label[rec.peran]))

    @api.model
    def _sd_walidata(self, company=None):
        company = company or self.env.company
        return self.search([('peran', '=', 'walidata'), ('company_id', '=', company.id)], limit=1)


class ResUsers(models.Model):
    _inherit = 'res.users'

    sd_instansi_id = fields.Many2one(
        'satu_data.instansi', string='Instansi Satu Data', index=True,
        help='Instansi tempat pengguna bertugas (Produsen Data, Walidata, atau Pembina Data).',
    )


class SatuDataTopik(models.Model):
    """Topik/kategori data, mengikuti topik di portal data.go.id."""
    _name        = 'satu_data.topik'
    _description = 'Topik Data'
    _order       = 'sequence, name'

    name     = fields.Char('Nama Topik', required=True, translate=False)
    sequence = fields.Integer(default=10)
    ikon     = fields.Char('Ikon', help='Kelas Font Awesome, mis. fa-heartbeat.')
    active   = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE(name)', 'Nama topik sudah dipakai.')
