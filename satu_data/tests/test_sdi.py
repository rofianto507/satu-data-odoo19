from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import SatuDataCase


@tagged('post_install', '-at_install', 'satu_data')
class TestSatuDataIndonesia(SatuDataCase):
    """Fondasi Satu Data Indonesia: frekuensi periode, Daftar Data, instansi."""

    def test_periode_bulanan_boleh_di_dalam_semester(self):
        Periode = self.env['satu_data.periode']
        # "Uji 2095 Semester I" (semesteran) sudah ada; bulan di dalamnya boleh dibuat.
        jan = Periode.create({'name': 'Uji Januari 2095', 'frekuensi': 'bulanan',
                              'tanggal_mulai': '2095-01-01', 'tanggal_akhir': '2095-01-31'})
        self.assertEqual(jan.tahun, 2095)
        with self.assertRaises(ValidationError, msg='Bulanan bertumpuk dengan bulanan'):
            Periode.create({'name': 'Uji Jan bis 2095', 'frekuensi': 'bulanan',
                            'tanggal_mulai': '2095-01-15', 'tanggal_akhir': '2095-02-14'})

    def test_buat_periode_baku(self):
        Periode = self.env['satu_data.periode']
        baru = Periode.sd_buat_periode_baku(2097, 'bulanan')
        self.assertEqual(len(baru), 12)
        self.assertEqual(baru.sorted('tanggal_mulai')[1].name, 'Februari 2097')
        self.assertEqual(str(baru.sorted('tanggal_mulai')[1].tanggal_akhir), '2097-02-28')
        self.assertFalse(Periode.sd_buat_periode_baku(2097, 'bulanan'), 'Tidak dobel')

        tw = Periode.sd_buat_periode_baku(2097, 'triwulanan')
        self.assertEqual(sorted(tw.mapped('name'))[0], '2097 Triwulan I')
        self.assertEqual(str(tw.sorted('tanggal_mulai')[-1].tanggal_akhir), '2097-12-31')
        # "Uji 2096 Semester I" sudah ada: hanya Semester II yang dibuat.
        sem = Periode.sd_buat_periode_baku(2096, 'semesteran')
        self.assertEqual(sem.mapped('name'), ['2096 Semester II'])
        self.assertEqual(Periode.sd_buat_periode_baku(2097, 'tahunan').name, 'Tahun 2097')

    def test_metadata_daftar_data(self):
        Data = self.env['satu_data.data']
        d = Data.create({'name': 'Uji Data', 'kode': 'uji.data', 'company_id': self.company_a.id})
        self.assertFalse(d.memenuhi_sdi)
        self.assertIn('Definisi', d.metadata_kurang)
        instansi = self.env['satu_data.instansi'].create({
            'name': 'Dinas Uji', 'company_id': self.company_a.id})
        d.write({
            'instansi_id': instansi.id,
            'urusan_id': self.env.ref('satu_data.urusan_1_02').id,
            'topik_id': self.env.ref('satu_data.topik_kesehatan').id,
            'definisi': 'Definisi uji', 'metode': 'Rumus uji', 'ukuran': 'Jumlah',
            'satuan': 'Orang', 'klasifikasi_penyajian': 'Kecamatan', 'frekuensi': 'tahunan',
            'kode_referensi': 'Kode wilayah Kemendagri',
        })
        self.assertTrue(d.memenuhi_sdi)
        self.assertFalse(d.metadata_kurang)
        self.assertEqual(instansi.jumlah_data, 1)

    def test_satu_walidata_per_wilayah(self):
        Instansi = self.env['satu_data.instansi']
        Instansi.create({'name': 'Kominfo A', 'peran': 'walidata', 'company_id': self.company_a.id})
        with self.assertRaises(ValidationError):
            Instansi.create({'name': 'Kominfo A2', 'peran': 'walidata',
                             'company_id': self.company_a.id})
        # Wilayah lain boleh punya Walidata sendiri.
        Instansi.create({'name': 'Kominfo B', 'peran': 'walidata', 'company_id': self.company_b.id})

    def test_topik_data_go_id(self):
        self.assertEqual(self.env.ref('satu_data.topik_kesehatan').name,
                         'Perlindungan Sosial dan Kesehatan')
        self.assertEqual(self.env.ref('satu_data.instansi_walidata').peran, 'walidata')
        self.assertEqual(self.env.ref('satu_data.instansi_sekretariat').peran, 'sekretariat')

    def test_satu_sekretariat_per_wilayah(self):
        Instansi = self.env['satu_data.instansi']
        Instansi.create({'name': 'Bappeda A', 'peran': 'sekretariat', 'company_id': self.company_a.id})
        with self.assertRaises(ValidationError):
            Instansi.create({'name': 'Bappeda A2', 'peran': 'sekretariat',
                             'company_id': self.company_a.id})
        # Walidata Pendukung boleh lebih dari satu.
        Instansi.create({'name': 'Pendukung 1', 'peran': 'walidata_pendukung',
                         'company_id': self.company_a.id})
        Instansi.create({'name': 'Pendukung 2', 'peran': 'walidata_pendukung',
                         'company_id': self.company_a.id})

    def test_urusan_dari_instansi(self):
        kesehatan = self.env.ref('satu_data.urusan_1_02')
        self.assertEqual(kesehatan.display_name, '1.02 Kesehatan')
        self.assertIn(kesehatan, self.env['satu_data.urusan'].search(
            [('display_name', 'ilike', '1.02')]))
        sebelum = kesehatan.jumlah_data     # modul sektor kesehatan bisa sudah menambah data
        dinkes = self.env['satu_data.instansi'].create({
            'name': 'Dinkes Uji', 'company_id': self.company_a.id, 'urusan_ids': [(6, 0, kesehatan.ids)]})
        d = self.env['satu_data.data'].create({'name': 'Uji Urusan', 'kode': 'uji.urusan',
                                               'company_id': self.company_a.id,
                                               'instansi_id': dinkes.id, 'frekuensi': 'bulanan',
                                               'batas_hari': 10})
        self.assertEqual(d.urusan_id, kesehatan, 'Instansi dengan satu urusan mengisi urusan data')
        kesehatan.invalidate_recordset(['jumlah_data'])
        self.assertEqual(kesehatan.jumlah_data, sebelum + 1)
        self.assertIn('10 hari setelah periode berakhir', d.jadwal_pemutakhiran)
        d.acuan_batas = 'awal'
        self.assertIn('setelah periode dimulai', d.jadwal_pemutakhiran)
        with self.assertRaises(ValidationError):
            d.batas_hari = -1

    def test_forum_satu_data(self):
        Data = self.env['satu_data.data']
        d1 = Data.create({'name': 'Uji F1', 'kode': 'uji.f1', 'company_id': self.company_a.id})
        d2 = Data.create({'name': 'Uji F2', 'kode': 'uji.f2', 'company_id': self.company_a.id,
                          'prioritas': True})
        self.assertEqual(d1.status_daftar, 'usulan')
        forum = self.env['satu_data.forum'].create({
            'tahun': 2095, 'company_id': self.company_a.id})
        with self.assertRaises(UserError):
            forum.action_tetapkan()     # belum ada data
        forum.data_ids = d1 | d2
        self.assertEqual((forum.jumlah_data, forum.jumlah_prioritas), (2, 1))
        pengguna = new_test_user(self.env, login='sd_pengguna_forum',
                                 groups='satu_data.group_satu_data_pengguna',
                                 company_id=self.company_a.id, company_ids=[self.company_a.id])
        with self.assertRaises(AccessError):
            forum.with_user(pengguna).action_tetapkan()
        forum.action_tetapkan()
        self.assertEqual(forum.state, 'ditetapkan')
        self.assertEqual(set((d1 | d2).mapped('status_daftar')), {'disepakati'})
        self.assertEqual(d1.tahun_daftar, 2095)
        d1.action_hentikan()
        self.assertEqual(d1.status_daftar, 'dihentikan')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['satu_data.forum'].create({'tahun': 2095, 'company_id': self.company_a.id})
