from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Sasaran program kesehatan per desa per tahun: penyebut 12 SPM bidang kesehatan
# (Permenkes 6/2024) + bayi untuk imunisasi dasar lengkap.
# (field, label, nomor SPM atau None)
SASARAN = [
    ('ibu_hamil',       'Ibu Hamil',                                   1),
    ('ibu_bersalin',    'Ibu Bersalin',                                2),
    ('bayi_baru_lahir', 'Bayi Baru Lahir',                             3),
    ('bayi',            'Bayi (0–11 bulan)',                           None),
    ('balita',          'Balita (0–59 bulan)',                         4),
    ('usia_dasar',      'Anak Usia Pendidikan Dasar (7–15 tahun)',     5),
    ('usia_produktif',  'Usia Produktif (15–59 tahun)',                6),
    ('usia_lanjut',     'Usia Lanjut (60 tahun ke atas)',              7),
    ('hipertensi',      'Penderita Hipertensi (15 tahun ke atas)',     8),
    ('diabetes',        'Penderita Diabetes Melitus (15 tahun ke atas)', 9),
    ('odgj_berat',      'ODGJ Berat',                                  10),
    ('terduga_tbc',     'Terduga Tuberkulosis',                        11),
    ('risiko_hiv',      'Orang Berisiko Terinfeksi HIV',               12),
]


class SatuDataKesehatanSasaran(models.Model):
    """Sasaran program kesehatan tahunan per desa/kelurahan.

    Angka proyeksi/penetapan Dinas Kesehatan, menjadi penyebut capaian SPM dan
    indikator kesehatan. Kecamatan dan puskesmas dicatat saat data dibuat (snapshot).
    """
    _name        = 'satu_data.kesehatan.sasaran'
    _description = 'Sasaran Program Kesehatan per Desa/Kelurahan'
    # Desa, kecamatan & puskesmas (snapshot), company, sumber: satu_data.kesehatan.wilayah.mixin
    _inherit     = ['mail.thread', 'satu_data.rekap.mixin', 'satu_data.kesehatan.wilayah.mixin']
    _sd_sektor   = 'kesehatan_sasaran'
    _order       = 'periode_id, kecamatan_id, desa_id'
    _rec_name    = 'desa_id'

    periode_id   = fields.Many2one(
        'satu_data.periode', string='Tahun', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('frekuensi', '=', 'tahunan')]",
        default=lambda self: self.env['satu_data.periode']._periode_bawaan('tahunan'),
        help='Periode tahunan, diatur di Konfigurasi > Periode Data.')

    sasaran_ibu_hamil       = fields.Integer('Ibu Hamil', tracking=True)
    sasaran_ibu_bersalin    = fields.Integer('Ibu Bersalin', tracking=True)
    sasaran_bayi_baru_lahir = fields.Integer('Bayi Baru Lahir', tracking=True)
    sasaran_bayi            = fields.Integer('Bayi (0–11 bulan)', tracking=True)
    sasaran_balita          = fields.Integer('Balita (0–59 bulan)', tracking=True)
    sasaran_usia_dasar      = fields.Integer('Usia Pendidikan Dasar (7–15 th)', tracking=True)
    sasaran_usia_produktif  = fields.Integer('Usia Produktif (15–59 th)', tracking=True)
    sasaran_usia_lanjut     = fields.Integer('Usia Lanjut (60+ th)', tracking=True)
    sasaran_hipertensi      = fields.Integer('Penderita Hipertensi', tracking=True)
    sasaran_diabetes        = fields.Integer('Penderita Diabetes Melitus', tracking=True)
    sasaran_odgj_berat      = fields.Integer('ODGJ Berat', tracking=True)
    sasaran_terduga_tbc     = fields.Integer('Terduga Tuberkulosis', tracking=True)
    sasaran_risiko_hiv      = fields.Integer('Berisiko Terinfeksi HIV', tracking=True)

    _desa_periode_uniq = models.Constraint(
        'UNIQUE(desa_id, periode_id)',
        'Sasaran kesehatan desa/kelurahan ini untuk tahun tersebut sudah ada.',
    )

    @api.constrains(*[f'sasaran_{f}' for f, _l, _s in SASARAN])
    def _check_tidak_negatif(self):
        self._cek_tidak_negatif([f'sasaran_{f}' for f, _l, _s in SASARAN],
                                self.env._('Angka sasaran tidak boleh bernilai negatif.'))

    @api.constrains('sasaran_bayi', 'sasaran_balita', 'sasaran_ibu_bersalin', 'sasaran_ibu_hamil')
    def _check_konsisten(self):
        for rec in self:
            if rec.sasaran_bayi > rec.sasaran_balita and rec.sasaran_balita:
                raise ValidationError(self.env._(
                    '%(desa)s: sasaran bayi tidak boleh melebihi sasaran balita.',
                    desa=rec.desa_id.name))
            if rec.sasaran_ibu_bersalin > rec.sasaran_ibu_hamil and rec.sasaran_ibu_hamil:
                raise ValidationError(self.env._(
                    '%(desa)s: sasaran ibu bersalin tidak boleh melebihi sasaran ibu hamil.',
                    desa=rec.desa_id.name))
