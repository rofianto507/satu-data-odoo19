import csv
import io
import json
import unittest
from unittest.mock import patch

import openpyxl

from odoo.tests import HttpCase, tagged

from odoo.addons.satu_data.tests.common import SatuDataCase
from odoo.addons.satu_data_portal.controllers import batas
from odoo.addons.satu_data_portal.models.daftar_data import desimal_dari, format_angka
from odoo.addons.satu_data_portal.models.dasbor import kelas_warna, sederhanakan_geometri

API = '/api/satu-data/v1'


@tagged('post_install', '-at_install', 'satu_data', 'satu_data_portal')
class TestPortal(SatuDataCase, HttpCase):
    """Portal publik memakai data kependudukan sebagai contoh sektor.

    Wilayah A: Kecamatan Satu (Desa Satu 2 km², Kelurahan Dua tanpa luas) dan Kecamatan Dua
    (Desa Tiga 1 km²). Periode uji bergeser +70 tahun (lihat ``SatuDataCase``).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'satu_data.kependudukan' not in cls.env:
            raise unittest.SkipTest('Tes portal memakai modul satu_data_kependudukan.')
        Pdd = cls.env['satu_data.kependudukan']
        baru, lama = cls.periode['2025_1'], cls.periode['2024_2']
        for desa, periode, laki, perempuan, kk in (
                (cls.desa_1, baru, 100, 120, 60),
                (cls.desa_2, baru, 50, 50, 30),
                (cls.desa_3, baru, 10, 10, 5),
                (cls.desa_1, lama, 90, 110, 55),
                (cls.desa_b, baru, 9999, 9999, 1)):
            Pdd.create({'desa_id': desa.id, 'periode_id': periode.id, 'jumlah_laki_laki': laki,
                        'jumlah_perempuan': perempuan, 'jumlah_kk': kk})

        Instansi = cls.env['satu_data.instansi']
        cls.dukcapil_a = Instansi.create({'name': 'Dinas Kependudukan Uji A', 'singkatan': 'DukcapilA',
                                          'company_id': cls.company_a.id})
        cls.dukcapil_b = Instansi.create({'name': 'Dinas Kependudukan Uji B',
                                          'company_id': cls.company_b.id})
        Pengajuan = cls.env['satu_data.pengajuan']
        cls.laporan = Pengajuan
        for company, instansi in ((cls.company_a, cls.dukcapil_a), (cls.company_b, cls.dukcapil_b)):
            for periode in (baru, lama):
                lap = Pengajuan.sd_siapkan('kependudukan', periode, company, instansi)
                lap.sudo().write({'state': 'terbit'})
                cls.laporan |= lap

        Data = cls.env['satu_data.data']
        cls.topik = cls.env['satu_data.topik'].create({'name': 'Topik Uji Portal', 'ikon': 'fa-users'})

        def data(kode, nama, company=None, instansi=None, **kw):
            return Data.create(dict({
                'kode': kode, 'name': nama, 'sektor': 'kependudukan', 'frekuensi': 'semesteran',
                'company_id': (company or cls.company_a).id,
                'instansi_id': (instansi or cls.dukcapil_a).id,
                'definisi': f'Definisi {nama}.', 'satuan': 'Jiwa', 'topik_id': cls.topik.id,
            }, **kw))

        cls.d_penduduk = data('kependudukan.jumlah_penduduk', 'Penduduk Uji Portal')
        cls.d_kepadatan = data('kependudukan.kepadatan', 'Kepadatan Uji Portal',
                               satuan='Jiwa/km²')
        cls.d_perempuan = data('kependudukan.jumlah_perempuan', 'Perempuan Uji Portal',
                               tingkat_penyajian='kabupaten')
        cls.d_kk = data('kependudukan.jumlah_kk', 'KK Terbatas Uji Portal', akses='terbatas')
        cls.d_laki = data('kependudukan.jumlah_laki_laki', 'Laki-laki Dihentikan Uji Portal',
                          status_daftar='dihentikan')
        cls.d_b = data('kependudukan.jumlah_penduduk', 'Penduduk Wilayah B Uji Portal',
                       company=cls.company_b, instansi=cls.dukcapil_b)

        # Website khusus wilayah A untuk permintaan HTTP di tes ini.
        cls.website_a = cls.env['website'].create({
            'name': 'Satu Data Uji A', 'company_id': cls.company_a.id, 'domain': cls.base_url(),
        })

    def setUp(self):
        super().setUp()
        # Pembatas permintaan per IP disimpan di memori: mulai bersih di tiap tes.
        batas._hitungan.clear()
        self.addCleanup(batas._hitungan.clear)

    def _kode_publik(self, company=None, **kw):
        hasil, _faset = self.env['satu_data.data']._sd_cari_publik(company or self.company_a, **kw)
        return {d.kode for d, _info in hasil if d.name.endswith('Uji Portal')}

    # ── Nilai dari modul sektor ──────────────────────────────────────────────

    def test_nilai_jumlah_field(self):
        nilai = self.d_penduduk._sd_nilai_publik(self.periode['2025_1'])
        self.assertEqual(nilai, {self.kec_1.id: 320, self.kec_2.id: 20, False: 340})
        nilai = self.d_penduduk._sd_nilai_publik(self.periode['2024_2'])
        self.assertEqual(nilai, {self.kec_1.id: 200, False: 200}, 'Kecamatan tanpa data tidak dimuat')

    def test_nilai_kepadatan_hanya_bila_luas_lengkap(self):
        nilai = self.d_kepadatan._sd_nilai_publik(self.periode['2025_1'])
        self.assertIsNone(nilai[self.kec_1.id], 'Kelurahan Dua tanpa luas: tidak dihitung')
        self.assertEqual(nilai[self.kec_2.id], 20.0)
        self.assertIsNone(nilai[False])

    def test_nilai_belum_terbit_kosong(self):
        self.laporan.filtered(lambda l: l.company_id == self.company_a).sudo().write(
            {'state': 'draf'})
        self.assertEqual(self.d_penduduk._sd_periode_publik(), self.env['satu_data.periode'])
        self.assertEqual(self._kode_publik(), set())

    # ── Katalog ──────────────────────────────────────────────────────────────

    def test_katalog_hanya_data_publik(self):
        self.assertEqual(self._kode_publik(), {
            'kependudukan.jumlah_penduduk', 'kependudukan.kepadatan',
            'kependudukan.jumlah_perempuan'},
            'Akses terbatas dan data dihentikan tidak tampil')
        self.assertEqual(self._kode_publik(company=self.company_b), {'kependudukan.jumlah_penduduk'})
        hasil, _f = self.env['satu_data.data']._sd_cari_publik(self.company_b)
        self.assertNotIn(self.d_penduduk, [d for d, _i in hasil], 'Data wilayah lain tidak tercampur')

    def test_katalog_cari_dan_saring(self):
        self.assertEqual(self._kode_publik(cari='kepadatan'), {'kependudukan.kepadatan'})
        self.assertEqual(self._kode_publik(cari='Dinas Kependudukan Uji A'), {
            'kependudukan.jumlah_penduduk', 'kependudukan.kepadatan',
            'kependudukan.jumlah_perempuan'})
        self.assertEqual(self._kode_publik(instansi=self.dukcapil_b.id), set())
        self.assertEqual(len(self._kode_publik(tahun=2094)), 3)
        self.assertEqual(self._kode_publik(tahun=2093), set())
        _hasil, faset = self.env['satu_data.data']._sd_cari_publik(self.company_a, cari='Uji Portal')
        self.assertEqual(faset['tahun'][2095], 3)
        self.assertEqual(faset['instansi'][self.dukcapil_a], 3)

    def test_katalog_urutan_abjad(self):
        hasil, _f = self.env['satu_data.data']._sd_cari_publik(
            self.company_a, cari='Uji Portal', urut='abjad')
        nama = [d.name for d, _i in hasil]
        self.assertEqual(nama, sorted(nama, key=str.lower))

    # ── Tabel dan grafik ─────────────────────────────────────────────────────

    def test_tabel_per_kecamatan(self):
        tabel = self.d_penduduk._sd_tabel_publik()
        self.assertEqual([p['id'] for p in tabel['periode']],
                         [self.periode['2024_2'].id, self.periode['2025_1'].id], 'Terlama dulu')
        total, *kecamatan = tabel['baris']
        self.assertTrue(total['total'])
        self.assertEqual(total['nama'], 'Kota Wilayah Tes A')
        self.assertEqual(total['nilai'], [200, 340])
        per_kec = {b['id']: b for b in kecamatan}
        self.assertEqual(set(per_kec), {self.kec_1.id, self.kec_2.id},
                         'Hanya kecamatan; desa tidak pernah dirinci di portal')
        self.assertEqual(per_kec[self.kec_2.id]['nilai'], [None, 20])
        self.assertEqual(per_kec[self.kec_2.id]['teks'], ['–', '20'])
        self.assertFalse(tabel['daftar_tahun'], 'Semesteran: semua periode dalam satu tabel')

    def test_tabel_tingkat_kabupaten(self):
        tabel = self.d_perempuan._sd_tabel_publik()
        self.assertFalse(tabel['rinci'])
        self.assertEqual(len(tabel['baris']), 1)
        self.assertEqual(tabel['baris'][0]['nilai'], [110, 180])
        self.assertEqual(self.d_perempuan._sd_grafik_publik(tabel)['kecamatan'], [])

    def test_grafik_kecamatan_periode_terakhir(self):
        grafik = self.d_penduduk._sd_grafik_publik(self.d_penduduk._sd_tabel_publik())
        self.assertEqual(grafik['total'], [200, 340])
        self.assertEqual(grafik['periode_kecamatan'], self.periode['2025_1'].name)
        self.assertEqual([k['nilai'] for k in grafik['kecamatan']], [320, 20], 'Terbesar dulu')

    def test_format_angka(self):
        self.assertEqual(format_angka(1234567.5, 1), '1.234.567,5')
        self.assertEqual(format_angka(None), '–')
        self.assertEqual(format_angka(0), '0')
        self.assertEqual(desimal_dari([1.0, 2.25, 3]), 2)
        self.assertEqual(desimal_dari([10, 20.0]), 0)

    # ── Halaman (tanpa login) ────────────────────────────────────────────────

    def test_http_katalog(self):
        res = self.url_open('/data')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Penduduk Uji Portal', res.text)
        self.assertNotIn('KK Terbatas Uji Portal', res.text)
        self.assertNotIn('Laki-laki Dihentikan Uji Portal', res.text)
        self.assertNotIn('Penduduk Wilayah B Uji Portal', res.text)
        res = self.url_open('/data?q=kepadatan&tahun=bukan-angka&instansi=-3&urut=aneh')
        self.assertEqual(res.status_code, 200, 'Parameter asal-asalan diabaikan')
        self.assertIn('Kepadatan Uji Portal', res.text)
        self.assertNotIn('Perempuan Uji Portal', res.text)

    def test_http_halaman_data(self):
        res = self.url_open('/data/kependudukan.jumlah_penduduk')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Kecamatan Satu', res.text)
        self.assertIn('340', res.text)
        self.assertIn('Dinas Kependudukan Uji A', res.text)
        for nama_desa in ('Desa Satu', 'Kelurahan Dua', 'Desa Tiga'):
            self.assertNotIn(nama_desa, res.text, 'Desa tidak tampil di portal')

    def test_http_data_tertutup_404(self):
        for kode in ('kependudukan.jumlah_kk', 'kependudukan.jumlah_laki_laki', 'tidak.ada'):
            res = self.url_open(f'/data/{kode}')
            self.assertEqual(res.status_code, 404, kode)
            res = self.url_open(f'/data/{kode}/unduh/csv')
            self.assertEqual(res.status_code, 404, kode)
            res = self.url_open(f'{API}/data/{kode}')
            self.assertEqual(res.status_code, 404, kode)
            self.assertEqual(res.json()['error']['code'], 404)

    # ── Format panjang dan unduhan ───────────────────────────────────────────

    def test_baris_publik(self):
        baris = self.d_penduduk._sd_baris_publik()
        self.assertEqual([(b['tahun'], b['kode_wilayah'], b['nilai']) for b in baris], [
            (2094, '98.01', 200), (2094, 'K1', 200),
            (2095, '98.01', 340), (2095, 'K1', 320), (2095, 'K2', 20),
        ], 'Kab/kota lalu kecamatan per periode; wilayah tanpa data tidak dimuat')
        self.assertEqual(baris[0]['tingkat_wilayah'], 'kabupaten_kota')
        self.assertEqual(baris[0]['tanggal_mulai'], '2094-07-01')
        kab_saja = self.d_perempuan._sd_baris_publik()
        self.assertEqual({b['tingkat_wilayah'] for b in kab_saja}, {'kabupaten_kota'})

    def test_unduh_csv(self):
        res = self.url_open('/data/kependudukan.jumlah_penduduk/unduh/csv')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res.headers['Content-Type'])
        self.assertIn('kependudukan.jumlah_penduduk.csv', res.headers['Content-Disposition'])
        baris = list(csv.DictReader(io.StringIO(res.content.decode('utf-8-sig'))))
        self.assertEqual(len(baris), 5)
        self.assertEqual(baris[-1]['nama_wilayah'], 'Kecamatan Dua')
        self.assertEqual(baris[-1]['nilai'], '20')
        # Kepadatan: nilai yang tidak dapat dihitung ditulis kosong.
        res = self.url_open('/data/kependudukan.kepadatan/unduh/csv')
        kepadatan = list(csv.DictReader(io.StringIO(res.content.decode('utf-8-sig'))))
        self.assertIn('', [b['nilai'] for b in kepadatan])
        self.assertIn('20.0', [b['nilai'] for b in kepadatan], 'Titik desimal untuk mesin')

    def test_unduh_json(self):
        res = self.url_open('/data/kependudukan.jumlah_penduduk/unduh/json')
        self.assertEqual(res.status_code, 200)
        isi = res.json()
        self.assertEqual(isi['metadata']['kode'], 'kependudukan.jumlah_penduduk')
        self.assertEqual(isi['metadata']['produsen_data'], 'Dinas Kependudukan Uji A')
        self.assertEqual(isi['metadata']['tahun_tersedia'], [2094, 2095])
        self.assertEqual(len(isi['data']), 5)

    def test_unduh_xlsx(self):
        res = self.url_open('/data/kependudukan.jumlah_penduduk/unduh/xlsx')
        self.assertEqual(res.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(res.content), read_only=True)
        self.assertEqual(wb.sheetnames, ['Tabel', 'Data', 'Metadata'])
        tabel = list(wb['Tabel'].iter_rows(min_row=4, values_only=True))
        self.assertEqual(tabel[0], ('Wilayah', self.periode['2024_2'].name, self.periode['2025_1'].name))
        self.assertEqual(tabel[1], ('Kota Wilayah Tes A', 200, 340))
        self.assertEqual(len(list(wb['Data'].iter_rows(values_only=True))), 6, 'Kepala + 5 baris')
        metadata = dict(r for r in wb['Metadata'].iter_rows(min_row=2, values_only=True))
        self.assertEqual(metadata['Produsen Data'], 'Dinas Kependudukan Uji A')

    def test_unduh_format_tidak_dikenal(self):
        res = self.url_open('/data/kependudukan.jumlah_penduduk/unduh/pdf')
        self.assertEqual(res.status_code, 404)

    # ── API ──────────────────────────────────────────────────────────────────

    def test_api_daftar_data(self):
        res = self.url_open(f'{API}/data?urut=abjad&per_halaman=2')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), '*')
        isi = res.json()
        self.assertEqual(isi['total'], 3, 'Hanya data publik wilayah website ini')
        self.assertEqual([d['nama'] for d in isi['data']],
                         ['Kepadatan Uji Portal', 'Penduduk Uji Portal'])
        self.assertTrue(isi['data'][0]['url_nilai'].endswith(
            f'{API}/data/kependudukan.kepadatan/nilai'))
        isi = self.url_open(f'{API}/data?per_halaman=2&halaman=2').json()
        self.assertEqual(len(isi['data']), 1)
        isi = self.url_open(f'{API}/data?q=kepadatan&per_halaman=999').json()
        self.assertEqual((isi['total'], isi['per_halaman']), (1, 100))

    def test_api_metadata(self):
        isi = self.url_open(f'{API}/data/kependudukan.jumlah_penduduk').json()
        self.assertEqual(isi['metadata']['nama'], 'Penduduk Uji Portal')
        self.assertEqual([p['tahun'] for p in isi['periode']], [2094, 2095])
        self.assertTrue(isi['unduhan']['xlsx'].endswith('/data/kependudukan.jumlah_penduduk/unduh/xlsx'))

    def test_api_nilai(self):
        isi = self.url_open(f'{API}/data/kependudukan.jumlah_penduduk/nilai').json()
        self.assertEqual(isi['jumlah'], 5)
        isi = self.url_open(f'{API}/data/kependudukan.jumlah_penduduk/nilai?tahun=2095').json()
        self.assertEqual([b['kode_wilayah'] for b in isi['data']], ['98.01', 'K1', 'K2'])
        isi = self.url_open(f'{API}/data/kependudukan.jumlah_penduduk/nilai?wilayah=K1').json()
        self.assertEqual([b['nilai'] for b in isi['data']], [200, 320])
        for b in isi['data']:
            self.assertNotIn('desa', json.dumps(b).lower(), 'Tidak ada rincian desa')

    def test_api_referensi_dan_wilayah(self):
        isi = self.url_open(f'{API}/wilayah').json()
        self.assertEqual(isi['kabupaten_kota'], {'kode': '98.01', 'nama': 'Kota Wilayah Tes A'})
        self.assertEqual([k['kode'] for k in isi['kecamatan']], ['K1', 'K2'])
        isi = self.url_open(f'{API}/referensi').json()
        self.assertEqual(isi['instansi'], [{'id': self.dukcapil_a.id,
                                            'nama': 'Dinas Kependudukan Uji A', 'jumlah_data': 3}])
        self.assertEqual(isi['tahun'], [2095, 2094])

    def test_api_batas_permintaan(self):
        with patch.object(batas, 'BATAS_PER_MENIT', 2):
            self.assertEqual(self.url_open(f'{API}/wilayah').status_code, 200)
            self.assertEqual(self.url_open(f'{API}/wilayah').status_code, 200)
            res = self.url_open(f'{API}/wilayah')
            self.assertEqual(res.status_code, 429)
            self.assertTrue(res.headers.get('Retry-After'))
            res = self.url_open('/data/kependudukan.jumlah_penduduk/unduh/csv')
            self.assertEqual(res.status_code, 429, 'Unduhan ikut dibatasi')

    def test_http_dokumentasi_api(self):
        res = self.url_open('/data/api')
        self.assertEqual(res.status_code, 200)
        self.assertIn(f'{API}/data/kependudukan.', res.text)

    # ── Statistik dan cache ──────────────────────────────────────────────────

    def test_statistik_kunjungan_dan_unduhan(self):
        Statistik = self.env['satu_data.portal.statistik']
        self.url_open('/data/kependudukan.kepadatan')
        self.url_open('/data/kependudukan.kepadatan')
        self.url_open('/data/kependudukan.kepadatan', headers={'User-Agent': 'Googlebot/2.1'})
        self.url_open('/data/kependudukan.kepadatan/unduh/csv')
        self.url_open(f'{API}/data/kependudukan.kepadatan/nilai')
        self.assertEqual(Statistik._sd_jumlah(self.d_kepadatan), {'kunjungan': 2, 'unduhan': 1},
                         'Perayap dan API tidak dihitung')
        self.assertEqual(Statistik._sd_jumlah(self.d_penduduk), {'kunjungan': 0, 'unduhan': 0})
        hasil, _f = self.env['satu_data.data']._sd_cari_publik(self.company_a, urut='populer')
        self.assertEqual(hasil[0][0], self.d_kepadatan)
        res = self.url_open('/data?urut=populer')
        self.assertLess(res.text.index('Kepadatan Uji Portal'), res.text.index('Penduduk Uji Portal'))

    def test_cache_dibersihkan_saat_wilayah_berubah(self):
        kec_1 = lambda: next(b for b in self.d_kepadatan._sd_tabel_publik()['baris']
                             if b['id'] == self.kec_1.id)['nilai'][-1]
        self.assertIsNone(kec_1(), 'Kelurahan Dua belum punya luas')
        self.desa_2.luas_km2 = 1.0
        self.env['satu_data.kependudukan'].flush_model()
        self.assertEqual(kec_1(), 106.7, '320 jiwa / 3 km² setelah luas diisi')

    # ── Dashboard tematik ────────────────────────────────────────────────────

    def test_kelas_warna(self):
        tetap = kelas_warna([10, 90], 'naik', [25, 50, 75, 100])
        self.assertEqual([(k['bawah'], k['atas']) for k in tetap],
                         [(None, 25), (25, 50), (50, 75), (75, 100), (100, None)])
        self.assertEqual(tetap[0]['warna'], '#d7191c', 'Arah naik: nilai rendah merah')
        kuantil = kelas_warna([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 'netral')
        self.assertEqual([k['atas'] for k in kuantil], [2, 4, 6, 8, None])
        sedikit = kelas_warna([None, 50], False)
        self.assertEqual([k['atas'] for k in sedikit], [10, 20, 30, 40, None],
                         'Nilai terlalu sedikit: interval sama sampai nilai terbesar')

    def test_sederhanakan_geometri(self):
        # Persegi dengan titik-titik segaris di tiap sisi: cukup 5 titik (4 sudut + penutup).
        sisi = [[110 + i * 0.001, -7.0] for i in range(11)]
        cincin = (sisi + [[110.01, -7 + i * 0.001] for i in range(1, 11)]
                  + [[110.01 - i * 0.001, -6.99] for i in range(1, 11)]
                  + [[110.0, -6.99 - i * 0.001] for i in range(1, 11)])
        hasil = sederhanakan_geometri({'type': 'Polygon', 'coordinates': [cincin]})
        self.assertEqual(len(hasil['coordinates'][0]), 5)
        self.assertEqual(hasil['coordinates'][0][0], hasil['coordinates'][0][-1])
        self.assertIsNone(sederhanakan_geometri(None))

    def test_dasbor_publik(self):
        isi = self.d_penduduk._sd_dasbor_publik()
        self.assertEqual(isi['periode'], [self.periode['2024_2'].name, self.periode['2025_1'].name])
        self.assertEqual(isi['total']['nilai'], [200, 340])
        self.assertEqual(isi['wilayah'][str(self.kec_2.id)]['nilai'], [None, 20])
        self.assertEqual(isi['arah'], 'netral')
        self.assertEqual(len(isi['kelas']), 2, 'Kelas warna per periode')
        kab = self.d_perempuan._sd_dasbor_publik()
        self.assertFalse(kab['rinci'])
        self.assertEqual(kab['wilayah'], {}, 'Tingkat kab/kota: tidak ada nilai kecamatan')

    def test_peta_publik_dan_cache(self):
        Kec = self.env['satu_data.kecamatan']
        peta = Kec._sd_peta_publik(self.company_a.id)
        self.assertEqual({f['properties']['kode'] for f in peta['features']}, {'K1', 'K2'})
        self.kec_2.name = 'Kecamatan Dua Baru'
        peta = Kec._sd_peta_publik(self.company_a.id)
        self.assertIn('Kecamatan Dua Baru', [f['properties']['nama'] for f in peta['features']],
                      'Cache dibersihkan saat kecamatan berubah')

    def test_tema_publik(self):
        tema = self.env['satu_data.data']._sd_tema_publik(self.company_a)
        self.assertEqual([(t['topik'], t['jumlah'], t['jumlah_peta']) for t in tema],
                         [(self.topik, 3, 2)], 'Data tingkat kab/kota tidak dihitung di peta')

    def test_http_beranda_dashboard_tentang(self):
        res = self.url_open('/beranda')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Satu Data Kota Wilayah Tes A', res.text)
        self.assertIn('Penduduk Uji Portal', res.text)
        self.assertIn(f'/dashboard/{self.topik.id}', res.text)
        self.assertIn('Katalog Data', res.text, 'Footer portal')
        self.assertIn('>Masuk<', res.text)
        self.assertNotIn('>Sign in<', res.text)

        res = self.url_open('/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Topik Uji Portal', res.text)

        res = self.url_open(f'/dashboard/{self.topik.id}?data=kependudukan.kepadatan')
        self.assertEqual(res.status_code, 200)
        self.assertIn('data-kode="kependudukan.kepadatan"', res.text)
        self.assertNotIn('KK Terbatas Uji Portal', res.text)
        res = self.url_open(f'/dashboard/{self.topik.id}?data=kependudukan.jumlah_kk')
        self.assertIn('data-kode="kependudukan.kepadatan"', res.text,
                      'Data terbatas tidak bisa dipilih; kembali ke indikator pertama (abjad)')
        self.assertEqual(self.url_open('/dashboard/999999').status_code, 404)

        res = self.url_open('/dashboard/peta.json')
        self.assertEqual(len(res.json()['features']), 2)
        res = self.url_open('/dashboard/data/kependudukan.jumlah_penduduk.json')
        self.assertEqual(res.json()['total']['nilai'], [200, 340])
        self.assertEqual(self.url_open('/dashboard/data/kependudukan.jumlah_kk.json').status_code, 404)

        res = self.url_open('/tentang')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Dinas Kependudukan Uji A', res.text)
        self.assertIn('Prinsip Satu Data', res.text)

    def test_website_nama_wilayah(self):
        self.assertEqual(self.website_a.sd_nama_wilayah(), 'Kota Wilayah Tes A')
        self.assertFalse(self.website_a.sd_instansi('walidata'))
        self.assertEqual(self.website_a.sd_instansi('produsen'), self.dukcapil_a)

    def test_cache_dipakai(self):
        periode = self.periode['2025_1']
        self.d_penduduk._sd_nilai_publik_cache(periode)
        with patch.object(type(self.d_penduduk), '_sd_nilai_publik',
                          side_effect=AssertionError('tidak boleh menghitung ulang')):
            self.assertEqual(self.d_penduduk._sd_nilai_publik_cache(periode)[False], 340)
