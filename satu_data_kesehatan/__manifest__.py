{
    'name': 'Satu Data - Kesehatan',
    'version': '19.0.1.6.1',
    'summary': 'Fasilitas kesehatan, wilayah kerja puskesmas, dan sasaran program kesehatan per desa',
    'description': """
Satu Data: Kesehatan
====================

Modul sektor kesehatan untuk Satu Data (modul inti ``satu_data``).
Produsen Data = Dinas Kesehatan.

* Master fasilitas kesehatan: puskesmas, puskesmas pembantu, rumah sakit, klinik;
  lokasi desa dan koordinat; wilayah kerja puskesmas (desa/kelurahan binaan).
* Sasaran program kesehatan tahunan per desa/kelurahan (sasaran 12 SPM bidang
  kesehatan + bayi), dengan puskesmas wilayah kerja dicatat saat data dibuat.
  Diajukan ke Walidata per tahun dan terdaftar di Daftar Data beserta metadatanya.
* Rekap layanan kesehatan bulanan per desa/kelurahan (laporan bulanan puskesmas):
  pelayanan 12 SPM sesuai standar, imunisasi dasar lengkap, balita diukur/stunting,
  lahir hidup, kematian ibu/bayi, kasus/kematian DBD; puskesmas dicatat saat data
  dibuat; isian cepat per puskesmas; diajukan ke Walidata per bulan (batas tanggal 10).
* Indikator (terdaftar di Daftar Data): capaian 12 SPM, imunisasi dasar lengkap,
  prevalensi stunting, kematian ibu/bayi + rasio per kelahiran hidup, kasus/IR/CFR DBD;
  per bulan atau kumulatif s.d. bulan. Dashboard "Kesehatan" di sidebar Dashboard:
  peta choropleth kecamatan → desa, titik puskesmas, capaian SPM, tren bulanan.
  Data terbatas tidak dirinci di bawah tingkat penyajian terendahnya.

Hanya angka rekap per wilayah, tidak menyimpan data per orang.
""",
    'category': 'Productivity',
    'depends': ['satu_data'],
    'data': [
        'security/satu_data_kesehatan_security.xml',
        'security/ir.model.access.csv',
        'data/satu_data_kesehatan_data.xml',
        'data/satu_data_kesehatan_indikator.xml',
        'views/faskes_views.xml',
        'views/sasaran_views.xml',
        'views/rekap_views.xml',
        'views/laporan_views.xml',
        'views/desa_views.xml',
        'views/periode_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/satu_data_kesehatan_demo.xml',
        'demo/satu_data_kesehatan_demo_rekap.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'satu_data_kesehatan/static/src/css/dashboard_kesehatan.css',
            'satu_data_kesehatan/static/src/xml/dashboard_kesehatan.xml',
            'satu_data_kesehatan/static/src/js/dashboard_kesehatan.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
