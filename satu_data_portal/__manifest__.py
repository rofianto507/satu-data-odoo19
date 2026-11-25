{
    'name': 'Satu Data: Portal Publik',
    'version': '19.0.1.5.2',
    'summary': 'Portal Satu Data untuk publik: katalog, halaman data, unduhan, dan API baca',
    'description': """
Portal Publik Satu Data
=======================

Tahap penyebarluasan Satu Data Indonesia (Perpres 39/2019) di website Odoo, tanpa login:

* Katalog Daftar Data: pencarian, filter Produsen Data, urusan, topik, dan tahun; urut
  terbaru atau abjad.
* Halaman data: metadata (selaras isian data.go.id), tabel per periode dan wilayah, grafik.
* Unduhan CSV, Excel (tabel + data + metadata), dan JSON + metadata.
* API baca JSON ``/api/satu-data/v1`` (daftar data, metadata, nilai, wilayah, referensi),
  CORS terbuka, batas permintaan per IP; dokumentasi di ``/data/api``.
* Statistik kunjungan dan unduhan per data per hari (angka agregat, tanpa data pengunjung)
  untuk urutan "Populer" dan menu Statistik Portal bagi Walidata.
* Formulir Permintaan Data (/permintaan) dengan pengaman berlapis (CSRF, kolom jebakan, tanda waktu
  bertanda tangan, batas per IP) dan halaman status berbasis token acak; ditangani Walidata di
  menu Tata Kelola.
* Kunci API opsional untuk instansi lain (hanya hash yang disimpan, batas permintaan lebih
  longgar; tidak membuka data tertutup).
* Pengumuman di atas portal lewat parameter sistem ``satu_data_portal.pengumuman``.
* Cache nilai per data per periode; dibersihkan saat laporan terbit/ditarik atau wilayah
  berubah.
* Beranda portal beranimasi (hero dengan ilustrasi vektor, angka kunci berhitung naik, cara
  memakai data, alur kerja, data terbaru/populer, Produsen Data), dashboard
  tematik per topik (peta choropleth kecamatan, peringkat, tren), halaman Tentang (prinsip,
  alur, penyelenggara, tanya-jawab), serta footer dan menu berbahasa Indonesia.
* Saat dipasang: bahasa Indonesia menjadi bahasa website, beranda diarahkan ke portal, menu
  "Contact us" dihapus (sekali saja; tidak menimpa pengaturan Admin sesudahnya).

Hanya data yang sudah diterbitkan Walidata, berstatus akses "Terbuka", dan tidak
dihentikan. Angka disajikan paling rendah per kecamatan (atau hanya kab/kota bila
tingkat penyajiannya kab/kota), tanpa data per orang. Nilai dihitung oleh modul sektor
(kait ``_sd_nilai_publik``) sehingga sama dengan dashboard internal.
""",
    'category': 'Website',
    'depends': ['satu_data', 'website', 'portal'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'security/satu_data_portal_security.xml',
        'data/sequence.xml',
        'data/website_menu.xml',
        'views/templates.xml',
        'views/beranda.xml',
        'views/tentang.xml',
        'views/ikon.xml',
        'views/permintaan.xml',
        'views/permintaan_views.xml',
        'views/statistik_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'satu_data_portal/static/src/scss/portal.scss',
            'satu_data_portal/static/src/scss/beranda.scss',
            'satu_data_portal/static/src/js/grafik_data.js',
            'satu_data_portal/static/src/js/dasbor.js',
            'satu_data_portal/static/src/js/beranda.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
