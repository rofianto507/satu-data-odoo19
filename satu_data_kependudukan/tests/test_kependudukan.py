from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.satu_data.tests.common import SatuDataCase


@tagged("post_install", "-at_install", "satu_data", "satu_data_kependudukan")
class TestKependudukan(SatuDataCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Pdd = cls.env['satu_data.kependudukan']
        # Periode 2025 Semester I (terbaru)
        # Luas diambil dari desa: desa_1 = 2 km², desa_2 kosong, desa_3 = 1 km².
        cls.p1 = Pdd.create({'desa_id': cls.desa_1.id, 'periode_id': cls.periode['2025_1'].id,
                             'jumlah_laki_laki': 100, 'jumlah_perempuan': 120,
                             'jumlah_kk': 60})
        cls.p2 = Pdd.create({'desa_id': cls.desa_2.id, 'periode_id': cls.periode['2025_1'].id,
                             'jumlah_laki_laki': 50, 'jumlah_perempuan': 50,
                             'jumlah_kk': 30})
        cls.p3 = Pdd.create({'desa_id': cls.desa_3.id, 'periode_id': cls.periode['2025_1'].id,
                             'jumlah_laki_laki': 10, 'jumlah_perempuan': 10,
                             'jumlah_kk': 5})
        # Periode lama
        Pdd.create({'desa_id': cls.desa_1.id, 'periode_id': cls.periode['2024_2'].id,
                    'jumlah_laki_laki': 90, 'jumlah_perempuan': 110, 'jumlah_kk': 55})
        # Wilayah B tidak boleh ikut terhitung di wilayah A
        Pdd.create({'desa_id': cls.desa_b.id, 'periode_id': cls.periode['2025_1'].id,
                    'jumlah_laki_laki': 9999, 'jumlah_perempuan': 9999, 'jumlah_kk': 1})

        cls.user_a = new_test_user(
            cls.env, login='sd_pengguna_a', groups='satu_data.group_satu_data_pengguna',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.user_produsen = new_test_user(
            cls.env, login='sd_produsen_a',
            groups='satu_data_kependudukan.group_produsen_kependudukan',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.user_walidata = new_test_user(
            cls.env, login='sd_walidata_a', groups='satu_data.group_satu_data_walidata',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        Instansi = cls.env['satu_data.instansi']
        cls.dukcapil_a = Instansi.create({'name': 'Dukcapil A', 'company_id': cls.company_a.id})
        cls.dukcapil_b = Instansi.create({'name': 'Dukcapil B', 'company_id': cls.company_b.id})

    def _terbitkan_semua(self):
        """Terbitkan semua periode yang punya data (dashboard hanya memakai data terbit)."""
        Pengajuan = self.env['satu_data.pengajuan']
        for company, periode in self.env['satu_data.kependudukan']._read_group(
                [], ['company_id', 'periode_id']):
            if company not in (self.company_a, self.company_b):
                continue
            p = Pengajuan.sd_siapkan('kependudukan', periode, company,
                                     self.dukcapil_a if company == self.company_a else self.dukcapil_b)
            if p.state != 'terbit':
                p.sudo().write({'state': 'terbit'})

    def _dashboard(self, company=None, terbitkan=True, **kw):
        if terbitkan:
            self._terbitkan_semua()
        return self.env['satu_data.kependudukan'].with_company(
            company or self.company_a).get_dashboard_peta(**kw)

    # ── Field dan constraint ─────────────────────────────────────────────────

    def test_compute(self):
        self.assertEqual(self.p1.jumlah_penduduk, 220)
        self.assertEqual(self.p1.kepadatan, 110.0)
        self.assertEqual(self.p2.kepadatan, 0.0)
        self.assertEqual(self.p1.display_name, 'Desa Satu – Uji 2095 Semester I')
        self.assertEqual(self.p1.kecamatan_id, self.kec_1)
        self.assertEqual(self.p1.company_id, self.company_a)

    def test_angka_negatif_ditolak(self):
        for field in ('jumlah_laki_laki', 'jumlah_perempuan', 'jumlah_kk'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.p1.write({field: -1})
        with self.assertRaises(ValidationError):
            self.desa_1.luas_km2 = -1

    def test_luas_dari_desa(self):
        self.assertEqual(self.p1.luas_km2, 2.0)
        self.desa_2.luas_km2 = 4.0
        self.assertEqual(self.p2.luas_km2, 4.0)
        self.assertEqual(self.p2.kepadatan, 25.0)
        self.assertEqual(self.kec_1.luas_km2, 6.0)

    def test_kecamatan_snapshot_saat_desa_dipindah(self):
        # Pemekaran: desa_1 pindah ke kec_2. Data lama tetap di kec_1.
        self.desa_1.kecamatan_id = self.kec_2
        self.assertEqual(self.p1.kecamatan_id, self.kec_1)
        baru = self.env['satu_data.kependudukan'].create({
            'desa_id': self.desa_1.id, 'periode_id': self.periode['2026_1'].id,
            'jumlah_laki_laki': 1, 'jumlah_perempuan': 1})
        self.assertEqual(baru.kecamatan_id, self.kec_2)

        # Periode 2025 I: desa_1 masih dihitung di kec_1 dan tetap tampil di daftar desanya.
        data = self._dashboard(kecamatan_id=self.kec_1.id, periode_id=self.periode['2025_1'].id)
        per_desa = {w['id']: w for w in data['wilayah']}
        self.assertIn(self.desa_1.id, per_desa)
        self.assertTrue(per_desa[self.desa_1.id]['arsip'])
        self.assertEqual(data['ringkasan']['penduduk'], 320)

    def test_desa_tidak_bisa_pindah_company_bila_ada_data(self):
        with self.assertRaises(ValidationError):
            self.desa_1.write({'company_id': self.company_b.id, 'kecamatan_id': self.kec_b.id})

    def test_kk_melebihi_penduduk_ditolak(self):
        with self.assertRaises(ValidationError):
            self.p3.jumlah_kk = 21

    def test_periode_unik_per_desa(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.env['satu_data.kependudukan'].create({
                'desa_id': self.desa_1.id, 'periode_id': self.periode['2025_1'].id})

    # ── Endpoint agregasi ────────────────────────────────────────────────────

    def test_dashboard_level_kecamatan(self):
        data = self._dashboard()
        self.assertEqual(data['level'], 'kecamatan')
        self.assertEqual(data['periode']['id'], self.periode['2025_1'].id,
                         'Default = periode terbaru yang punya data')
        self.assertEqual(data['periode']['label'], 'Uji 2095 Semester I')
        self.assertEqual([p['id'] for p in data['daftar_periode']],
                         [self.periode['2025_1'].id, self.periode['2024_2'].id],
                         'Hanya periode berdata, terbaru lebih dulu')
        self.assertEqual(data['wilayah_induk']['nama'], 'Wilayah Tes A')

        # Total kabupaten/kota = jumlah semua desa wilayah A
        kab = data['kabupaten']
        self.assertEqual(kab['penduduk'], 340)
        self.assertEqual(kab['laki_laki'], 160)
        self.assertEqual(kab['perempuan'], 180)
        self.assertEqual(kab['kk'], 95)
        self.assertEqual(kab['jumlah_data'], 3)
        self.assertFalse(kab['luas_lengkap'])
        self.assertFalse(kab['kepadatan'])

        per_kec = {w['id']: w for w in data['wilayah']}
        self.assertEqual(set(per_kec), {self.kec_1.id, self.kec_2.id})
        k1 = per_kec[self.kec_1.id]
        self.assertEqual(k1['angka']['penduduk'], 320)
        self.assertEqual(k1['angka']['kk'], 90)
        self.assertEqual(k1['jumlah_desa'], 2)
        self.assertFalse(k1['angka']['kepadatan'], 'Satu desa tanpa luas: kepadatan tidak dihitung')
        k2 = per_kec[self.kec_2.id]
        self.assertEqual(k2['angka']['penduduk'], 20)
        self.assertEqual(k2['angka']['kepadatan'], 20.0)
        self.assertEqual(k1['geometri']['type'], 'Polygon')

        # Kelas: maks 320 -> langkah 100 -> 320 di kelas ke-4 (indeks 3), 20 di kelas 1
        self.assertEqual(len(data['kelas']), 5)
        self.assertEqual(data['kelas'][-1]['atas'], 500)
        self.assertEqual(k1['kelas'], 3)
        self.assertEqual(k2['kelas'], 0)

    def test_dashboard_level_desa(self):
        data = self._dashboard(kecamatan_id=self.kec_1.id)
        self.assertEqual(data['level'], 'desa')
        self.assertEqual(data['kecamatan']['id'], self.kec_1.id)
        self.assertEqual(data['ringkasan']['penduduk'], 320)
        self.assertEqual(data['ringkasan']['jumlah_wilayah'], 2)
        per_desa = {w['id']: w for w in data['wilayah']}
        self.assertEqual(set(per_desa), {self.desa_1.id, self.desa_2.id})
        self.assertEqual(per_desa[self.desa_1.id]['angka']['kepadatan'], 110.0)
        self.assertEqual(per_desa[self.desa_2.id]['jenis'], 'kelurahan')
        self.assertIsNone(per_desa[self.desa_2.id]['geometri'])

    def test_dashboard_periode_lama_dan_tanpa_data(self):
        data = self._dashboard(periode_id=self.periode['2024_2'].id)
        self.assertEqual(data['kabupaten']['penduduk'], 200)
        per_kec = {w['id']: w for w in data['wilayah']}
        self.assertFalse(per_kec[self.kec_2.id]['angka'])
        self.assertEqual(per_kec[self.kec_2.id]['kelas'], -1)

    def test_dashboard_wilayah_diarsipkan_tetap_terhitung(self):
        self.desa_2.active = False
        # Level desa: desa_2 tetap tampil karena punya data, total tetap 320.
        data = self._dashboard(kecamatan_id=self.kec_1.id)
        per_desa = {w['id']: w for w in data['wilayah']}
        self.assertTrue(per_desa[self.desa_2.id]['arsip'])
        self.assertEqual(data['ringkasan']['penduduk'],
                         sum(w['angka']['penduduk'] for w in data['wilayah'] if w['angka']))
        # Periode tanpa data desa_2: desa_2 yang diarsipkan tidak ditampilkan.
        data = self._dashboard(kecamatan_id=self.kec_1.id, periode_id=self.periode['2024_2'].id)
        self.assertNotIn(self.desa_2.id, [w['id'] for w in data['wilayah']])

        # Level kecamatan: total kab/kota = jumlah kecamatan yang tampil.
        self.desa_2.active = True
        self.kec_2.with_context(active_test=False).desa_ids.active = False
        self.kec_2.active = False
        data = self._dashboard()
        self.assertEqual(data['kabupaten']['penduduk'],
                         sum(w['angka']['penduduk'] for w in data['wilayah'] if w['angka']))
        self.assertIn(self.kec_2.id, [w['id'] for w in data['wilayah']])

    def test_dashboard_periode_tidak_dikenal_ditolak(self):
        with self.assertRaises(UserError):
            self._dashboard(periode_id=self.periode['2026_1'].id + 100000)

    def test_dashboard_periode_tanpa_data(self):
        data = self._dashboard(periode_id=self.periode['2026_1'].id)
        self.assertEqual(data['periode']['label'], 'Uji 2096 Semester I')
        self.assertEqual(data['kabupaten']['penduduk'], 0)
        self.assertTrue(all(w['kelas'] == -1 for w in data['wilayah']))

    # ── Periode ──────────────────────────────────────────────────────────────

    def test_periode_dipakai_tidak_bisa_dihapus(self):
        with self.assertRaises(UserError):
            self.periode['2025_1'].unlink()
        self.assertEqual(self.periode['2025_1'].jumlah_data, 4)
        self.periode['2026_1'].unlink()  # belum dipakai: boleh

    def test_periode_bawaan(self):
        # Periode semesteran yang mencakup hari ini; bila tidak ada, yang terbaru.
        Periode = self.env['satu_data.periode']
        hari_ini = fields.Date.context_today(Periode)
        dom = [('frekuensi', '=', 'semesteran')]
        berjalan = Periode.search(dom + [('tanggal_mulai', '<=', hari_ini),
                                         ('tanggal_akhir', '>=', hari_ini)], limit=1)
        bawaan = self.env['satu_data.kependudukan'].new({}).periode_id
        self.assertEqual(bawaan, berjalan or Periode.search(dom, limit=1))

    def test_dashboard_penduduk_nol_tanpa_warna(self):
        self.env['satu_data.kependudukan'].create({
            'desa_id': self.desa_3.id, 'periode_id': self.periode['2023_1'].id})
        data = self._dashboard(periode_id=self.periode['2023_1'].id)
        per_kec = {w['id']: w for w in data['wilayah']}
        self.assertEqual(per_kec[self.kec_2.id]['kelas'], -1)
        self.assertFalse(per_kec[self.kec_2.id]['angka'], 'Baris kosong = belum ada data')

    def test_dashboard_peta_dasar(self):
        param = self.env['ir.config_parameter']
        param.set_param('satu_data.url_peta_dasar', False)
        param.set_param('satu_data.peta_dasar', False)
        param.set_param('satu_data.carto_api_key', False)

        # Tanpa API key: CARTO disembunyikan (hanya akan memberi tile bertanda air).
        pd = self._dashboard()['peta_dasar']
        self.assertEqual([p['kode'] for p in pd['pilihan']], ['osm'])
        self.assertEqual(pd['bawaan'], 'osm')
        param.set_param('satu_data.peta_dasar', 'voyager')
        self.assertEqual(self._dashboard()['peta_dasar']['bawaan'], 'osm')
        param.set_param('satu_data.peta_dasar', False)

        param.set_param('satu_data.carto_api_key', 'kunci-uji')
        pd = self._dashboard()['peta_dasar']
        self.assertEqual([p['kode'] for p in pd['pilihan']], ['positron', 'voyager', 'osm'])
        self.assertEqual(pd['bawaan'], 'positron')
        self.assertTrue(pd['pilihan'][0]['url'].endswith('.png?key=kunci-uji'))
        self.assertNotIn('carto', pd['pilihan'][0])
        self.assertIn('CARTO', pd['pilihan'][0]['atribusi'])
        self.assertNotIn('key=', pd['pilihan'][2]['url'])
        self.assertTrue(pd['pilihan'][2]['abu'], 'OSM standar dibuat abu-abu')

        param.set_param('satu_data.peta_dasar', 'voyager')
        self.assertEqual(self._dashboard()['peta_dasar']['bawaan'], 'voyager')
        param.set_param('satu_data.peta_dasar', 'tidak-ada')
        self.assertEqual(self._dashboard()['peta_dasar']['bawaan'], 'positron')

        # Server tile sendiri muncul sebagai pilihan pertama dan jadi bawaan.
        param.set_param('satu_data.peta_dasar', False)
        param.set_param('satu_data.url_peta_dasar', 'https://tile.contoh/{z}/{x}/{y}.png')
        pd = self._dashboard()['peta_dasar']
        self.assertEqual(pd['pilihan'][0]['url'], 'https://tile.contoh/{z}/{x}/{y}.png')
        self.assertEqual(pd['bawaan'], 'kustom')

    def test_dashboard_company_lain(self):
        data = self._dashboard(company=self.company_b)
        self.assertEqual(data['kabupaten']['penduduk'], 19998)
        self.assertEqual([w['id'] for w in data['wilayah']], [self.kec_b.id])
        with self.assertRaises(UserError):
            self._dashboard(company=self.company_b, kecamatan_id=self.kec_1.id)

    # ── Hak akses dan record rule ────────────────────────────────────────────

    def test_pengguna_hanya_melihat_company_sendiri(self):
        Pdd = self.env['satu_data.kependudukan'].with_user(self.user_a)
        self.assertNotIn(self.desa_b, Pdd.search([]).desa_id)
        self.assertFalse(self.env['satu_data.kecamatan'].with_user(self.user_a).search(
            [('id', '=', self.kec_b.id)]))
        self._terbitkan_semua()
        data = Pdd.with_company(self.company_a).get_dashboard_peta()
        self.assertEqual(data['kabupaten']['penduduk'], 340)

    def test_pengguna_tidak_bisa_mengubah(self):
        with self.assertRaises(AccessError):
            self.p1.with_user(self.user_a).write({'jumlah_kk': 1})
        with self.assertRaises(AccessError):
            self.kec_1.with_user(self.user_a).write({'name': 'Ganti'})

    # ── Satu Data Indonesia: pemeriksaan Walidata ────────────────────────────

    def test_dashboard_hanya_data_terbit(self):
        data = self._dashboard(terbitkan=False)
        self.assertEqual(data['daftar_periode'], [], 'Belum ada periode terbit')
        self.assertEqual(data['kabupaten']['penduduk'], 0)
        # Hanya 2024 Semester II yang terbit: periode itu jadi bawaan.
        self.env['satu_data.pengajuan'].sd_siapkan(
            'kependudukan', self.periode['2024_2'], self.company_a, self.dukcapil_a
        ).sudo().write({'state': 'terbit'})
        data = self._dashboard(terbitkan=False)
        self.assertEqual([p['id'] for p in data['daftar_periode']], [self.periode['2024_2'].id])
        self.assertEqual(data['kabupaten']['penduduk'], 200)
        # Periode belum terbit yang diminta langsung tetap kosong.
        data = self._dashboard(terbitkan=False, periode_id=self.periode['2025_1'].id)
        self.assertEqual(data['kabupaten']['penduduk'], 0)

    def test_alur_pengajuan(self):
        Pengajuan = self.env['satu_data.pengajuan']
        p = Pengajuan.with_user(self.user_produsen).sd_siapkan(
            'kependudukan', self.periode['2025_1'], self.company_a, self.dukcapil_a)
        self.assertEqual(p.state, 'draf')
        self.assertEqual(p.jumlah_record, 3, 'Hanya data wilayah A')
        self.assertEqual(self.p1.sd_status, 'draf')

        # Status tidak bisa diubah langsung, hanya lewat tombol.
        with self.assertRaises(AccessError):
            p.with_user(self.user_produsen).write({'state': 'terbit'})

        p.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(p.state, 'diajukan')
        self.assertEqual(p.diajukan_oleh, self.user_produsen)
        # Data terkunci selama diperiksa
        with self.assertRaises(UserError):
            self.p1.with_user(self.user_produsen).write({'jumlah_kk': 61})
        desa_baru = self.env['satu_data.desa'].create({
            'kode': 'D9', 'name': 'Desa Baru', 'kecamatan_id': self.kec_1.id,
            'company_id': self.company_a.id})
        with self.assertRaises(UserError):
            self.env['satu_data.kependudukan'].with_user(self.user_produsen).create({
                'desa_id': desa_baru.id, 'periode_id': self.periode['2025_1'].id})
        # Data periode lain tetap bisa diubah
        self.env['satu_data.kependudukan'].with_user(self.user_produsen).create({
            'desa_id': self.desa_2.id, 'periode_id': self.periode['2024_2'].id,
            'jumlah_laki_laki': 1, 'jumlah_perempuan': 1})

        # Produsen tidak bisa menerbitkan sendiri
        with self.assertRaises(AccessError):
            p.with_user(self.user_produsen).action_terbitkan()
        p.with_user(self.user_walidata).action_terbitkan()
        self.assertEqual(p.state, 'terbit')
        self.assertEqual(p.diperiksa_oleh, self.user_walidata)
        self.assertEqual(self.p1.sd_status, 'terbit')

        # Mengembalikan wajib dengan catatan; setelah dikembalikan data bisa diperbaiki.
        with self.assertRaises(UserError):
            p.with_user(self.user_walidata).action_kembalikan()
        with self.assertRaises(AccessError):
            p.with_user(self.user_produsen).write({'catatan': 'catatan produsen'})
        p.with_user(self.user_walidata).write({'catatan': 'Jumlah KK desa 1 perlu dicek.'})
        p.with_user(self.user_walidata).action_kembalikan()
        self.assertEqual(p.state, 'draf')
        self.assertTrue(p.perlu_perbaikan)
        self.p1.with_user(self.user_produsen).write({'jumlah_kk': 61})
        self.assertEqual(self.p1.jumlah_kk, 61)

    def test_laporan_semester(self):
        Wizard = self.env['satu_data.pengajuan.wizard'].with_user(self.user_produsen).with_context(
            default_sektor='kependudukan')
        aksi = Wizard.create({'sektor': 'kependudukan', 'periode_id': self.periode['2024_2'].id,
                              'instansi_id': self.dukcapil_a.id,
                              'company_id': self.company_a.id}).action_buka()
        lap = self.env['satu_data.pengajuan'].browse(aksi['res_id'])
        # Baris lama masuk laporan, desa yang belum ada dibuat kosong.
        self.assertEqual(lap.kependudukan_ids.desa_id, self.desa_1 | self.desa_2 | self.desa_3)
        self.assertEqual((lap.jumlah_record, lap.jumlah_terisi, lap.jumlah_kosong), (3, 1, 2))
        # Isi langsung dari form laporan.
        baris = lap.kependudukan_ids.filtered(lambda r: r.desa_id == self.desa_2)
        lap.with_user(self.user_produsen).write({'kependudukan_ids': [
            (1, baris.id, {'jumlah_laki_laki': 5, 'jumlah_perempuan': 5, 'jumlah_kk': 3})]})
        self.assertEqual((lap.jumlah_terisi, lap.jumlah_kosong), (2, 1))
        # Boleh dikirim walau satu desa kosong; desa kosong tidak tampil di dashboard.
        lap.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(lap.state, 'diajukan')
        lap.with_user(self.user_walidata).action_terbitkan()
        data = self.env['satu_data.kependudukan'].with_company(self.company_a).get_dashboard_peta(
            periode_id=self.periode['2024_2'].id)
        self.assertEqual(data['kabupaten']['jumlah_data'], 2)
        self.assertEqual(data['kabupaten']['penduduk'], 210)
        # Dikembalikan: status Diisi + penanda; kirim ulang menghapus penanda.
        lap.with_user(self.user_walidata).write({'catatan': 'Lengkapi Desa Tiga.'})
        lap.with_user(self.user_walidata).action_kembalikan()
        self.assertEqual((lap.state, lap.perlu_perbaikan), ('draf', True))
        lap.with_user(self.user_produsen).action_ajukan()
        self.assertFalse(lap.perlu_perbaikan)

    def test_pengajuan_tanpa_data_ditolak(self):
        p = self.env['satu_data.pengajuan'].sd_siapkan(
            'kependudukan', self.periode['2026_1'], self.company_a, self.dukcapil_a)
        with self.assertRaises(UserError):
            p.with_user(self.user_produsen).action_ajukan()

    def test_pengguna_tidak_bisa_mengajukan(self):
        p = self.env['satu_data.pengajuan'].sd_siapkan(
            'kependudukan', self.periode['2025_1'], self.company_a, self.dukcapil_a)
        with self.assertRaises(AccessError):
            p.with_user(self.user_a).action_ajukan()

    def test_daftar_data_kependudukan(self):
        data = self.env.ref('satu_data_kependudukan.data_jumlah_penduduk')
        self.assertEqual(data.sektor, 'kependudukan')
        self.assertTrue(data.memenuhi_sdi, data.metadata_kurang)
        self.assertEqual(data.instansi_id, self.env.ref('satu_data_kependudukan.instansi_dukcapil'))
        self.assertEqual(data.urusan_id, self.env.ref('satu_data.urusan_2_12'))

    def test_ketepatan_jadwal_pemutakhiran(self):
        Pengajuan = self.env['satu_data.pengajuan']
        p1 = Pengajuan.sd_siapkan('kependudukan', self.periode['2025_1'], self.company_a,
                                  self.dukcapil_a)
        p2 = Pengajuan.sd_siapkan('kependudukan', self.periode['2024_2'], self.company_a,
                                  self.dukcapil_a)
        akhir1 = self.periode['2025_1'].tanggal_akhir
        akhir2 = self.periode['2024_2'].tanggal_akhir
        # Wilayah A belum punya Daftar Data kependudukan: batas bawaan 30 hari.
        self.assertEqual(p1.batas_pengajuan, fields.Date.add(akhir1, days=30))
        # Jadwal di Daftar Data mengubah batas pengajuan yang belum diajukan.
        data = self.env['satu_data.data'].create({
            'name': 'Uji Penduduk A', 'kode': 'uji.penduduk', 'sektor': 'kependudukan',
            'company_id': self.company_a.id, 'batas_hari': 10})
        self.assertEqual(p1.batas_pengajuan, fields.Date.add(akhir1, days=10))

        with freeze_time(fields.Datetime.to_datetime(fields.Date.add(akhir1, days=15))
                         .replace(hour=5)):
            p1.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(p1.ketepatan, 'terlambat')
        self.assertEqual(p1.hari_terlambat, 5)
        with freeze_time(fields.Datetime.to_datetime(akhir2).replace(hour=5)):
            p2.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(p2.ketepatan, 'tepat')
        self.assertEqual(self.dukcapil_a.jumlah_pengajuan, 2)
        self.assertEqual(self.dukcapil_a.persen_tepat, 50.0)

        # Batas yang sudah dipakai menilai tidak berubah; ditarik lalu diajukan lagi
        # tetap memakai tanggal pengajuan pertama.
        data.batas_hari = 60
        self.assertEqual(p1.batas_pengajuan, fields.Date.add(akhir1, days=10))
        p1.with_user(self.user_produsen).action_tarik()
        p1.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(p1.ketepatan, 'terlambat')
        with self.assertRaises(AccessError):
            p1.with_user(self.user_produsen).write({'tanggal_diajukan_pertama': False})
