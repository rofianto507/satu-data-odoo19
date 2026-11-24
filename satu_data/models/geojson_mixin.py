import json
import numbers

from odoo import api, fields, models
from odoo.exceptions import ValidationError

TIPE_GEOMETRI = ('Polygon', 'MultiPolygon')

# Geometri untuk peta: koordinat dibulatkan ke 5 desimal (~1 m) lalu
# disederhanakan (Douglas-Peucker) dengan toleransi ~5 m. Cukup untuk peta
# desa/kecamatan dan jauh lebih kecil dari batas wilayah resmi yang rinci.
PRESISI_PETA = 5
TOLERANSI_PETA = 0.00005  # derajat


def _douglas_peucker(titik, toleransi):
    """Sederhanakan garis (iteratif, aman untuk ring sangat panjang)."""
    n = len(titik)
    simpan = [False] * n
    simpan[0] = simpan[-1] = True
    batas2 = toleransi * toleransi
    tumpukan = [(0, n - 1)]
    while tumpukan:
        a, b = tumpukan.pop()
        ax, ay = titik[a]
        dx, dy = titik[b][0] - ax, titik[b][1] - ay
        panjang2 = dx * dx + dy * dy
        jauh2, idx = 0.0, None
        for i in range(a + 1, b):
            px, py = titik[i][0] - ax, titik[i][1] - ay
            if panjang2:
                t = max(0.0, min(1.0, (px * dx + py * dy) / panjang2))
                px, py = px - t * dx, py - t * dy
            d2 = px * px + py * py
            if d2 > jauh2:
                jauh2, idx = d2, i
        if idx is not None and jauh2 > batas2:
            simpan[idx] = True
            tumpukan.extend(((a, idx), (idx, b)))
    return [t for t, s in zip(titik, simpan) if s]


def _ringkas_ring(ring):
    titik = [[round(t[0], PRESISI_PETA), round(t[1], PRESISI_PETA)] for t in ring]
    bersih = [titik[0]]
    for t in titik[1:]:
        if t != bersih[-1]:
            bersih.append(t)
    if len(bersih) < 4:
        return titik
    hasil = _douglas_peucker(bersih, TOLERANSI_PETA)
    return hasil if len(hasil) >= 4 else bersih


def ringkas_geometri(geometri):
    """Geometri (dict tervalidasi) yang dibulatkan dan disederhanakan untuk peta."""
    if geometri['type'] == 'Polygon':
        koordinat = [_ringkas_ring(r) for r in geometri['coordinates']]
    else:
        koordinat = [[_ringkas_ring(r) for r in p] for p in geometri['coordinates']]
    return {'type': geometri['type'], 'coordinates': koordinat}


def _kotak_batas(geometri, perlebar=0.0):
    """Kotak batas (min_x, min_y, maks_x, maks_y) geometri, diperlebar sekian kali ukurannya."""
    poligon_list = ([geometri['coordinates']] if geometri['type'] == 'Polygon'
                    else geometri['coordinates'])
    xs = [t[0] for p in poligon_list for r in p for t in r]
    ys = [t[1] for p in poligon_list for r in p for t in r]
    dx, dy = (max(xs) - min(xs)) * perlebar, (max(ys) - min(ys)) * perlebar
    return (min(xs) - dx, min(ys) - dy, max(xs) + dx, max(ys) + dy)


def _kotak_bersinggungan(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


class SatuDataGeojsonMixin(models.AbstractModel):
    """Field batas wilayah (GeoJSON) beserta validasinya.

    Isi yang diterima: objek geometri bertipe Polygon atau MultiPolygon, atau
    sebuah Feature yang geometrinya bertipe tersebut. Koordinat urutan GeoJSON:
    [bujur, lintang].
    """
    _name        = 'satu_data.geojson.mixin'
    _description = 'Mixin Batas Wilayah (GeoJSON)'

    # prefetch=False: teks batas wilayah resmi bisa berukuran besar; jangan ikut
    # terbaca setiap kali record dibuka di list atau dashboard.
    geojson = fields.Text(
        'Batas Wilayah (GeoJSON)', prefetch=False,
        help='Geometri GeoJSON bertipe Polygon atau MultiPolygon. '
             'Koordinat berurutan [bujur, lintang].',
    )
    geojson_peta = fields.Text(
        'Geometri Peta', compute='_compute_geojson_peta', store=True,
        help='Geometri yang sudah divalidasi dan disederhanakan untuk dashboard peta.',
    )

    @api.depends('geojson')
    def _compute_geojson_peta(self):
        for rec in self:
            try:
                geometri = rec._sd_parse_geojson(rec.geojson) if rec.geojson else None
            except ValidationError:
                geometri = None  # constraint _check_geojson yang menolak isinya
            rec.geojson_peta = (json.dumps(ringkas_geometri(geometri), separators=(',', ':'))
                                if geometri else False)

    @api.constrains('geojson')
    def _check_geojson(self):
        for rec in self:
            if rec.geojson:
                rec._sd_parse_geojson(rec.geojson)

    # ── Helper ────────────────────────────────────────────────────────────────

    @api.model
    def _sd_parse_geojson(self, teks):
        """Ubah teks GeoJSON menjadi dict geometri yang sudah divalidasi.

        :raises ValidationError: bila bukan JSON, bukan Polygon/MultiPolygon,
            atau struktur koordinatnya tidak sah.
        """
        _ = self.env._
        try:
            data = json.loads(teks)
        except (TypeError, ValueError) as e:
            raise ValidationError(_('GeoJSON bukan JSON yang valid: %(err)s', err=e)) from e

        if not isinstance(data, dict):
            raise ValidationError(_('GeoJSON harus berupa objek JSON.'))

        if data.get('type') == 'Feature':
            data = data.get('geometry') or {}
            if not isinstance(data, dict):
                raise ValidationError(_('Feature GeoJSON tidak memiliki geometri.'))

        tipe = data.get('type')
        if tipe not in TIPE_GEOMETRI:
            raise ValidationError(_(
                'Tipe geometri harus Polygon atau MultiPolygon, bukan "%(tipe)s".',
                tipe=tipe or '-',
            ))

        koordinat = data.get('coordinates')
        poligon_list = [koordinat] if tipe == 'Polygon' else koordinat
        if not isinstance(poligon_list, list) or not poligon_list:
            raise ValidationError(_('Koordinat geometri kosong atau tidak sah.'))
        for poligon in poligon_list:
            self._sd_cek_poligon(poligon)

        return {'type': tipe, 'coordinates': koordinat}

    @api.model
    def _sd_cek_poligon(self, poligon):
        _ = self.env._
        if not isinstance(poligon, list) or not poligon:
            raise ValidationError(_('Polygon harus berisi minimal satu ring koordinat.'))
        for ring in poligon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValidationError(_('Setiap ring Polygon minimal berisi 4 titik.'))
            for titik in ring:
                if (not isinstance(titik, list) or len(titik) < 2
                        or not all(isinstance(v, numbers.Real) and not isinstance(v, bool)
                                   for v in titik[:2])):
                    raise ValidationError(_('Titik koordinat harus berupa [bujur, lintang].'))
                bujur, lintang = titik[0], titik[1]
                if not (-180 <= bujur <= 180 and -90 <= lintang <= 90):
                    raise ValidationError(_(
                        'Koordinat [%(bujur)s, %(lintang)s] di luar jangkauan. '
                        'Pastikan urutannya [bujur, lintang].',
                        bujur=bujur, lintang=lintang,
                    ))
            if ring[0][:2] != ring[-1][:2]:
                raise ValidationError(_('Ring Polygon harus tertutup (titik awal = titik akhir).'))

    # ── Editor peta (widget sd_geojson_peta) ─────────────────────────────────

    @api.model
    def sd_info_editor_peta(self, record_id=False, company_id=False, kecamatan_id=False):
        """Data pendukung editor batas wilayah di form.

        :return: ``pembanding`` (batas wilayah sekitar, sebagai acuan saat menggeser
            titik), ``induk`` (batas wilayah induk, bila ada) dan ``peta_dasar``.
        """
        domain = self._sd_domain_pembanding(company_id, kecamatan_id)
        domain.append(('geojson_peta', '!=', False))
        record = self.browse(int(record_id)).exists() if record_id else self.browse()
        if record:
            domain.append(('id', '!=', record.id))
        induk = self._sd_geometri_induk(kecamatan_id)

        # Hanya wilayah di sekitar record (kotak batas diperlebar), agar data yang
        # dikirim tetap kecil walau jumlah desanya ratusan.
        acuan = (record and record._sd_geometri()) or induk
        kotak = _kotak_batas(acuan, perlebar=0.25) if acuan else None
        pembanding = []
        for r in self.search(domain):
            geometri = r._sd_geometri()
            if kotak and not _kotak_bersinggungan(kotak, _kotak_batas(geometri)):
                continue
            pembanding.append({'nama': r.display_name, 'geometri': geometri})
        return {
            'pembanding': pembanding,
            'induk': induk,
            'peta_dasar': self.env['satu_data.peta.mixin']._sd_peta_dasar(),
        }

    @api.model
    def _sd_domain_pembanding(self, company_id, kecamatan_id):
        return [('company_id', '=', int(company_id))] if company_id else []

    @api.model
    def _sd_geometri_induk(self, kecamatan_id):
        return None

    def _sd_geometri(self):
        """Geometri peta record ini sebagai dict, atau None bila kosong.

        Memakai ``geojson_peta`` yang sudah divalidasi dan disederhanakan saat
        disimpan, sehingga dashboard tidak mem-parse ulang batas wilayah mentah.
        """
        self.ensure_one()
        return json.loads(self.geojson_peta) if self.geojson_peta else None
