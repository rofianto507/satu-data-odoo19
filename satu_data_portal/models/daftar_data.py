"""Daftar Data untuk portal publik: pencarian katalog, tabel, unduhan, dan API.

Aturan penyebarluasan (berlaku sama untuk halaman, unduhan, dan API):
* hanya Daftar Data aktif, akses "Terbuka", tidak dihentikan, dan sudah punya data terbit;
* angka paling rendah per kecamatan (hanya kab/kota bila tingkat penyajiannya kab/kota);
* nilai dihitung modul sektor lewat ``_sd_nilai_publik`` (sama dengan dashboard).
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from odoo import api, fields, models, tools

# Data dengan frekuensi ini ditampilkan per tahun (12 bulan / 4 triwulan per tabel).
FREKUENSI_PER_TAHUN = ('bulanan', 'triwulanan')
URUTAN = ('terbaru', 'populer', 'abjad')
# Rentang hari untuk urutan "Populer".
HARI_POPULER = 90


def format_angka(nilai, desimal=0):
    """Format Indonesia: titik ribuan, koma desimal; '–' bila tidak ada nilai."""
    if nilai is None or nilai is False:
        return '–'
    teks = f'{nilai:,.{desimal}f}'
    return teks.replace(',', 'X').replace('.', ',').replace('X', '.')


def desimal_dari(nilai_list, maks=2):
    """Banyak angka desimal yang perlu agar semua nilai tampil apa adanya (maks. 2)."""
    desimal = 0
    for v in nilai_list:
        if isinstance(v, float) and not v.is_integer():
            pecahan = f'{v:.{maks}f}'.rstrip('0').split('.')[1]
            desimal = max(desimal, len(pecahan))
    return desimal


class SatuDataData(models.Model):
    _inherit = 'satu_data.data'

    # ── Katalog ──────────────────────────────────────────────────────────────

    @api.model
    def _sd_domain_publik(self, company):
        return [('company_id', '=', company.id), ('active', '=', True), ('akses', '=', 'terbuka'),
                ('status_daftar', '!=', 'dihentikan'), ('sektor', '!=', False)]

    @api.model
    def _sd_terbit_publik(self, company):
        """``{(sektor, frekuensi): {'tahun': set, 'terakhir': datetime}}`` dari laporan terbit."""
        hasil = defaultdict(lambda: {'tahun': set(), 'terakhir': False})
        for pj in self.env['satu_data.pengajuan'].sudo().search(
                [('company_id', '=', company.id), ('state', '=', 'terbit')]):
            info = hasil[(pj.sektor, pj.periode_id.frekuensi)]
            info['tahun'].add(pj.periode_id.tahun)
            if pj.tanggal_diperiksa and (not info['terakhir']
                                         or pj.tanggal_diperiksa > info['terakhir']):
                info['terakhir'] = pj.tanggal_diperiksa
        return hasil

    def _sd_info_terbit(self, terbit):
        """Tahun tersedia dan waktu terbit terakhir data ini (dari ``_sd_terbit_publik``)."""
        self.ensure_one()
        cocok = [info for (sektor, frek), info in terbit.items()
                 if sektor == self.sektor and (not self.frekuensi or frek == self.frekuensi)]
        tahun = set().union(*(i['tahun'] for i in cocok)) if cocok else set()
        terakhir = max((i['terakhir'] for i in cocok if i['terakhir']), default=False)
        return {'tahun': sorted(tahun, reverse=True), 'terakhir': terakhir}

    @api.model
    def _sd_cari_kode_publik(self, company, kode):
        """Satu data publik menurut kodenya: ``(data, info_terbit)`` atau ``(None, None)``."""
        data = self.sudo().search(self._sd_domain_publik(company) + [('kode', '=', kode)], limit=1)
        if not data:
            return None, None
        info = data._sd_info_terbit(self._sd_terbit_publik(company))
        return (data, info) if info['tahun'] else (None, None)

    @api.model
    def _sd_cari_publik(self, company, cari=None, instansi=None, urusan=None, topik=None,
                        tahun=None, urut='terbaru'):
        """Cari Daftar Data publik yang sudah punya data terbit.

        :return: ``(hasil, faset)``; ``hasil`` = ``[(data, info_terbit)]`` setelah semua filter,
            ``faset`` = jumlah data per Produsen/urusan/topik/tahun dari hasil pencarian teks
            (sebelum filter faset), agar pilihan lain tetap terlihat.
        """
        domain = self._sd_domain_publik(company)
        if cari:
            domain += ['|', '|', '|', '|', ('name', 'ilike', cari), ('definisi', 'ilike', cari),
                       ('tag', 'ilike', cari), ('kode', 'ilike', cari),
                       ('instansi_id.name', 'ilike', cari)]
        terbit = self._sd_terbit_publik(company)
        semua = []
        for data in self.sudo().search(domain):
            info = data._sd_info_terbit(terbit)
            if info['tahun']:
                semua.append((data, info))

        faset = {
            'instansi': Counter(d.instansi_id for d, _i in semua if d.instansi_id),
            'urusan': Counter(d.urusan_id for d, _i in semua if d.urusan_id),
            'topik': Counter(d.topik_id for d, _i in semua if d.topik_id),
            'tahun': Counter(t for _d, i in semua for t in i['tahun']),
        }

        def cocok(data, info):
            return ((not instansi or data.instansi_id.id == instansi)
                    and (not urusan or data.urusan_id.id == urusan)
                    and (not topik or data.topik_id.id == topik)
                    and (not tahun or tahun in info['tahun']))

        hasil = [(d, i) for d, i in semua if cocok(d, i)]
        # Sort stabil: abjad dulu, lalu kunci utama (yang sama tetap urut abjad).
        hasil.sort(key=lambda di: di[0].name.lower())
        if urut == 'populer':
            skor = self._sd_popularitas(company)
            hasil.sort(key=lambda di: skor.get(di[0].id, 0), reverse=True)
        elif urut != 'abjad':
            hasil.sort(key=lambda di: di[1]['terakhir'] or datetime.min, reverse=True)
        return hasil, faset

    @api.model
    def _sd_popularitas(self, company, hari=HARI_POPULER):
        """``{data_id: kunjungan + unduhan}`` dalam ``hari`` terakhir."""
        Statistik = self.env['satu_data.portal.statistik'].sudo()
        sejak = fields.Date.today() - timedelta(days=hari)
        return {data.id: (k or 0) + (u or 0) for data, k, u in Statistik._read_group(
            [('data_id.company_id', '=', company.id), ('tanggal', '>=', sejak)],
            ['data_id'], ['kunjungan:sum', 'unduhan:sum'])}

    # ── Nilai (dengan cache) ─────────────────────────────────────────────────

    @tools.ormcache('self.id', 'periode.id')
    def _sd_nilai_publik_cache(self, periode):
        """``_sd_nilai_publik`` yang disimpan di cache (hanya dibaca; jangan diubah).

        Dibersihkan saat laporan berubah status, wilayah berubah, atau Daftar Data diubah
        (lihat ``cache.py``). Baris rekap yang sudah terbit terkunci, jadi tidak perlu dipantau.
        """
        return self._sd_nilai_publik(periode)

    def _sd_kecamatan_publik(self, ada_ids):
        """Kecamatan yang ditampilkan: yang aktif, ditambah yang diarsipkan tetapi berdata."""
        return self.env['satu_data.kecamatan'].sudo().with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
            '|', ('active', '=', True), ('id', 'in', list(ada_ids))])

    @api.model
    def _sd_nama_wilayah(self, company):
        jenis = dict(company._fields['sd_jenis_wilayah']._description_selection(self.env)).get(
            company.sd_jenis_wilayah)
        if jenis and not company.name.lower().startswith(jenis.lower()):
            return f'{jenis} {company.name}'
        return company.name

    # ── Halaman data ─────────────────────────────────────────────────────────

    def _sd_tabel_publik(self, tahun=None, semua=False):
        """Tabel nilai: baris = kab/kota lalu kecamatan, kolom = periode terbit.

        Frekuensi bulanan/triwulanan ditampilkan per tahun (bawaan: tahun terbaru), kecuali
        ``semua`` (mis. untuk unduhan Excel).
        """
        self.ensure_one()
        company = self.company_id
        periode_semua = self._sd_periode_publik()
        daftar_tahun = sorted(set(periode_semua.mapped('tahun')), reverse=True)
        per_tahun = self.frekuensi in FREKUENSI_PER_TAHUN and not semua
        if per_tahun and daftar_tahun:
            tahun = tahun if tahun in daftar_tahun else daftar_tahun[0]
            periode = periode_semua.filtered(lambda p: p.tahun == tahun)
        else:
            tahun = False
            periode = periode_semua
        nilai = [self._sd_nilai_publik_cache(p) for p in periode]

        baris = [{'id': False, 'kode': company.sd_kode_wilayah or '',
                  'nama': self._sd_nama_wilayah(company), 'total': True,
                  'nilai': [n.get(False) for n in nilai]}]
        rinci = self.tingkat_penyajian != 'kabupaten'
        if rinci:
            ada = set().union(*nilai) - {False} if nilai else set()
            baris += [{'id': k.id, 'kode': k.kode or '', 'nama': k.name, 'total': False,
                       'nilai': [n.get(k.id) for n in nilai]}
                      for k in self._sd_kecamatan_publik(ada)]

        desimal = desimal_dari(v for b in baris for v in b['nilai'])
        for b in baris:
            b['teks'] = [format_angka(v, desimal) for v in b['nilai']]
        return {
            'periode': [{'id': p.id, 'label': p.name, 'tahun': p.tahun} for p in periode],
            'baris': baris,
            'daftar_tahun': daftar_tahun if per_tahun else [],
            'tahun': tahun,
            'rinci': rinci,
            'desimal': desimal,
            'catatan': self._sd_catatan_publik(),
        }

    def _sd_grafik_publik(self, tabel):
        """Data grafik: tren kab/kota per periode dan sebaran kecamatan pada periode terakhir
        yang berdata."""
        self.ensure_one()
        total = tabel['baris'][0]
        grafik = {
            'satuan': self.satuan or '',
            'desimal': tabel['desimal'],
            'periode': [p['label'] for p in tabel['periode']],
            'total': total['nilai'],
            'nama_total': total['nama'],
            'kecamatan': [],
            'periode_kecamatan': False,
        }
        if not tabel['rinci']:
            return grafik
        for i in range(len(tabel['periode']) - 1, -1, -1):
            isi = [{'nama': b['nama'], 'nilai': b['nilai'][i]}
                   for b in tabel['baris'][1:] if b['nilai'][i] is not None]
            if isi:
                grafik['kecamatan'] = sorted(isi, key=lambda x: x['nilai'], reverse=True)
                grafik['periode_kecamatan'] = tabel['periode'][i]['label']
                break
        return grafik

    def _sd_metadata_publik(self, info_terbit):
        """``[(kunci, label, teks)]`` metadata yang terisi, urutan mengikuti isian data.go.id.

        ``kunci`` dipakai di JSON (unduhan dan API), ``label`` di halaman dan Excel.
        """
        self.ensure_one()

        def pilihan(field):
            return dict(self._fields[field]._description_selection(self.env)).get(self[field])

        tingkat_publik = ('Kabupaten/Kota' if self.tingkat_penyajian == 'kabupaten'
                          else 'Kecamatan')
        baris = [
            ('kode', 'Kode Data', self.kode),
            ('nama', 'Nama Data', self.name),
            ('produsen_data', 'Produsen Data', self.instansi_id.name),
            ('urusan', 'Urusan', self.urusan_id.display_name),
            ('topik', 'Topik', self.topik_id.name),
            ('jenis', 'Jenis', pilihan('jenis')),
            ('konsep', 'Konsep', self.konsep),
            ('definisi', 'Definisi', self.definisi),
            ('metode', 'Metode/Cara Perhitungan', self.metode),
            ('ukuran', 'Ukuran', self.ukuran),
            ('satuan', 'Satuan', self.satuan),
            ('klasifikasi_penyajian', 'Klasifikasi Penyajian', self.klasifikasi_penyajian),
            ('tingkat_penyajian', 'Tingkat Penyajian di Portal', tingkat_publik),
            ('frekuensi', 'Frekuensi', pilihan('frekuensi')),
            ('jadwal_pemutakhiran', 'Jadwal Pemutakhiran', self.jadwal_pemutakhiran),
            ('kegiatan', 'Kegiatan Pengumpulan', self.kegiatan_id.name),
            ('kode_sds', 'Kode SDS', self.kode_sds),
            ('kode_referensi', 'Kode Referensi', ' '.join(filter(None, [
                self.kode_referensi, self.versi_kode_referensi]))),
            ('sumber_referensi', 'Sumber Referensi', self.sumber_referensi),
            ('tahun_tersedia', 'Tahun Tersedia', ', '.join(map(str, sorted(info_terbit['tahun'])))),
            ('terakhir_diperbarui', 'Terakhir Diperbarui',
             info_terbit['terakhir'].date().isoformat() if info_terbit['terakhir'] else False),
            ('data_prioritas', 'Data Prioritas', 'Ya' if self.prioritas else False),
            ('catatan', 'Catatan', self._sd_catatan_publik()),
        ]
        return [(k, label, teks) for k, label, teks in baris if teks]

    def _sd_metadata_json(self, info_terbit):
        """Metadata untuk JSON: teks yang terisi, tahun sebagai daftar angka."""
        meta = {k: teks for k, _label, teks in self._sd_metadata_publik(info_terbit)}
        meta['tahun_tersedia'] = sorted(info_terbit['tahun'])
        meta['data_prioritas'] = bool(self.prioritas)
        return meta

    # ── Format panjang (unduhan dan API) ─────────────────────────────────────

    def _sd_baris_publik(self, periode=None):
        """Satu baris per wilayah per periode (format "panjang", mudah diolah mesin).

        Wilayah tanpa data pada periode itu tidak dimuat; nilai ``None`` = tidak dapat dihitung.
        """
        self.ensure_one()
        company = self.company_id
        periode = self._sd_periode_publik() if periode is None else periode
        nilai = {p.id: self._sd_nilai_publik_cache(p) for p in periode}
        rinci = self.tingkat_penyajian != 'kabupaten'
        kecamatan = self.env['satu_data.kecamatan']
        if rinci:
            kecamatan = self._sd_kecamatan_publik(set().union(*nilai.values()) - {False}
                                                  if nilai else set())
        kab = (company.sd_kode_wilayah or '', self._sd_nama_wilayah(company), 'kabupaten_kota')
        hasil = []
        for p in periode:
            n = nilai[p.id]
            wilayah = ([(False, *kab)] if False in n else []) + [
                (k.id, k.kode or '', k.name, 'kecamatan') for k in kecamatan if k.id in n]
            for wid, kode, nama, tingkat in wilayah:
                hasil.append({
                    'kode_wilayah': kode, 'nama_wilayah': nama, 'tingkat_wilayah': tingkat,
                    'periode': p.name, 'tahun': p.tahun,
                    'tanggal_mulai': p.tanggal_mulai.isoformat(),
                    'tanggal_akhir': p.tanggal_akhir.isoformat(),
                    'nilai': n[wid], 'satuan': self.satuan or '',
                })
        return hasil
