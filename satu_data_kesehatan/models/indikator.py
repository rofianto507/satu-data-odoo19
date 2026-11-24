"""Indikator kesehatan dan endpoint dashboard.

Semua indikator dihitung dari dua sumber yang sudah terbit (diperiksa Walidata):
rekap bulanan per desa (pembilang) dan sasaran tahunan per desa (penyebut).
Perhitungan dilakukan di tingkat desa lalu dijumlahkan ke puskesmas, kecamatan,
dan kabupaten/kota: rasio wilayah = jumlah pembilang / jumlah penyebut (bukan
rata-rata rasio desa).
"""
import math
from collections import defaultdict

from odoo import api, models
from odoo.exceptions import UserError

from .rekap import FIELD_ANGKA, LAYANAN_SPM

GRUP_RINCI = ('satu_data.group_satu_data_walidata', 'satu_data_kesehatan.group_produsen_kesehatan')

# Palet 5 kelas. "naik": makin tinggi makin baik (merah -> hijau, RdYlGn);
# "turun": makin tinggi makin buruk (kuning -> merah, YlOrRd).
PALET = {
    'naik':  ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641'],
    'turun': ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'],
}

NAMA_SPM = {
    'ibu_hamil':       'Pelayanan Kesehatan Ibu Hamil',
    'ibu_bersalin':    'Pelayanan Kesehatan Ibu Bersalin',
    'bayi_baru_lahir': 'Pelayanan Kesehatan Bayi Baru Lahir',
    'balita':          'Pelayanan Kesehatan Balita',
    'usia_dasar':      'Pelayanan Kesehatan Usia Pendidikan Dasar',
    'usia_produktif':  'Pelayanan Kesehatan Usia Produktif',
    'usia_lanjut':     'Pelayanan Kesehatan Usia Lanjut',
    'hipertensi':      'Pelayanan Kesehatan Penderita Hipertensi',
    'diabetes':        'Pelayanan Kesehatan Penderita Diabetes Melitus',
    'odgj_berat':      'Pelayanan Kesehatan ODGJ Berat',
    'terduga_tbc':     'Pelayanan Kesehatan Orang Terduga Tuberkulosis',
    'risiko_hiv':      'Pelayanan Kesehatan Orang Berisiko Terinfeksi HIV',
}
# Penyajian terendah bawaan bila Daftar Data belum ada (data sensitif: kecamatan).
KECAMATAN_SAJA = {'spm_odgj_berat', 'spm_risiko_hiv', 'kematian_ibu', 'aki', 'kematian_bayi', 'akb'}


def _indikator():
    daftar = []
    for no, (kode, label, field_sasaran) in enumerate(LAYANAN_SPM, 1):
        daftar.append({
            'kode': f'spm_{kode}', 'nama': NAMA_SPM[kode], 'singkat': label,
            'kelompok': 'Standar Pelayanan Minimal', 'no_spm': no,
            'jenis': 'rasio', 'pembilang': f'layanan_{kode}', 'penyebut': field_sasaran,
            'faktor': 100, 'satuan': '%', 'arah': 'naik', 'batas': [25, 50, 75, 100],
            'label_pembilang': 'Dilayani sesuai standar', 'label_penyebut': 'Sasaran tahunan',
            'definisi': f'Persentase {label.lower()} yang mendapat pelayanan kesehatan sesuai '
                        f'standar dibanding sasaran tahunan (SPM {no}).',
        })
    daftar += [
        {'kode': 'idl', 'nama': 'Imunisasi Dasar Lengkap', 'singkat': 'IDL',
         'kelompok': 'Imunisasi dan Gizi', 'jenis': 'rasio', 'pembilang': 'bayi_idl',
         'penyebut': 'sasaran_bayi', 'faktor': 100, 'satuan': '%', 'arah': 'naik',
         'batas': [25, 50, 75, 95],
         'label_pembilang': 'Bayi imunisasi dasar lengkap', 'label_penyebut': 'Sasaran bayi',
         'definisi': 'Persentase bayi 0–11 bulan yang mendapat imunisasi dasar lengkap dibanding '
                     'sasaran bayi.'},
        {'kode': 'stunting', 'nama': 'Prevalensi Balita Stunting', 'singkat': 'Stunting',
         'kelompok': 'Imunisasi dan Gizi', 'jenis': 'rasio', 'pembilang': 'ukur_stunting',
         'penyebut': 'ukur_diukur', 'faktor': 100, 'satuan': '%', 'arah': 'turun',
         'batas': [10, 14, 20, 30], 'tanpa_mode': True,
         'label_pembilang': 'Balita stunting', 'label_penyebut': 'Balita diukur',
         'definisi': 'Persentase balita pendek dan sangat pendek (TB/U < -2 SD) dari balita yang '
                     'diukur, memakai bulan pengukuran terakhir tiap desa/kelurahan.'},
        {'kode': 'kematian_ibu', 'nama': 'Jumlah Kematian Ibu', 'singkat': 'Kematian ibu',
         'kelompok': 'Kematian Ibu dan Bayi', 'jenis': 'jumlah', 'pembilang': 'kematian_ibu',
         'satuan': 'Kasus', 'arah': 'turun', 'definisi': 'Jumlah kematian ibu saat hamil, '
         'bersalin, atau nifas.'},
        {'kode': 'aki', 'nama': 'Rasio Kematian Ibu', 'singkat': 'AKI',
         'kelompok': 'Kematian Ibu dan Bayi', 'jenis': 'rasio', 'pembilang': 'kematian_ibu',
         'penyebut': 'lahir_hidup', 'faktor': 100000, 'satuan': 'per 100.000 KH',
         'arah': 'turun', 'desimal': 0,
         'label_pembilang': 'Kematian ibu', 'label_penyebut': 'Lahir hidup',
         'definisi': 'Kematian ibu per 100.000 kelahiran hidup.'},
        {'kode': 'kematian_bayi', 'nama': 'Jumlah Kematian Bayi', 'singkat': 'Kematian bayi',
         'kelompok': 'Kematian Ibu dan Bayi', 'jenis': 'jumlah', 'pembilang': 'kematian_bayi',
         'satuan': 'Kasus', 'arah': 'turun', 'definisi': 'Jumlah kematian bayi usia 0–11 bulan.'},
        {'kode': 'akb', 'nama': 'Rasio Kematian Bayi', 'singkat': 'AKB',
         'kelompok': 'Kematian Ibu dan Bayi', 'jenis': 'rasio', 'pembilang': 'kematian_bayi',
         'penyebut': 'lahir_hidup', 'faktor': 1000, 'satuan': 'per 1.000 KH', 'arah': 'turun',
         'label_pembilang': 'Kematian bayi', 'label_penyebut': 'Lahir hidup',
         'definisi': 'Kematian bayi 0–11 bulan per 1.000 kelahiran hidup.'},
        {'kode': 'kasus_dbd', 'nama': 'Jumlah Kasus DBD', 'singkat': 'Kasus DBD',
         'kelompok': 'Penyakit Menular', 'jenis': 'jumlah', 'pembilang': 'kasus_dbd',
         'satuan': 'Kasus', 'arah': 'turun', 'definisi': 'Jumlah kasus Demam Berdarah Dengue.'},
        {'kode': 'ir_dbd', 'nama': 'Angka Kesakitan DBD', 'singkat': 'IR DBD',
         'kelompok': 'Penyakit Menular', 'jenis': 'rasio', 'pembilang': 'kasus_dbd',
         'penyebut': 'penduduk', 'faktor': 100000, 'satuan': 'per 100.000 penduduk',
         'arah': 'turun', 'perlu_penduduk': True,
         'label_pembilang': 'Kasus DBD', 'label_penyebut': 'Penduduk',
         'definisi': 'Kasus DBD per 100.000 penduduk (incidence rate). Penduduk dari data '
                     'kependudukan terbit terakhir.'},
        {'kode': 'cfr_dbd', 'nama': 'Angka Kematian DBD', 'singkat': 'CFR DBD',
         'kelompok': 'Penyakit Menular', 'jenis': 'rasio', 'pembilang': 'kematian_dbd',
         'penyebut': 'kasus_dbd', 'faktor': 100, 'satuan': '%', 'arah': 'turun',
         'batas': [0.5, 1, 2, 5],
         'label_pembilang': 'Kematian DBD', 'label_penyebut': 'Kasus DBD',
         'definisi': 'Persentase kematian di antara kasus DBD (case fatality rate).'},
    ]
    for ind in daftar:
        ind.setdefault('desimal', 1 if ind['jenis'] == 'rasio' else 0)
        ind.setdefault('tingkat', 'kecamatan' if ind['kode'] in KECAMATAN_SAJA else 'desa')
    return daftar


INDIKATOR = _indikator()
INDIKATOR_BY_KODE = {i['kode']: i for i in INDIKATOR}
INDIKATOR_BAWAAN = 'spm_ibu_hamil'


def nilai_indikator(ind, angka):
    """Nilai indikator dari kumpulan angka dasar; None bila tidak bisa dihitung.

    Tanpa rekap pada rentang bulan yang dihitung (``rekap``), atau tanpa pengukuran
    untuk stunting, nilai dianggap belum ada (bukan 0).
    """
    if not angka:
        return None
    if ind['pembilang'].startswith('ukur_'):
        if not angka.get('ukur_diukur'):
            return None
    elif not angka.get('rekap'):
        return None
    pembilang = angka.get(ind['pembilang'], 0)
    if ind['jenis'] == 'jumlah':
        return pembilang
    penyebut = angka.get(ind['penyebut'], 0)
    if not penyebut:
        return None
    return round(pembilang / penyebut * ind['faktor'], ind['desimal'])


class SatuDataKesehatanDashboard(models.AbstractModel):
    _name        = 'satu_data.kesehatan.dashboard'
    _description = 'Dashboard Kesehatan'
    _inherit     = ['satu_data.peta.mixin']

    # ── Endpoint ─────────────────────────────────────────────────────────────

    @api.model
    def get_dashboard_kesehatan(self, indikator=False, periode_id=False, kecamatan_id=False,
                                mode='kumulatif'):
        """Data dashboard kesehatan untuk company aktif.

        :param indikator: kode indikator (lihat ``INDIKATOR``)
        :param periode_id: bulan (periode bulanan) yang datanya terbit; bawaan = terbaru
        :param kecamatan_id: tanpa = level kecamatan; dengan = level desa/kelurahan
        :param mode: ``'kumulatif'`` (Januari s.d. bulan terpilih) atau ``'bulan'``
        """
        company = self.env.company
        ind = INDIKATOR_BY_KODE.get(indikator or INDIKATOR_BAWAAN)
        if not ind:
            raise UserError(self.env._('Indikator tidak dikenal.'))
        mode = 'bulan' if mode == 'bulan' else 'kumulatif'
        ada_penduduk = 'satu_data.kependudukan' in self.env

        bulan_terbit = self.env['satu_data.pengajuan']._sd_periode_terbit('kesehatan', company)
        bulan_terbit = bulan_terbit.filtered(lambda p: p.frekuensi == 'bulanan').sorted()
        if periode_id:
            periode = bulan_terbit.filtered(lambda p: p.id == int(periode_id))
            if not periode:
                raise UserError(self.env._('Data bulan ini belum terbit atau tidak ditemukan.'))
        else:
            periode = bulan_terbit[:1]

        info_tingkat = self._sd_tingkat_penyajian(company)
        daftar_indikator = [
            {'kode': i['kode'], 'nama': i['nama'], 'kelompok': i['kelompok'], 'satuan': i['satuan']}
            for i in INDIKATOR if ada_penduduk or not i.get('perlu_penduduk')]

        hasil = {
            'wilayah_induk': self._sd_info_wilayah_induk(company),
            'daftar_indikator': daftar_indikator,
            'indikator': self._sd_info_indikator(ind, info_tingkat),
            'daftar_periode': [{'id': p.id, 'label': p.name} for p in bulan_terbit],
            'periode': {'id': periode.id or False, 'label': periode.name or False},
            'mode': mode,
            'warna_tanpa_data': self._sd_warna_tanpa_data(),
            'peta_dasar': self._sd_peta_dasar(),
        }

        # Bulan yang dipakai menghitung angka saat ini (untuk tombol "Lihat detail data").
        if not periode:
            hasil['periode_ids'] = []
        elif mode == 'bulan':
            hasil['periode_ids'] = periode.ids
        else:
            hasil['periode_ids'] = bulan_terbit.filtered(
                lambda p: p.tanggal_mulai.year == periode.tanggal_mulai.year
                and p.tanggal_mulai <= periode.tanggal_mulai).ids

        dasar = self._sd_angka_dasar(periode, mode, company) if periode else {}
        Kecamatan = self.env['satu_data.kecamatan'].with_context(active_test=False)
        Desa = self.env['satu_data.desa'].with_context(active_test=False)
        dom_company = [('company_id', '=', company.id)]
        total = self._sd_jumlahkan(dasar.values())

        if kecamatan_id:
            kecamatan = Kecamatan.search([('id', '=', int(kecamatan_id))] + dom_company, limit=1)
            if not kecamatan:
                raise UserError(self.env._('Kecamatan tidak ditemukan di wilayah ini.'))
            per_desa = defaultdict(list)
            for (kec, desa), angka in dasar.items():
                if kec == kecamatan.id:
                    per_desa[desa].append(angka)
            per_wilayah = {d: self._sd_jumlahkan(a) for d, a in per_desa.items()}
            wilayah = Desa.search(dom_company + [
                '|', '&', ('active', '=', True), ('kecamatan_id', '=', kecamatan.id),
                ('id', 'in', list(per_wilayah))])
            ringkasan = self._sd_jumlahkan(
                a for (kec, _d), a in dasar.items() if kec == kecamatan.id)
            level = 'desa'
            hasil['kecamatan'] = {'id': kecamatan.id, 'kode': kecamatan.kode,
                                  'nama': kecamatan.name}
        else:
            per_kec = defaultdict(list)
            for (kec, _desa), angka in dasar.items():
                per_kec[kec].append(angka)
            per_wilayah = {k: self._sd_jumlahkan(a) for k, a in per_kec.items()}
            wilayah = Kecamatan.search(dom_company + [
                '|', ('active', '=', True), ('id', 'in', list(per_wilayah))])
            ringkasan = total
            level = 'kecamatan'
            hasil['kecamatan'] = False

        # Data sensitif tidak dirinci di bawah tingkat penyajian terendahnya, kecuali
        # untuk Walidata dan Produsen Data kesehatan.
        tersembunyi = level == 'desa' and not hasil['indikator']['boleh_desa']
        nilai = {wid: nilai_indikator(ind, a) for wid, a in per_wilayah.items()}
        kelas = self._sd_kelas_indikator(
            ind, [] if tersembunyi else [v for v in nilai.values() if v is not None])

        hasil_wilayah = []
        for w in wilayah:
            angka = per_wilayah.get(w.id)
            v = None if tersembunyi else nilai.get(w.id)
            item = {
                'id': w.id, 'kode': w.kode, 'nama': w.name,
                'arsip': not w.active or (level == 'desa' and w.kecamatan_id.id != kecamatan.id),
                'geometri': w._sd_geometri(),
                'nilai': v,
                'pembilang': None if tersembunyi or not angka else angka.get(ind['pembilang'], 0),
                'penyebut': (None if tersembunyi or not angka or ind['jenis'] != 'rasio'
                             else angka.get(ind['penyebut'], 0)),
                'lapor': angka.get('lapor', 0) if angka else 0,
                'kelas': self._sd_kelas_index(v, kelas) if v is not None else -1,
            }
            if level == 'desa':
                item['jenis'] = w.jenis
                item['puskesmas'] = w.sd_puskesmas_id.name or False
            hasil_wilayah.append(item)

        hasil.update({
            'level': level,
            'tersembunyi': tersembunyi,
            'wilayah': hasil_wilayah,
            'kelas': kelas,
            'ringkasan': self._sd_ringkasan(ringkasan, ind),
            'semua_indikator': self._sd_semua_indikator(ringkasan, ada_penduduk),
            'jumlah_desa': self.env['satu_data.desa'].search_count(
                dom_company + ([('kecamatan_id', '=', int(kecamatan_id))] if kecamatan_id else [])),
            'puskesmas': self._sd_titik_puskesmas(dasar, ind, company, kecamatan_id),
            'tren': self._sd_tren(ind, periode, bulan_terbit, mode, company,
                                  int(kecamatan_id) if kecamatan_id else False) if periode else [],
        })
        return hasil

    # ── Angka dasar per desa ─────────────────────────────────────────────────

    @api.model
    def _sd_angka_dasar(self, periode, mode, company):
        """{(kecamatan_id, desa_id): {field: jumlah, 'lapor': n, ...}} untuk satu bulan.

        Pembilang: rekap bulan itu (mode bulan) atau Januari s.d. bulan itu (kumulatif).
        Penyebut: sasaran tahunan terbit yang mencakup bulan itu. Stunting: hasil
        pengukuran terakhir tiap desa dalam 12 bulan terakhir s.d. bulan itu.
        """
        Rekap = self.env['satu_data.kesehatan.rekap']
        Sasaran = self.env['satu_data.kesehatan.sasaran']
        dom_company = [('company_id', '=', company.id)]
        # Hanya baris yang sudah diisi petugas; baris kosong di laporan dianggap belum ada data.
        bulan_terbit = Rekap._sd_domain_terbit(company) + Rekap._sd_domain_terisi()
        dasar = defaultdict(lambda: defaultdict(int))

        # Pembilang
        if mode == 'bulan':
            dom_bulan = [('periode_id', '=', periode.id)]
        else:
            awal_tahun = periode.tanggal_mulai.replace(month=1, day=1)
            dom_bulan = [('periode_id.tanggal_mulai', '>=', awal_tahun),
                         ('periode_id.tanggal_mulai', '<=', periode.tanggal_mulai),
                         ('periode_id.frekuensi', '=', 'bulanan')]
        for kec, desa, n, *jumlah in Rekap._read_group(
                dom_company + bulan_terbit + dom_bulan, ['kecamatan_id', 'desa_id'],
                ['__count'] + [f'{f}:sum' for f in FIELD_ANGKA]):
            angka = dasar[(kec.id, desa.id)]
            angka['rekap'] += n
            for f, v in zip(FIELD_ANGKA, jumlah):
                angka[f] += v or 0
        # "lapor" = desa yang punya rekap pada bulan terpilih
        for kec, desa, n in Rekap._read_group(
                dom_company + bulan_terbit + [('periode_id', '=', periode.id)],
                ['kecamatan_id', 'desa_id'], ['__count']):
            dasar[(kec.id, desa.id)]['lapor'] += n

        # Stunting: pengukuran terakhir tiap desa
        batas_awal = periode.tanggal_mulai.replace(year=periode.tanggal_mulai.year - 1)
        ukur = Rekap.search(dom_company + bulan_terbit + [
            ('balita_diukur', '>', 0),
            ('periode_id.tanggal_mulai', '>', batas_awal),
            ('periode_id.tanggal_mulai', '<=', periode.tanggal_mulai)])
        terakhir = {}
        for r in ukur.sorted(lambda r: r.periode_id.tanggal_mulai):
            terakhir[r.desa_id.id] = r
        for r in terakhir.values():
            angka = dasar[(r.kecamatan_id.id, r.desa_id.id)]
            angka['ukur_diukur'] += r.balita_diukur
            angka['ukur_stunting'] += r.balita_stunting

        # Penyebut: sasaran tahun berjalan
        tahun = self.env['satu_data.pengajuan']._sd_periode_terbit('kesehatan_sasaran', company)
        tahun = tahun.filtered(lambda p: p.frekuensi == 'tahunan'
                               and p.tanggal_mulai <= periode.tanggal_mulai <= p.tanggal_akhir)
        if tahun:
            field_sasaran = [f for f in Sasaran._fields if f.startswith('sasaran_')]
            for kec, desa, *jumlah in Sasaran._read_group(
                    dom_company + Sasaran._sd_domain_terisi() + [('periode_id', 'in', tahun[:1].ids)],
                    ['kecamatan_id', 'desa_id'], [f'{f}:sum' for f in field_sasaran]):
                angka = dasar[(kec.id, desa.id)]
                for f, v in zip(field_sasaran, jumlah):
                    angka[f] += v or 0

        # Penduduk (bila modul kependudukan terpasang): data terbit terakhir s.d. bulan ini
        if 'satu_data.kependudukan' in self.env:
            Pdd = self.env['satu_data.kependudukan']
            dom_pdd = dom_company + Pdd._sd_domain_terbit(company) + [
                ('periode_id.tanggal_mulai', '<=', periode.tanggal_akhir)]
            terbaru = Pdd.search(dom_pdd, order='periode_id', limit=1).periode_id
            if terbaru:
                for kec, desa, jumlah in Pdd._read_group(
                        dom_pdd + [('periode_id', '=', terbaru.id)],
                        ['kecamatan_id', 'desa_id'], ['jumlah_penduduk:sum']):
                    dasar[(kec.id, desa.id)]['penduduk'] += jumlah or 0
        return dasar

    @api.model
    def _sd_jumlahkan(self, kumpulan):
        total = defaultdict(int)
        for angka in kumpulan:
            for k, v in angka.items():
                total[k] += v
        return dict(total)

    # ── Penyajian ────────────────────────────────────────────────────────────

    @api.model
    def _sd_tingkat_penyajian(self, company):
        """{kode indikator: tingkat penyajian terendah} dari Daftar Data (bisa diubah Walidata)."""
        data = self.env['satu_data.data'].sudo().search([
            ('company_id', '=', company.id), ('kode', 'like', 'kesehatan.%')])
        return {d.kode.split('.', 1)[1]: d.tingkat_penyajian for d in data}

    @api.model
    def _sd_info_indikator(self, ind, info_tingkat):
        tingkat = info_tingkat.get(ind['kode'], ind['tingkat'])
        boleh_rinci = any(self.env.user.has_group(g) for g in GRUP_RINCI)
        info = {k: ind.get(k) for k in ('kode', 'nama', 'singkat', 'kelompok', 'satuan', 'arah',
                                        'jenis', 'desimal', 'definisi', 'label_pembilang',
                                        'label_penyebut')}
        info.update({'tingkat': tingkat, 'tanpa_mode': bool(ind.get('tanpa_mode')),
                     'boleh_desa': tingkat == 'desa' or boleh_rinci})
        return info

    @api.model
    def _sd_ringkasan(self, angka, ind):
        return {
            'nilai': nilai_indikator(ind, angka),
            'pembilang': angka.get(ind['pembilang'], 0) if angka else 0,
            'penyebut': angka.get(ind.get('penyebut'), 0) if angka and ind['jenis'] == 'rasio' else None,
            'lapor': angka.get('lapor', 0) if angka else 0,
        }

    @api.model
    def _sd_semua_indikator(self, angka, ada_penduduk):
        return {i['kode']: nilai_indikator(i, angka) for i in INDIKATOR
                if ada_penduduk or not i.get('perlu_penduduk')}

    @api.model
    def _sd_titik_puskesmas(self, dasar, ind, company, kecamatan_id):
        """Puskesmas aktif berkoordinat; nilai = indikator gabungan desa wilayah kerjanya."""
        dom = [('company_id', '=', company.id), ('jenis', '=', 'puskesmas'),
               '|', ('latitude', '!=', 0), ('longitude', '!=', 0)]
        if kecamatan_id:
            dom += ['|', ('kecamatan_id', '=', int(kecamatan_id)),
                    ('wilayah_kerja_ids.kecamatan_id', '=', int(kecamatan_id))]
        per_desa = defaultdict(list)
        for (_kec, desa), angka in dasar.items():
            per_desa[desa].append(angka)
        hasil = []
        for p in self.env['satu_data.faskes'].search(dom):
            angka = self._sd_jumlahkan(a for d in p.wilayah_kerja_ids.ids for a in per_desa.get(d, []))
            hasil.append({
                'id': p.id, 'nama': p.name, 'lat': p.latitude, 'lng': p.longitude,
                'kategori': dict(p._fields['kategori']._description_selection(self.env)).get(
                    p.kategori, ''),
                'desa': p.desa_id.name, 'jumlah_desa': len(p.wilayah_kerja_ids),
                'nilai': nilai_indikator(ind, angka) if angka else None,
            })
        return hasil

    @api.model
    def _sd_tren(self, ind, periode, bulan_terbit, mode, company, kecamatan_id):
        """Nilai indikator per bulan terbit pada tahun yang sama, s.d. bulan terpilih."""
        tahun = periode.tanggal_mulai.year
        hasil = []
        for p in bulan_terbit.sorted('tanggal_mulai'):
            if p.tanggal_mulai.year != tahun or p.tanggal_mulai > periode.tanggal_mulai:
                continue
            dasar = self._sd_angka_dasar(p, mode, company)
            angka = self._sd_jumlahkan(
                a for (kec, _d), a in dasar.items() if not kecamatan_id or kec == kecamatan_id)
            hasil.append({'id': p.id, 'label': p.name, 'nilai': nilai_indikator(ind, angka)})
        return hasil

    # ── Kelas warna desimal ──────────────────────────────────────────────────

    @api.model
    def _sd_kelas_indikator(self, ind, nilai_list):
        """5 kelas warna. Batas tetap bila indikator punya target (mis. SPM 100%),
        selain itu kuantil nilai wilayah. Kelas ke-i: batas[i-1] <= nilai < batas[i]."""
        palet = PALET[ind['arah']]
        desimal = ind['desimal']
        batas = ind.get('batas')
        if not batas:
            nilai = sorted(nilai_list)
            batas = None
            if len(set(nilai)) >= 5:
                n = len(nilai)
                batas = [self._sd_bulat(nilai[math.ceil(n * i / 5) - 1], desimal)
                         for i in range(1, 5)]
                if batas[0] <= 0 or any(b <= a for a, b in zip(batas, batas[1:])):
                    batas = None    # bertumpuk setelah dibulatkan: interval sama
            if batas is None:
                maks = nilai[-1] if nilai else 0
                langkah = self._sd_bulat(maks / 5, desimal) or (10 ** -desimal) or 1
                batas = [round(langkah * i, desimal) for i in range(1, 5)]
        fmt = lambda v: f'{v:,.{desimal}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        kelas = []
        for i, warna in enumerate(palet):
            if i == 0:
                label = f'< {fmt(batas[0])}'
            elif i == 4:
                label = f'≥ {fmt(batas[3])}'
            else:
                label = f'{fmt(batas[i - 1])} – < {fmt(batas[i])}'
            kelas.append({'warna': warna, 'label': label,
                          'bawah': batas[i - 1] if i else None, 'atas': batas[i] if i < 4 else None})
        return kelas

    @api.model
    def _sd_kelas_index(self, nilai, kelas):
        for i, k in enumerate(kelas):
            if k['atas'] is None or nilai < k['atas']:
                return i
        return len(kelas) - 1

    @api.model
    def _sd_bulat(self, x, desimal):
        """Bulatkan ke 2 angka penting, tidak lebih halus dari ``desimal``."""
        if x <= 0:
            return 0
        pangkat = math.floor(math.log10(x)) - 1
        satuan = max(10 ** pangkat, 10 ** -desimal)
        return round(round(x / satuan) * satuan, desimal)
