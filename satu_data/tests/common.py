import json

from odoo.tests.common import TransactionCase


def kotak(bujur, lintang, sisi=0.01):
    """GeoJSON Polygon persegi sederhana untuk tes."""
    return json.dumps({
        'type': 'Polygon',
        'coordinates': [[
            [bujur, lintang],
            [bujur + sisi, lintang],
            [bujur + sisi, lintang + sisi],
            [bujur, lintang + sisi],
            [bujur, lintang],
        ]],
    })


class SatuDataCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({
            'name': 'Wilayah Tes A', 'sd_jenis_wilayah': 'kota', 'sd_kode_wilayah': '98.01',
        })
        cls.company_b = cls.env['res.company'].create({
            'name': 'Wilayah Tes B', 'sd_jenis_wilayah': 'kabupaten', 'sd_kode_wilayah': '98.02',
        })
        Kec = cls.env['satu_data.kecamatan']
        Desa = cls.env['satu_data.desa']
        cls.kec_1 = Kec.create({'kode': 'K1', 'name': 'Kecamatan Satu',
                                'company_id': cls.company_a.id, 'geojson': kotak(110.0, -7.0)})
        cls.kec_2 = Kec.create({'kode': 'K2', 'name': 'Kecamatan Dua',
                                'company_id': cls.company_a.id, 'geojson': kotak(110.1, -7.0)})
        cls.desa_1 = Desa.create({'kode': 'D1', 'name': 'Desa Satu', 'jenis': 'desa',
                                  'kecamatan_id': cls.kec_1.id, 'company_id': cls.company_a.id,
                                  'geojson': kotak(110.0, -7.0, 0.005), 'luas_km2': 2.0})
        # Tanpa luas dan tanpa batas wilayah
        cls.desa_2 = Desa.create({'kode': 'D2', 'name': 'Kelurahan Dua', 'jenis': 'kelurahan',
                                  'kecamatan_id': cls.kec_1.id, 'company_id': cls.company_a.id})
        cls.desa_3 = Desa.create({'kode': 'D3', 'name': 'Desa Tiga', 'jenis': 'desa',
                                  'kecamatan_id': cls.kec_2.id, 'company_id': cls.company_a.id,
                                  'luas_km2': 1.0})
        # Periode uji, kunci "<tahun>_<semester>". Tanggal digeser +70 tahun agar tidak
        # bertumpuk dengan periode yang sudah ada di database (mis. data demo).
        cls.periode = {}
        for tahun, semester in ((2023, 1), (2024, 2), (2025, 1), (2026, 1)):
            t = tahun + 70
            mulai, akhir = (f'{t}-01-01', f'{t}-06-30') if semester == 1 else \
                (f'{t}-07-01', f'{t}-12-31')
            cls.periode[f'{tahun}_{semester}'] = cls.env['satu_data.periode'].create({
                'name': f'Uji {t} Semester {"I" * semester}',
                'tanggal_mulai': mulai, 'tanggal_akhir': akhir,
            })
        # Wilayah B dengan kode yang sama dengan wilayah A (boleh: unik per company).
        cls.kec_b = Kec.create({'kode': 'K1', 'name': 'Kecamatan B',
                                'company_id': cls.company_b.id})
        cls.desa_b = Desa.create({'kode': 'D1', 'name': 'Desa B', 'jenis': 'desa',
                                  'kecamatan_id': cls.kec_b.id, 'company_id': cls.company_b.id})
