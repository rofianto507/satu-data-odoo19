{
    'name': 'Satu Data - Pendidikan',
    'version': '19.0.1.0.0',
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

Rekap semester per jenjang, indikator, dan dashboard menyusul.

Hanya menyimpan angka rekap per wilayah dan data satuan pendidikan, tidak ada data
peserta didik perorangan.
""",
    'category': 'Productivity',
    'depends': ['satu_data'],
    'data': [
        'security/satu_data_pendidikan_security.xml',
        'security/ir.model.access.csv',
        'data/satu_data_pendidikan_data.xml',
        'views/sekolah_views.xml',
        'views/usia_sekolah_views.xml',
        'views/laporan_views.xml',
        'views/periode_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/satu_data_pendidikan_demo.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
