from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Layanan SPM bidang kesehatan (Permenkes 6/2024): jumlah orang yang mendapat
# pelayanan sesuai standar pada bulan itu. Pasangan sasarannya ada di model sasaran.
# (kode, label singkat, field sasaran)
LAYANAN_SPM = [
    ('ibu_hamil',       'Ibu Hamil',           'sasaran_ibu_hamil'),
    ('ibu_bersalin',    'Ibu Bersalin',        'sasaran_ibu_bersalin'),
    ('bayi_baru_lahir', 'Bayi Baru Lahir',     'sasaran_bayi_baru_lahir'),
    ('balita',          'Balita',              'sasaran_balita'),
    ('usia_dasar',      'Usia Pendidikan Dasar', 'sasaran_usia_dasar'),
    ('usia_produktif',  'Usia Produktif',      'sasaran_usia_produktif'),
    ('usia_lanjut',     'Usia Lanjut',         'sasaran_usia_lanjut'),
    ('hipertensi',      'Penderita Hipertensi', 'sasaran_hipertensi'),
    ('diabetes',        'Penderita DM',        'sasaran_diabetes'),
    ('odgj_berat',      'ODGJ Berat',          'sasaran_odgj_berat'),
    ('terduga_tbc',     'Terduga TBC',         'sasaran_terduga_tbc'),
    ('risiko_hiv',      'Berisiko HIV',        'sasaran_risiko_hiv'),
]
# Kejadian bulanan lain (dasar indikator imunisasi, stunting, kematian, DBD).
KEJADIAN = [
    'bayi_idl', 'balita_diukur', 'balita_stunting', 'lahir_hidup',
    'kematian_ibu', 'kematian_bayi', 'kasus_dbd', 'kematian_dbd',
]
FIELD_ANGKA = [f'layanan_{k}' for k, _l, _s in LAYANAN_SPM] + KEJADIAN


class SatuDataKesehatanRekap(models.Model):
    """Rekap layanan kesehatan bulanan per desa/kelurahan (laporan bulanan puskesmas).

    Angka adalah kejadian/layanan pada bulan itu (bukan kumulatif); capaian
    kumulatif s.d. bulan tertentu dihitung dengan menjumlahkan bulan-bulan.
    Pengecualian: balita diukur/stunting adalah hasil pengukuran pada bulan itu.
    """
    _name        = 'satu_data.kesehatan.rekap'
    _description = 'Rekap Layanan Kesehatan Bulanan per Desa/Kelurahan'
    _inherit     = ['mail.thread', 'satu_data.kesehatan.wilayah.mixin', 'satu_data.rekap.mixin']
    _sd_sektor   = 'kesehatan'
    _sd_field_angka = tuple(FIELD_ANGKA)
    _order       = 'periode_id, kecamatan_id, desa_id'
    _rec_name    = 'desa_id'

    periode_id = fields.Many2one(
        'satu_data.periode', string='Bulan', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('frekuensi', '=', 'bulanan')]",
        default=lambda self: self.env['satu_data.periode']._periode_bawaan('bulanan'),
        help='Periode bulanan, diatur di Konfigurasi > Periode Data.')

    # ── Layanan SPM (jumlah yang mendapat pelayanan sesuai standar) ──────────
    layanan_ibu_hamil       = fields.Integer('Ibu Hamil Dilayani Sesuai Standar', tracking=True)
    layanan_ibu_bersalin    = fields.Integer('Persalinan Sesuai Standar', tracking=True)
    layanan_bayi_baru_lahir = fields.Integer('Bayi Baru Lahir Dilayani', tracking=True)
    layanan_balita          = fields.Integer('Balita Dilayani', tracking=True)
    layanan_usia_dasar      = fields.Integer('Anak Usia Pendidikan Dasar Diskrining', tracking=True)
    layanan_usia_produktif  = fields.Integer('Usia Produktif Diskrining', tracking=True)
    layanan_usia_lanjut     = fields.Integer('Usia Lanjut Diskrining', tracking=True)
    layanan_hipertensi      = fields.Integer('Penderita Hipertensi Dilayani', tracking=True)
    layanan_diabetes        = fields.Integer('Penderita DM Dilayani', tracking=True)
    layanan_odgj_berat      = fields.Integer('ODGJ Berat Dilayani', tracking=True)
    layanan_terduga_tbc     = fields.Integer('Terduga TBC Dilayani', tracking=True)
    layanan_risiko_hiv      = fields.Integer('Berisiko HIV Diperiksa', tracking=True)

    # ── Kejadian lain ────────────────────────────────────────────────────────
    bayi_idl        = fields.Integer('Bayi Imunisasi Dasar Lengkap', tracking=True,
                                     help='Bayi yang pada bulan ini melengkapi imunisasi dasar.')
    # Hasil pengukuran, bukan kejadian: jangan dijumlahkan antarbulan (prevalensi
    # stunting memakai bulan pengukuran terakhir, mis. bulan penimbangan Februari/Agustus).
    balita_diukur   = fields.Integer('Balita Diukur Tinggi Badan', tracking=True,
                                     help='Balita yang diukur pada bulan ini (mis. bulan '
                                          'penimbangan Februari dan Agustus).')
    balita_stunting = fields.Integer('Balita Stunting', tracking=True,
                                     help='Balita pendek/sangat pendek (TB/U < -2 SD) hasil '
                                          'pengukuran bulan ini.')
    lahir_hidup     = fields.Integer('Lahir Hidup', tracking=True)
    kematian_ibu    = fields.Integer('Kematian Ibu', tracking=True,
                                     help='Kematian ibu saat hamil, bersalin, atau nifas.')
    kematian_bayi   = fields.Integer('Kematian Bayi (0–11 bulan)', tracking=True)
    kasus_dbd       = fields.Integer('Kasus DBD', tracking=True)
    kematian_dbd    = fields.Integer('Kematian DBD', tracking=True)

    _desa_periode_uniq = models.Constraint(
        'UNIQUE(desa_id, periode_id)',
        'Rekap kesehatan desa/kelurahan ini untuk bulan tersebut sudah ada.',
    )

    @api.constrains(*FIELD_ANGKA)
    def _check_tidak_negatif(self):
        self._cek_tidak_negatif(FIELD_ANGKA,
                                self.env._('Angka rekap kesehatan tidak boleh bernilai negatif.'))

    @api.constrains('balita_stunting', 'balita_diukur', 'kematian_dbd', 'kasus_dbd')
    def _check_konsisten(self):
        for rec in self:
            if rec.balita_stunting > rec.balita_diukur:
                raise ValidationError(self.env._(
                    '%(desa)s: balita stunting tidak boleh melebihi balita yang diukur.',
                    desa=rec.desa_id.name))
            if rec.kematian_dbd > rec.kasus_dbd:
                raise ValidationError(self.env._(
                    '%(desa)s: kematian DBD tidak boleh melebihi kasus DBD.',
                    desa=rec.desa_id.name))
