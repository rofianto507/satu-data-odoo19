from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Aggregate yang dijumlahkan dari desa (urutan = urutan kolom hasil _read_group).
AGREGAT = [
    ('laki_laki', 'jumlah_laki_laki:sum'),
    ('perempuan', 'jumlah_perempuan:sum'),
    ('penduduk',  'jumlah_penduduk:sum'),
    ('kk',        'jumlah_kk:sum'),
    ('luas',      'luas_km2:sum'),
    ('jumlah_data', '__count'),
]


class SatuDataKependudukan(models.Model):
    _name        = 'satu_data.kependudukan'
    _description = 'Rekap Kependudukan per Desa/Kelurahan'
    # Dari modul inti: satu_data.peta.mixin (kelas warna, peta dasar, info wilayah induk)
    # dan satu_data.rekap.mixin (kunci data yang diperiksa/terbit, status pemeriksaan).
    _inherit     = ['mail.thread', 'satu_data.peta.mixin', 'satu_data.rekap.mixin']
    _sd_sektor   = 'kependudukan'
    # periode_id mengikuti urutan model periode: terbaru lebih dulu.
    _order       = 'periode_id, kecamatan_id, desa_id'
    _rec_name    = 'desa_id'

    # Tanpa check_company: company_id justru diturunkan dari desa_id, sehingga
    # pada record baru company_id masih kosong dan domain otomatis check_company
    # ('company_id' in [False]) membuat tidak ada desa yang bisa dipilih.
    # Konsistensi company sudah dijamin karena company_id = desa_id.company_id.
    desa_id      = fields.Many2one(
        'satu_data.desa', string='Desa/Kelurahan', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('company_id', 'in', allowed_company_ids)]",
    )
    # Kecamatan dicatat saat data dibuat (snapshot), bukan related: bila desa
    # dipindah kecamatan (pemekaran), data periode lama tetap di kecamatan lama.
    kecamatan_id = fields.Many2one(
        'satu_data.kecamatan', string='Kecamatan', compute='_compute_kecamatan_id',
        store=True, precompute=True, index=True, readonly=True,
        help='Kecamatan desa/kelurahan pada saat data ini dicatat.',
    )
    company_id   = fields.Many2one(
        related='desa_id.company_id', store=True, index=True, string='Wilayah (Kab/Kota)',
    )

    periode_id = fields.Many2one(
        'satu_data.periode', string='Periode', required=True, index=True,
        ondelete='restrict', tracking=True,
        # Data kependudukan (DKB Dukcapil) disajikan per semester.
        domain="[('frekuensi', '=', 'semesteran')]",
        default=lambda self: self.env['satu_data.periode']._periode_bawaan('semesteran'),
        help='Periode semesteran, diatur di Konfigurasi > Periode Data.',
    )

    # Laporan semester tempat baris ini berada (satu laporan per periode dan wilayah).
    pengajuan_id = fields.Many2one(
        'satu_data.pengajuan', string='Laporan', compute='_compute_pengajuan_id',
        store=True, index=True, ondelete='set null')

    jumlah_laki_laki = fields.Integer('Laki-laki', tracking=True)
    jumlah_perempuan = fields.Integer('Perempuan', tracking=True)
    jumlah_penduduk  = fields.Integer('Jumlah Penduduk', compute='_compute_jumlah_penduduk',
                                      store=True)
    jumlah_kk        = fields.Integer('Jumlah KK', tracking=True)
    luas_km2         = fields.Float(related='desa_id.luas_km2', store=True,
                                    help='Diambil dari master desa/kelurahan.')
    kepadatan        = fields.Float('Kepadatan (jiwa/km²)', digits=(12, 1),
                                    compute='_compute_kepadatan', store=True, aggregator=None)
    sumber           = fields.Char('Sumber Data',
                                   help='Asal angka, misalnya dokumen atau instansi penerbit rekap.')

    _desa_periode_uniq = models.Constraint(
        'UNIQUE(desa_id, periode_id)',
        'Data kependudukan desa/kelurahan ini untuk periode tersebut sudah ada.',
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('desa_id')
    def _compute_kecamatan_id(self):
        # Sengaja hanya bergantung pada desa_id, bukan desa_id.kecamatan_id.
        for rec in self:
            rec.kecamatan_id = rec.desa_id.kecamatan_id

    @api.depends('periode_id', 'company_id')
    def _compute_pengajuan_id(self):
        laporan = {
            (p.periode_id.id, p.company_id.id): p.id
            for p in self.env['satu_data.pengajuan'].sudo().search([
                ('sektor', '=', self._sd_sektor), ('periode_id', 'in', self.periode_id.ids)])
        }
        for rec in self:
            rec.pengajuan_id = laporan.get((rec.periode_id.id, rec.company_id.id), False)

    @api.model
    def _sd_domain_terisi(self):
        return [('jumlah_penduduk', '>', 0)]

    @api.depends('jumlah_laki_laki', 'jumlah_perempuan')
    def _compute_jumlah_penduduk(self):
        for rec in self:
            rec.jumlah_penduduk = (rec.jumlah_laki_laki or 0) + (rec.jumlah_perempuan or 0)

    @api.depends('jumlah_penduduk', 'luas_km2')
    def _compute_kepadatan(self):
        for rec in self:
            rec.kepadatan = rec.jumlah_penduduk / rec.luas_km2 if rec.luas_km2 > 0 else 0.0

    @api.depends('desa_id.name', 'periode_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ' – '.join(filter(None, [rec.desa_id.name, rec.periode_id.name]))

    # ── Constraint ────────────────────────────────────────────────────────────

    @api.constrains('jumlah_laki_laki', 'jumlah_perempuan', 'jumlah_kk')
    def _check_angka_tidak_negatif(self):
        for rec in self:
            if min(rec.jumlah_laki_laki, rec.jumlah_perempuan, rec.jumlah_kk) < 0:
                raise ValidationError(self.env._(
                    'Jumlah penduduk dan jumlah KK tidak boleh bernilai negatif.'))

    @api.constrains('jumlah_kk', 'jumlah_laki_laki', 'jumlah_perempuan')
    def _check_kk(self):
        for rec in self:
            if rec.jumlah_kk > rec.jumlah_penduduk:
                raise ValidationError(self.env._(
                    'Jumlah KK (%(kk)s) tidak boleh melebihi jumlah penduduk (%(penduduk)s).',
                    kk=rec.jumlah_kk, penduduk=rec.jumlah_penduduk,
                ))

    # ── Endpoint dashboard peta ───────────────────────────────────────────────

    @api.model
    def get_dashboard_peta(self, kecamatan_id=False, periode_id=False):
        """Data dashboard peta untuk company (wilayah) yang sedang aktif.

        Tanpa ``kecamatan_id``: level kecamatan (angka = jumlah desa per kecamatan).
        Dengan ``kecamatan_id``: level desa/kelurahan di kecamatan tersebut.
        Tanpa periode: periode terbaru yang punya data.
        Hanya data yang sudah diperiksa dan diterbitkan Walidata (prinsip Satu Data).

        Semua angka dihitung dengan ``_read_group`` sehingga hak akses dan
        record rule pengguna tetap berlaku.
        """
        company = self.env.company
        dom_company = [('company_id', '=', company.id)]
        # Baris desa yang masih kosong di laporan dianggap belum ada data.
        dom_data = dom_company + self._sd_domain_terbit(company) + self._sd_domain_terisi()
        Kecamatan = self.env['satu_data.kecamatan'].with_context(active_test=False)
        Desa = self.env['satu_data.desa'].with_context(active_test=False)

        # Hanya periode yang punya data di wilayah ini, terbaru lebih dulu.
        periode_berdata = self.env['satu_data.periode'].browse([
            p.id for (p,) in self._read_group(dom_data, ['periode_id'])
        ]).sorted()
        daftar_periode = [{'id': p.id, 'label': p.name} for p in periode_berdata]
        if periode_id:
            periode = self.env['satu_data.periode'].with_context(
                active_test=False).search([('id', '=', int(periode_id))])
            if not periode:
                raise UserError(self.env._('Periode tidak ditemukan.'))
        else:
            periode = periode_berdata[:1]

        dom_periode = dom_data + [('periode_id', '=', periode.id)]

        kabupaten = self._sd_agregat(dom_periode, False).get(None) or self._sd_angka_kosong()

        # Wilayah yang ditampilkan: yang aktif, ditambah yang sudah diarsipkan atau
        # dipindah tetapi masih punya data pada periode ini. Dengan begitu total
        # kab/kota dan kecamatan selalu sama dengan jumlah rinciannya.
        if kecamatan_id:
            kecamatan = Kecamatan.search(
                [('id', '=', int(kecamatan_id))] + dom_company, limit=1)
            if not kecamatan:
                raise UserError(self.env._('Kecamatan tidak ditemukan di wilayah ini.'))
            agregat = self._sd_agregat(
                dom_periode + [('kecamatan_id', '=', kecamatan.id)], 'desa_id')
            wilayah = Desa.search(dom_company + [
                '|', '&', ('active', '=', True), ('kecamatan_id', '=', kecamatan.id),
                ('id', 'in', list(agregat)),
            ])
            ringkasan = self._sd_agregat(
                dom_periode + [('kecamatan_id', '=', kecamatan.id)], False
            ).get(None) or self._sd_angka_kosong()
            ringkasan['jumlah_wilayah'] = len(wilayah)
            level = 'desa'
            info_kecamatan = {'id': kecamatan.id, 'kode': kecamatan.kode, 'nama': kecamatan.name}
        else:
            agregat = self._sd_agregat(dom_periode, 'kecamatan_id')
            wilayah = Kecamatan.search(dom_company + [
                '|', ('active', '=', True), ('id', 'in', list(agregat))])
            jumlah_desa = dict(self.env['satu_data.desa']._read_group(
                dom_company, ['kecamatan_id'], ['__count']))
            ringkasan = dict(kabupaten)
            ringkasan['jumlah_wilayah'] = len(wilayah)
            level = 'kecamatan'
            info_kecamatan = False

        kelas = self._hitung_kelas([a['penduduk'] for a in agregat.values()])
        hasil_wilayah = []
        for w in wilayah:
            angka = agregat.get(w.id)
            item = {
                'id':       w.id,
                'kode':     w.kode,
                'nama':     w.name,
                # Diarsipkan, atau (level desa) sudah pindah ke kecamatan lain.
                'arsip':    not w.active or (level == 'desa' and w.kecamatan_id != kecamatan),
                'geometri': w._sd_geometri(),
                'angka':    angka or False,
                # Penduduk 0 diperlakukan seperti belum ada data (warna abu-abu).
                'kelas':    (self._kelas_index(angka['penduduk'], kelas)
                             if angka and angka['penduduk'] > 0 else -1),
            }
            if level == 'desa':
                item['jenis'] = w.jenis
            else:
                item['jumlah_desa'] = jumlah_desa.get(w, 0)
            hasil_wilayah.append(item)

        return {
            'wilayah_induk': self._sd_info_wilayah_induk(company),
            'daftar_periode': daftar_periode,
            'periode': {'id': periode.id or False, 'label': periode.name or False},
            'level':      level,
            'kecamatan':  info_kecamatan,
            'kabupaten':  kabupaten,
            'ringkasan':  ringkasan,
            'wilayah':    hasil_wilayah,
            'kelas':      kelas,
            'warna_tanpa_data': self._sd_warna_tanpa_data(),
            'peta_dasar': self._sd_peta_dasar(),
        }

    # ── Helper agregasi ───────────────────────────────────────────────────────

    @api.model
    def _sd_angka_kosong(self):
        return {
            'laki_laki': 0, 'perempuan': 0, 'penduduk': 0, 'kk': 0, 'luas': 0.0,
            'jumlah_data': 0, 'luas_lengkap': False, 'kepadatan': False,
        }

    @api.model
    def _sd_agregat(self, domain, groupby):
        """Jumlahkan angka desa sesuai ``domain``.

        :param groupby: nama field Many2one (``'kecamatan_id'``/``'desa_id'``) atau
            False untuk satu total.
        :return: dict {id wilayah (None bila tanpa groupby): angka}
        """
        groupby_list = [groupby] if groupby else []
        aggregates = [spec for _key, spec in AGREGAT]
        baris = self._read_group(domain, groupby_list, aggregates)
        # Jumlah baris yang luasnya terisi, per kelompok.
        baris_luas = self._read_group(domain + [('luas_km2', '>', 0)], groupby_list, ['__count'])
        if groupby:
            dengan_luas = dict(baris_luas)
        else:
            dengan_luas = {None: baris_luas[0][0]}

        hasil = {}
        for row in baris:
            if groupby:
                rec, nilai = row[0], row[1:]
                kunci, kunci_luas = rec.id, rec
            else:
                nilai, kunci, kunci_luas = row, None, None
            angka = {key: (v or 0) for (key, _spec), v in zip(AGREGAT, nilai)}
            if not angka['jumlah_data']:
                continue
            angka['luas'] = round(angka['luas'], 2)
            # Kepadatan hanya bila semua desa yang berdata memiliki luas.
            angka['luas_lengkap'] = dengan_luas.get(kunci_luas, 0) == angka['jumlah_data']
            angka['kepadatan'] = (round(angka['penduduk'] / angka['luas'], 1)
                                  if angka['luas_lengkap'] and angka['luas'] > 0 else False)
            hasil[kunci] = angka
        return hasil

