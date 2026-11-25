{
    'name': 'Satu Data - Pendidikan',
    'version': '19.0.1.4.1',
    'summary': 'Satuan pendidikan (sekolah) dan penduduk usia sekolah per desa',
    'description': """
Satu Data: Pendidikan
=====================

Modul sektor pendidikan untuk Satu Data (modul inti ``satu_data``).
Produsen Data = Dinas Pendidikan; madrasah dibina Kementerian Agama (Produsen Data
vertikal) dan dihimpun dalam laporan yang sama.

* Master satuan pendidikan (sekolah): NPSN, jenjang (PAUD/TK, SD, MI, SMP, MTs, SMA, SMK,
  MA, SLB, PKBM), status negeri/swasta, pembina (Disdik/Kemenag), akreditasi, desa
  lokasi, dan koordinat.
* Penduduk usia sekolah tahunan per desa/kelurahan (usia 5–6, 7–12, 13–15, 16–18 tahun),
  penyebut angka partisipasi. Diajukan ke Walidata per tahun lewat Laporan dan terdaftar
  di Daftar Data beserta metadatanya.

* Rekap semester per desa/kelurahan dan kelompok jenjang (PAUD/TK, SD/MI, SMP/MTs, SMA/SMK/MA):
  jumlah sekolah, siswa (L/P, usia resmi), rombel, guru (S1/D4, bersertifikat), ruang kelas
  (baik/rusak), putus sekolah, lulusan, dan melanjutkan; diajukan ke Walidata per semester.

* Indikator (terdaftar di Daftar Data): ketersediaan (sekolah, siswa, guru), mutu layanan
  (rasio murid per guru, murid per rombel, ruang kelas baik, guru S1/D4 dan bersertifikat),
  partisipasi (APK dan APM per jenjang, disajikan paling rendah per kecamatan), dan
  keberlanjutan (putus sekolah, melanjutkan). Dashboard "Pendidikan" di sidebar Dashboard:
  peta choropleth kecamatan → desa, titik satuan pendidikan per kecamatan, partisipasi per
  jenjang, tren semester.

Hanya menyimpan angka rekap per wilayah dan data satuan pendidikan, tidak ada data
peserta didik perorangan.
""",
    'category': 'Productivity',
    'depends': ['satu_data'],
    'data': [
        'security/satu_data_pendidikan_security.xml',
        'security/ir.model.access.csv',
        'data/satu_data_pendidikan_data.xml',
        'data/satu_data_pendidikan_indikator.xml',
        'views/sekolah_views.xml',
        'views/usia_sekolah_views.xml',
        'views/rekap_views.xml',
        'views/laporan_views.xml',
        'views/periode_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/satu_data_pendidikan_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'satu_data_pendidikan/static/src/css/dashboard_pendidikan.css',
            'satu_data_pendidikan/static/src/xml/dashboard_pendidikan.xml',
            'satu_data_pendidikan/static/src/js/dashboard_pendidikan.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
