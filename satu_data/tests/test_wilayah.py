import json

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import SatuDataCase, kotak


@tagged('post_install', '-at_install', 'satu_data')
class TestWilayah(SatuDataCase):

    # ── Identitas wilayah (company) ───────────────────────────────────────────

    def test_kode_wilayah_format(self):
        with self.assertRaises(ValidationError):
            self.company_a.sd_kode_wilayah = '9801'
        self.company_a.sd_kode_wilayah = '98.09'
        self.assertEqual(self.company_a.sd_kode_wilayah, '98.09')

    def test_kode_wilayah_unik(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.company_b.sd_kode_wilayah = '98.01'
            self.env.flush_all()

    def test_wizard_identitas_hanya_field_sd(self):
        admin_sd = new_test_user(
            self.env, login='sd_admin_b', groups='satu_data.group_satu_data_admin',
            company_id=self.company_b.id, company_ids=[self.company_b.id])
        Wizard = self.env['satu_data.identitas.wizard'].with_user(admin_sd).with_company(self.company_b)
        self.assertEqual(Wizard.action_buka()['res_model'], 'satu_data.identitas.wizard')

        wiz = Wizard.create({})
        self.assertEqual(wiz.company_id, self.company_b)
        self.assertEqual(wiz.name, 'Wilayah Tes B')
        self.assertEqual(wiz.sd_kode_wilayah, '98.02')
        # PNG 1x1 piksel
        logo = (b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAwS2O'
                b'UAAAAABJRU5ErkJggg==')
        wiz.write({'name': ' Kota Tes Baru ', 'logo': logo,
                   'sd_jenis_wilayah': 'kota', 'sd_kode_wilayah': ' 98.05 ',
                   'carto_api_key': ' kunci-carto '})
        wiz.action_simpan()
        self.assertEqual(self.env['ir.config_parameter'].get_param('satu_data.carto_api_key'),
                         'kunci-carto')
        self.assertEqual(Wizard.create({}).carto_api_key, 'kunci-carto')
        self.assertEqual(self.company_b.name, 'Kota Tes Baru')
        self.assertTrue(self.company_b.logo)
        self.assertEqual(self.company_b.sd_jenis_wilayah, 'kota')
        self.assertEqual(self.company_b.sd_kode_wilayah, '98.05')

        # Format tetap divalidasi walau ditulis dengan sudo.
        wiz = Wizard.create({'sd_kode_wilayah': 'salah'})
        with self.assertRaises(ValidationError):
            wiz.action_simpan()

        # Di luar wizard, admin Satu Data tetap tidak bisa menulis ke company.
        with self.assertRaises(AccessError):
            self.company_b.with_user(admin_sd).write({'currency_id': self.env.ref('base.USD').id})

    # ── Kode unik per company ────────────────────────────────────────────────

    def test_kode_kecamatan_unik_per_company(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.env['satu_data.kecamatan'].create({
                'kode': 'K1', 'name': 'Duplikat', 'company_id': self.company_a.id})
        # Kode yang sama di company lain boleh (lihat kec_b di setUpClass).
        self.assertEqual(self.kec_b.kode, self.kec_1.kode)

    def test_kode_desa_unik_per_company(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.env['satu_data.desa'].create({
                'kode': 'D1', 'name': 'Duplikat', 'kecamatan_id': self.kec_2.id,
                'company_id': self.company_a.id})
        self.assertEqual(self.desa_b.kode, self.desa_1.kode)

    def test_desa_harus_satu_company_dengan_kecamatan(self):
        with self.assertRaises(UserError):
            self.env['satu_data.desa'].create({
                'kode': 'DX', 'name': 'Salah Company', 'kecamatan_id': self.kec_1.id,
                'company_id': self.company_b.id})

    def test_jumlah_desa(self):
        self.assertEqual(self.kec_1.jumlah_desa, 2)
        self.assertEqual(self.kec_2.jumlah_desa, 1)

    def test_kecamatan_tidak_bisa_pindah_company_bila_ada_desa(self):
        with self.assertRaises(ValidationError):
            self.kec_2.company_id = self.company_b
        kosong = self.env['satu_data.kecamatan'].create({
            'kode': 'K9', 'name': 'Kosong', 'company_id': self.company_a.id})
        kosong.company_id = self.company_b
        self.assertEqual(kosong.company_id, self.company_b)

    # ── Validasi GeoJSON ─────────────────────────────────────────────────────

    def test_geojson_valid(self):
        multi = {
            'type': 'MultiPolygon',
            'coordinates': [json.loads(kotak(110.2, -7.0))['coordinates'],
                            json.loads(kotak(110.3, -7.0))['coordinates']],
        }
        self.kec_2.geojson = json.dumps(multi)
        feature = {'type': 'Feature', 'properties': {}, 'geometry': json.loads(kotak(110.4, -7.0))}
        self.kec_2.geojson = json.dumps(feature)
        self.assertEqual(self.kec_2._sd_geometri()['type'], 'Polygon')
        self.kec_2.geojson = False
        self.assertIsNone(self.kec_2._sd_geometri())

    def test_geojson_peta_disederhanakan(self):
        # Sisi bawah kotak berisi 100 titik segaris dan koordinat 9 desimal.
        bawah = [[round(110.0 + i * 0.0001, 9) + 1e-9, -7.0] for i in range(100)]
        ring = bawah + [[110.01, -7.0], [110.01, -6.99], [110.0, -6.99], bawah[0]]
        self.desa_3.geojson = json.dumps({'type': 'Polygon', 'coordinates': [ring]})
        geometri = self.desa_3._sd_geometri()
        hasil = geometri['coordinates'][0]
        self.assertEqual(len(hasil), 5, 'Titik segaris dibuang, tinggal 4 sudut + penutup')
        self.assertEqual(hasil[0], hasil[-1])
        self.assertTrue(all(len(str(v).split('.')[-1]) <= 5 for t in hasil for v in t))
        # Teks asli tidak diubah.
        self.assertEqual(len(json.loads(self.desa_3.geojson)['coordinates'][0]), 104)

    def test_geojson_tidak_valid(self):
        salah = [
            '{bukan json',
            '[1, 2, 3]',
            json.dumps({'type': 'Point', 'coordinates': [110.0, -7.0]}),
            json.dumps({'type': 'FeatureCollection', 'features': []}),
            json.dumps({'type': 'Polygon', 'coordinates': []}),
            # Ring kurang dari 4 titik
            json.dumps({'type': 'Polygon', 'coordinates': [[[110, -7], [110.1, -7], [110, -7]]]}),
            # Ring tidak tertutup
            json.dumps({'type': 'Polygon', 'coordinates': [[[110, -7], [110.1, -7], [110.1, -6.9], [110, -6.9]]]}),
            # Urutan terbalik [lintang, bujur] dengan lintang di luar jangkauan
            json.dumps({'type': 'Polygon', 'coordinates': [[[-7, 110], [-7, 110.1], [-6.9, 110.1], [-7, 110]]]}),
            # Koordinat bukan angka
            json.dumps({'type': 'Polygon', 'coordinates': [[['a', 'b'], [1, 1], [2, 2], ['a', 'b']]]}),
        ]
        for teks in salah:
            with self.subTest(geojson=teks), self.assertRaises(ValidationError):
                self.desa_3.geojson = teks

    def test_info_editor_peta(self):
        Kec = self.env['satu_data.kecamatan']
        # Kecamatan bersebelahan dengan kec_1, dan satu yang jauh (kec_2 di 110.1).
        dekat = Kec.create({'kode': 'K3', 'name': 'Kecamatan Dekat',
                            'company_id': self.company_a.id, 'geojson': kotak(110.01, -7.0)})
        info = Kec.sd_info_editor_peta(record_id=self.kec_1.id, company_id=self.company_a.id)
        self.assertEqual([w['nama'] for w in info['pembanding']], [dekat.display_name],
                         'Hanya wilayah di sekitar, tanpa record itu sendiri')
        self.assertIsNone(info['induk'])
        self.assertIn('pilihan', info['peta_dasar'])

        # Record baru tanpa geometri: semua kecamatan company itu.
        info = Kec.sd_info_editor_peta(company_id=self.company_a.id)
        self.assertEqual(len(info['pembanding']), 3)

        # Desa: batas kecamatan induk ikut dikirim sebagai acuan.
        info = self.env['satu_data.desa'].sd_info_editor_peta(
            record_id=self.desa_1.id, company_id=self.company_a.id, kecamatan_id=self.kec_1.id)
        self.assertEqual(info['induk']['type'], 'Polygon')
        self.assertEqual(info['pembanding'], [])
