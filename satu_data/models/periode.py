from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Frekuensi penyajian data (dipakai periode, Daftar Data, dan Metadata Kegiatan).
FREKUENSI = [
    ('bulanan',    'Bulanan'),
    ('triwulanan', 'Triwulanan'),
    ('semesteran', 'Semesteran'),
    ('tahunan',    'Tahunan'),
]
NAMA_BULAN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
              'Agustus', 'September', 'Oktober', 'November', 'Desember']
ROMAWI = ['I', 'II', 'III', 'IV']


def daftar_periode_baku(tahun, frekuensi):
    """[(nama, tanggal_mulai, tanggal_akhir)] periode baku satu tahun."""
    hasil = []
    if frekuensi == 'tahunan':
        return [(f'Tahun {tahun}', date(tahun, 1, 1), date(tahun, 12, 31))]
    langkah = {'bulanan': 1, 'triwulanan': 3, 'semesteran': 6}[frekuensi]
    for i in range(12 // langkah):
        mulai = date(tahun, i * langkah + 1, 1)
        akhir = mulai + relativedelta(months=langkah, days=-1)
        if frekuensi == 'bulanan':
            nama = f'{NAMA_BULAN[i]} {tahun}'
        elif frekuensi == 'triwulanan':
            nama = f'{tahun} Triwulan {ROMAWI[i]}'
        else:
            nama = f'{tahun} Semester {ROMAWI[i]}'
        hasil.append((nama, mulai, akhir))
    return hasil


class SatuDataPeriode(models.Model):
    """Master periode data, misalnya "2026 Semester I" atau "Januari 2026".

    Berlaku untuk semua wilayah (company), agar label periode di seluruh data
    seragam. Rentang tanggal tidak boleh bertumpuk dengan periode lain yang
    frekuensinya sama (periode bulanan boleh berada di dalam semester).
    """
    _name        = 'satu_data.periode'
    _description = 'Periode Data'
    _order       = 'tanggal_mulai desc, tanggal_akhir, id desc'

    name          = fields.Char('Nama Periode', required=True)
    frekuensi     = fields.Selection(FREKUENSI, string='Frekuensi', required=True,
                                     default='semesteran', index=True)
    tanggal_mulai = fields.Date('Tanggal Mulai', required=True)
    tanggal_akhir = fields.Date('Tanggal Akhir', required=True)
    tahun         = fields.Integer('Tahun', compute='_compute_tahun', store=True,
                                   aggregator=None, index=True)
    active        = fields.Boolean(default=True)
    jumlah_data   = fields.Integer('Jumlah Data', compute='_compute_jumlah_data',
                                   help='Jumlah record data semua sektor pada periode ini.')

    _name_uniq = models.Constraint(
        'UNIQUE(name)',
        'Nama periode sudah dipakai.',
    )

    @api.depends('tanggal_mulai')
    def _compute_tahun(self):
        for rec in self:
            rec.tahun = rec.tanggal_mulai.year if rec.tanggal_mulai else 0

    @api.model
    def _sd_model_berperiode(self):
        """Nama model data sektor yang punya field ``periode_id`` ke model ini.

        Modul sektor (kependudukan, pendidikan, ...) menambahkan modelnya lewat
        ``_inherit = 'satu_data.periode'`` dan ``super()``.
        """
        return []

    def _compute_jumlah_data(self):
        total = dict.fromkeys(self.ids, 0)
        for model in self._sd_model_berperiode():
            for periode, jumlah in self.env[model]._read_group(
                    [('periode_id', 'in', self.ids)], ['periode_id'], ['__count']):
                total[periode.id] += jumlah
        for rec in self:
            rec.jumlah_data = total.get(rec.id, 0)

    @api.constrains('tanggal_mulai', 'tanggal_akhir', 'frekuensi')
    def _check_tidak_bertumpuk(self):
        for rec in self:
            if rec.tanggal_akhir < rec.tanggal_mulai:
                raise ValidationError(self.env._(
                    'Tanggal akhir tidak boleh sebelum tanggal mulai.'))
            lain = self.with_context(active_test=False).search([
                ('id', '!=', rec.id),
                ('frekuensi', '=', rec.frekuensi),
                ('tanggal_mulai', '<=', rec.tanggal_akhir),
                ('tanggal_akhir', '>=', rec.tanggal_mulai),
            ], limit=1)
            if lain:
                raise ValidationError(self.env._(
                    'Rentang tanggal periode "%(nama)s" bertumpuk dengan periode "%(lain)s" '
                    '(frekuensi sama).', nama=rec.name, lain=lain.name))

    @api.ondelete(at_uninstall=False)
    def _unlink_kecuali_dipakai(self):
        for model in self._sd_model_berperiode():
            Model = self.env[model].sudo().with_context(active_test=False)
            dipakai = Model.search([('periode_id', 'in', self.ids)], limit=1)
            if dipakai:
                raise UserError(self.env._(
                    'Periode "%(nama)s" sudah dipakai di %(data)s sehingga tidak bisa '
                    'dihapus. Arsipkan saja bila tidak dipakai lagi.',
                    nama=dipakai.periode_id.name, data=Model._description))

    @api.model
    def _periode_bawaan(self, frekuensi=None):
        """Periode yang mencakup hari ini; bila tidak ada, periode terbaru."""
        hari_ini = fields.Date.context_today(self)
        dom = [('frekuensi', '=', frekuensi)] if frekuensi else []
        return (self.search(dom + [('tanggal_mulai', '<=', hari_ini),
                                   ('tanggal_akhir', '>=', hari_ini)], limit=1)
                or self.search(dom, limit=1))

    @api.model
    def sd_buat_periode_baku(self, tahun, frekuensi):
        """Buat periode baku satu tahun yang belum ada. :return: periode baru."""
        baru = self.browse()
        Semua = self.with_context(active_test=False)
        for nama, mulai, akhir in daftar_periode_baku(int(tahun), frekuensi):
            ada = Semua.search(['|', ('name', '=', nama), '&', '&',
                                ('frekuensi', '=', frekuensi),
                                ('tanggal_mulai', '<=', akhir),
                                ('tanggal_akhir', '>=', mulai)], limit=1)
            if not ada:
                baru |= self.create({'name': nama, 'frekuensi': frekuensi,
                                     'tanggal_mulai': mulai, 'tanggal_akhir': akhir})
        return baru


class SatuDataPeriodeGenerator(models.TransientModel):
    _name        = 'satu_data.periode.generator'
    _description = 'Buat Periode Baku'

    tahun     = fields.Integer('Tahun', required=True,
                               default=lambda self: fields.Date.context_today(self).year)
    frekuensi = fields.Selection(FREKUENSI, string='Frekuensi', required=True, default='bulanan')

    @api.constrains('tahun')
    def _check_tahun(self):
        for rec in self:
            if not 1990 <= rec.tahun <= 2100:
                raise ValidationError(self.env._('Tahun %(tahun)s tidak wajar.', tahun=rec.tahun))

    def action_buat(self):
        self.ensure_one()
        self.env['satu_data.periode'].sd_buat_periode_baku(self.tahun, self.frekuensi)
        # Buka ulang daftar periode (sekaligus menutup dialog) agar periode baru terlihat.
        return self.env['ir.actions.act_window']._for_xml_id('satu_data.action_periode')
