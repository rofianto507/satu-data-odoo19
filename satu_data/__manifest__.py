{
    'name': 'Satu Data',
    'version': '19.0.3.5.0',
    'summary': 'Inti Satu Data: wilayah kabupaten/kota, kecamatan, desa, periode, dan peta',
    'description': """
Satu Data
=========

Modul inti portal data wilayah untuk satu kabupaten/kota. Wilayah ditentukan oleh
company: nama company menjadi nama wilayah, logo company menjadi logo wilayah.

Fitur inti
----------
* Identitas wilayah: jenis (kabupaten/kota) dan kode wilayah Kemendagri pada company.
* Master kecamatan dan desa/kelurahan beserta batas wilayah (GeoJSON) dan editor peta.
* Master periode data (nama, tanggal mulai, tanggal akhir), misalnya "2026 Semester I".
* Penyelenggaraan Satu Data Indonesia (Perpres 39/2019): Instansi (Produsen Data,
  Walidata, Walidata Pendukung, Sekretariat Satu Data, Pembina Data), Daftar Data
  dengan metadata/standar data (selaras isian data.go.id), urusan pemerintahan,
  Metadata Kegiatan, topik data.go.id, dan Pemeriksaan data (Produsen mengajukan,
  Walidata menerbitkan/mengembalikan; dashboard hanya data terbit).
* Forum Satu Data: kesepakatan Daftar Data tahunan, data prioritas, jadwal
  pemutakhiran; ketepatan waktu pengajuan sebagai penilaian kinerja Produsen Data.
* Grup: Pengguna Data, Produsen Data, Walidata, Admin, Pembina Data; pembatasan per company.
* Perkakas peta bersama (``satu_data.peta.mixin``, komponen Leaflet ``SatuDataPeta``):
  kelas warna choropleth, pilihan peta dasar, info wilayah induk.

Data sektoral dipasang sebagai modul terpisah yang bergantung pada modul ini,
misalnya ``satu_data_kependudukan``.

Hanya menyimpan angka rekap per wilayah, tidak menyimpan data per orang.
""",
    'category': 'Productivity',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/satu_data_security.xml',
        'security/ir.model.access.csv',
        'data/satu_data_urusan_data.xml',
        'data/satu_data_data.xml',
        'views/res_company_views.xml',
        'views/kecamatan_views.xml',
        'views/desa_views.xml',
        'views/periode_views.xml',
        'views/sdi_views.xml',
        'views/dashboard_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/satu_data_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Leaflet (salinan lokal). Guard menjaga window.L yang sudah ada
            # bila modul lain juga memuat Leaflet.
            'satu_data/static/lib/leaflet/leaflet.css',
            'satu_data/static/lib/leaflet_guard/before.js',
            'satu_data/static/lib/leaflet/leaflet.js',
            'satu_data/static/lib/leaflet_guard/after.js',
            # Pengelompokan titik berdekatan (plugin markercluster, MIT)
            'satu_data/static/lib/leaflet-markercluster/MarkerCluster.css',
            'satu_data/static/lib/leaflet-markercluster/MarkerCluster.Default.css',
            'satu_data/static/lib/leaflet-markercluster/leaflet.markercluster.js',
            # Gaya dashboard dan komponen peta bersama (dipakai modul sektor)
            'satu_data/static/src/css/dashboard_peta.css',
            'satu_data/static/src/xml/peta_wilayah.xml',
            'satu_data/static/src/js/peta_wilayah.js',
            # Pemuat ECharts (pustakanya dimuat saat dibutuhkan, tidak masuk bundel)
            'satu_data/static/src/js/echarts_loader.js',
            'satu_data/static/src/xml/grafik_echarts.xml',
            'satu_data/static/src/js/grafik_echarts.js',
            # Kerangka Dashboard: sidebar sektor (registry "satu_data_dashboard")
            'satu_data/static/src/css/dashboard_shell.css',
            'satu_data/static/src/xml/dashboard_shell.xml',
            'satu_data/static/src/js/dashboard_shell.js',
            # Editor batas wilayah di form kecamatan/desa
            'satu_data/static/src/css/geojson_peta_field.css',
            'satu_data/static/src/xml/geojson_peta_field.xml',
            'satu_data/static/src/js/geojson_peta_field.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
