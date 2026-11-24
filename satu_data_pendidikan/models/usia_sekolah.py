from odoo import api, fields, models

# Kelompok usia sekolah (penyebut angka partisipasi): (field, label)
FIELD_USIA = [
    ('usia_5_6',   'Usia 5–6 tahun (PAUD/TK)'),
    ('usia_7_12',  'Usia 7–12 tahun (SD/MI)'),
    ('usia_13_15', 'Usia 13–15 tahun (SMP/MTs)'),
    ('usia_16_18', 'Usia 16–18 tahun (SMA/SMK/MA)'),
]
NAMA_FIELD_USIA = tuple(f for f, _l in FIELD_USIA)


class SatuDataPendidikanUsiaSekolah(models.Model):
    """Penduduk usia sekolah tahunan per desa/kelurahan.

    Angka proyeksi/penetapan (Disdik bersama Disdukcapil atau BPS), penyebut angka
    partisipasi (APK dan APM). Sistem belum punya data penduduk menurut umur, jadi
    angkanya dimasukkan di sini seperti sasaran pada modul kesehatan.
    """
    _name        = 'satu_data.pendidikan.usia_sekolah'
    _description = 'Penduduk Usia Sekolah per Desa/Kelurahan'
    # Desa, kecamatan (snapshot), company, sumber, laporan induk, "terisi", kunci data
    # yang sedang diperiksa/terbit: satu_data.rekap.desa.mixin (modul inti).
    _inherit     = ['mail.thread', 'satu_data.rekap.desa.mixin']
    _sd_sektor   = 'pendidikan_usia_sekolah'
    _sd_field_angka = NAMA_FIELD_USIA
    _order       = 'periode_id, kecamatan_id, desa_id'
    _rec_name    = 'desa_id'

    periode_id = fields.Many2one(
        'satu_data.periode', string='Tahun', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('frekuensi', '=', 'tahunan')]",
        default=lambda self: self.env['satu_data.periode']._periode_bawaan('tahunan'),
        help='Periode tahunan, diatur di Konfigurasi > Periode Data.')

    usia_5_6   = fields.Integer('Usia 5–6 tahun', tracking=True)
    usia_7_12  = fields.Integer('Usia 7–12 tahun', tracking=True)
    usia_13_15 = fields.Integer('Usia 13–15 tahun', tracking=True)
    usia_16_18 = fields.Integer('Usia 16–18 tahun', tracking=True)
    usia_total = fields.Integer('Total Usia 5–18 tahun', compute='_compute_usia_total', store=True)

    _desa_periode_uniq = models.Constraint(
        'UNIQUE(desa_id, periode_id)',
        'Data penduduk usia sekolah desa/kelurahan ini untuk tahun tersebut sudah ada.',
    )

    @api.depends(*NAMA_FIELD_USIA)
    def _compute_usia_total(self):
        for rec in self:
            rec.usia_total = sum(rec[f] for f in NAMA_FIELD_USIA)

    @api.constrains(*NAMA_FIELD_USIA)
    def _check_tidak_negatif(self):
        self._cek_tidak_negatif(NAMA_FIELD_USIA,
                                self.env._('Jumlah penduduk usia sekolah tidak boleh negatif.'))
