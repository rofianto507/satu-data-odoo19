{
    'name': 'Satu Data - Kependudukan',
    'version': '19.0.2.2.0',
    'summary': 'Rekap kependudukan per desa/kelurahan dan dashboard peta penduduk',
    'description': """
Satu Data: Kependudukan
=======================

Modul sektor kependudukan untuk Satu Data (modul inti ``satu_data``).

* Rekap per desa/kelurahan per periode: laki-laki, perempuan, jumlah KK.
  Kecamatan dicatat saat data dibuat (snapshot), luas dan kepadatan dari master desa.
* Angka kecamatan dan kabupaten/kota dihitung dari penjumlahan desa.
* Dashboard peta choropleth jumlah penduduk dengan drill down kecamatan ke desa/kelurahan.
* Satu Data Indonesia: Produsen Data = Dispendukcapil; data terdaftar di Daftar Data
  beserta metadatanya; rekap per semester diajukan ke Walidata dan hanya tampil di
  dashboard setelah terbit.

Hanya menyimpan angka rekap per wilayah, tidak menyimpan data per orang.
""",
    'category': 'Productivity',
    'depends': ['satu_data'],
    'data': [
        'security/satu_data_kependudukan_security.xml',
        'security/ir.model.access.csv',
        'data/satu_data_kependudukan_data.xml',
        'views/kependudukan_views.xml',
        'views/periode_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/satu_data_kependudukan_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'satu_data_kependudukan/static/src/xml/grafik_penduduk.xml',
            'satu_data_kependudukan/static/src/js/grafik_penduduk.js',
            'satu_data_kependudukan/static/src/xml/dashboard_peta.xml',
            'satu_data_kependudukan/static/src/js/dashboard_peta.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
