<p align="center">
  <img src="docs/banner.png" alt="Satu Data untuk Odoo 19" width="100%">
</p>

<p align="center">
  <img alt="Odoo 19" src="https://img.shields.io/badge/Odoo-19.0-5B21B6">
  <img alt="Lisensi LGPL-3.0" src="https://img.shields.io/badge/Lisensi-LGPL--3.0-FF005C">
  <img alt="Bahasa Indonesia" src="https://img.shields.io/badge/Antarmuka-Bahasa%20Indonesia-7C3AED">
  <img alt="Data demo fiktif" src="https://img.shields.io/badge/Data%20demo-fiktif-C4B5FD?labelColor=5B21B6">
</p>

# Satu Data untuk Odoo 19

Portal data wilayah tingkat kabupaten/kota yang mengikuti konsep **Satu Data Indonesia**
(Perpres 39/2019): standar data, metadata, kode referensi, serta pembagian peran Produsen Data,
Walidata, dan Pembina Data. Dibangun untuk Odoo 19 Community, seluruh antarmuka berbahasa Indonesia.
Contoh data demo memakai Kabupaten Jember.

Sistem hanya menyimpan **angka rekap per wilayah**, tidak ada data perorangan.

## Tampilan

Seluruh angka pada tangkapan layar di bawah adalah **data demo fiktif**, bukan data resmi.

### Dashboard Kependudukan
Peta kepadatan penduduk per kecamatan yang bisa dibuka sampai tingkat desa/kelurahan, lengkap dengan
kartu ringkasan, panel detail, dan daftar wilayah.

<img src="docs/screenshots/dashboard-kependudukan-peta.png" alt="Dashboard Kependudukan: kartu ringkasan, peta jumlah penduduk per kecamatan, dan panel detail Kabupaten Jember" width="100%">

Grafik batang bertumpuk laki-laki dan perempuan per kecamatan. Klik sebuah batang untuk melihat desa/kelurahannya.

<img src="docs/screenshots/dashboard-kependudukan-grafik.png" alt="Grafik batang bertumpuk jumlah penduduk laki-laki dan perempuan per kecamatan" width="100%">

### Dashboard Kesehatan
Pilih indikator (12 SPM, imunisasi dasar lengkap, stunting, kematian ibu dan bayi, DBD), bulan, dan cara
hitung bulanan atau kumulatif. Peta memberi warna wilayah menurut capaian dan menandai lokasi puskesmas.

<img src="docs/screenshots/dashboard-kesehatan-peta.png" alt="Dashboard Kesehatan: kartu indikator kunci dan peta capaian dengan penanda puskesmas" width="100%">

Klik penanda puskesmas untuk melihat jendela infonya, lalu **Lihat detail data** untuk membuka rekap
bulanannya.

<img src="docs/screenshots/dashboard-kesehatan-info-puskesmas.png" alt="Jendela info puskesmas di peta dengan tombol Lihat detail data" width="100%">

Capaian 12 Standar Pelayanan Minimal dan tren bulanan indikator yang dipilih.

<img src="docs/screenshots/dashboard-kesehatan-grafik.png" alt="Grafik capaian 12 SPM kesehatan dan tren bulanan" width="100%">

## Fitur utama

- **Alur Satu Data yang sederhana.** Produsen Data mengisi laporan, Walidata memeriksa, dan hanya
  data yang sudah diterbitkan yang tampil di dashboard. Data yang sedang diperiksa atau sudah terbit dikunci.
- **Dashboard peta per sektor.** Peta choropleth kabupaten → kecamatan → desa/kelurahan, kartu ringkasan,
  grafik, dan titik fasilitas dengan jendela info, dengan sidebar untuk berpindah antarsektor.
- **Tata kelola data.** Daftar Data dengan metadata selaras data.go.id, urusan pemerintahan,
  Forum Satu Data, jadwal pemutakhiran, dan penilaian ketepatan waktu Produsen Data.
- **Editor batas wilayah.** Geser, tambah, dan hapus titik batas desa/kecamatan langsung di peta.
- **Data terbatas.** Indikator sensitif hanya disajikan sampai tingkat yang ditetapkan, misalnya kecamatan.
- **Tanpa layanan luar.** Leaflet dan ECharts disertakan secara lokal, tidak ada pemuatan dari CDN.

## Modul

| Modul | Isi |
|---|---|
| `satu_data` | Modul inti: wilayah (kecamatan, desa/kelurahan, batas peta GeoJSON dan editornya), periode data, instansi, Daftar Data berikut metadata, Forum Satu Data, laporan dan pemeriksaan Walidata, peran akses, kerangka dashboard dengan sidebar per sektor |
| `satu_data_kependudukan` | Laporan semester penduduk per desa (laki-laki, perempuan, KK, kepadatan), dashboard peta penduduk dengan grafik laki-laki/perempuan |
| `satu_data_kesehatan` | Fasilitas kesehatan dan wilayah kerja puskesmas, laporan bulanan dan laporan sasaran tahunan per desa, 21 indikator (12 SPM, imunisasi dasar lengkap, stunting, kematian ibu/bayi, DBD), dashboard peta dengan titik puskesmas |

Modul sektor bergantung pada `satu_data`. Modul inti bisa dipasang tanpa modul sektor.

## Alur kerja

Setiap sektor memakai satu pola: **satu laporan per periode** dengan tiga status,
**Diisi → Diperiksa → Terbit**.

<img src="docs/alur-laporan.png" alt="Diagram alur laporan: Produsen Data membuka laporan, mengisi tabel desa, dan mengirim; Walidata memeriksa lalu menerbitkan atau mengembalikan dengan catatan; dashboard menampilkan data terbit" width="100%">

1. **Buka laporan.** Produsen Data memilih periode dan langsung mendapat baris semua desa/kelurahan.
2. **Isi tabel desa.** Angka diisi langsung di tabel, dan desa yang masih kosong ditandai.
3. **Kirim ke Walidata.** Sistem memeriksa kelengkapan. Laporan tetap bisa dikirim walau ada desa kosong,
   tetapi Walidata melihat jumlahnya dan desa itu tidak tampil di dashboard.
4. **Periksa.** Walidata menerbitkan, atau mengembalikan dengan catatan wajib. Laporan yang dikembalikan
   kembali ke status Diisi dan catatan Walidata tampil di bagian atasnya.
5. **Terbit.** Data resmi dan terkunci, lalu tampil di dashboard.

<img src="docs/screenshots/laporan-semester.png" alt="Laporan semester kependudukan dengan bilah status Diisi, Diperiksa, Terbit dan tabel isian per desa" width="100%">

### Peran

| Peran | Tugas |
|---|---|
| Pengguna Data | Melihat dashboard dan data |
| Produsen Data (per sektor) | Mengisi dan mengirim laporan sektornya |
| Walidata | Memeriksa, menerbitkan, atau mengembalikan laporan semua sektor |
| Pembina Data | Melengkapi standar data dan metadata |
| Admin | Mengatur wilayah, periode, instansi, dan pengguna |

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

### Peta dasar

Peta dasar CARTO memerlukan API key (isi di Identitas Wilayah). Tanpa key, dashboard memakai
OpenStreetMap. Server tile sendiri bisa dipakai lewat parameter sistem `satu_data.url_peta_dasar`.

## Data demo

Seluruh data demo bersifat **fiktif** dan hanya contoh, bukan data resmi:

- Batas dan kode wilayah Kabupaten Jember bersumber dari
  [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah) (MIT),
  [pararawendy/border-desa-indonesia-geojson](https://github.com/pararawendy/border-desa-indonesia-geojson),
  dan [cahyadsn/wilayah_boundaries](https://github.com/cahyadsn/wilayah_boundaries) (MIT).
- Angka penduduk dan data kesehatan dibangkitkan secara acak dengan pola yang masuk akal.

## Rencana pengembangan

- Integrasi API: sistem tiap OPD mengirim angka rekap langsung ke Satu Data, dengan kode wilayah
  Kemendagri sebagai kunci desa dan tetap melewati pemeriksaan Walidata
- Penanda angka yang tidak wajar untuk membantu pemeriksaan Walidata
- Portal publik: katalog Daftar Data, unduhan CSV/XLSX/JSON beserta metadata, dan permintaan data
- Modul pendidikan

## Lisensi

LGPL-3.0, sesuai Odoo. Leaflet dan ECharts memiliki lisensinya sendiri
(lihat `satu_data/static/lib/`).
