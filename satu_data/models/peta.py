"""Perkakas peta bersama untuk semua modul sektor (kependudukan, pendidikan, ...).

Modul sektor mewarisi ``satu_data.peta.mixin`` pada model datanya untuk memakai
pembagian kelas warna choropleth, pilihan peta dasar, dan info wilayah induk.
"""
import math
from urllib.parse import urlencode

from odoo import api, models

from .utils import format_angka

# 5 kelas warna berurutan (terang ke gelap, ColorBrewer YlOrRd) + warna "tidak ada data".
WARNA_KELAS = ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026']
WARNA_TANPA_DATA = '#d9d9d9'
JUMLAH_KELAS = len(WARNA_KELAS)

# Pilihan peta dasar di dashboard dan editor batas wilayah.
# Bawaan diatur parameter sistem "satu_data.peta_dasar" (kode di bawah).
# Server tile sendiri: isi "satu_data.url_peta_dasar" (+ "satu_data.atribusi_peta_dasar"),
# muncul sebagai pilihan "Kustom".
# Server OSM dan CARTO publik hanya untuk pemakaian wajar; lihat
# https://operations.osmfoundation.org/policies/tiles/ dan https://carto.com/basemaps
ATRIBUSI_OSM = ('© <a href="https://www.openstreetmap.org/copyright" target="_blank">'
                'OpenStreetMap</a>')
ATRIBUSI_CARTO = ATRIBUSI_OSM + (' contributors, © <a href="https://carto.com/attribution/" '
                                 'target="_blank">CARTO</a>')
# CARTO mewajibkan API key (parameter "key" di URL); tanpa key tile diberi tanda air.
# Key diisi di parameter sistem "satu_data.carto_api_key"; selama kosong, pilihan
# CARTO tidak ditampilkan. Daftar dan atur key: https://carto.com/basemaps/apikey
PETA_DASAR = [
    {'kode': 'positron', 'nama': 'Positron (terang)', 'abu': False, 'maks_zoom': 20,
     'maks_zoom_asli': 18, 'carto': True,
     'url': 'https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
     'subdomain': '', 'atribusi': ATRIBUSI_CARTO},
    {'kode': 'voyager', 'nama': 'Voyager (lembut)', 'abu': False, 'maks_zoom': 20,
     'maks_zoom_asli': 18, 'carto': True,
     'url': 'https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
     'subdomain': '', 'atribusi': ATRIBUSI_CARTO},
    {'kode': 'osm', 'nama': 'OSM (abu-abu)', 'abu': True, 'maks_zoom': 19,
     'url': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
     'subdomain': '', 'atribusi': ATRIBUSI_OSM},
]
PETA_DASAR_BAWAAN = 'positron'
PETA_DASAR_TANPA_KEY = 'osm'


class SatuDataPetaMixin(models.AbstractModel):
    _name        = 'satu_data.peta.mixin'
    _description = 'Perkakas Peta Satu Data'

    # ── Wilayah induk dan peta dasar ──────────────────────────────────────────

    @api.model
    def _sd_info_wilayah_induk(self, company=None):
        """Identitas kab/kota (company) untuk kepala dashboard."""
        company = company or self.env.company
        return {
            'id':    company.id,
            'nama':  company.name,
            'jenis': company.sd_jenis_wilayah or False,
            'kode':  company.sd_kode_wilayah or False,
            # "unique" = versi, agar browser tidak memakai logo lama dari cache.
            'logo':  (f'/web/image/res.company/{company.id}/logo'
                      f'?unique={int(company.write_date.timestamp())}'
                      if company.logo else False),
        }

    @api.model
    def _sd_peta_dasar(self):
        """Pilihan peta dasar dan kode bawaannya (dari parameter sistem)."""
        param = self.env['ir.config_parameter'].sudo()
        key_carto = (param.get_param('satu_data.carto_api_key') or '').strip()
        pilihan = []
        for p in PETA_DASAR:
            p = dict(p)
            if p.pop('carto', False):
                if not key_carto:
                    continue  # tanpa key CARTO hanya memberi tile bertanda air
                p['url'] += '?' + urlencode({'key': key_carto})
            pilihan.append(p)
        url_kustom = (param.get_param('satu_data.url_peta_dasar') or '').strip()
        if url_kustom:
            pilihan.insert(0, {
                'kode': 'kustom', 'nama': 'Kustom', 'abu': False, 'maks_zoom': 19,
                'url': url_kustom, 'subdomain': '',
                'atribusi': param.get_param('satu_data.atribusi_peta_dasar') or '',
            })
        kode_ada = {p['kode'] for p in pilihan} | {'tanpa'}
        cadangan = PETA_DASAR_BAWAAN if key_carto else PETA_DASAR_TANPA_KEY
        bawaan = param.get_param('satu_data.peta_dasar') or (
            'kustom' if url_kustom else cadangan)
        return {'pilihan': pilihan,
                'bawaan': bawaan if bawaan in kode_ada else cadangan}

    # ── Kelas warna choropleth ────────────────────────────────────────────────

    @api.model
    def _hitung_kelas(self, nilai_list):
        """Bagi nilai (> 0) menjadi 5 kelas warna.

        Utama: kuantil, yaitu tiap kelas berisi jumlah wilayah yang kurang lebih sama,
        sehingga kelima warna terpakai walau sebarannya timpang (kota vs desa).
        Batas dibulatkan ke 2 angka penting agar legenda mudah dibaca.

        Cadangan, bila nilai berbeda kurang dari 5 atau batas kuantil bertumpuk
        setelah dibulatkan: interval sama dengan langkah 1, 2, 2,5, atau 5 x 10^n.
        """
        nilai = sorted(v for v in nilai_list if v > 0)
        atas_list = None
        if len(set(nilai)) >= JUMLAH_KELAS:
            n = len(nilai)
            atas_list = [self._bulat_penting(nilai[math.ceil(n * i / JUMLAH_KELAS) - 1])
                         for i in range(1, JUMLAH_KELAS)]
            atas_list.append(self._bulat_penting(nilai[-1], ke_atas=True))
            if any(b <= a for a, b in zip(atas_list, atas_list[1:])):
                atas_list = None  # batas bertumpuk: pakai interval sama
        if atas_list is None:
            maks = nilai[-1] if nilai else 0
            langkah = self._langkah_bulat(maks / JUMLAH_KELAS) if maks > 0 else 1
            atas_list = [(i + 1) * langkah for i in range(JUMLAH_KELAS)]

        kelas = []
        bawah = 0
        for i, (warna, atas) in enumerate(zip(WARNA_KELAS, atas_list)):
            if i == 0:
                label = f'≤ {format_angka(atas)}'
            elif bawah + 1 == atas:
                label = format_angka(atas)  # langkah 1: "3", bukan "3 – 3"
            else:
                label = f'{format_angka(bawah + 1)} – {format_angka(atas)}'
            kelas.append({'bawah': bawah, 'atas': atas, 'warna': warna, 'label': label})
            bawah = atas
        return kelas

    @api.model
    def _bulat_penting(self, x, ke_atas=False):
        """Bulatkan bilangan bulat positif ke 2 angka penting: 45.321 -> 45.000."""
        if x < 100:
            return int(math.ceil(x) if ke_atas else round(x))
        satuan = 10 ** (int(math.log10(x)) - 1)
        bulat = math.ceil(x / satuan) if ke_atas else round(x / satuan)
        return int(bulat * satuan)

    @api.model
    def _langkah_bulat(self, x):
        pangkat = 10 ** math.floor(math.log10(x)) if x > 0 else 1
        for faktor in (1, 2, 2.5, 5, 10):
            langkah = faktor * pangkat
            if langkah >= x and langkah == int(langkah):
                return int(langkah)
        return int(10 * pangkat)

    @api.model
    def _kelas_index(self, nilai, kelas):
        for i, k in enumerate(kelas):
            if nilai <= k['atas']:
                return i
        return len(kelas) - 1

    @api.model
    def _sd_warna_tanpa_data(self):
        return WARNA_TANPA_DATA
