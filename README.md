# Satu Data untuk Odoo 19

Portal data wilayah tingkat kabupaten/kota yang mengikuti konsep **Satu Data Indonesia**
(Perpres 39/2019): standar data, metadata, kode referensi, serta pembagian peran Produsen Data,
Walidata, dan Pembina Data. Dibangun untuk Odoo 19 Community, seluruh antarmuka berbahasa Indonesia.
Contoh data demo memakai Kabupaten Jember.

Sistem hanya menyimpan **angka rekap per wilayah**, tidak ada data perorangan.

## Modul

| Modul | Isi |
|---|---|
| `satu_data` | Modul inti: wilayah (kecamatan, desa/kelurahan, batas peta GeoJSON dan editornya), periode data, instansi, Daftar Data berikut metadata, Forum Satu Data, laporan dan pemeriksaan Walidata, peran akses, kerangka dashboard dengan sidebar per sektor |
| `satu_data_kependudukan` | Rekap penduduk per desa per semester, dashboard peta penduduk dengan grafik laki-laki/perempuan |
| `satu_data_kesehatan` | Fasilitas kesehatan dan wilayah kerja puskesmas, sasaran tahunan, rekap layanan bulanan per desa, 21 indikator (12 SPM, imunisasi, stunting, kematian ibu/bayi, DBD), dashboard peta dengan titik puskesmas |

Modul sektor bergantung pada `satu_data`. Modul inti bisa dipasang tanpa modul sektor.

## Alur kerja

```
Produsen Data mengisi laporan  ──Kirim──▶  Walidata memeriksa  ──Terbitkan──▶  Dashboard
        (Diisi)                              (Diperiksa)                         (Terbit)
              ◀────────── Kembalikan dengan catatan ──────────┘
```

Dashboard hanya menampilkan data yang sudah diterbitkan Walidata. Data yang sedang diperiksa
atau sudah terbit dikunci.

## Pemasangan

1. Salin ketiga folder modul ke folder `addons` Odoo 19.
2. Aktifkan mode pengembang, perbarui daftar aplikasi, lalu pasang **Satu Data - Kependudukan**
   dan/atau **Satu Data - Kesehatan** (modul inti ikut terpasang).
3. Untuk mencoba, buat database dengan *data demo* (wilayah, penduduk, dan data kesehatan Jember).
4. Atur nama, logo, dan kode wilayah di **Konfigurasi › Identitas Wilayah**.

Menjalankan tes:

```
odoo-bin -c odoo.conf -d <database> --test-enable --test-tags /satu_data,/satu_data_kependudukan,/satu_data_kesehatan --stop-after-init
```

## Peta dasar

Peta dasar CARTO memerlukan API key (isi di Identitas Wilayah). Tanpa key, dashboard memakai
OpenStreetMap. Server tile sendiri bisa dipakai lewat parameter sistem `satu_data.url_peta_dasar`.
Leaflet dan ECharts disertakan secara lokal, tidak ada pemuatan dari CDN.

## Data demo

Seluruh data demo bersifat **fiktif** dan hanya contoh, bukan data resmi:

- Batas dan kode wilayah Kabupaten Jember bersumber dari
  [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah) (MIT),
  [pararawendy/border-desa-indonesia-geojson](https://github.com/pararawendy/border-desa-indonesia-geojson),
  dan [cahyadsn/wilayah_boundaries](https://github.com/cahyadsn/wilayah_boundaries) (MIT).
- Angka penduduk dan data kesehatan dibangkitkan secara acak dengan pola yang masuk akal.

## Lisensi

LGPL-3.0, sesuai Odoo. Leaflet dan ECharts memiliki lisensinya sendiri
(lihat `satu_data/static/lib/`).
