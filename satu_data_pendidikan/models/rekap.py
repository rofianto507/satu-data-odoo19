from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Kelompok jenjang pada rekap semester. SLB dan PKBM belum punya baris tersendiri
# (tetap tercatat di master satuan pendidikan).
KELOMPOK_REKAP = [
    ('paud',       'PAUD/TK'),
    ('sd_mi',      'SD/MI'),
    ('smp_mts',    'SMP/MTs'),
    ('sma_smk_ma', 'SMA/SMK/MA'),
]
# Field angka yang diisi petugas. Jumlah sekolah tidak termasuk: terisi otomatis dari master
# satuan pendidikan saat baris dibuat, sehingga tidak menandai baris sebagai "terisi".
FIELD_ISIAN = [
    'siswa_l', 'siswa_p', 'siswa_usia_resmi', 'rombel',
    'guru', 'guru_s1', 'guru_sertifikasi',
    'kelas_baik', 'kelas_rusak_ringan', 'kelas_rusak_berat',
    'putus_sekolah', 'lulusan', 'melanjutkan',
]
FIELD_ANGKA = ['sekolah_negeri', 'sekolah_swasta'] + FIELD_ISIAN


class SatuDataPendidikanRekap(models.Model):
    """Rekap pendidikan per semester, per desa/kelurahan dan kelompok jenjang.

    Satu baris = satu desa x satu kelompok jenjang x satu semester. Data per lokasi
    sekolah (bukan tempat tinggal siswa), sehingga angka partisipasi paling akurat di
    tingkat kecamatan dan kabupaten/kota. Disdik menghimpun juga data madrasah dari Kemenag.
    Lulusan, putus sekolah, dan melanjutkan diisi pada akhir tahun ajaran (Semester I,
    Januari–Juni); pada semester lain boleh nol.
    """
    _name        = 'satu_data.pendidikan.rekap'
    _description = 'Rekap Pendidikan Semester per Desa/Kelurahan dan Jenjang'
    _inherit     = ['mail.thread', 'satu_data.rekap.desa.mixin']
    _sd_sektor   = 'pendidikan'
    _sd_field_angka = tuple(FIELD_ISIAN)
    _sd_baris_per_desa = len(KELOMPOK_REKAP)
    _sd_satuan_baris = 'baris desa dan jenjang'
    _order       = 'periode_id, kecamatan_id, desa_id, kelompok'
    _rec_name    = 'desa_id'

    periode_id = fields.Many2one(
        'satu_data.periode', string='Semester', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('frekuensi', '=', 'semesteran')]",
        default=lambda self: self.env['satu_data.periode']._periode_bawaan('semesteran'),
        help='Periode semesteran, diatur di Konfigurasi > Periode Data.')
    kelompok   = fields.Selection(KELOMPOK_REKAP, string='Jenjang', required=True, index=True,
                                  tracking=True)

    sekolah_negeri = fields.Integer('Sekolah Negeri', tracking=True,
                                    help='Terisi dari master satuan pendidikan saat baris dibuat; '
                                         'sesuaikan bila berbeda.')
    sekolah_swasta = fields.Integer('Sekolah Swasta', tracking=True)
    sekolah_total  = fields.Integer('Jumlah Sekolah', compute='_compute_total', store=True)

    siswa_l    = fields.Integer('Siswa Laki-laki', tracking=True)
    siswa_p    = fields.Integer('Siswa Perempuan', tracking=True)
    siswa      = fields.Integer('Jumlah Siswa', compute='_compute_total', store=True)
    siswa_usia_resmi = fields.Integer(
        'Siswa Usia Resmi', tracking=True,
        help='Siswa yang berusia sesuai jenjangnya (SD/MI 7–12, SMP/MTs 13–15, SMA/SMK/MA 16–18, '
             'PAUD/TK 5–6 tahun). Dasar angka partisipasi murni (APM).')
    rombel     = fields.Integer('Rombongan Belajar', tracking=True)

    guru       = fields.Integer('Jumlah Guru', tracking=True)
    guru_s1    = fields.Integer('Guru Berkualifikasi S1/D4', tracking=True)
    guru_sertifikasi = fields.Integer('Guru Bersertifikat Pendidik', tracking=True)

    kelas_baik         = fields.Integer('Ruang Kelas Baik', tracking=True)
    kelas_rusak_ringan = fields.Integer('Ruang Kelas Rusak Ringan', tracking=True)
    kelas_rusak_berat  = fields.Integer('Ruang Kelas Rusak Berat', tracking=True)
    kelas_total        = fields.Integer('Jumlah Ruang Kelas', compute='_compute_total', store=True)

    putus_sekolah = fields.Integer('Siswa Putus Sekolah', tracking=True,
                                   help='Siswa putus sekolah selama tahun ajaran (isi di Semester I).')
    lulusan       = fields.Integer('Lulusan', tracking=True,
                                   help='Siswa lulus pada akhir tahun ajaran (isi di Semester I).')
    melanjutkan   = fields.Integer('Lulusan Melanjutkan', tracking=True,
                                   help='Lulusan yang melanjutkan ke jenjang berikutnya.')

    _desa_kelompok_periode_uniq = models.Constraint(
        'UNIQUE(desa_id, kelompok, periode_id)',
        'Rekap pendidikan desa/kelurahan, jenjang, dan semester ini sudah ada.',
    )

    @api.depends('sekolah_negeri', 'sekolah_swasta', 'siswa_l', 'siswa_p',
                 'kelas_baik', 'kelas_rusak_ringan', 'kelas_rusak_berat')
    def _compute_total(self):
        for rec in self:
            rec.sekolah_total = rec.sekolah_negeri + rec.sekolah_swasta
            rec.siswa = rec.siswa_l + rec.siswa_p
            rec.kelas_total = rec.kelas_baik + rec.kelas_rusak_ringan + rec.kelas_rusak_berat

    @api.depends('desa_id.name', 'periode_id.name', 'kelompok')
    def _compute_display_name(self):
        label = dict(KELOMPOK_REKAP)
        for rec in self:
            rec.display_name = ' – '.join(filter(None, [
                rec.desa_id.name, label.get(rec.kelompok), rec.periode_id.name]))

    @api.constrains(*FIELD_ANGKA)
    def _check_tidak_negatif(self):
        self._cek_tidak_negatif(FIELD_ANGKA,
                                self.env._('Angka rekap pendidikan tidak boleh bernilai negatif.'))

    @api.constrains('siswa_l', 'siswa_p', 'siswa_usia_resmi', 'guru', 'guru_s1',
                    'guru_sertifikasi', 'lulusan', 'melanjutkan')
    def _check_konsisten(self):
        for rec in self:
            nama = rec.desa_id.name
            if rec.siswa_usia_resmi > rec.siswa:
                raise ValidationError(self.env._(
                    '%(desa)s: siswa usia resmi tidak boleh melebihi jumlah siswa.', desa=nama))
            if rec.guru_s1 > rec.guru or rec.guru_sertifikasi > rec.guru:
                raise ValidationError(self.env._(
                    '%(desa)s: guru berkualifikasi S1/D4 dan guru bersertifikat tidak boleh '
                    'melebihi jumlah guru.', desa=nama))
            if rec.melanjutkan > rec.lulusan:
                raise ValidationError(self.env._(
                    '%(desa)s: lulusan yang melanjutkan tidak boleh melebihi jumlah lulusan.',
                    desa=nama))
