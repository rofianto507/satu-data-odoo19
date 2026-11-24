from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.satu_data.tests.common import SatuDataCase
from odoo.addons.satu_data_kesehatan.models.faskes import titik_tengah


@tagged('post_install', '-at_install', 'satu_data', 'satu_data_kesehatan')
class TestKesehatan(SatuDataCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Faskes = cls.env['satu_data.faskes']
        cls.pkm_1 = Faskes.create({
            'name': 'Puskesmas Desa Satu', 'jenis': 'puskesmas', 'desa_id': cls.desa_1.id,
            'wilayah_kerja_ids': [(6, 0, (cls.desa_1 | cls.desa_2).ids)]})
        cls.pkm_2 = Faskes.create({
            'name': 'Puskesmas Desa Tiga', 'jenis': 'puskesmas', 'desa_id': cls.desa_3.id})
        cls.tahun = cls.env['satu_data.periode'].create({
            'name': 'Uji Tahun 2095', 'frekuensi': 'tahunan',
            'tanggal_mulai': '2095-01-01', 'tanggal_akhir': '2095-12-31'})
        cls.dinkes_a = cls.env['satu_data.instansi'].create({
            'name': 'Dinkes A', 'company_id': cls.company_a.id})
        cls.user_produsen = new_test_user(
            cls.env, login='sd_produsen_kes_a', groups='satu_data_kesehatan.group_produsen_kesehatan',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.user_walidata = new_test_user(
            cls.env, login='sd_walidata_kes_a', groups='satu_data.group_satu_data_walidata',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.user_pengguna = new_test_user(
            cls.env, login='sd_pengguna_kes_a', groups='satu_data.group_satu_data_pengguna',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])

    def _sasaran(self, desa, **vals):
        return self.env['satu_data.kesehatan.sasaran'].create(
            {'desa_id': desa.id, 'periode_id': self.tahun.id, **vals})

    # ── Fasilitas dan wilayah kerja ──────────────────────────────────────────

    def test_puskesmas_desa(self):
        self.assertEqual(self.desa_1.sd_puskesmas_id, self.pkm_1)
        self.assertEqual(self.desa_2.sd_puskesmas_id, self.pkm_1)
        self.assertFalse(self.desa_3.sd_puskesmas_id)
        self.assertEqual(self.pkm_1.jumlah_desa, 2)
        self.assertEqual(self.pkm_1.company_id, self.company_a)
        self.assertEqual(self.pkm_1.kecamatan_id, self.kec_1)
        cari = self.env['satu_data.desa'].search([('sd_puskesmas_id', 'in', self.pkm_1.ids)])
        self.assertEqual(cari, self.desa_1 | self.desa_2)

    def test_wilayah_kerja_satu_puskesmas(self):
        with self.assertRaises(ValidationError):
            self.pkm_2.wilayah_kerja_ids = [(4, self.desa_2.id)]
        # Puskesmas diarsipkan tidak menghalangi.
        self.pkm_1.active = False
        self.pkm_2.wilayah_kerja_ids = [(4, self.desa_2.id)]
        self.assertEqual(self.desa_2.sd_puskesmas_id, self.pkm_2)

    def test_wilayah_kerja_hanya_puskesmas_dan_wilayah_sama(self):
        Faskes = self.env['satu_data.faskes']
        with self.assertRaises(ValidationError):
            Faskes.create({'name': 'RS Uji', 'jenis': 'rumah_sakit', 'desa_id': self.desa_3.id,
                           'wilayah_kerja_ids': [(6, 0, self.desa_3.ids)]})
        with self.assertRaises(ValidationError):
            self.pkm_2.wilayah_kerja_ids = [(4, self.desa_b.id)]
        with self.assertRaises(ValidationError):
            Faskes.create({'name': 'Pustu Uji', 'jenis': 'pustu', 'desa_id': self.desa_3.id,
                           'induk_id': Faskes.create({'name': 'Klinik', 'jenis': 'klinik',
                                                      'desa_id': self.desa_3.id}).id})
        pustu = Faskes.create({'name': 'Pustu Uji', 'jenis': 'pustu', 'desa_id': self.desa_2.id,
                               'induk_id': self.pkm_1.id})
        self.assertEqual(self.pkm_1.pustu_ids, pustu)

    def test_kode_faskes_unik_per_wilayah(self):
        self.pkm_1.kode = 'P001'
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.pkm_2.kode = 'P001'
            self.env.flush_all()

    def test_titik_tengah(self):
        self.assertEqual(titik_tengah(None), None)
        self.assertEqual(titik_tengah('{"type": "Point", "coordinates": [1, 2]}'), None)
        self.pkm_1.action_koordinat_dari_desa()
        self.assertAlmostEqual(self.pkm_1.latitude, -6.9975, places=5)
        self.assertAlmostEqual(self.pkm_1.longitude, 110.0025, places=5)
        pkm_desa_2 = self.env['satu_data.faskes'].create({
            'name': 'Klinik Uji', 'jenis': 'klinik', 'desa_id': self.desa_2.id})
        with self.assertRaises(UserError):
            pkm_desa_2.action_koordinat_dari_desa()     # desa tanpa batas wilayah
        with self.assertRaises(ValidationError):
            self.pkm_1.latitude = 95

    def test_hak_akses_faskes(self):
        with self.assertRaises(AccessError):
            self.env['satu_data.faskes'].with_user(self.user_pengguna).create({
                'name': 'Liar', 'jenis': 'klinik', 'desa_id': self.desa_3.id})
        self.env['satu_data.faskes'].with_user(self.user_produsen).create({
            'name': 'Klinik Produsen', 'jenis': 'klinik', 'desa_id': self.desa_3.id})
        self.assertEqual(self.env['satu_data.faskes'].with_user(self.user_pengguna).search_count(
            [('name', 'in', ['Puskesmas Desa Satu', 'Klinik Produsen'])]), 2)

    def test_desa_tidak_bisa_pindah_wilayah(self):
        # desa_2 masuk wilayah kerja puskesmas wilayah A.
        with self.assertRaises(ValidationError):
            self.desa_2.write({'company_id': self.company_b.id, 'kecamatan_id': self.kec_b.id})
        # Desa tanpa data kesehatan boleh pindah.
        kosong = self.env['satu_data.desa'].create({
            'kode': 'D8', 'name': 'Desa Kosong', 'kecamatan_id': self.kec_1.id,
            'company_id': self.company_a.id})
        kosong.write({'company_id': self.company_b.id, 'kecamatan_id': self.kec_b.id})

    # ── Sasaran ──────────────────────────────────────────────────────────────

    def test_sasaran_snapshot_puskesmas(self):
        s = self._sasaran(self.desa_2, sasaran_ibu_hamil=40, sasaran_balita=200, sasaran_bayi=38)
        self.assertEqual(s.puskesmas_id, self.pkm_1)
        self.assertEqual(s.kecamatan_id, self.kec_1)
        # Wilayah kerja berubah: data yang sudah dicatat tetap di puskesmas lama.
        self.pkm_1.wilayah_kerja_ids = [(3, self.desa_2.id)]
        self.pkm_2.wilayah_kerja_ids = [(4, self.desa_2.id)]
        self.assertEqual(s.puskesmas_id, self.pkm_1)
        # Desa tanpa puskesmas: kosong, bisa diisi manual.
        s3 = self._sasaran(self.desa_3)
        self.assertFalse(s3.puskesmas_id)
        s3.puskesmas_id = self.pkm_2
        with self.assertRaises(ValidationError):
            s3.puskesmas_id = self.env['satu_data.faskes'].create({
                'name': 'Klinik', 'jenis': 'klinik', 'desa_id': self.desa_3.id})

    def test_sasaran_validasi(self):
        with self.assertRaises(ValidationError):
            self._sasaran(self.desa_1, sasaran_balita=-1)
        with self.assertRaises(ValidationError):
            self._sasaran(self.desa_1, sasaran_bayi=50, sasaran_balita=40)
        with self.assertRaises(ValidationError):
            self._sasaran(self.desa_1, sasaran_ibu_hamil=10, sasaran_ibu_bersalin=11)
        self._sasaran(self.desa_1, sasaran_ibu_hamil=10, sasaran_ibu_bersalin=9)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._sasaran(self.desa_1)

    def test_alur_pengajuan_sasaran(self):
        s = self._sasaran(self.desa_1, sasaran_ibu_hamil=10)
        Pengajuan = self.env['satu_data.pengajuan']
        p = Pengajuan.with_user(self.user_produsen).sd_siapkan(
            'kesehatan_sasaran', self.tahun, self.company_a, self.dinkes_a)
        self.assertEqual(p.jumlah_record, 1)
        # Sasaran tahunan: batas 31 hari setelah awal tahun (jadwal bawaan sektor).
        self.assertEqual(p.batas_pengajuan, fields.Date.to_date('2095-02-01'))
        with self.assertRaises(AccessError):
            p.with_user(self.user_pengguna).action_ajukan()
        p.with_user(self.user_produsen).action_ajukan()
        self.assertEqual(p.ketepatan, 'tepat')
        with self.assertRaises(UserError):
            s.with_user(self.user_produsen).sasaran_ibu_hamil = 11
        p.with_user(self.user_walidata).action_terbitkan()
        self.assertEqual(s.sd_status, 'terbit')

    # ── Rekap bulanan ────────────────────────────────────────────────────────

    def _bulan(self, bulan):
        akhir = {1: 31, 2: 28}[bulan]
        return self.env['satu_data.periode'].create({
            'name': f'Uji Rekap {bulan:02d}-2095', 'frekuensi': 'bulanan',
            'tanggal_mulai': f'2095-{bulan:02d}-01', 'tanggal_akhir': f'2095-{bulan:02d}-{akhir}'})

    def test_rekap_snapshot_dan_validasi(self):
        Rekap = self.env['satu_data.kesehatan.rekap']
        jan = self._bulan(1)
        r = Rekap.create({'desa_id': self.desa_1.id, 'periode_id': jan.id,
                          'layanan_ibu_hamil': 5, 'balita_diukur': 50, 'balita_stunting': 7,
                          'kasus_dbd': 2, 'kematian_dbd': 1})
        self.assertEqual((r.puskesmas_id, r.kecamatan_id), (self.pkm_1, self.kec_1))
        self.assertEqual(r.display_name, f'Desa Satu – {jan.name}')
        with self.assertRaises(ValidationError):
            r.balita_stunting = 51
        with self.assertRaises(ValidationError):
            r.kematian_dbd = 3
        with self.assertRaises(ValidationError):
            r.kematian_ibu = -1
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            Rekap.create({'desa_id': self.desa_1.id, 'periode_id': jan.id})

    def _buka_laporan(self, sektor, periode, user=None):
        """Buka laporan lewat wizard seperti petugas (membuat baris semua desa bila baru)."""
        Wizard = self.env['satu_data.pengajuan.wizard']
        if user:
            Wizard = Wizard.with_user(user)
        aksi = Wizard.create({'sektor': sektor, 'periode_id': periode.id,
                              'instansi_id': self.dinkes_a.id,
                              'company_id': self.company_a.id}).action_buka()
        return self.env['satu_data.pengajuan'].browse(aksi['res_id'])

    def test_laporan_bulanan(self):
        jan = self._bulan(1)
        Rekap = self.env['satu_data.kesehatan.rekap']
        lap = self._buka_laporan('kesehatan', jan, self.user_produsen)
        # Baris semua desa wilayah A dibuat kosong; wilayah B tidak ikut.
        self.assertEqual(lap.kesehatan_ids.desa_id, self.desa_1 | self.desa_2 | self.desa_3)
        self.assertEqual((lap.jumlah_record, lap.jumlah_terisi, lap.jumlah_kosong), (3, 0, 3))
        self.assertEqual(lap.kesehatan_ids.filtered(lambda r: r.desa_id == self.desa_1).puskesmas_id,
                         self.pkm_1, 'Puskesmas terisi dari wilayah kerja')
        with self.assertRaises(UserError):
            lap.with_user(self.user_produsen).action_ajukan()       # belum ada yang terisi
        # Membuka lagi tidak menggandakan baris.
        self.assertEqual(self._buka_laporan('kesehatan', jan, self.user_produsen), lap)
        self.assertEqual(Rekap.search_count([('periode_id', '=', jan.id)]), 3)

        # Isi dari form laporan; angka nol yang diketik tetap dianggap terisi.
        baris = {r.desa_id: r for r in lap.kesehatan_ids}
        lap.with_user(self.user_produsen).write({'kesehatan_ids': [
            (1, baris[self.desa_1].id, {'layanan_ibu_hamil': 8, 'kasus_dbd': 2}),
            (1, baris[self.desa_2].id, {'kasus_dbd': 0}),
        ]})
        self.assertEqual((lap.jumlah_terisi, lap.jumlah_kosong), (2, 1))
        self.assertTrue(baris[self.desa_2].terisi)
        self.assertFalse(baris[self.desa_3].terisi)

        # Boleh dikirim walau ada desa kosong; baris kosong tidak ikut ke dashboard.
        lap.with_user(self.user_produsen).action_ajukan()
        lap.with_user(self.user_walidata).action_terbitkan()
        d = self._dash(indikator='kasus_dbd', periode_id=jan.id, mode='bulan')
        self.assertEqual(d['ringkasan']['nilai'], 2)
        self.assertEqual(d['ringkasan']['lapor'], 2)
        # Dikembalikan: kembali ke Diisi dengan penanda; desa kosong bisa dilengkapi.
        lap.with_user(self.user_walidata).write({'catatan': 'Lengkapi Desa Tiga.'})
        lap.with_user(self.user_walidata).action_kembalikan()
        self.assertEqual((lap.state, lap.perlu_perbaikan), ('draf', True))
        baris[self.desa_3].with_user(self.user_produsen).kasus_dbd = 1
        self.assertEqual(lap.jumlah_terisi, 3)
        lap.with_user(self.user_produsen).action_ajukan()
        self.assertFalse(lap.perlu_perbaikan)

    def test_laporan_sasaran_tahunan(self):
        lap = self._buka_laporan('kesehatan_sasaran', self.tahun, self.user_produsen)
        self.assertEqual(lap.sasaran_kesehatan_ids.desa_id, self.desa_1 | self.desa_2 | self.desa_3)
        self.assertEqual((lap.jumlah_terisi, lap.jumlah_kosong), (0, 3))
        baris = lap.sasaran_kesehatan_ids.filtered(lambda r: r.desa_id == self.desa_1)
        lap.with_user(self.user_produsen).write({'sasaran_kesehatan_ids': [
            (1, baris.id, {'sasaran_ibu_hamil': 40, 'sasaran_balita': 300})]})
        self.assertEqual((lap.jumlah_terisi, lap.jumlah_kosong), (1, 2))
        # Sasaran kosong tidak ikut menjadi penyebut dashboard.
        lap.with_user(self.user_produsen).action_ajukan()
        lap.with_user(self.user_walidata).action_terbitkan()
        bulan = self._bulan(1)
        self.env['satu_data.kesehatan.rekap'].create(
            {'desa_id': self.desa_1.id, 'periode_id': bulan.id, 'layanan_ibu_hamil': 10})
        self.env['satu_data.pengajuan'].sd_siapkan(
            'kesehatan', bulan, self.company_a, self.dinkes_a).sudo().write({'state': 'terbit'})
        d = self._dash(indikator='spm_ibu_hamil', periode_id=bulan.id)
        self.assertEqual((d['ringkasan']['pembilang'], d['ringkasan']['penyebut']), (10, 40))

    def test_laporan_menyusul_baris_lama(self):
        """Baris yang dibuat sebelum laporannya ada ikut masuk ke laporan baru."""
        jan = self._bulan(1)
        r = self.env['satu_data.kesehatan.rekap'].create(
            {'desa_id': self.desa_1.id, 'periode_id': jan.id, 'kasus_dbd': 1})
        self.assertFalse(r.pengajuan_id)
        lap = self._buka_laporan('kesehatan', jan)
        self.assertEqual(r.pengajuan_id, lap)
        self.assertEqual(lap.jumlah_terisi, 1)
        # Desa baru muncul belakangan: bisa ditambahkan ke laporan yang masih Diisi.
        desa_baru = self.env['satu_data.desa'].create({
            'kode': 'D7', 'name': 'Desa Baru', 'kecamatan_id': self.kec_1.id,
            'company_id': self.company_a.id})
        lap.with_user(self.user_produsen).action_lengkapi_baris()
        self.assertIn(desa_baru, lap.kesehatan_ids.desa_id)
        lap.with_user(self.user_produsen).action_ajukan()
        with self.assertRaises(UserError):
            lap.with_user(self.user_produsen).kesehatan_ids[:1].kasus_dbd = 9
        with self.assertRaises(AccessError):
            lap.with_user(self.user_pengguna).action_lengkapi_baris()

    def test_aksi_lihat_data_per_puskesmas(self):
        lap = self._buka_laporan('kesehatan', self._bulan(1))
        aksi = lap.action_lihat_data()
        self.assertEqual(aksi['res_model'], 'satu_data.kesehatan.rekap')
        self.assertEqual(aksi['views'][0][0], self.env.ref('satu_data_kesehatan.view_rekap_list_isian').id)
        self.assertEqual(aksi['context']['search_default_group_puskesmas'], 1)
        self.assertEqual(self.env['satu_data.kesehatan.rekap'].search_count(aksi['domain']), 3)

    def test_alur_pengajuan_rekap_bulanan(self):
        jan, feb = self._bulan(1), self._bulan(2)
        Rekap = self.env['satu_data.kesehatan.rekap']
        r = Rekap.create({'desa_id': self.desa_1.id, 'periode_id': jan.id, 'kasus_dbd': 1})
        Rekap.create({'desa_id': self.desa_1.id, 'periode_id': feb.id})
        p = self.env['satu_data.pengajuan'].with_user(self.user_produsen).sd_siapkan(
            'kesehatan', jan, self.company_a, self.dinkes_a)
        # Laporan bulanan: batas tanggal 10 bulan berikutnya.
        self.assertEqual(p.batas_pengajuan, fields.Date.to_date('2095-02-10'))
        self.assertEqual(p.jumlah_record, 1)
        p.with_user(self.user_produsen).action_ajukan()
        with self.assertRaises(UserError):
            r.with_user(self.user_produsen).kasus_dbd = 2
        # Bulan lain tidak ikut terkunci.
        Rekap.search([('periode_id', '=', feb.id)]).with_user(self.user_produsen).kasus_dbd = 3
        p.with_user(self.user_walidata).action_terbitkan()
        self.assertEqual(r.sd_status, 'terbit')
        with self.assertRaises(AccessError):
            Rekap.with_user(self.user_pengguna).create({'desa_id': self.desa_2.id,
                                                        'periode_id': feb.id})

    # ── Indikator dan dashboard ──────────────────────────────────────────────

    def _siapkan_indikator(self):
        """Sasaran 2095 + rekap Januari & Februari 2095, semuanya terbit."""
        jan, feb = self._bulan(1), self._bulan(2)
        self._sasaran(self.desa_1, sasaran_ibu_hamil=100, sasaran_bayi=50, sasaran_balita=400)
        self._sasaran(self.desa_2, sasaran_ibu_hamil=50)
        Rekap = self.env['satu_data.kesehatan.rekap']
        Rekap.create([
            {'desa_id': self.desa_1.id, 'periode_id': jan.id, 'layanan_ibu_hamil': 10,
             'bayi_idl': 5, 'balita_diukur': 100, 'balita_stunting': 20, 'lahir_hidup': 10,
             'kematian_bayi': 1, 'kasus_dbd': 2},
            {'desa_id': self.desa_2.id, 'periode_id': jan.id, 'layanan_ibu_hamil': 5},
            {'desa_id': self.desa_1.id, 'periode_id': feb.id, 'layanan_ibu_hamil': 15},
        ])
        Pengajuan = self.env['satu_data.pengajuan']
        for sektor, periode in (('kesehatan_sasaran', self.tahun), ('kesehatan', jan),
                                ('kesehatan', feb)):
            Pengajuan.sd_siapkan(sektor, periode, self.company_a, self.dinkes_a).sudo().write(
                {'state': 'terbit'})
        return jan, feb

    def _dash(self, user=None, **kw):
        Dash = self.env['satu_data.kesehatan.dashboard']
        if user:
            Dash = Dash.with_user(user)
        return Dash.with_company(self.company_a).get_dashboard_kesehatan(**kw)

    def test_dashboard_indikator(self):
        jan, feb = self._siapkan_indikator()
        d = self._dash()
        self.assertEqual(d['periode']['id'], feb.id, 'Bawaan: bulan terbit terbaru')
        self.assertEqual([p['id'] for p in d['daftar_periode']], [feb.id, jan.id])
        # SPM ibu hamil kumulatif Jan–Feb: (10 + 5 + 15) / (100 + 50) = 20%
        self.assertEqual(d['ringkasan']['nilai'], 20.0)
        self.assertEqual((d['ringkasan']['pembilang'], d['ringkasan']['penyebut']), (30, 150))
        self.assertEqual(d['ringkasan']['lapor'], 1, 'Hanya desa 1 melapor Februari')
        semua = d['semua_indikator']
        self.assertEqual(semua['idl'], 10.0)
        self.assertEqual(semua['stunting'], 20.0, 'Pengukuran terakhir (Januari)')
        self.assertEqual(semua['kematian_bayi'], 1)
        self.assertEqual(semua['akb'], 100.0)
        self.assertEqual(semua['cfr_dbd'], 0.0)
        self.assertIsNone(semua['spm_usia_lanjut'], 'Tanpa sasaran: tidak bisa dihitung')
        # Kelas warna tetap untuk SPM: 20% masuk kelas terendah.
        kec_1 = next(w for w in d['wilayah'] if w['id'] == self.kec_1.id)
        self.assertEqual((kec_1['nilai'], kec_1['kelas']), (20.0, 0))
        kec_2 = next(w for w in d['wilayah'] if w['id'] == self.kec_2.id)
        self.assertIsNone(kec_2['nilai'])
        self.assertEqual(kec_2['kelas'], -1)
        # Tren kumulatif per bulan
        self.assertEqual([t['nilai'] for t in d['tren']], [10.0, 20.0])

        # Bulan yang dipakai menghitung (untuk tombol "Lihat detail data" puskesmas).
        self.assertEqual(set(d['periode_ids']), {jan.id, feb.id})
        self.assertEqual(self._dash(mode='bulan')['periode_ids'], [feb.id])
        # Mode bulan: Februari saja = 15 / 150
        self.assertEqual(self._dash(mode='bulan')['ringkasan']['nilai'], 10.0)
        # Bulan Januari
        self.assertEqual(self._dash(periode_id=jan.id)['ringkasan']['nilai'], 10.0)

        # Level desa
        d = self._dash(kecamatan_id=self.kec_1.id)
        self.assertEqual(d['level'], 'desa')
        nilai = {w['id']: w['nilai'] for w in d['wilayah']}
        self.assertEqual(nilai, {self.desa_1.id: 25.0, self.desa_2.id: 10.0})
        desa_1 = next(w for w in d['wilayah'] if w['id'] == self.desa_1.id)
        self.assertEqual(desa_1['puskesmas'], 'Puskesmas Desa Satu')

    def test_dashboard_hanya_data_terbit(self):
        jan, feb = self._siapkan_indikator()
        maret = self.env['satu_data.periode'].create({
            'name': 'Uji Rekap 03-2095', 'frekuensi': 'bulanan',
            'tanggal_mulai': '2095-03-01', 'tanggal_akhir': '2095-03-31'})
        self.env['satu_data.kesehatan.rekap'].create({
            'desa_id': self.desa_1.id, 'periode_id': maret.id, 'layanan_ibu_hamil': 99})
        d = self._dash()
        self.assertEqual(d['periode']['id'], feb.id, 'Maret belum terbit')
        with self.assertRaises(UserError):
            self._dash(periode_id=maret.id)
        # Wilayah lain tidak melihat data wilayah A.
        kosong = self.env['satu_data.kesehatan.dashboard'].with_company(
            self.company_b).get_dashboard_kesehatan()
        self.assertFalse(kosong['periode']['id'])
        self.assertIsNone(kosong['ringkasan']['nilai'])

    def test_dashboard_data_terbatas(self):
        self._siapkan_indikator()
        d = self._dash(user=self.user_pengguna, indikator='kematian_bayi', kecamatan_id=self.kec_1.id)
        self.assertTrue(d['tersembunyi'])
        self.assertTrue(all(w['nilai'] is None for w in d['wilayah']))
        self.assertEqual(d['ringkasan']['nilai'], 1, 'Total kecamatan tetap tampil')
        d = self._dash(user=self.user_produsen, indikator='kematian_bayi', kecamatan_id=self.kec_1.id)
        self.assertFalse(d['tersembunyi'])
        # Indikator terbuka tetap dirinci untuk pengguna biasa.
        self.assertFalse(self._dash(user=self.user_pengguna, kecamatan_id=self.kec_1.id)['tersembunyi'])
        with self.assertRaises(UserError):
            self._dash(indikator='tidak_ada')

    def test_dashboard_puskesmas(self):
        self._siapkan_indikator()
        self.assertFalse(self._dash()['puskesmas'], 'Puskesmas tanpa koordinat tidak ditampilkan')
        self.pkm_1.action_koordinat_dari_desa()
        titik = self._dash()['puskesmas']
        self.assertEqual(len(titik), 1)
        self.assertEqual(titik[0]['nilai'], 20.0, 'Gabungan desa wilayah kerja: 30 / 150')
        self.assertEqual(titik[0]['jumlah_desa'], 2)
        self.assertFalse(self._dash(kecamatan_id=self.kec_2.id)['puskesmas'])

    def test_kelas_indikator(self):
        from odoo.addons.satu_data_kesehatan.models.indikator import INDIKATOR_BY_KODE
        Dash = self.env['satu_data.kesehatan.dashboard']
        kelas = Dash._sd_kelas_indikator(INDIKATOR_BY_KODE['spm_balita'], [])
        self.assertEqual([k['label'] for k in kelas],
                         ['< 25,0', '25,0 – < 50,0', '50,0 – < 75,0', '75,0 – < 100,0', '≥ 100,0'])
        self.assertEqual(Dash._sd_kelas_index(100, kelas), 4)
        self.assertEqual(Dash._sd_kelas_index(24.9, kelas), 0)
        # Tanpa batas tetap: kuantil, warna "turun" (makin tinggi makin merah)
        kelas = Dash._sd_kelas_indikator(INDIKATOR_BY_KODE['akb'], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(kelas[0]['warna'], '#ffffb2')
        self.assertEqual(Dash._sd_kelas_index(10, kelas), 4)
        self.assertEqual(Dash._sd_kelas_index(1, kelas), 0)
        # Nilai sedikit: interval sama
        kelas = Dash._sd_kelas_indikator(INDIKATOR_BY_KODE['kasus_dbd'], [0, 5])
        self.assertEqual(kelas[0]['atas'], 1)

    def test_daftar_data_indikator(self):
        Data = self.env['satu_data.data']
        indikator = Data.search([('sektor', '=', 'kesehatan')])
        self.assertEqual(len(indikator), 21)
        self.assertTrue(all(indikator.mapped('memenuhi_sdi')), indikator.mapped('metadata_kurang'))
        aki = self.env.ref('satu_data_kesehatan.data_aki')
        self.assertEqual((aki.akses, aki.tingkat_penyajian, aki.prioritas),
                         ('terbatas', 'kecamatan', True))

    def test_demo_tidak_menimpa(self):
        from odoo.addons.satu_data_kesehatan.models.demo import _poisson
        import random
        rng = random.Random(1)
        self.assertEqual(_poisson(rng, 0), 0)
        sampel = [_poisson(rng, 3) for _ in range(2000)]
        self.assertAlmostEqual(sum(sampel) / len(sampel), 3, delta=0.2)
        self.assertGreater(_poisson(rng, 1000), 800)
        main = self.env.ref('base.main_company')
        Rekap = self.env['satu_data.kesehatan.rekap']
        if not Rekap.search_count([('company_id', '=', main.id)], limit=1):
            desa = self.env['satu_data.desa'].search([('company_id', '=', main.id)], limit=1)
            if not desa:
                return
            Rekap.create({'desa_id': desa.id, 'periode_id': self._bulan(1).id})
        jumlah = Rekap.search_count([])
        self.assertFalse(self.env['satu_data.kesehatan.demo']._sd_demo_kesehatan())
        self.assertEqual(Rekap.search_count([]), jumlah)

    def test_daftar_data_kesehatan(self):
        data = self.env.ref('satu_data_kesehatan.data_sasaran_ibu_hamil')
        self.assertTrue(data.memenuhi_sdi, data.metadata_kurang)
        self.assertEqual(data.urusan_id, self.env.ref('satu_data.urusan_1_02'))
        self.assertEqual(data.acuan_batas, 'awal')
        odgj = self.env.ref('satu_data_kesehatan.data_sasaran_odgj_berat')
        self.assertEqual((odgj.akses, odgj.tingkat_penyajian), ('terbatas', 'kecamatan'))
        self.assertEqual(self.env['satu_data.data'].search_count(
            [('sektor', '=', 'kesehatan_sasaran')]), 13)
