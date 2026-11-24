"""Indikator pendidikan dan endpoint dashboard.

Sumber hitung (hanya yang sudah terbit, diperiksa Walidata): rekap semester per desa dan
jenjang (pembilang) dan penduduk usia sekolah tahunan (penyebut angka partisipasi).
Perhitungan dilakukan di tingkat desa lalu dijumlahkan ke kecamatan dan kabupaten/kota:
nilai wilayah = jumlah pembilang / jumlah penyebut (bukan rata-rata rasio desa).

Rumus partisipasi mengikuti definisi baku (SD/MI usia 7–12, SMP/MTs 13–15, SMA/SMK/MA 16–18,
PAUD/TK 5–6 tahun):
    APK = siswa jenjang / penduduk usia resmi jenjang x 100
    APM = siswa usia resmi jenjang / penduduk usia resmi jenjang x 100
Data per lokasi sekolah (bukan tempat tinggal siswa), sehingga partisipasi disajikan paling
rendah di tingkat kecamatan.
"""
import math
from collections import defaultdict

from odoo import api, models
from odoo.exceptions import UserError

from .rekap import KELOMPOK_REKAP

GRUP_RINCI = ('satu_data.group_satu_data_walidata', 'satu_data_pendidikan.group_produsen_pendidikan')

# Palet 5 kelas. "naik": makin tinggi makin baik (merah -> hijau);
# "turun": makin tinggi makin buruk (kuning -> merah).
PALET = {
    'naik':  ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641'],
    'turun': ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'],
}

# Penyebut partisipasi per jenjang: (kelompok, field usia, label)
JENJANG_USIA = {
    'paud':       ('usia_5_6',   'PAUD/TK',    '5–6 tahun'),
    'sd':         ('usia_7_12',  'SD/MI',      '7–12 tahun'),
    'smp':        ('usia_13_15', 'SMP/MTs',    '13–15 tahun'),
    'sma':        ('usia_16_18', 'SMA/SMK/MA', '16–18 tahun'),
}
KELOMPOK_JENJANG_USIA = {'paud': 'paud', 'sd': 'sd_mi', 'smp': 'smp_mts', 'sma': 'sma_smk_ma'}

# Field rekap yang dijumlahkan (field turunan tersimpan ikut).
FIELD_JUMLAH = ['sekolah_total', 'siswa', 'siswa_usia_resmi', 'rombel', 'guru', 'guru_s1',
                'guru_sertifikasi', 'kelas_baik', 'kelas_total', 'putus_sekolah', 'lulusan',
                'melanjutkan']
# Angka tahun ajaran (Semester I) untuk indikator keberlanjutan.
FIELD_TAHUN_AJARAN = ['siswa', 'putus_sekolah', 'lulusan', 'melanjutkan']
FIELD_USIA = [u for u, _l, _t in JENJANG_USIA.values()]


def _indikator():
    daftar = [
        # ── Ketersediaan ─────────────────────────────────────────────────────
        {'kode': 'jml_sekolah', 'nama': 'Jumlah Satuan Pendidikan', 'singkat': 'Sekolah',
         'kelompok': 'Ketersediaan', 'jenis': 'jumlah', 'pembilang': 'sekolah_total',
         'satuan': 'Sekolah', 'arah': 'naik',
         'definisi': 'Jumlah satuan pendidikan (negeri dan swasta, termasuk madrasah) menurut '
                     'rekap semester.'},
        {'kode': 'jml_siswa', 'nama': 'Jumlah Peserta Didik', 'singkat': 'Siswa',
         'kelompok': 'Ketersediaan', 'jenis': 'jumlah', 'pembilang': 'siswa',
         'satuan': 'Siswa', 'arah': 'naik',
         'definisi': 'Jumlah peserta didik laki-laki dan perempuan pada semester terpilih.'},
        {'kode': 'jml_guru', 'nama': 'Jumlah Guru', 'singkat': 'Guru',
         'kelompok': 'Ketersediaan', 'jenis': 'jumlah', 'pembilang': 'guru',
         'satuan': 'Guru', 'arah': 'naik',
         'definisi': 'Jumlah guru pada semester terpilih.'},
        # ── Mutu layanan ─────────────────────────────────────────────────────
        {'kode': 'rasio_murid_guru', 'nama': 'Rasio Murid per Guru', 'singkat': 'Murid/guru',
         'kelompok': 'Mutu Layanan', 'jenis': 'rasio', 'pembilang': 'siswa', 'penyebut': 'guru',
         'faktor': 1, 'satuan': 'murid per guru', 'arah': 'turun', 'batas': [10, 14, 18, 24],
         'label_pembilang': 'Peserta didik', 'label_penyebut': 'Guru',
         'definisi': 'Jumlah peserta didik dibagi jumlah guru. Makin rendah makin banyak '
                     'perhatian guru per murid.'},
        {'kode': 'murid_per_rombel', 'nama': 'Rata-rata Murid per Rombongan Belajar',
         'singkat': 'Murid/rombel', 'kelompok': 'Mutu Layanan', 'jenis': 'rasio',
         'pembilang': 'siswa', 'penyebut': 'rombel', 'faktor': 1, 'satuan': 'murid per rombel',
         'arah': 'turun', 'batas': [16, 21, 26, 32],
         'label_pembilang': 'Peserta didik', 'label_penyebut': 'Rombongan belajar',
         'definisi': 'Jumlah peserta didik dibagi jumlah rombongan belajar.'},
        {'kode': 'kelas_baik', 'nama': 'Ruang Kelas dalam Kondisi Baik', 'singkat': 'Kelas baik',
         'kelompok': 'Mutu Layanan', 'jenis': 'rasio', 'pembilang': 'kelas_baik',
         'penyebut': 'kelas_total', 'faktor': 100, 'satuan': '%', 'arah': 'naik',
         'batas': [50, 65, 80, 90],
         'label_pembilang': 'Ruang kelas baik', 'label_penyebut': 'Seluruh ruang kelas',
         'definisi': 'Persentase ruang kelas dalam kondisi baik dari seluruh ruang kelas '
                     '(baik, rusak ringan, rusak berat).'},
        {'kode': 'guru_s1', 'nama': 'Guru Berkualifikasi S1/D4', 'singkat': 'Guru S1/D4',
         'kelompok': 'Mutu Layanan', 'jenis': 'rasio', 'pembilang': 'guru_s1', 'penyebut': 'guru',
         'faktor': 100, 'satuan': '%', 'arah': 'naik', 'batas': [50, 65, 80, 90],
         'label_pembilang': 'Guru S1/D4', 'label_penyebut': 'Guru',
         'definisi': 'Persentase guru berkualifikasi akademik minimal S1/D4.'},
        {'kode': 'guru_sertifikasi', 'nama': 'Guru Bersertifikat Pendidik', 'singkat': 'Guru bersertifikat',
         'kelompok': 'Mutu Layanan', 'jenis': 'rasio', 'pembilang': 'guru_sertifikasi',
         'penyebut': 'guru', 'faktor': 100, 'satuan': '%', 'arah': 'naik',
         'batas': [30, 45, 60, 75],
         'label_pembilang': 'Guru bersertifikat', 'label_penyebut': 'Guru',
         'definisi': 'Persentase guru yang memiliki sertifikat pendidik.'},
    ]
    # ── Partisipasi: tiap jenjang punya indikator sendiri ────────────────────
    for kode, (usia, nama, rentang) in JENJANG_USIA.items():
        kel = KELOMPOK_JENJANG_USIA[kode]
        daftar.append({
            'kode': f'apk_{kode}', 'nama': f'Angka Partisipasi Kasar (APK) {nama}',
            'singkat': f'APK {nama}', 'kelompok': 'Partisipasi', 'jenis': 'rasio',
            'pembilang': f'siswa__{kel}', 'penyebut': usia, 'faktor': 100, 'satuan': '%',
            'arah': 'naik', 'batas': [50, 70, 85, 95], 'jenjang_tetap': kel, 'tingkat': 'kecamatan',
            'ada': f'rekap__{kel}',
            'label_pembilang': f'Peserta didik {nama}', 'label_penyebut': f'Penduduk usia {rentang}',
            'definisi': f'Peserta didik {nama} (berapa pun usianya) dibagi penduduk usia {rentang}, '
                        'dikali 100. Dapat melebihi 100% bila ada siswa di luar usia resmi.'})
        if kode != 'paud':
            daftar.append({
                'kode': f'apm_{kode}', 'nama': f'Angka Partisipasi Murni (APM) {nama}',
                'singkat': f'APM {nama}', 'kelompok': 'Partisipasi', 'jenis': 'rasio',
                'pembilang': f'siswa_usia_resmi__{kel}', 'penyebut': usia, 'faktor': 100,
                'satuan': '%', 'arah': 'naik', 'batas': [40, 60, 75, 90], 'jenjang_tetap': kel,
                'tingkat': 'kecamatan', 'ada': f'rekap__{kel}',
                'label_pembilang': f'Peserta didik {nama} usia resmi',
                'label_penyebut': f'Penduduk usia {rentang}',
                'definisi': f'Peserta didik {nama} yang berusia {rentang} dibagi penduduk usia '
                            f'{rentang}, dikali 100. Tidak melebihi 100%.'})
    daftar += [
        # ── Keberlanjutan (data akhir tahun ajaran, Semester I) ──────────────
        {'kode': 'jml_putus', 'nama': 'Jumlah Siswa Putus Sekolah', 'singkat': 'Putus sekolah',
         'kelompok': 'Keberlanjutan', 'jenis': 'jumlah', 'pembilang': 'ta_putus_sekolah',
         'ada': 'ta_rekap', 'satuan': 'Siswa', 'arah': 'turun',
         'definisi': 'Siswa putus sekolah selama tahun ajaran (dari rekap Semester I).'},
        {'kode': 'angka_putus', 'nama': 'Angka Putus Sekolah', 'singkat': 'Angka putus sekolah',
         'kelompok': 'Keberlanjutan', 'jenis': 'rasio', 'pembilang': 'ta_putus_sekolah',
         'penyebut': 'ta_siswa', 'ada': 'ta_rekap', 'faktor': 100, 'satuan': '%', 'arah': 'turun',
         'desimal': 2, 'batas': [0.2, 0.5, 1, 2],
         'label_pembilang': 'Siswa putus sekolah', 'label_penyebut': 'Peserta didik',
         'definisi': 'Siswa putus sekolah dibagi jumlah peserta didik, dikali 100 (Semester I).'},
        {'kode': 'angka_melanjutkan', 'nama': 'Angka Melanjutkan', 'singkat': 'Melanjutkan',
         'kelompok': 'Keberlanjutan', 'jenis': 'rasio', 'pembilang': 'ta_melanjutkan',
         'penyebut': 'ta_lulusan', 'ada': 'ta_rekap', 'faktor': 100, 'satuan': '%',
         'arah': 'naik', 'batas': [40, 60, 80, 95],
         'label_pembilang': 'Lulusan melanjutkan', 'label_penyebut': 'Lulusan',
         'definisi': 'Lulusan yang melanjutkan ke jenjang berikutnya dibagi jumlah lulusan, '
                     'dikali 100 (Semester I).'},
    ]
    for ind in daftar:
        ind.setdefault('desimal', 1 if ind['jenis'] == 'rasio' else 0)
        ind.setdefault('tingkat', 'desa')
        ind.setdefault('ada', 'rekap')
    return daftar


INDIKATOR = _indikator()
INDIKATOR_BY_KODE = {i['kode']: i for i in INDIKATOR}
INDIKATOR_BAWAAN = 'jml_siswa'
KELOMPOK_LABEL = dict(KELOMPOK_REKAP)


def nilai_indikator(ind, angka):
    """Nilai indikator dari kumpulan angka dasar; None bila tidak bisa dihitung.

    Tanpa baris rekap terisi pada semester yang dihitung, nilai dianggap belum ada (bukan 0).
    """
    if not angka or not angka.get(ind['ada']):
        return None
    pembilang = angka.get(ind['pembilang'], 0)
    if ind['jenis'] == 'jumlah':
        return pembilang
    penyebut = angka.get(ind['penyebut'], 0)
    if not penyebut:
        return None
    return round(pembilang / penyebut * ind['faktor'], ind['desimal'])


class SatuDataPendidikanDashboard(models.AbstractModel):
    _name        = 'satu_data.pendidikan.dashboard'
    _description = 'Dashboard Pendidikan'
    _inherit     = ['satu_data.peta.mixin']

    # ── Endpoint ─────────────────────────────────────────────────────────────

    @api.model
    def get_dashboard_pendidikan(self, indikator=False, periode_id=False, kecamatan_id=False,
                                 jenjang=False):
        """Data dashboard pendidikan untuk company aktif.

        :param indikator: kode indikator (lihat ``INDIKATOR``)
        :param periode_id: semester yang datanya terbit; bawaan = terbaru
        :param kecamatan_id: tanpa = level kecamatan; dengan = level desa/kelurahan
        :param jenjang: kelompok jenjang (``paud``, ``sd_mi``, ...); tanpa = semua jenjang.
            Diabaikan oleh indikator partisipasi, yang jenjangnya sudah tertentu.
        """
        company = self.env.company
        ind = INDIKATOR_BY_KODE.get(indikator or INDIKATOR_BAWAAN)
        if not ind:
            raise UserError(self.env._('Indikator tidak dikenal.'))
        if jenjang and jenjang not in KELOMPOK_LABEL:
            raise UserError(self.env._('Jenjang tidak dikenal.'))
        jenjang = jenjang or False
        if ind.get('jenjang_tetap'):
            jenjang_dipakai = ind['jenjang_tetap']
        else:
            jenjang_dipakai = jenjang

        semester_terbit = self.env['satu_data.pengajuan']._sd_periode_terbit('pendidikan', company)
        semester_terbit = semester_terbit.filtered(lambda p: p.frekuensi == 'semesteran').sorted(
            'tanggal_mulai', reverse=True)
        if periode_id:
            periode = semester_terbit.filtered(lambda p: p.id == int(periode_id))
            if not periode:
                raise UserError(self.env._('Data semester ini belum terbit atau tidak ditemukan.'))
        else:
            periode = semester_terbit[:1]

        info_tingkat = self._sd_tingkat_penyajian(company)
        hasil = {
            'wilayah_induk': self._sd_info_wilayah_induk(company),
            'daftar_indikator': [
                {'kode': i['kode'], 'nama': i['nama'], 'kelompok': i['kelompok'], 'satuan': i['satuan'],
                 'jenjang_tetap': i.get('jenjang_tetap') or False} for i in INDIKATOR],
            'daftar_jenjang': [{'kode': k, 'label': v} for k, v in KELOMPOK_REKAP],
            'jenjang': jenjang,
            'indikator': self._sd_info_indikator(ind, info_tingkat),
            'daftar_periode': [{'id': p.id, 'label': p.name} for p in semester_terbit],
            'periode': {'id': periode.id or False, 'label': periode.name or False},
            'warna_tanpa_data': self._sd_warna_tanpa_data(),
            'peta_dasar': self._sd_peta_dasar(),
        }

        dasar = self._sd_angka_dasar(periode, jenjang_dipakai, company) if periode else {}
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
            hasil['kecamatan'] = {'id': kecamatan.id, 'kode': kecamatan.kode, 'nama': kecamatan.name}
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

        # Data yang disajikan paling rendah di kecamatan tidak dirinci per desa, kecuali untuk
        # Walidata dan Produsen Data pendidikan.
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
                'kelas': self._sd_kelas_index(v, kelas) if v is not None else -1,
            }
            if level == 'desa':
                item['jenis'] = w.jenis
            hasil_wilayah.append(item)

        hasil.update({
            'level': level,
            'tersembunyi': tersembunyi,
            'wilayah': hasil_wilayah,
            'kelas': kelas,
            'ringkasan': self._sd_ringkasan(ringkasan, ind),
            'semua_indikator': self._sd_semua_indikator(periode, jenjang, company, kecamatan_id),
            'jumlah_desa': self.env['satu_data.desa'].search_count(
                dom_company + ([('kecamatan_id', '=', int(kecamatan_id))] if kecamatan_id else [])),
            'sekolah': self._sd_titik_sekolah(company, kecamatan_id, jenjang_dipakai)
                       if kecamatan_id else [],
            'tren': self._sd_tren(ind, periode, semester_terbit, jenjang_dipakai, company,
                                  int(kecamatan_id) if kecamatan_id else False) if periode else [],
            'jenjang_dipakai': jenjang_dipakai,
        })
        return hasil

    # ── Angka dasar per desa ─────────────────────────────────────────────────

    @api.model
    def _sd_angka_dasar(self, periode, jenjang, company):
        """{(kecamatan_id, desa_id): {kunci: jumlah}} untuk satu semester.

        Kunci: jumlah field rekap (``jenjang`` bila diisi, selain itu semua jenjang), ``rekap``
        (banyak baris terisi), ``rekap__<kelompok>``, ``siswa__<kelompok>`` dan
        ``siswa_usia_resmi__<kelompok>`` (selalu per kelompok, untuk APK/APM), ``usia_*`` (penduduk usia sekolah tahun
        berjalan) dan ``ta_*`` (angka tahun ajaran dari Semester I).
        """
        Rekap = self.env['satu_data.pendidikan.rekap']
        dom_company = [('company_id', '=', company.id)]
        # Hanya baris yang sudah diisi petugas; baris kosong di laporan dianggap belum ada data.
        terbit = Rekap._sd_domain_terbit(company) + Rekap._sd_domain_terisi()
        dasar = defaultdict(lambda: defaultdict(int))

        def kumpulkan(domain_periode, jenjang_dipilih, awalan, per_kelompok):
            for kec, desa, kel, n, *jumlah in Rekap._read_group(
                    dom_company + terbit + domain_periode, ['kecamatan_id', 'desa_id', 'kelompok'],
                    ['__count'] + [f'{f}:sum' for f in FIELD_JUMLAH]):
                angka = dasar[(kec.id, desa.id)]
                nilai = dict(zip(FIELD_JUMLAH, jumlah))
                if per_kelompok:
                    angka[f'rekap__{kel}'] += n
                    angka[f'siswa__{kel}'] += nilai['siswa'] or 0
                    angka[f'siswa_usia_resmi__{kel}'] += nilai['siswa_usia_resmi'] or 0
                if jenjang_dipilih and kel != jenjang_dipilih:
                    continue
                if awalan:
                    angka['ta_rekap'] += n
                    for f in FIELD_TAHUN_AJARAN:
                        angka[f'ta_{f}'] += nilai[f] or 0
                else:
                    angka['rekap'] += n
                    for f in FIELD_JUMLAH:
                        angka[f] += nilai[f] or 0

        kumpulkan([('periode_id', '=', periode.id)], jenjang, False, True)

        # Tahun ajaran: Semester I pada tahun yang sama (Semester II memakai Semester I-nya).
        semester_1 = self.env['satu_data.pengajuan']._sd_periode_terbit('pendidikan', company).filtered(
            lambda p: p.frekuensi == 'semesteran' and p.tanggal_mulai.year == periode.tanggal_mulai.year
            and p.tanggal_mulai.month == 1)
        if semester_1:
            kumpulkan([('periode_id', '=', semester_1[0].id)], jenjang, True, False)

        # Penyebut partisipasi: penduduk usia sekolah tahun yang mencakup semester ini.
        Usia = self.env['satu_data.pendidikan.usia_sekolah']
        tahun = self.env['satu_data.pengajuan']._sd_periode_terbit('pendidikan_usia_sekolah', company)
        tahun = tahun.filtered(lambda p: p.frekuensi == 'tahunan'
                               and p.tanggal_mulai <= periode.tanggal_mulai <= p.tanggal_akhir)
        if tahun:
            for kec, desa, *jumlah in Usia._read_group(
                    dom_company + Usia._sd_domain_terisi() + [('periode_id', 'in', tahun[:1].ids)],
                    ['kecamatan_id', 'desa_id'], [f'{f}:sum' for f in FIELD_USIA]):
                angka = dasar[(kec.id, desa.id)]
                for f, v in zip(FIELD_USIA, jumlah):
                    angka[f] += v or 0
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
            ('company_id', '=', company.id), ('kode', 'like', 'pendidikan.%')])
        return {d.kode.split('.', 1)[1]: d.tingkat_penyajian for d in data}

    @api.model
    def _sd_info_indikator(self, ind, info_tingkat):
        tingkat = info_tingkat.get(ind['kode'], ind['tingkat'])
        boleh_rinci = any(self.env.user.has_group(g) for g in GRUP_RINCI)
        info = {k: ind.get(k) for k in ('kode', 'nama', 'singkat', 'kelompok', 'satuan', 'arah',
                                        'jenis', 'desimal', 'definisi', 'label_pembilang',
                                        'label_penyebut')}
        info.update({'tingkat': tingkat, 'jenjang_tetap': ind.get('jenjang_tetap') or False,
                     'boleh_desa': tingkat == 'desa' or boleh_rinci})
        return info

    @api.model
    def _sd_ringkasan(self, angka, ind):
        return {
            'nilai': nilai_indikator(ind, angka),
            'pembilang': angka.get(ind['pembilang'], 0) if angka else 0,
            'penyebut': angka.get(ind.get('penyebut'), 0) if angka and ind['jenis'] == 'rasio' else None,
        }

    @api.model
    def _sd_semua_indikator(self, periode, jenjang, company, kecamatan_id):
        """{kode: nilai} untuk seluruh indikator pada cakupan yang sama (kartu ringkas, grafik).

        Indikator partisipasi memakai jenjangnya sendiri; yang lain memakai jenjang pilihan.
        """
        if not periode:
            return {}
        dasar = self._sd_angka_dasar(periode, jenjang, company)
        angka = self._sd_jumlahkan(
            a for (kec, _d), a in dasar.items() if not kecamatan_id or kec == int(kecamatan_id))
        return {i['kode']: nilai_indikator(i, angka) for i in INDIKATOR}

    @api.model
    def _sd_titik_sekolah(self, company, kecamatan_id, kelompok):
        """Satuan pendidikan aktif berkoordinat di satu kecamatan (hanya saat dirinci per desa,
        agar peta tidak memuat ribuan titik sekaligus)."""
        dom = [('company_id', '=', company.id), ('kecamatan_id', '=', int(kecamatan_id)),
               '|', ('latitude', '!=', 0), ('longitude', '!=', 0)]
        if kelompok:
            dom.append(('kelompok', '=', kelompok))
        Sekolah = self.env['satu_data.sekolah']
        jenjang = dict(Sekolah._fields['jenjang']._description_selection(self.env))
        status = dict(Sekolah._fields['status']._description_selection(self.env))
        akreditasi = dict(Sekolah._fields['akreditasi']._description_selection(self.env))
        return [{
            'id': s.id, 'nama': s.name, 'lat': s.latitude, 'lng': s.longitude,
            'keterangan': [
                f'{jenjang.get(s.jenjang, "")} · {status.get(s.status, "")}',
                f'NPSN {s.npsn}' if s.npsn else 'NPSN belum diisi',
                f'Akreditasi: {akreditasi.get(s.akreditasi, "–")}',
                f'Desa/Kel. {s.desa_id.name}',
            ],
        } for s in Sekolah.search(dom)]

    @api.model
    def _sd_tren(self, ind, periode, semester_terbit, jenjang, company, kecamatan_id):
        """Nilai indikator per semester terbit, dari yang terlama s.d. semester terpilih."""
        hasil = []
        for p in semester_terbit.sorted('tanggal_mulai'):
            if p.tanggal_mulai > periode.tanggal_mulai:
                continue
            dasar = self._sd_angka_dasar(p, jenjang, company)
            angka = self._sd_jumlahkan(
                a for (kec, _d), a in dasar.items() if not kecamatan_id or kec == kecamatan_id)
            hasil.append({'id': p.id, 'label': p.name, 'nilai': nilai_indikator(ind, angka)})
        return hasil

    # ── Kelas warna ──────────────────────────────────────────────────────────

    @api.model
    def _sd_kelas_indikator(self, ind, nilai_list):
        """5 kelas warna. Batas tetap bila indikator punya batas (target/standar), selain itu
        kuantil nilai wilayah. Kelas ke-i: batas[i-1] <= nilai < batas[i]."""
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
