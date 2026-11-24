from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .periode import FREKUENSI

STATUS_DAFTAR = [
    ('usulan',     'Usulan'),
    ('disepakati', 'Disepakati'),
    ('dihentikan', 'Dihentikan'),
]
# Jadwal pemutakhiran bawaan: diajukan paling lambat 30 hari setelah periode berakhir.
BATAS_HARI_BAWAAN = 30
ACUAN_BATAS = [
    ('akhir', 'setelah periode berakhir'),
    ('awal',  'setelah periode dimulai'),
]


def hitung_batas(periode, hari, acuan):
    """Tanggal batas pengajuan untuk satu periode."""
    dasar = periode.tanggal_mulai if acuan == 'awal' else periode.tanggal_akhir
    return fields.Date.add(dasar, days=hari) if dasar else False

TINGKAT_PENYAJIAN = [
    ('kabupaten', 'Kabupaten/Kota'),
    ('kecamatan', 'Kecamatan'),
    ('desa',      'Desa/Kelurahan'),
]
AKSES = [
    ('terbuka',  'Terbuka'),
    ('terbatas', 'Terbatas'),
    ('tertutup', 'Tertutup'),
]
# Isian metadata yang wajib agar sebuah data dianggap memenuhi prinsip Satu Data
# (standar data + metadata + kode referensi). Kode SDS tidak wajib: tidak semua
# data sudah punya Standar Data Statistik dari BPS.
METADATA_WAJIB = [
    ('instansi_id',           'Produsen Data'),
    ('urusan_id',             'Urusan'),
    ('topik_id',              'Topik'),
    ('definisi',              'Definisi'),
    ('metode',                'Metode/cara perhitungan'),
    ('ukuran',                'Ukuran'),
    ('satuan',                'Satuan'),
    ('klasifikasi_penyajian', 'Klasifikasi penyajian'),
    ('frekuensi',             'Frekuensi'),
    ('kode_referensi',        'Kode referensi'),
]


class SatuDataKegiatan(models.Model):
    """Metadata Kegiatan: kegiatan pengumpulan data (pola Metadata Statistik BPS)."""
    _name        = 'satu_data.kegiatan'
    _description = 'Metadata Kegiatan'
    _order       = 'name'

    name        = fields.Char('Nama Kegiatan', required=True)
    instansi_id = fields.Many2one('satu_data.instansi', string='Penyelenggara', required=True,
                                  index=True, ondelete='restrict')
    company_id  = fields.Many2one(related='instansi_id.company_id', store=True, index=True)
    jenis       = fields.Selection([
        ('kompilasi', 'Kompilasi Produk Administrasi'),
        ('survei',    'Survei'),
        ('sensus',    'Sensus'),
    ], string='Cara Pengumpulan', required=True, default='kompilasi')
    frekuensi   = fields.Selection(FREKUENSI, string='Frekuensi')
    tujuan      = fields.Text('Tujuan Kegiatan')
    keterangan  = fields.Text('Uraian Pengumpulan',
                              help='Sumber dan alur data, mis. laporan bulanan puskesmas ke Dinkes.')
    active      = fields.Boolean(default=True)


class SatuDataData(models.Model):
    """Daftar Data: satu record per data/indikator beserta metadatanya.

    Isian mengikuti metadata dataset di portal data.go.id (Nama Data, Instansi,
    Kode SDS, Definisi, Ukuran, Satuan, Klasifikasi Penyajian, Kode Referensi,
    Metode, dll.). Rumus perhitungan berada di modul sektor; record ini dibuat
    oleh modul sektor saat dipasang dan dilengkapi Walidata/Pembina Data.
    """
    _name        = 'satu_data.data'
    _description = 'Daftar Data'
    _inherit     = ['mail.thread']
    _order       = 'sektor, sequence, name'

    name        = fields.Char('Nama Data', required=True, tracking=True)
    kode        = fields.Char('Kode Data', required=True, index=True,
                              help='Kode unik di sistem, mis. kependudukan.jumlah_penduduk.')
    sequence    = fields.Integer(default=10)
    active      = fields.Boolean(default=True)
    sektor      = fields.Selection([], string='Sektor', index=True,
                                   help='Modul sektor yang menghitung data ini.')
    jenis       = fields.Selection([
        ('indikator', 'Indikator'),
        ('variabel',  'Variabel'),
    ], string='Jenis', required=True, default='indikator')
    instansi_id = fields.Many2one('satu_data.instansi', string='Produsen Data', index=True,
                                  ondelete='restrict', tracking=True)
    company_id  = fields.Many2one('res.company', string='Wilayah (Kab/Kota)', required=True,
                                  index=True, default=lambda self: self.env.company)
    kegiatan_id = fields.Many2one('satu_data.kegiatan', string='Kegiatan Pengumpulan',
                                  ondelete='restrict')
    topik_id    = fields.Many2one('satu_data.topik', string='Topik', ondelete='restrict',
                                  tracking=True)
    urusan_id   = fields.Many2one('satu_data.urusan', string='Urusan', ondelete='restrict',
                                  index=True, tracking=True,
                                  compute='_compute_urusan_id', store=True, readonly=False,
                                  help='Urusan pemerintahan daerah (UU 23/2014).')
    prioritas   = fields.Boolean('Data Prioritas', tracking=True,
                                 help='Termasuk Daftar Data Prioritas yang disepakati Forum Satu Data.')
    akses       = fields.Selection(AKSES, string='Status Akses', required=True,
                                   default='terbuka', tracking=True)

    # Perencanaan data (Forum Satu Data)
    status_daftar = fields.Selection(STATUS_DAFTAR, string='Status Daftar Data', required=True,
                                     default='usulan', tracking=True, copy=False)
    forum_id    = fields.Many2one('satu_data.forum', string='Disepakati di Forum',
                                  ondelete='set null', index=True, tracking=True, copy=False,
                                  domain="[('company_id', '=', company_id)]")
    tahun_daftar = fields.Integer('Tahun Daftar Data', related='forum_id.tahun', store=True)
    batas_hari  = fields.Integer(
        'Batas Pengajuan (hari)', default=BATAS_HARI_BAWAAN, tracking=True,
        help='Jadwal pemutakhiran: data periode ini paling lambat diajukan ke Walidata '
             'sekian hari setelah periode berakhir (atau dimulai). Dipakai menilai '
             'ketepatan waktu.')
    acuan_batas = fields.Selection(ACUAN_BATAS, string='Acuan Batas', required=True,
                                   default='akhir', tracking=True,
                                   help='Mis. sasaran tahunan ditetapkan di awal tahun: '
                                        '"setelah periode dimulai".')
    jadwal_pemutakhiran = fields.Char('Jadwal Pemutakhiran', compute='_compute_jadwal')

    # Standar data (pola Standar Data Statistik BPS)
    konsep      = fields.Text('Konsep')
    definisi    = fields.Text('Definisi', tracking=True)
    metode      = fields.Text('Metode', help='Cara perhitungan atau rumus.', tracking=True)
    ukuran      = fields.Char('Ukuran', help='Mis. Jumlah, Persentase, Rasio, Angka.')
    satuan      = fields.Char('Satuan', help='Mis. Jiwa, Persen, Per 1.000 kelahiran hidup.')
    klasifikasi_penyajian = fields.Char(
        'Klasifikasi Penyajian', help='Mis. Kecamatan, Desa/Kelurahan; Jenis kelamin.')
    tingkat_penyajian = fields.Selection(
        TINGKAT_PENYAJIAN, string='Tingkat Penyajian Terendah', required=True, default='desa',
        help='Wilayah terkecil yang boleh ditampilkan untuk publik.')
    frekuensi   = fields.Selection(FREKUENSI, string='Frekuensi')
    kode_sds    = fields.Char('Kode SDS', help='Kode Standar Data Statistik (BPS), bila ada.')
    tipe_sds    = fields.Selection([
        ('nasional', 'SDS Nasional'),
        ('sektoral', 'SDS Sektoral'),
    ], string='Tipe SDS')
    versi_sds   = fields.Char('Versi SDS')
    kode_referensi = fields.Char('Kode Referensi',
                                 help='Kode baku yang dipakai, mis. kode wilayah Kemendagri.')
    versi_kode_referensi = fields.Char('Versi Kode Referensi')
    sumber_referensi     = fields.Char('Sumber Referensi',
                                       help='Dasar hukum atau acuan definisi, mis. Permenkes.')
    tag         = fields.Char('Tag', help='Pisahkan dengan koma.')

    # Turunan
    metadata_kurang = fields.Char('Metadata Belum Lengkap', compute='_compute_metadata',
                                  store=True)
    memenuhi_sdi    = fields.Boolean('Memenuhi Prinsip SDI', compute='_compute_metadata',
                                     store=True)
    tahun_tersedia  = fields.Char('Tahun Tersedia', compute='_compute_ketersediaan')
    terakhir_terbit = fields.Datetime('Terakhir Terbit', compute='_compute_ketersediaan')

    _kode_company_uniq = models.Constraint(
        'UNIQUE(company_id, kode)',
        'Kode data sudah dipakai di wilayah ini.',
    )

    @api.depends('instansi_id')
    def _compute_urusan_id(self):
        for rec in self:
            urusan = rec.instansi_id.urusan_ids
            if not rec.urusan_id and len(urusan) == 1:
                rec.urusan_id = urusan
            else:
                rec.urusan_id = rec.urusan_id

    @api.depends('frekuensi', 'batas_hari', 'acuan_batas')
    def _compute_jadwal(self):
        label = dict(FREKUENSI)
        acuan = dict(ACUAN_BATAS)
        for rec in self:
            if not rec.batas_hari:
                rec.jadwal_pemutakhiran = False
                continue
            rec.jadwal_pemutakhiran = self.env._(
                '%(frek)s, paling lambat %(hari)s hari %(acuan)s',
                frek=label.get(rec.frekuensi, self.env._('Tiap periode')), hari=rec.batas_hari,
                acuan=acuan.get(rec.acuan_batas, ''))

    @api.constrains('batas_hari')
    def _check_batas_hari(self):
        if any(rec.batas_hari < 0 for rec in self):
            raise ValidationError(self.env._('Batas pengajuan tidak boleh negatif.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sd_hitung_ulang_batas()
        return records

    def write(self, vals):
        sektor_lama = set(self.mapped('sektor'))
        res = super().write(vals)
        if {'batas_hari', 'acuan_batas', 'sektor', 'active', 'company_id'} & set(vals):
            self._sd_hitung_ulang_batas(sektor_lama)
        return res

    def _sd_hitung_ulang_batas(self, sektor_lain=()):
        """Batas pengajuan yang belum diajukan mengikuti jadwal Daftar Data terbaru."""
        sektor = (set(self.mapped('sektor')) | set(sektor_lain)) - {False}
        if not sektor:
            return
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        belum = Pengajuan.search([('sektor', 'in', list(sektor)),
                                  ('tanggal_diajukan_pertama', '=', False)])
        if belum:
            self.env.add_to_compute(Pengajuan._fields['batas_pengajuan'], belum)

    def action_hentikan(self):
        self.write({'status_daftar': 'dihentikan'})

    def action_jadikan_usulan(self):
        self.write({'status_daftar': 'usulan'})

    @api.depends(*[f for f, _label in METADATA_WAJIB])
    def _compute_metadata(self):
        for rec in self:
            kurang = [label for field, label in METADATA_WAJIB if not rec[field]]
            rec.metadata_kurang = ', '.join(kurang) or False
            rec.memenuhi_sdi = not kurang

    def _compute_ketersediaan(self):
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        for rec in self:
            terbit = Pengajuan.search([
                ('sektor', '=', rec.sektor), ('company_id', '=', rec.company_id.id),
                ('state', '=', 'terbit')]) if rec.sektor else Pengajuan
            tahun = sorted(set(terbit.periode_id.mapped('tahun')))
            rec.tahun_tersedia = ', '.join(map(str, tahun)) or False
            rec.terakhir_terbit = max(terbit.mapped('tanggal_diperiksa'), default=False)
