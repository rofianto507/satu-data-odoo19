"""Tes keamanan portal publik: formulir permintaan, kunci API, dan penyalahgunaan umum."""
import re
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.satu_data_portal.controllers import batas
from odoo.addons.satu_data_portal.controllers.unduhan import aman_csv

from .test_portal import PortalBase

API = '/api/satu-data/v1'
MODUL_FORM = 'odoo.addons.satu_data_portal.controllers.permintaan'
SKRIP = '<script>alert(1)</script>'


@tagged('post_install', '-at_install', 'satu_data', 'satu_data_portal', 'satu_data_keamanan')
class TestKeamanan(PortalBase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.walidata_a = new_test_user(
            cls.env, login='sd_walidata_portal_a', groups='satu_data.group_satu_data_walidata',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.portal_user = new_test_user(
            cls.env, login='sd_portal_pengguna', groups='base.group_portal',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])

    def setUp(self):
        super().setUp()
        batas._jendela.clear()
        self.addCleanup(batas._jendela.clear)
        # Formulir yang diuji dikirim seketika: matikan batas waktu minimum (diuji terpisah).
        for nama, nilai in (('MIN_DETIK', 0), ('BATAS_KIRIM', 1000)):
            patcher = patch(f'{MODUL_FORM}.{nama}', nilai)
            patcher.start()
            self.addCleanup(patcher.stop)

    # ── Bantu ────────────────────────────────────────────────────────────────

    def _form(self):
        res = self.url_open('/permintaan')
        token = re.search(r'name="csrf_token" value="([^"]+)"', res.text).group(1)
        dibuka = re.search(r'name="dibuka" value="([^"]+)"', res.text).group(1)
        return token, dibuka

    def _isian(self, **ubah):
        data = {
            'jenis': 'data', 'pemohon_jenis': 'akademisi', 'nama_pemohon': 'Budi Santoso',
            'email': 'budi@example.org', 'organisasi': 'Universitas Uji',
            'uraian': 'Data stunting per kecamatan tahun 2025 lengkap.',
            'tujuan': 'Penelitian skripsi tentang stunting.', 'setuju': '1',
        }
        data.update(ubah)
        return data

    def _kirim(self, token=None, dibuka=None, tanpa_csrf=False, **ubah):
        if token is None:
            token, dibuka_asli = self._form()
            dibuka = dibuka_asli if dibuka is None else dibuka
        data = self._isian(**ubah)
        data['dibuka'] = dibuka
        if not tanpa_csrf:
            data['csrf_token'] = token
        return self.url_open('/permintaan', data=data, allow_redirects=False)

    def _jumlah(self):
        return self.env['satu_data.permintaan'].sudo().search_count([])

    def _kunci_baru(self, **kw):
        rec = self.env['satu_data.api.key'].create(dict({
            'name': 'Aplikasi Uji', 'company_id': self.company_a.id}, **kw))
        pesan = rec.action_buat_kunci()['params']['message']
        return rec, re.search(r'sdk_[A-Za-z0-9_\-]+', pesan).group(0)

    # ── Formulir permintaan ──────────────────────────────────────────────────

    def test_form_terbuka(self):
        res = self.url_open('/permintaan')
        self.assertEqual(res.status_code, 200)
        self.assertIn('name="csrf_token"', res.text)
        self.assertIn('name="situs_web"', res.text, 'Kolom jebakan ada')
        for kolom in ('jenis', 'pemohon_jenis', 'nama_pemohon', 'email', 'telepon', 'organisasi',
                      'uraian', 'tujuan', 'setuju'):
            self.assertIn(f'id="{kolom}"', res.text, f'Kolom {kolom} tampil di formulir')

    def test_tanpa_csrf_ditolak(self):
        sebelum = self._jumlah()
        res = self._kirim(tanpa_csrf=True)
        self.assertEqual(res.status_code, 400)
        res = self._kirim(token='bukan-token-sah')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._jumlah(), sebelum)

    def test_kirim_berhasil_dan_status(self):
        res = self._kirim()
        self.assertEqual(res.status_code, 303)
        rec = self.env['satu_data.permintaan'].sudo().search([], limit=1)
        self.assertTrue(rec.name.startswith('PD/'))
        self.assertEqual((rec.state, rec.company_id, rec.email), ('baru', self.company_a, 'budi@example.org'))
        self.assertEqual(res.headers['Location'].rsplit('/', 1)[-1], rec.token)
        self.assertGreaterEqual(len(rec.token), 30, 'Token acak, bukan urutan')

        res = self.url_open(f'/permintaan/{rec.token}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(rec.name, res.text)
        self.assertIn('Baru', res.text)
        for rahasia in ('budi@example.org', 'Budi Santoso', 'Universitas Uji'):
            self.assertNotIn(rahasia, res.text, 'Data kontak pemohon tidak tampil di halaman status')
        self.assertEqual(res.headers['Cache-Control'], 'no-store')
        self.assertIn('noindex', res.headers['X-Robots-Tag'])
        self.assertEqual(res.headers['Referrer-Policy'], 'no-referrer')

    def test_data_terkait_hanya_data_publik(self):
        self._kirim(data='kependudukan.jumlah_penduduk')
        rec = self.env['satu_data.permintaan'].sudo().search([], limit=1)
        self.assertEqual(rec.data_id, self.d_penduduk)
        self._kirim(data='kependudukan.jumlah_kk')   # akses terbatas: diabaikan
        rec = self.env['satu_data.permintaan'].sudo().search([], order='id desc', limit=1)
        self.assertFalse(rec.data_id)

    def test_xss_di_escape(self):
        self._kirim(uraian=f'{SKRIP} data penduduk lengkap')
        rec = self.env['satu_data.permintaan'].sudo().search([], limit=1)
        res = self.url_open(f'/permintaan/{rec.token}')
        self.assertNotIn(SKRIP, res.text)
        self.assertIn('&lt;script&gt;', res.text)
        # Isian yang dikembalikan ke formulir saat ada galat juga di-escape.
        res = self._kirim(nama_pemohon='"><img src=x onerror=alert(1)>', email='salah')
        self.assertEqual(res.status_code, 400)
        self.assertNotIn('<img src=x onerror', res.text)

    def test_kolom_jebakan(self):
        sebelum = self._jumlah()
        res = self._kirim(situs_web='http://spam.example')
        self.assertEqual(res.status_code, 200, 'Robot dijawab seolah berhasil')
        self.assertIn('Terima kasih', res.text)
        self.assertEqual(self._jumlah(), sebelum, 'Tetapi tidak disimpan')

    def test_terlalu_cepat_dan_tanda_waktu(self):
        sebelum = self._jumlah()
        with patch(f'{MODUL_FORM}.MIN_DETIK', 3):
            res = self._kirim()
            self.assertEqual(res.status_code, 400)
            self.assertIn('terlalu cepat', res.text)
        res = self._kirim(dibuka='abc')
        self.assertEqual(res.status_code, 400)
        _token, dibuka = self._form()
        ts, tanda = dibuka.split('.')
        res = self._kirim(dibuka=f'{int(ts) - 100}.{tanda}')   # waktu diubah, tanda tangan lama
        self.assertEqual(res.status_code, 400)
        self.assertIn('tidak valid', res.text)
        with patch(f'{MODUL_FORM}.MAKS_UMUR_DETIK', -1):
            res = self._kirim()
            self.assertEqual(res.status_code, 400)
            self.assertIn('kedaluwarsa', res.text)
        self.assertEqual(self._jumlah(), sebelum)

    def test_validasi_isian(self):
        sebelum = self._jumlah()
        kasus = (
            ({'email': 'bukan-email'}, 'email yang valid'),
            ({'email': 'a@b'}, 'email yang valid'),
            ({'uraian': 'pendek'}, 'minimal'),
            ({'tujuan': ''}, 'tujuan penggunaan'),
            ({'nama_pemohon': 'x'}, 'nama'),
            ({'nama_pemohon': 'a' * 101}, 'Maksimal 100'),
            ({'uraian': 'a' * 2001}, 'Maksimal 2000'),
            ({'telepon': 'abc'}, 'telepon'),
            ({'jenis': 'sembarang'}, 'jenis permintaan'),
            ({'pemohon_jenis': 'sembarang'}, 'jenis pemohon'),
            ({'setuju': ''}, 'persetujuan'),
        )
        for ubah, pesan in kasus:
            res = self._kirim(**ubah)
            self.assertEqual(res.status_code, 400, ubah)
            self.assertIn(pesan.lower(), res.text.lower(), ubah)
        self.assertEqual(self._jumlah(), sebelum)

    def test_karakter_kontrol_dibuang(self):
        self._kirim(nama_pemohon='Bu\x00di\x07 Uji', uraian='Baris satu\r\nbaris dua cukup panjang')
        rec = self.env['satu_data.permintaan'].sudo().search([], limit=1)
        self.assertEqual(rec.nama_pemohon, 'Budi Uji')
        self.assertEqual(rec.uraian, 'Baris satu\nbaris dua cukup panjang')

    def test_batas_kiriman_per_ip(self):
        with patch(f'{MODUL_FORM}.BATAS_KIRIM', 2):
            self.assertEqual(self._kirim().status_code, 303)
            self.assertEqual(self._kirim().status_code, 303)
            res = self._kirim()
            self.assertEqual(res.status_code, 429)
            self.assertTrue(res.headers.get('Retry-After'))

    def test_token_status_tidak_dapat_ditebak(self):
        self._kirim()
        for token in ('a' * 30, 'x', 'a' * 200, 'sdk_abc', 'a%2fb', '%5c..%5cwindows', 'a b', '%3Cscript%3E'):
            res = self.url_open(f'/permintaan/{token}')
            self.assertEqual(res.status_code, 404, token)
        # Permintaan wilayah lain tidak terbuka lewat website wilayah ini.
        lain = self.env['satu_data.permintaan'].sudo().create({
            'company_id': self.company_b.id, 'nama_pemohon': 'Pemohon B', 'email': 'b@example.org',
            'uraian': 'Data wilayah lain cukup panjang.', 'tujuan': 'Tujuan wilayah lain cukup.'})
        self.assertEqual(self.url_open(f'/permintaan/{lain.token}').status_code, 404)

    def test_tanggapan_walidata_tampil_di_status(self):
        self._kirim()
        rec = self.env['satu_data.permintaan'].sudo().search([], limit=1)
        with self.assertRaises(ValidationError):
            rec.with_user(self.walidata_a).action_selesai()   # tanggapan wajib
        rec.tanggapan = f'Data tersedia di katalog. {SKRIP}'
        rec.with_user(self.walidata_a).action_selesai()
        self.assertEqual(rec.state, 'selesai')
        res = self.url_open(f'/permintaan/{rec.token}')
        self.assertIn('Data tersedia di katalog', res.text)
        self.assertNotIn(SKRIP, res.text)
        self.assertIn('Selesai', res.text)

    # ── Hak akses model ──────────────────────────────────────────────────────

    def test_akses_model_publik_dan_portal(self):
        self._kirim()
        publik = self.env.ref('base.public_user')
        for model in ('satu_data.permintaan', 'satu_data.api.key'):
            for pengguna in (publik, self.portal_user):
                with self.assertRaises(AccessError, msg=f'{model} {pengguna.login}'):
                    self.env[model].with_user(pengguna).search([])

    def test_walidata_hanya_wilayahnya_dan_token_tersembunyi(self):
        self._kirim()
        lain = self.env['satu_data.permintaan'].sudo().create({
            'company_id': self.company_b.id, 'nama_pemohon': 'Pemohon B', 'email': 'b@example.org',
            'uraian': 'Data wilayah lain cukup panjang.', 'tujuan': 'Tujuan wilayah lain cukup.'})
        Perm = self.env['satu_data.permintaan'].with_user(self.walidata_a)
        daftar = Perm.search([])
        self.assertTrue(daftar)
        self.assertNotIn(lain, daftar, 'Record rule wilayah')
        with self.assertRaises(AccessError):
            daftar[0].token   # noqa: B018 - token hanya untuk sistem
        kunci_b = self.env['satu_data.api.key'].create({'name': 'Kunci B', 'company_id': self.company_b.id})
        self.assertNotIn(kunci_b, self.env['satu_data.api.key'].with_user(self.walidata_a).search([]))

    # ── Kunci API ────────────────────────────────────────────────────────────

    def test_kunci_hanya_hash_tersimpan(self):
        rec, kunci = self._kunci_baru()
        self.assertTrue(kunci.startswith('sdk_'))
        self.assertEqual(rec.prefix, kunci[:12])
        hash_tersimpan = rec.sudo().key_hash
        self.assertNotEqual(hash_tersimpan, kunci)
        self.assertEqual(len(hash_tersimpan), 64)
        with self.assertRaises(AccessError):
            rec.with_user(self.walidata_a).key_hash   # noqa: B018 - hash hanya untuk sistem
        self.env.cr.execute('SELECT 1 FROM satu_data_api_key WHERE key_hash = %s OR prefix = %s',
                            (kunci, kunci))
        self.assertFalse(self.env.cr.fetchone(), 'Kunci lengkap tidak ada di database')

    def test_api_dengan_kunci(self):
        rec, kunci = self._kunci_baru()
        for header in ({'X-API-Key': kunci}, {'Authorization': f'Bearer {kunci}'}):
            res = self.url_open(f'{API}/data', headers=header)
            self.assertEqual(res.status_code, 200, header)
        rec.invalidate_recordset()
        self.assertEqual(rec.jumlah_panggilan, 2)
        self.assertTrue(rec.terakhir_dipakai)
        self.assertIn('X-API-Key', res.headers['Vary'])
        self.assertEqual(res.headers['X-Content-Type-Options'], 'nosniff')

    def test_api_kunci_tidak_sah_ditolak(self):
        rec, kunci = self._kunci_baru()
        kasus = ['sdk_' + 'a' * 40, 'bukan-kunci', 'sdk_', kunci[:-1] + ('a' if kunci[-1] != 'a' else 'b'),
                 "sdk_' OR 1=1 --", 'sdk_' + 'a' * 500]
        for salah in kasus:
            res = self.url_open(f'{API}/data', headers={'X-API-Key': salah})
            self.assertEqual(res.status_code, 401, salah[:30])
            self.assertIn('Bearer', res.headers['WWW-Authenticate'])
        rec.active = False
        self.assertEqual(self.url_open(f'{API}/data', headers={'X-API-Key': kunci}).status_code, 401,
                         'Kunci nonaktif')
        rec.active = True
        self.assertEqual(self.url_open(f'{API}/data', headers={'X-API-Key': kunci}).status_code, 200)
        # Kunci milik wilayah lain tidak berlaku di website wilayah ini.
        _rec_b, kunci_b = self._kunci_baru(company_id=self.company_b.id)
        self.assertEqual(self.url_open(f'{API}/data', headers={'X-API-Key': kunci_b}).status_code, 401)

    def test_putar_kunci_mematikan_yang_lama(self):
        rec, lama = self._kunci_baru()
        pesan = rec.action_buat_kunci()['params']['message']
        baru = re.search(r'sdk_[A-Za-z0-9_\-]+', pesan).group(0)
        self.assertNotEqual(lama, baru)
        self.assertEqual(self.url_open(f'{API}/data', headers={'X-API-Key': lama}).status_code, 401)
        self.assertEqual(self.url_open(f'{API}/data', headers={'X-API-Key': baru}).status_code, 200)

    def test_batas_kunci_terpisah_dari_batas_ip(self):
        rec, kunci = self._kunci_baru(batas_per_menit=10)
        kunci_hdr = {'X-API-Key': kunci}
        # Waktu dibekukan agar semua permintaan jatuh di menit yang sama.
        with freeze_time('2026-11-25 10:00:30'), patch.object(batas, 'BATAS_PER_MENIT', 2):
            for _ in range(5):   # jauh di atas batas IP, tetapi kunci punya bucket sendiri
                self.assertEqual(self.url_open(f'{API}/data', headers=kunci_hdr).status_code, 200)
            self.assertEqual(self.url_open(f'{API}/data').status_code, 200)
            self.assertEqual(self.url_open(f'{API}/data').status_code, 200)
            self.assertEqual(self.url_open(f'{API}/data').status_code, 429, 'Tanpa kunci tetap dibatasi')
            for _ in range(5):   # genap 10 panggilan berkunci: masih diizinkan
                self.assertEqual(self.url_open(f'{API}/data', headers=kunci_hdr).status_code, 200)
            res = self.url_open(f'{API}/data', headers=kunci_hdr)
            self.assertEqual(res.status_code, 429, 'Batas milik kunci terlampaui')
            self.assertTrue(res.headers.get('Retry-After'))

    def test_batas_per_menit_kunci_wajar(self):
        for nilai in (0, 5, 6001):
            with self.assertRaises(ValidationError):
                self.env['satu_data.api.key'].create({
                    'name': 'X', 'company_id': self.company_a.id, 'batas_per_menit': nilai})

    def test_kunci_tidak_membuka_data_terbatas(self):
        _rec, kunci = self._kunci_baru()
        res = self.url_open(f'{API}/data/kependudukan.jumlah_kk', headers={'X-API-Key': kunci})
        self.assertEqual(res.status_code, 404)

    # ── Penyalahgunaan umum ──────────────────────────────────────────────────

    def test_csv_injeksi_rumus(self):
        for nilai in ('=1+1', '+cmd', '-2+3', '@SUM(A1)', '\tx'):
            self.assertTrue(aman_csv(nilai).startswith("'"), nilai)
        self.assertEqual(aman_csv('Jember'), 'Jember')
        self.assertEqual(aman_csv(-5.0), -5.0, 'Angka negatif tidak diubah')
        self.kec_1.name = '=HYPERLINK("http://jahat.example")'
        res = self.url_open('/data/kependudukan.jumlah_penduduk/unduh/csv')
        self.assertEqual(res.status_code, 200)
        self.assertIn("'=HYPERLINK", res.content.decode('utf-8-sig'))
        self.assertEqual(res.headers['X-Content-Type-Options'], 'nosniff')

    def test_pencarian_dan_kode_berbahaya(self):
        for q in ("'; DROP TABLE satu_data_data; --", '%25%27%22\\', '<script>alert(1)</script>', 'a' * 5000):
            res = self.url_open(f'/data?q={q}')
            self.assertEqual(res.status_code, 200, q[:30])
            self.assertNotIn(SKRIP, res.text)
        for kode in ('x%2fy', '%5c..%5cwindows', "x'%20OR%201=1--", 'a' * 500, '%3Cscript%3E'):
            self.assertEqual(self.url_open(f'/data/{kode}').status_code, 404, kode)
            self.assertEqual(self.url_open(f'/data/{kode}/unduh/csv').status_code, 404, kode)
            self.assertEqual(self.url_open(f'{API}/data/{kode}').status_code, 404, kode)
        self.assertTrue(self._kode_publik(), 'Tabel data tetap utuh')

    def test_pengumuman_portal_di_escape(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'satu_data_portal.pengumuman', 'Data contoh <b>uji coba</b>')
        res = self.url_open('/data')
        self.assertIn('Data contoh &lt;b&gt;uji coba&lt;/b&gt;', res.text)
        self.env['ir.config_parameter'].sudo().set_param('satu_data_portal.pengumuman', '')
        self.assertNotIn('sd-pengumuman"', self.url_open('/data').text)
