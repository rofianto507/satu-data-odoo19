import random

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.satu_data.tests.common import SatuDataCase
from odoo.addons.satu_data_pendidikan.models.demo import _bagian, _di_dalam, _titik_acak
from odoo.addons.satu_data_pendidikan.models.indikator import (
    INDIKATOR, INDIKATOR_BY_KODE, nilai_indikator)


@tagged('post_install', '-at_install', 'satu_data', 'satu_data_pendidikan')
class TestPendidikan(SatuDataCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tahun = cls.env['satu_data.periode'].create({
            'name': 'Uji Tahun 2095 Pendidikan', 'frekuensi': 'tahunan',
            'tanggal_mulai': '2095-01-01', 'tanggal_akhir': '2095-12-31'})
        cls.semester = cls.periode['2025_1']     # 2095 Semester I (fixture bersama)
        cls.disdik_a =cls.env['satu_data.instansi'].create({
            'name': 'Disdik A', 'company_id': cls.company_a.id})
        cls.user_produsen = new_test_user(
            cls.env, login='sd_produsen_pdd_a', groups='satu_data_pendidikan.group_produsen_pendidikan',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.user_walidata = new_test_user(
            cls.env, login='sd_walidata_pdd_a', groups='satu_data.group_satu_data_walidata',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.user_pengguna = new_test_user(
            cls.env, login='sd_pengguna_pdd_a', groups='satu_data.group_satu_data_pengguna',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])

    def _sekolah(self, **vals):
        vals.setdefault('name', 'SDN Uji 1')
        vals.setdefault('desa_id', self.desa_1.id)
        return self.env['satu_data.sekolah'].create(vals)

    def _buka_laporan(self, user=None, sektor='pendidikan_usia_sekolah', periode=None):
        Wizard = self.env['satu_data.pengajuan.wizard']
        if user:
            Wizard = Wizard.with_user(user)
        aksi = Wizard.create({'sektor': sektor, 'periode_id': (periode or self.tahun).id,
                              'instansi_id': self.disdik_a.id,
                              'company_id': self.company_a.id}).action_buka()
        return self.env['satu_data.pengajuan'].browse(aksi['res_id'])

    # ── Satuan pendidikan ────────────────────────────────────────────────────

    def test_jenjang_kelompok_dan_pembina(self):
        sd = self._sekolah(jenjang='sd')
        mi = self._sekolah(name='MI Uji', jenjang='mi', status='swasta')
        sma = self._sekolah(name='SMAN Uji', jenjang='sma')
        self.assertEqual((sd.kelompok, sd.pembina), ('sd_mi', 'disdik'))
        self.assertEqual((mi.kelompok, mi.pembina), ('sd_mi', 'kemenag'), 'Madrasah dibina Kemenag')
        self.assertEqual((sma.kelompok, sma.pembina), ('sma_smk_ma', 'disdik'))
        # Pembina bisa diubah (mis. RA = PAUD binaan Kemenag) dan tidak ditimpa saat disimpan lagi.
        ra = self._sekolah(name='RA Uji', jenjang='paud', pembina='kemenag')
        self.assertEqual(ra.pembina, 'kemenag')
        ra.akreditasi = 'a'
        self.assertEqual(ra.pembina, 'kemenag')
        self.assertEqual(sd.kecamatan_id, self.kec_1)
        self.assertEqual(sd.company_id, self.company_a)

    def test_npsn(self):
        self._sekolah(npsn='90000001')
        for salah in ('1234567', 'ABCDEFGH', '123456789'):
            with self.assertRaises(ValidationError, msg=salah):
                self._sekolah(name='Salah', npsn=salah)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._sekolah(name='Ganda', npsn='90000001')
            self.env.flush_all()

    def test_npsn_sama_di_wilayah_lain_boleh(self):
        self._sekolah(npsn='90000002')
        self._sekolah(name='SDN B', npsn='90000002', desa_id=self.desa_b.id)

    def test_koordinat(self):
        s = self._sekolah()
        with self.assertRaises(ValidationError):
            s.latitude = 95
        s.write({'latitude': -8.2, 'longitude': 113.4})

    def test_hak_akses_sekolah(self):
        with self.assertRaises(AccessError):
            self.env['satu_data.sekolah'].with_user(self.user_pengguna).create({
                'name': 'Liar', 'jenjang': 'sd', 'desa_id': self.desa_1.id})
        self.env['satu_data.sekolah'].with_user(self.user_produsen).create({
            'name': 'SDN Produsen', 'jenjang': 'sd', 'desa_id': self.desa_1.id})
        self.assertTrue(self.env['satu_data.sekolah'].with_user(self.user_pengguna).search_count(
            [('name', '=', 'SDN Produsen')]))

    # ── Penduduk usia sekolah ────────────────────────────────────────────────

    def test_usia_sekolah_validasi_dan_snapshot(self):
        Usia = self.env['satu_data.pendidikan.usia_sekolah']
        r = Usia.create({'desa_id': self.desa_1.id, 'periode_id': self.tahun.id,
                         'usia_5_6': 10, 'usia_7_12': 40, 'usia_13_15': 20, 'usia_16_18': 20})
        self.assertEqual(r.usia_total, 90)
        self.assertTrue(r.terisi)
        self.assertEqual(r.kecamatan_id, self.kec_1)
        with self.assertRaises(ValidationError):
            r.usia_7_12 = -1
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            Usia.create({'desa_id': self.desa_1.id, 'periode_id': self.tahun.id})
        # Desa pindah kecamatan: data yang sudah dicatat tetap di kecamatan lama.
        self.desa_1.kecamatan_id = self.kec_2
        self.assertEqual(r.kecamatan_id, self.kec_1)

    def test_desa_tidak_bisa_pindah_wilayah_bila_ada_data(self):
        self.env['satu_data.pendidikan.usia_sekolah'].create({
            'desa_id': self.desa_1.id, 'periode_id': self.tahun.id, 'usia_7_12': 5})
        with self.assertRaises(ValidationError):
            self.desa_1.write({'company_id': self.company_b.id, 'kecamatan_id': self.kec_b.id})
        kosong = self.env['satu_data.desa'].create({
            'kode': 'D7', 'name': 'Desa Kosong', 'kecamatan_id': self.kec_1.id,
            'company_id': self.company_a.id})
        kosong.write({'company_id': self.company_b.id, 'kecamatan_id': self.kec_b.id})

    def test_laporan_usia_sekolah(self):
        Usia = self.env['satu_data.pendidikan.usia_sekolah']
        lap = self._buka_laporan(self.user_produsen)
        self.assertEqual(lap.usia_sekolah_ids.desa_id, self.desa_1 | self.desa_2 | self.desa_3)
        self.assertEqual((lap.jumlah_record, lap.jumlah_terisi, lap.jumlah_kosong), (3, 0, 3))
        # Batas pengajuan: 31 hari setelah awal tahun.
        self.assertEqual(lap.batas_pengajuan, fields.Date.to_date('2095-02-01'))
        with self.assertRaises(UserError):
            lap.with_user(self.user_produsen).action_ajukan()       # belum ada yang terisi
        self.assertEqual(self._buka_laporan(self.user_produsen), lap, 'Tidak menggandakan laporan')
        self.assertEqual(Usia.search_count([('periode_id', '=', self.tahun.id)]), 3)

        baris = {r.desa_id: r for r in lap.usia_sekolah_ids}
        lap.with_user(self.user_produsen).write({'usia_sekolah_ids': [
            (1, baris[self.desa_1].id, {'usia_5_6': 12, 'usia_7_12': 50}),
            (1, baris[self.desa_2].id, {'usia_16_18': 0}),
        ]})
        self.assertEqual((lap.jumlah_terisi, lap.jumlah_kosong), (2, 1), 'Angka nol yang diketik terisi')
        with self.assertRaises(AccessError):
            lap.with_user(self.user_pengguna).action_ajukan()
        lap.with_user(self.user_produsen).action_ajukan()
        with self.assertRaises(UserError):
            baris[self.desa_1].with_user(self.user_produsen).usia_7_12 = 99    # terkunci
        with self.assertRaises(AccessError):
            lap.with_user(self.user_produsen).action_terbitkan()
        lap.with_user(self.user_walidata).action_terbitkan()
        self.assertEqual(baris[self.desa_1].sd_status, 'terbit')
        lap.with_user(self.user_walidata).write({'catatan': 'Lengkapi Desa Tiga.'})
        lap.with_user(self.user_walidata).action_kembalikan()
        self.assertEqual((lap.state, lap.perlu_perbaikan), ('draf', True))
        baris[self.desa_3].with_user(self.user_produsen).usia_7_12 = 30
        self.assertEqual(lap.jumlah_terisi, 3)

    def test_laporan_menyusul_baris_lama_dan_desa_baru(self):
        r = self.env['satu_data.pendidikan.usia_sekolah'].create({
            'desa_id': self.desa_1.id, 'periode_id': self.tahun.id, 'usia_7_12': 7})
        self.assertFalse(r.pengajuan_id)
        lap = self._buka_laporan()
        self.assertEqual(r.pengajuan_id, lap)
        self.assertEqual(lap.jumlah_terisi, 1)
        desa_baru = self.env['satu_data.desa'].create({
            'kode': 'D6', 'name': 'Desa Baru', 'kecamatan_id': self.kec_1.id,
            'company_id': self.company_a.id})
        lap.with_user(self.user_produsen).action_lengkapi_baris()
        self.assertIn(desa_baru, lap.usia_sekolah_ids.desa_id)

    def test_aksi_lihat_data_per_kecamatan(self):
        lap = self._buka_laporan()
        aksi = lap.action_lihat_data()
        self.assertEqual(aksi['res_model'], 'satu_data.pendidikan.usia_sekolah')
        self.assertEqual(aksi['views'][0][0],
                         self.env.ref('satu_data_pendidikan.view_usia_sekolah_list_isian').id)
        self.assertEqual(aksi['context']['search_default_group_kecamatan'], 1)
        self.assertEqual(self.env['satu_data.pendidikan.usia_sekolah'].search_count(aksi['domain']), 3)

    # ── Rekap semester ───────────────────────────────────────────────────────

    def test_rekap_validasi(self):
        Rekap = self.env['satu_data.pendidikan.rekap']
        dasar = {'desa_id': self.desa_1.id, 'periode_id': self.semester.id, 'kelompok': 'sd_mi'}
        r = Rekap.create(dict(dasar, sekolah_negeri=2, sekolah_swasta=1, siswa_l=60, siswa_p=40,
                              siswa_usia_resmi=90, guru=8, guru_s1=7, guru_sertifikasi=4,
                              kelas_baik=5, kelas_rusak_ringan=2, kelas_rusak_berat=1,
                              lulusan=10, melanjutkan=9))
        self.assertEqual((r.sekolah_total, r.siswa, r.kelas_total), (3, 100, 8))
        self.assertTrue(r.terisi)
        for salah in ({'siswa_usia_resmi': 101}, {'guru_s1': 9}, {'guru_sertifikasi': 9},
                      {'melanjutkan': 11}, {'rombel': -1}, {'putus_sekolah': -1}):
            with self.assertRaises(ValidationError, msg=str(salah)):
                r.write(salah)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            Rekap.create(dasar)
            self.env.flush_all()

    def test_rekap_jenjang_lain_boleh(self):
        Rekap = self.env['satu_data.pendidikan.rekap']
        dasar = {'desa_id': self.desa_1.id, 'periode_id': self.semester.id}
        Rekap.create(dict(dasar, kelompok='sd_mi'))
        Rekap.create(dict(dasar, kelompok='smp_mts'))

    def test_laporan_semester(self):
        self._sekolah(name='SDN A', jenjang='sd', status='negeri')
        self._sekolah(name='SDN B', jenjang='sd', status='negeri')
        self._sekolah(name='MI C', jenjang='mi', status='swasta')
        self._sekolah(name='TK D', jenjang='paud', status='swasta', desa_id=self.desa_2.id)
        self._sekolah(name='SDN Arsip', jenjang='sd').active = False
        lap = self._buka_laporan(self.user_produsen, 'pendidikan', self.semester)
        # Satu baris per desa dan jenjang (3 desa x 4 jenjang), semuanya belum terisi.
        self.assertEqual(len(lap.rekap_pendidikan_ids), 12)
        self.assertEqual((lap.jumlah_record, lap.jumlah_terisi, lap.jumlah_desa, lap.jumlah_kosong),
                         (12, 0, 12, 12))
        self.assertEqual(lap.satuan_baris, 'baris desa dan jenjang')
        baris = {(r.desa_id, r.kelompok): r for r in lap.rekap_pendidikan_ids}
        sd = baris[(self.desa_1, 'sd_mi')]
        # Jumlah sekolah dari master (yang aktif) dan tidak menandai baris sebagai terisi.
        self.assertEqual((sd.sekolah_negeri, sd.sekolah_swasta), (2, 1))
        self.assertEqual(baris[(self.desa_2, 'paud')].sekolah_swasta, 1)
        self.assertFalse(sd.terisi)
        with self.assertRaises(UserError):
            lap.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(self._buka_laporan(self.user_produsen, 'pendidikan', self.semester), lap)
        self.assertEqual(self.env['satu_data.pendidikan.rekap'].search_count(
            [('periode_id', '=', self.semester.id)]), 12)

        lap.with_user(self.user_produsen).write({'rekap_pendidikan_ids': [
            (1, sd.id, {'siswa_l': 60, 'siswa_p': 55, 'guru': 7}),
            (1, baris[(self.desa_3, 'sma_smk_ma')].id, {'rombel': 0}),
        ]})
        self.assertEqual((lap.jumlah_terisi, lap.jumlah_kosong), (2, 10))
        lap.with_user(self.user_produsen).action_ajukan()
        with self.assertRaises(UserError):
            sd.with_user(self.user_produsen).guru = 9      # terkunci selama diperiksa
        lap.with_user(self.user_walidata).action_terbitkan()
        self.assertEqual(sd.sd_status, 'terbit')
        aksi = lap.action_lihat_data()
        self.assertEqual(aksi['res_model'], 'satu_data.pendidikan.rekap')
        self.assertEqual(aksi['views'][0][0], self.env.ref('satu_data_pendidikan.view_rekap_list_isian').id)

    def test_desa_baru_ditambahkan_ke_laporan_semester(self):
        lap = self._buka_laporan(self.user_produsen, 'pendidikan', self.semester)
        baru = self.env['satu_data.desa'].create({
            'kode': 'D5', 'name': 'Desa Baru', 'kecamatan_id': self.kec_1.id,
            'company_id': self.company_a.id})
        lap.with_user(self.user_produsen).action_lengkapi_baris()
        self.assertEqual(len(lap.rekap_pendidikan_ids.filtered(lambda r: r.desa_id == baru)), 4)

    def test_satuan_laporan_lain_tidak_berubah(self):
        lap = self._buka_laporan()
        self.assertEqual((lap.jumlah_desa, lap.satuan_baris), (3, 'desa/kelurahan'))

    # ── Indikator dan dashboard ──────────────────────────────────────────────

    def _terbitkan(self, sektor, periode, isian):
        """Buka laporan, isi baris yang diminta ({(desa, kelompok) atau desa: nilai}), terbitkan."""
        lap = self._buka_laporan(self.user_produsen, sektor, periode)
        rekap = sektor == 'pendidikan'
        baris = lap.rekap_pendidikan_ids if rekap else lap.usia_sekolah_ids
        perintah = []
        for r in baris:
            kunci = (r.desa_id, r.kelompok) if rekap else r.desa_id
            if kunci in isian:
                perintah.append((1, r.id, isian[kunci]))
        nama = 'rekap_pendidikan_ids' if rekap else 'usia_sekolah_ids'
        lap.with_user(self.user_produsen).write({nama: perintah})
        lap.with_user(self.user_produsen).action_ajukan()
        lap.with_user(self.user_walidata).action_terbitkan()
        return lap

    def _dashboard(self, user=None, **kw):
        return self.env['satu_data.pendidikan.dashboard'].with_user(user or self.user_walidata) \
            .get_dashboard_pendidikan(**kw)

    def _siapkan_data_dashboard(self):
        self._terbitkan('pendidikan_usia_sekolah', self.tahun, {
            self.desa_1: {'usia_7_12': 120, 'usia_13_15': 60}})
        self._terbitkan('pendidikan', self.semester, {
            (self.desa_1, 'sd_mi'): {
                'siswa_l': 60, 'siswa_p': 40, 'siswa_usia_resmi': 90, 'rombel': 4, 'guru': 5,
                'guru_s1': 4, 'guru_sertifikasi': 2, 'kelas_baik': 3, 'kelas_rusak_ringan': 1,
                'putus_sekolah': 2, 'lulusan': 10, 'melanjutkan': 9},
            (self.desa_2, 'sd_mi'): {
                'siswa_l': 30, 'siswa_p': 20, 'siswa_usia_resmi': 40, 'rombel': 2, 'guru': 5,
                'guru_s1': 5, 'kelas_baik': 2},
        })

    def test_rumus_indikator(self):
        ind = INDIKATOR_BY_KODE['apk_sd']
        self.assertEqual(nilai_indikator(ind, {'rekap__sd_mi': 1, 'siswa__sd_mi': 100, 'usia_7_12': 80}), 125.0)
        self.assertIsNone(nilai_indikator(ind, {'rekap__sd_mi': 1, 'siswa__sd_mi': 100}), 'Tanpa penyebut')
        self.assertIsNone(nilai_indikator(ind, {'rekap': 3, 'siswa__sd_mi': 100, 'usia_7_12': 80}),
                          'Tanpa rekap jenjangnya')
        self.assertEqual(nilai_indikator(INDIKATOR_BY_KODE['jml_siswa'], {'rekap': 1}), 0, 'Nol sah')
        self.assertEqual(len({i['kode'] for i in INDIKATOR}), len(INDIKATOR))

    def test_dashboard_tanpa_data_terbit(self):
        hasil = self._dashboard()
        self.assertEqual((hasil['daftar_periode'], hasil['periode']['id']), ([], False))
        self.assertIsNone(hasil['ringkasan']['nilai'])
        self.assertEqual(hasil['tren'], [])

    def test_dashboard_angka(self):
        self._siapkan_data_dashboard()
        hasil = self._dashboard(indikator='jml_siswa')
        self.assertEqual(hasil['periode']['id'], self.semester.id)
        self.assertEqual(hasil['ringkasan']['nilai'], 150)
        semua = hasil['semua_indikator']
        self.assertEqual(semua['rasio_murid_guru'], 15.0)            # 150 murid / 10 guru
        self.assertEqual(semua['murid_per_rombel'], 25.0)            # 150 / 6
        self.assertEqual(semua['guru_s1'], 90.0)                     # 9 / 10
        self.assertEqual(semua['kelas_baik'], 83.3)                  # 5 / (3 + 1 + 2)
        self.assertEqual(semua['jml_guru'], 10)
        # Partisipasi: siswa SD/MI 150 dan usia resmi 130 dibagi penduduk 7–12 tahun (120).
        self.assertEqual(semua['apk_sd'], 125.0)
        self.assertEqual(semua['apm_sd'], 108.3)
        self.assertIsNone(semua['apk_smp'], 'Belum ada siswa SMP: tidak ada data')
        # Keberlanjutan dari Semester I yang sama.
        self.assertEqual(semua['jml_putus'], 2)
        self.assertEqual(semua['angka_putus'], 1.33)
        self.assertEqual(semua['angka_melanjutkan'], 90.0)
        # Tren memuat semester terbit saja.
        self.assertEqual([t['id'] for t in hasil['tren']], [self.semester.id])

    def test_dashboard_jenjang(self):
        self._siapkan_data_dashboard()
        sd = self._dashboard(indikator='jml_siswa', jenjang='sd_mi')
        self.assertEqual(sd['ringkasan']['nilai'], 150)
        smp = self._dashboard(indikator='jml_siswa', jenjang='smp_mts')
        self.assertIsNone(smp['ringkasan']['nilai'])
        # Indikator partisipasi mengabaikan jenjang pilihan (jenjangnya tertentu).
        apk = self._dashboard(indikator='apk_sd', jenjang='smp_mts')
        self.assertEqual((apk['ringkasan']['nilai'], apk['jenjang_dipakai']), (125.0, 'sd_mi'))
        with self.assertRaises(UserError):
            self._dashboard(jenjang='tk')
        with self.assertRaises(UserError):
            self._dashboard(indikator='tidak_ada')

    def test_dashboard_rincian_wilayah_dan_hak_akses(self):
        self._siapkan_data_dashboard()
        kec = self.desa_1.kecamatan_id
        # Partisipasi (data lokasi sekolah) disajikan paling rendah di kecamatan.
        pengguna = self._dashboard(self.user_pengguna, indikator='apk_sd', kecamatan_id=kec.id)
        self.assertTrue(pengguna['tersembunyi'])
        self.assertTrue(all(w['nilai'] is None for w in pengguna['wilayah']))
        walidata = self._dashboard(self.user_walidata, indikator='apk_sd', kecamatan_id=kec.id)
        self.assertFalse(walidata['tersembunyi'])
        # Indikator tingkat desa terlihat oleh pengguna.
        desa = self._dashboard(self.user_pengguna, indikator='jml_siswa', kecamatan_id=kec.id)
        self.assertFalse(desa['tersembunyi'])
        nilai = {w['id']: w['nilai'] for w in desa['wilayah']}
        self.assertEqual(nilai[self.desa_1.id], 100)

    def test_dashboard_titik_sekolah_hanya_per_kecamatan(self):
        self._siapkan_data_dashboard()
        self._sekolah(name='SDN Peta', jenjang='sd', latitude=-8.2, longitude=113.7)
        self._sekolah(name='SMPN Peta', jenjang='smp', latitude=-8.21, longitude=113.71)
        self._sekolah(name='SDN Tanpa Titik', jenjang='sd')
        kec = self.desa_1.kecamatan_id
        self.assertEqual(self._dashboard(indikator='jml_siswa')['sekolah'], [])
        titik = self._dashboard(indikator='jml_siswa', kecamatan_id=kec.id)['sekolah']
        self.assertEqual(sorted(t['nama'] for t in titik), ['SDN Peta', 'SMPN Peta'])
        sd = self._dashboard(indikator='jml_siswa', kecamatan_id=kec.id, jenjang='sd_mi')['sekolah']
        self.assertEqual([t['nama'] for t in sd], ['SDN Peta'])

    def test_daftar_data_indikator(self):
        data = self.env['satu_data.data'].search([
            ('sektor', '=', 'pendidikan'), ('jenis', '=', 'indikator')])
        self.assertEqual({d.kode.split('.', 1)[1] for d in data}, set(INDIKATOR_BY_KODE))
        self.assertTrue(all(data.mapped('memenuhi_sdi')), data.mapped('metadata_kurang'))
        apk = data.filtered(lambda d: d.kode == 'pendidikan.apk_sd')
        self.assertEqual(apk.tingkat_penyajian, 'kecamatan')

    # ── Daftar Data dan instansi ─────────────────────────────────────────────

    def test_daftar_data_pendidikan(self):
        data = self.env['satu_data.data'].search([('sektor', '=', 'pendidikan_usia_sekolah')])
        self.assertEqual(len(data), 4)
        self.assertTrue(all(data.mapped('memenuhi_sdi')), data.mapped('metadata_kurang'))
        self.assertEqual(data[:1].urusan_id, self.env.ref('satu_data.urusan_1_01'))
        kemenag = self.env.ref('satu_data_pendidikan.instansi_kemenag')
        self.assertEqual((kemenag.jenis, kemenag.peran), ('vertikal', 'produsen'))

    # ── Demo ─────────────────────────────────────────────────────────────────

    def test_geometri_demo(self):
        kotak = {'type': 'Polygon', 'coordinates': [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]]}
        bagian = _bagian(kotak)[0]
        self.assertAlmostEqual(bagian['luas'], 16)
        self.assertTrue(_di_dalam(1, 1, bagian['poligon']))
        self.assertFalse(_di_dalam(5, 1, bagian['poligon']))
        lubang = {'type': 'Polygon', 'coordinates': [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]]}
        self.assertFalse(_di_dalam(5, 5, lubang['coordinates']))
        rng = random.Random(1)
        for _ in range(20):
            lat, lng = _titik_acak(rng, _bagian(lubang)[0])
            self.assertTrue(_di_dalam(lng, lat, lubang['coordinates']))

    def test_demo_tidak_menimpa(self):
        main = self.env.ref('base.main_company')
        Sekolah = self.env['satu_data.sekolah']
        if not Sekolah.search_count([('company_id', '=', main.id)], limit=1):
            desa = self.env['satu_data.desa'].search([('company_id', '=', main.id)], limit=1)
            if not desa:
                return
            Sekolah.create({'name': 'SDN Contoh', 'desa_id': desa.id})
        jumlah = Sekolah.search_count([])
        self.assertFalse(self.env['satu_data.pendidikan.demo']._sd_demo_pendidikan())
        self.assertEqual(Sekolah.search_count([]), jumlah)
