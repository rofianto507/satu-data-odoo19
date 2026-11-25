"""Dashboard tematik publik: peta choropleth kecamatan, peringkat, dan tren per topik.

Memakai aturan publik yang sama dengan katalog (``_sd_cari_publik``, ``_sd_tabel_publik``),
sehingga yang tampil hanya data terbuka yang terbit, paling rinci per kecamatan.
"""
import math

from odoo import api, models, tools

from .daftar_data import FREKUENSI_PER_TAHUN

# Palet 5 kelas (ColorBrewer). naik: makin tinggi makin baik; turun: makin tinggi makin buruk;
# netral: jumlah/besaran tanpa arah baik-buruk.
PALET = {
    'naik':   ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641'],
    'turun':  ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'],
    'netral': ['#eff3ff', '#bdd7e7', '#6baed6', '#3182bd', '#08519c'],
}
WARNA_TANPA_DATA = '#d9d9d9'
# Penyederhanaan batas kecamatan untuk peta publik (derajat; ~0,0004 = ±40 m).
TOLERANSI_PETA = 0.0004
DESIMAL_KOORDINAT = 5


def _bulat_penting(x, desimal):
    """Bulatkan ke 2 angka penting, tidak lebih halus dari ``desimal``."""
    if x <= 0:
        return 0
    pangkat = math.floor(math.log10(x)) - 1
    satuan = max(10 ** pangkat, 10 ** -desimal)
    return round(round(x / satuan) * satuan, desimal)


def kelas_warna(nilai_list, arah=False, batas=False, desimal=0):
    """5 kelas warna ``[{'warna', 'bawah', 'atas'}]``; kelas ke-i: bawah <= nilai < atas.

    Batas tetap bila ada (target/standar), selain itu kuantil nilai wilayah; bila nilainya
    terlalu sedikit/seragam, interval sama dari 0 s.d. nilai terbesar.
    """
    palet = PALET.get(arah) or PALET['netral']
    if not batas:
        nilai = sorted(v for v in nilai_list if v is not None)
        batas = None
        if len(set(nilai)) >= 5:
            n = len(nilai)
            batas = [_bulat_penting(nilai[math.ceil(n * i / 5) - 1], desimal) for i in range(1, 5)]
            if batas[0] <= 0 or any(b <= a for a, b in zip(batas, batas[1:])):
                batas = None
        if batas is None:
            maks = nilai[-1] if nilai else 0
            langkah = _bulat_penting(maks / 5, desimal) or (10 ** -desimal)
            batas = [round(langkah * i, desimal) for i in range(1, 5)]
    return [{'warna': warna, 'bawah': batas[i - 1] if i else None, 'atas': batas[i] if i < 4 else None}
            for i, warna in enumerate(palet)]


def _rdp(titik, toleransi):
    """Ramer–Douglas–Peucker untuk satu garis [[x, y], ...]."""
    if len(titik) < 3:
        return titik
    (x1, y1), (x2, y2) = titik[0], titik[-1]
    dx, dy = x2 - x1, y2 - y1
    panjang = math.hypot(dx, dy)
    jarak_maks, indeks = 0.0, 0
    for i in range(1, len(titik) - 1):
        x, y = titik[i]
        if panjang:
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / panjang
        else:
            d = math.hypot(x - x1, y - y1)
        if d > jarak_maks:
            jarak_maks, indeks = d, i
    if jarak_maks <= toleransi:
        return [titik[0], titik[-1]]
    kiri = _rdp(titik[:indeks + 1], toleransi)
    return kiri[:-1] + _rdp(titik[indeks:], toleransi)


def _sederhanakan_cincin(cincin, toleransi):
    hasil = _rdp([[round(x, DESIMAL_KOORDINAT), round(y, DESIMAL_KOORDINAT)]
                  for x, y, *_z in cincin], toleransi)
    if len(hasil) < 4:   # cincin kecil: pertahankan bentuk asli (dibulatkan)
        hasil = [[round(x, DESIMAL_KOORDINAT), round(y, DESIMAL_KOORDINAT)] for x, y, *_z in cincin]
    return hasil


def sederhanakan_geometri(geom, toleransi=TOLERANSI_PETA):
    """Polygon/MultiPolygon lebih ringan untuk tampilan tingkat kecamatan."""
    if not geom:
        return None
    if geom.get('type') == 'Polygon':
        return {'type': 'Polygon',
                'coordinates': [_sederhanakan_cincin(c, toleransi) for c in geom['coordinates']]}
    if geom.get('type') == 'MultiPolygon':
        return {'type': 'MultiPolygon',
                'coordinates': [[_sederhanakan_cincin(c, toleransi) for c in poli]
                                for poli in geom['coordinates']]}
    return geom


class SatuDataKecamatan(models.Model):
    _inherit = 'satu_data.kecamatan'

    @api.model
    @tools.ormcache('company_id')
    def _sd_peta_publik(self, company_id):
        """GeoJSON FeatureCollection kecamatan aktif (disederhanakan) untuk peta publik.

        Cache dibersihkan saat kecamatan berubah (lihat ``cache.py``).
        """
        fitur = []
        for k in self.sudo().search([('company_id', '=', company_id)]):
            geom = sederhanakan_geometri(k._sd_geometri())
            if geom:
                fitur.append({'type': 'Feature', 'geometry': geom,
                              'properties': {'id': k.id, 'kode': k.kode or '', 'nama': k.name}})
        return {'type': 'FeatureCollection', 'features': fitur}


class SatuDataData(models.Model):
    _inherit = 'satu_data.data'

    @api.model
    def _sd_tema_publik(self, company):
        """Topik yang punya data publik: ``[{'topik', 'jumlah', 'jumlah_peta'}]``.

        ``jumlah_peta`` = data yang dirinci per kecamatan (bisa dipetakan).
        """
        hasil, faset = self._sd_cari_publik(company)
        peta = {}
        for data, _info in hasil:
            if data.topik_id and data.tingkat_penyajian != 'kabupaten':
                peta[data.topik_id] = peta.get(data.topik_id, 0) + 1
        return [{'topik': t, 'jumlah': n, 'jumlah_peta': peta.get(t, 0)}
                for t, n in sorted(faset['topik'].items(), key=lambda x: (x[0].sequence, x[0].name))]

    def _sd_dasbor_publik(self):
        """Isi dashboard untuk satu data: semua periode, nilai per kecamatan, kelas warna per
        periode, dan metadata ringkas. Pilihan periode dilakukan di peramban."""
        self.ensure_one()
        tabel = self._sd_tabel_publik(semua=True)
        gaya = self._sd_gaya_publik()
        arah = gaya.get('arah') or 'netral'
        total, *kecamatan = tabel['baris']
        kelas = []
        for i in range(len(tabel['periode'])):
            nilai = [b['nilai'][i] for b in kecamatan]
            kelas.append(kelas_warna(nilai, arah, gaya.get('batas'), tabel['desimal']))
        return {
            'kode': self.kode,
            'nama': self.name,
            'definisi': self.definisi or '',
            'catatan': tabel['catatan'] or '',
            'satuan': self.satuan or '',
            'desimal': tabel['desimal'],
            'arah': arah,
            'rinci': tabel['rinci'],
            'produsen': self.instansi_id.name or '',
            'url': f'/data/{self.kode}',
            'periode': [p['label'] for p in tabel['periode']],
            'tahun': [p['tahun'] for p in tabel['periode']],
            # Data bulanan/triwulanan sering kumulatif per tahun: garis tren dipisah per tahun
            # agar tidak tampak "turun" saat tahun berganti.
            'putus_tahun': self.frekuensi in FREKUENSI_PER_TAHUN,
            'total': {'nama': total['nama'], 'nilai': total['nilai']},
            'wilayah': {str(b['id']): {'nama': b['nama'], 'nilai': b['nilai']} for b in kecamatan},
            'kelas': kelas,
            'warna_tanpa_data': WARNA_TANPA_DATA,
        }
