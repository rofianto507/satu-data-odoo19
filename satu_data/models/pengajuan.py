from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .daftar_data import BATAS_HARI_BAWAAN, hitung_batas

STATUS = [
    ('draf',     'Diisi'),
    ('diajukan', 'Diperiksa'),
    ('terbit',   'Terbit'),
]
# Data pada pengajuan berstatus ini tidak boleh diubah Produsen Data.
STATUS_TERKUNCI = ('diajukan', 'terbit')
GRUP_WALIDATA = 'satu_data.group_satu_data_walidata'


class SatuDataPengajuan(models.Model):
    """Pemeriksaan data (siklus Satu Data: pengumpulan -> pemeriksaan -> penyebarluasan).

    Satu pengajuan = data satu sektor, satu periode, satu wilayah. Produsen Data
    mengajukan; Walidata memeriksa lalu menerbitkan atau mengembalikan dengan
    catatan. Dashboard dan publikasi hanya memakai data dari pengajuan "Terbit".
    """
    _name        = 'satu_data.pengajuan'
    _description = 'Pengajuan Pemeriksaan Data'
    _inherit     = ['mail.thread']
    _order       = 'periode_mulai desc, sektor'
    _rec_name    = 'name'

    name          = fields.Char('Nama', compute='_compute_name', store=True)
    sektor        = fields.Selection([], string='Sektor', required=True, index=True,
                                     tracking=True)
    periode_id    = fields.Many2one('satu_data.periode', string='Periode', required=True,
                                    index=True, ondelete='restrict', tracking=True)
    periode_mulai = fields.Date(related='periode_id.tanggal_mulai', store=True)
    company_id    = fields.Many2one('res.company', string='Wilayah (Kab/Kota)', required=True,
                                    index=True, default=lambda self: self.env.company)
    instansi_id   = fields.Many2one('satu_data.instansi', string='Produsen Data', required=True,
                                    ondelete='restrict', tracking=True,
                                    domain="[('company_id', '=', company_id)]")
    state         = fields.Selection(STATUS, string='Status', required=True, default='draf',
                                     index=True, tracking=True, copy=False)
    catatan       = fields.Text('Catatan Pemeriksaan', tracking=True,
                                help='Diisi Walidata, terutama saat data dikembalikan.')
    diajukan_oleh     = fields.Many2one('res.users', string='Diajukan Oleh', readonly=True, copy=False)
    tanggal_diajukan  = fields.Datetime('Tanggal Diajukan', readonly=True, copy=False)
    diperiksa_oleh    = fields.Many2one('res.users', string='Diperiksa Oleh', readonly=True, copy=False)
    tanggal_diperiksa = fields.Datetime('Tanggal Diperiksa', readonly=True, copy=False)
    perlu_perbaikan = fields.Boolean('Perlu Perbaikan', readonly=True, copy=False, index=True,
                                     help='Dikembalikan Walidata; lihat Catatan Pemeriksaan.')
    jumlah_record = fields.Integer('Jumlah Baris', compute='_compute_jumlah_record')
    jumlah_terisi = fields.Integer('Desa Terisi', compute='_compute_jumlah_record')
    # Target baris laporan = jumlah desa x baris per desa (mis. pendidikan: desa x jenjang).
    jumlah_desa   = fields.Integer('Target Baris', compute='_compute_jumlah_record')
    jumlah_kosong = fields.Integer('Belum Terisi', compute='_compute_jumlah_record')
    satuan_baris  = fields.Char('Satuan Baris', compute='_compute_jumlah_record')
    boleh_periksa = fields.Boolean(compute='_compute_boleh_periksa')

    # Ketepatan jadwal pemutakhiran (penilaian kinerja Produsen Data)
    batas_pengajuan = fields.Date(
        'Batas Pengajuan', compute='_compute_batas_pengajuan', store=True,
        help='Akhir periode ditambah batas hari pada Daftar Data sektor ini '
             '(jadwal pemutakhiran yang disepakati Forum Satu Data).')
    tanggal_diajukan_pertama = fields.Datetime('Pertama Diajukan', readonly=True, copy=False)
    ketepatan     = fields.Selection([
        ('tepat',     'Tepat Waktu'),
        ('terlambat', 'Terlambat'),
    ], string='Ketepatan', compute='_compute_ketepatan', store=True, index=True)
    hari_terlambat = fields.Integer('Hari Terlambat', compute='_compute_ketepatan', store=True)

    _sektor_periode_uniq = models.Constraint(
        'UNIQUE(sektor, periode_id, company_id)',
        'Pengajuan untuk sektor, periode, dan wilayah ini sudah ada.',
    )

    # ── Kait modul sektor ─────────────────────────────────────────────────────

    @api.model
    def _sd_info_sektor(self):
        """{kode sektor: {'model': nama model rekap, 'grup': xmlid grup Produsen Data}}.

        Modul sektor menambahkan sektornya lewat ``_inherit`` dan ``super()``.
        """
        return {}

    def _sd_model(self):
        self.ensure_one()
        info = self._sd_info_sektor().get(self.sektor)
        return self.env[info['model']] if info else None

    # ── Compute ──────────────────────────────────────────────────────────────

    @api.depends('sektor', 'periode_id.name')
    def _compute_name(self):
        label = dict(self._fields['sektor']._description_selection(self.env))
        for rec in self:
            rec.name = ' – '.join(filter(None, [label.get(rec.sektor), rec.periode_id.name]))

    @api.depends('sektor', 'company_id', 'periode_id.tanggal_mulai', 'periode_id.tanggal_akhir')
    def _compute_batas_pengajuan(self):
        """Batas paling awal di antara jadwal Daftar Data sektor ini; bila belum ada
        Daftar Data, pakai jadwal bawaan sektor (``batas_hari``/``acuan_batas``)."""
        Data = self.env['satu_data.data'].sudo()
        info = self._sd_info_sektor()
        jadwal = {}
        for rec in self:
            if rec.tanggal_diajukan_pertama and rec.batas_pengajuan:
                # Batas yang sudah dipakai menilai ketepatan tidak berubah.
                rec.batas_pengajuan = rec.batas_pengajuan
                continue
            if not (rec.periode_id and rec.sektor):
                rec.batas_pengajuan = False
                continue
            kunci = (rec.sektor, rec.company_id.id)
            if kunci not in jadwal:
                data = Data.search([('sektor', '=', rec.sektor), ('batas_hari', '>', 0),
                                    ('company_id', '=', rec.company_id.id)])
                bawaan = info.get(rec.sektor) or {}
                jadwal[kunci] = {(d.batas_hari, d.acuan_batas) for d in data} or {
                    (bawaan.get('batas_hari', BATAS_HARI_BAWAAN),
                     bawaan.get('acuan_batas', 'akhir'))}
            rec.batas_pengajuan = min(
                hitung_batas(rec.periode_id, hari, acuan) for hari, acuan in jadwal[kunci])

    @api.depends('tanggal_diajukan_pertama', 'batas_pengajuan')
    def _compute_ketepatan(self):
        for rec in self:
            if not (rec.tanggal_diajukan_pertama and rec.batas_pengajuan):
                rec.ketepatan = False
                rec.hari_terlambat = 0
                continue
            tanggal = fields.Datetime.context_timestamp(rec, rec.tanggal_diajukan_pertama).date()
            selisih = (tanggal - rec.batas_pengajuan).days
            rec.hari_terlambat = max(selisih, 0)
            rec.ketepatan = 'tepat' if selisih <= 0 else 'terlambat'

    def _compute_boleh_periksa(self):
        walidata = self.env.user.has_group(GRUP_WALIDATA)
        for rec in self:
            rec.boleh_periksa = walidata

    def _compute_jumlah_record(self):
        Desa = self.env['satu_data.desa']
        for rec in self:
            Model = rec._sd_model()
            dom = [('periode_id', '=', rec.periode_id.id), ('company_id', '=', rec.company_id.id)]
            rec.jumlah_record = Model.search_count(dom) if Model is not None else 0
            rec.jumlah_terisi = (Model.search_count(dom + Model._sd_domain_terisi())
                                 if Model is not None else 0)
            per_desa = getattr(Model, '_sd_baris_per_desa', 1) if Model is not None else 1
            rec.jumlah_desa = Desa.search_count([('company_id', '=', rec.company_id.id)]) * per_desa
            rec.jumlah_kosong = max(rec.jumlah_desa - rec.jumlah_terisi, 0)
            rec.satuan_baris = (getattr(Model, '_sd_satuan_baris', 'desa/kelurahan')
                                if Model is not None else 'desa/kelurahan')

    # ── Alur ─────────────────────────────────────────────────────────────────

    def _cek_produsen(self):
        for rec in self:
            info = self._sd_info_sektor().get(rec.sektor) or {}
            grup = info.get('grup')
            if grup and not self.env.user.has_group(grup):
                raise AccessError(self.env._(
                    'Hanya Produsen Data sektor ini yang bisa mengajukan data.'))

    def _cek_walidata(self):
        if not self.env.user.has_group(GRUP_WALIDATA):
            raise AccessError(self.env._('Hanya Walidata yang bisa memeriksa data.'))

    def action_ajukan(self):
        self._cek_produsen()
        for rec in self:
            if rec.state != 'draf':
                raise UserError(self.env._('Hanya laporan berstatus Diisi yang bisa dikirim.'))
            if not rec.jumlah_terisi:
                raise UserError(self.env._(
                    'Belum ada data %(nama)s untuk dikirim.', nama=rec.name))
        sekarang = fields.Datetime.now()
        self.filtered(lambda r: not r.tanggal_diajukan_pertama).sudo().write(
            {'tanggal_diajukan_pertama': sekarang})
        self.sudo().write({'state': 'diajukan', 'perlu_perbaikan': False,
                           'diajukan_oleh': self.env.uid, 'tanggal_diajukan': sekarang})

    def action_tarik(self):
        """Produsen menarik kembali pengajuan yang belum diperiksa."""
        self._cek_produsen()
        if any(rec.state != 'diajukan' for rec in self):
            raise UserError(self.env._('Hanya laporan yang sedang diperiksa yang bisa dibatalkan.'))
        self.sudo().write({'state': 'draf'})

    def action_terbitkan(self):
        self._cek_walidata()
        if any(rec.state != 'diajukan' for rec in self):
            raise UserError(self.env._('Hanya laporan yang sedang diperiksa yang bisa diterbitkan.'))
        self.sudo().write({'state': 'terbit', 'diperiksa_oleh': self.env.uid,
                           'tanggal_diperiksa': fields.Datetime.now()})

    def action_kembalikan(self):
        """Walidata mengembalikan data untuk diperbaiki (juga untuk data yang sudah terbit)."""
        self._cek_walidata()
        for rec in self:
            if rec.state not in ('diajukan', 'terbit'):
                raise UserError(self.env._(
                    'Hanya laporan yang sedang diperiksa atau sudah terbit yang bisa dikembalikan.'))
            if not (rec.catatan or '').strip():
                raise UserError(self.env._(
                    'Isi Catatan Pemeriksaan dulu: jelaskan apa yang perlu diperbaiki.'))
        self.sudo().write({'state': 'draf', 'perlu_perbaikan': True, 'diperiksa_oleh': self.env.uid,
                           'tanggal_diperiksa': fields.Datetime.now()})

    def _sd_siapkan_baris(self):
        """Kait modul sektor: buat baris kosong untuk desa yang belum ada di laporan."""
        return True

    def action_lengkapi_baris(self):
        self._cek_produsen()
        self._sd_siapkan_baris()
        return True

    def action_lihat_data(self):
        self.ensure_one()
        Model = self._sd_model()
        if Model is None:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': Model._name,
            'view_mode': 'list,form',
            'domain': [('periode_id', '=', self.periode_id.id),
                       ('company_id', '=', self.company_id.id)],
            'context': {'default_periode_id': self.periode_id.id},
        }

    _FIELD_ALUR = {'state', 'perlu_perbaikan', 'diajukan_oleh', 'tanggal_diajukan', 'tanggal_diajukan_pertama',
                   'diperiksa_oleh', 'tanggal_diperiksa'}

    def write(self, vals):
        # Status hanya berubah lewat tombol alur (yang memeriksa peran dan memakai sudo).
        if not self.env.su and self._FIELD_ALUR & set(vals):
            raise AccessError(self.env._(
                'Status pengajuan hanya bisa diubah lewat tombol Ajukan/Terbitkan/Kembalikan.'))
        if not self.env.su and 'catatan' in vals and not self.env.user.has_group(GRUP_WALIDATA):
            raise AccessError(self.env._('Catatan pemeriksaan hanya diisi Walidata.'))
        if not self.env.su and {'sektor', 'periode_id', 'company_id'} & set(vals) and \
                any(rec.state in STATUS_TERKUNCI for rec in self):
            raise UserError(self.env._('Pengajuan yang sudah diajukan atau terbit tidak bisa diubah.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_kecuali_terbit(self):
        if any(rec.state in STATUS_TERKUNCI for rec in self):
            raise UserError(self.env._('Pengajuan yang sudah diajukan atau terbit tidak bisa dihapus.'))

    # ── Dipakai modul sektor ─────────────────────────────────────────────────

    @api.model
    def _sd_periode_terbit(self, sektor, company):
        """Periode yang datanya sudah terbit untuk sektor dan wilayah ini."""
        return self.sudo().search([('sektor', '=', sektor), ('company_id', '=', company.id),
                                   ('state', '=', 'terbit')]).periode_id

    @api.model
    def sd_siapkan(self, sektor, periode, company=None, instansi=None):
        """Pengajuan (draf) untuk sektor/periode/wilayah; dibuat bila belum ada."""
        company = company or self.env.company
        ada = self.search([('sektor', '=', sektor), ('periode_id', '=', periode.id),
                           ('company_id', '=', company.id)], limit=1)
        if ada:
            return ada
        return self.create({'sektor': sektor, 'periode_id': periode.id,
                            'company_id': company.id, 'instansi_id': instansi.id})


class SatuDataRekapMixin(models.AbstractModel):
    """Mixin model rekap sektor: kunci data yang sedang diperiksa atau sudah terbit.

    Model pewaris wajib punya ``periode_id`` dan ``company_id`` serta mengisi
    ``_sd_sektor`` (kode sektor yang sama dengan ``satu_data.pengajuan.sektor``).
    Konteks ``sd_lewati_kunci`` hanya untuk migrasi/data awal.
    """
    _name        = 'satu_data.rekap.mixin'
    _description = 'Mixin Rekap Satu Data'

    _sd_sektor = None

    sd_status = fields.Selection(
        STATUS, string='Status Laporan',
        compute='_compute_sd_status',
        help='Status laporan periode ini. Data hanya tampil di dashboard bila Terbit.')

    def _compute_sd_status(self):
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        status = {
            (p.periode_id.id, p.company_id.id): p.state
            for p in Pengajuan.search([('sektor', '=', self._sd_sektor),
                                       ('periode_id', 'in', self.periode_id.ids)])
        }
        for rec in self:
            rec.sd_status = status.get((rec.periode_id.id, rec.company_id.id), 'draf')

    def _sd_pasangan(self):
        return {(rec.periode_id.id, rec.company_id.id) for rec in self if rec.periode_id}

    def _sd_cek_kunci(self, pasangan):
        if not pasangan or self.env.context.get('sd_lewati_kunci'):
            return
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        for periode_id, company_id in pasangan:
            kunci = Pengajuan.search([
                ('sektor', '=', self._sd_sektor), ('periode_id', '=', periode_id),
                ('company_id', '=', company_id), ('state', 'in', STATUS_TERKUNCI)], limit=1)
            if kunci:
                raise UserError(self.env._(
                    'Data %(nama)s sedang diperiksa atau sudah terbit sehingga tidak bisa '
                    'diubah. Minta Walidata mengembalikannya bila perlu diperbaiki.',
                    nama=kunci.name))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sd_cek_kunci(records._sd_pasangan())
        records._sd_segarkan_hitungan()
        return records

    def write(self, vals):
        self._sd_cek_kunci(self._sd_pasangan())
        res = super().write(vals)
        if 'periode_id' in vals or 'company_id' in vals or 'desa_id' in vals:
            self._sd_cek_kunci(self._sd_pasangan())
        self._sd_segarkan_hitungan()
        return res

    def unlink(self):
        self._sd_cek_kunci(self._sd_pasangan())
        res = super().unlink()
        self._sd_segarkan_hitungan()
        return res

    def _sd_segarkan_hitungan(self):
        """Hitungan desa terisi/kosong di laporan tidak boleh memakai nilai lama."""
        self.env['satu_data.pengajuan'].invalidate_model(
            ['jumlah_record', 'jumlah_terisi', 'jumlah_desa', 'jumlah_kosong'], flush=False)

    @api.model
    def _sd_domain_terisi(self):
        """Domain baris yang dianggap sudah terisi (baris kosong tidak dihitung)."""
        return []

    @api.model
    def _sd_domain_terbit(self, company=None):
        """Domain data yang sudah terbit (untuk dashboard dan publikasi)."""
        periode = self.env['satu_data.pengajuan']._sd_periode_terbit(
            self._sd_sektor, company or self.env.company)
        return [('periode_id', 'in', periode.ids)]


class SatuDataPengajuanWizard(models.TransientModel):
    """Pilih periode lalu buka (atau buat) pengajuan pemeriksaannya."""
    _name        = 'satu_data.pengajuan.wizard'
    _description = 'Ajukan Periode ke Walidata'

    sektor      = fields.Char(required=True)
    frekuensi   = fields.Char()
    periode_id  = fields.Many2one('satu_data.periode', string='Periode', required=True,
                                  domain="[('frekuensi', '=', frekuensi)]")
    instansi_id = fields.Many2one('satu_data.instansi', string='Produsen Data', required=True,
                                  domain="[('company_id', '=', company_id)]")
    company_id  = fields.Many2one('res.company', required=True,
                                  default=lambda self: self.env.company)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sektor = res.get('sektor') or self.env.context.get('default_sektor')
        info = self.env['satu_data.pengajuan']._sd_info_sektor().get(sektor) or {}
        company = self.env.company
        if 'instansi_id' in fields_list and not res.get('instansi_id'):
            instansi = self.env.user.sd_instansi_id
            if (not instansi or instansi.peran != 'produsen') and info.get('instansi'):
                instansi = self.env.ref(info['instansi'], raise_if_not_found=False)
            if instansi and instansi.company_id == company:
                res['instansi_id'] = instansi.id
        if 'frekuensi' in fields_list and info.get('frekuensi'):
            res['frekuensi'] = info['frekuensi']
        if 'periode_id' in fields_list and not res.get('periode_id') and info.get('frekuensi'):
            periode = self.env['satu_data.periode']._periode_bawaan(info['frekuensi'])
            if periode:
                res['periode_id'] = periode.id
        return res

    def action_buka(self):
        self.ensure_one()
        pengajuan = self.env['satu_data.pengajuan'].sd_siapkan(
            self.sektor, self.periode_id, self.company_id, self.instansi_id)
        if pengajuan.state == 'draf':
            pengajuan._sd_siapkan_baris()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'satu_data.pengajuan',
            'res_id': pengajuan.id,
            'view_mode': 'form',
            'target': 'current',
        }
