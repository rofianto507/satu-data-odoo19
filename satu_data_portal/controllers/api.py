"""API baca publik Satu Data (JSON, tanpa login).

Aturan publik sama dengan portal (``satu_data.data._sd_cari_publik``): hanya data terbuka
yang sudah terbit, paling rendah tingkat kecamatan. Dokumentasi: halaman ``/data/api``.
"""
from odoo import http
from odoo.http import request

from odoo.addons.satu_data_portal.models.daftar_data import URUTAN

from . import batas
from .main import angka_param

AWALAN = '/api/satu-data/v1'
PER_HALAMAN_BAWAAN = 20
PER_HALAMAN_MAKS = 100


def _json(isi, status=200):
    # Header CORS dipasang Odoo dari opsi ``cors`` di rute.
    return request.make_json_response(isi, status=status, headers=[
        ('Cache-Control', 'public, max-age=300'),
        ('Vary', 'Authorization, X-API-Key'),
        ('X-Content-Type-Options', 'nosniff'),
    ])


def _galat(status, pesan):
    return _json({'error': {'code': status, 'message': pesan}}, status=status)


def rute(path):
    """Rute GET publik untuk API (CORS terbuka). Tidak ``readonly``: pemakaian kunci API dicatat
    dalam transaksi yang sama."""
    return http.route(AWALAN + path, type='http', auth='public', methods=['GET'], cors='*',
                      csrf=False, website=True, sitemap=False)


class SatuDataApi(http.Controller):

    def _company(self):
        return request.website.company_id

    def _url(self, path):
        return request.httprequest.host_url.rstrip('/') + path

    def _ringkas(self, data, info):
        frekuensi = dict(data._fields['frekuensi']._description_selection(request.env))
        return {
            'kode': data.kode,
            'nama': data.name,
            'produsen_data': data.instansi_id.name or None,
            'topik': data.topik_id.name or None,
            'urusan': data.urusan_id.display_name or None,
            'frekuensi': frekuensi.get(data.frekuensi),
            'satuan': data.satuan or None,
            'tahun_tersedia': sorted(info['tahun']),
            'terakhir_diperbarui': (info['terakhir'].date().isoformat()
                                    if info['terakhir'] else None),
            'url': self._url(f'/data/{data.kode}'),
            'url_nilai': self._url(f'{AWALAN}/data/{data.kode}/nilai'),
        }

    def _kunci_dari_header(self):
        """Kunci API dari ``X-API-Key`` atau ``Authorization: Bearer``; '' bila tidak ada."""
        header = request.httprequest.headers
        kunci = (header.get('X-API-Key') or '').strip()
        if not kunci:
            auth = header.get('Authorization') or ''
            if auth[:7].lower() == 'bearer ':
                kunci = auth[7:].strip()
        return kunci

    def _batas(self):
        """Periksa kunci (bila dikirim) dan batas permintaan; kembalikan respons galat atau None.

        Tanpa kunci: batas per IP. Dengan kunci sah: batas milik kunci itu (lebih longgar) dan
        pemakaiannya dicatat. Kunci yang dikirim tetapi tidak sah ditolak (401), bukan
        diperlakukan seperti tanpa kunci, agar salah konfigurasi segera ketahuan.
        """
        kunci = self._kunci_dari_header()
        if kunci:
            rec = request.env['satu_data.api.key']._sd_verifikasi(kunci, self._company())
            if not rec:
                respons = _galat(401, 'Kunci API tidak valid atau tidak aktif.')
                respons.headers['WWW-Authenticate'] = 'Bearer realm="satu-data"'
                return respons
            if batas.melebihi_batas(f'kunci:{rec.id}', rec.sudo().batas_per_menit):
                return self._terlalu_sering()
            rec._sd_catat_pemakaian()
            return None
        if batas.melebihi_batas(request.httprequest.remote_addr):
            return self._terlalu_sering()
        return None

    def _terlalu_sering(self):
        respons = _galat(429, 'Terlalu banyak permintaan. Coba lagi sebentar lagi.')
        respons.headers['Retry-After'] = str(batas.detik_ke_menit_berikutnya())
        return respons

    # ── Daftar data ──────────────────────────────────────────────────────────

    @rute('/data')
    def daftar_data(self, q='', instansi=None, urusan=None, topik=None, tahun=None,
                    urut='terbaru', halaman=1, per_halaman=PER_HALAMAN_BAWAAN, **_kw):
        if respons := self._batas():
            return respons
        urut = urut if urut in URUTAN else 'terbaru'
        hasil, _faset = request.env['satu_data.data']._sd_cari_publik(
            self._company(), cari=(q or '').strip()[:100], urut=urut,
            instansi=angka_param(instansi), urusan=angka_param(urusan),
            topik=angka_param(topik), tahun=angka_param(tahun))
        halaman = angka_param(halaman) or 1
        per_halaman = min(angka_param(per_halaman) or PER_HALAMAN_BAWAAN, PER_HALAMAN_MAKS)
        awal = (halaman - 1) * per_halaman
        return _json({
            'total': len(hasil),
            'halaman': halaman,
            'per_halaman': per_halaman,
            'data': [self._ringkas(d, i) for d, i in hasil[awal:awal + per_halaman]],
        })

    # ── Satu data ────────────────────────────────────────────────────────────

    def _cari(self, kode):
        return request.env['satu_data.data']._sd_cari_kode_publik(self._company(), kode)

    @rute('/data/<string:kode>')
    def metadata(self, kode, **_kw):
        if respons := self._batas():
            return respons
        data, info = self._cari(kode)
        if not data:
            return _galat(404, 'Data tidak ditemukan atau tidak terbuka untuk publik.')
        return _json({
            'metadata': data._sd_metadata_json(info),
            'periode': [{
                'nama': p.name, 'tahun': p.tahun,
                'tanggal_mulai': p.tanggal_mulai.isoformat(),
                'tanggal_akhir': p.tanggal_akhir.isoformat(),
            } for p in data._sd_periode_publik()],
            'unduhan': {f: self._url(f'/data/{data.kode}/unduh/{f}') for f in ('csv', 'xlsx', 'json')},
            'url': self._url(f'/data/{data.kode}'),
            'url_nilai': self._url(f'{AWALAN}/data/{data.kode}/nilai'),
        })

    @rute('/data/<string:kode>/nilai')
    def nilai(self, kode, tahun=None, wilayah=None, **_kw):
        """Nilai format panjang. Saring dengan ``tahun`` dan/atau ``wilayah`` (kode wilayah)."""
        if respons := self._batas():
            return respons
        data, info = self._cari(kode)
        if not data:
            return _galat(404, 'Data tidak ditemukan atau tidak terbuka untuk publik.')
        periode = data._sd_periode_publik()
        tahun = angka_param(tahun)
        if tahun:
            periode = periode.filtered(lambda p: p.tahun == tahun)
        baris = data._sd_baris_publik(periode)
        if wilayah:
            baris = [b for b in baris if b['kode_wilayah'] == wilayah]
        return _json({
            'metadata': {'kode': data.kode, 'nama': data.name, 'satuan': data.satuan or None,
                         'produsen_data': data.instansi_id.name or None},
            'jumlah': len(baris),
            'data': baris,
        })

    # ── Referensi ────────────────────────────────────────────────────────────

    @rute('/wilayah')
    def wilayah(self, **_kw):
        if respons := self._batas():
            return respons
        company = self._company()
        Data = request.env['satu_data.data']
        kecamatan = request.env['satu_data.kecamatan'].sudo().search(
            [('company_id', '=', company.id)])
        return _json({
            'kabupaten_kota': {'kode': company.sd_kode_wilayah or None,
                               'nama': Data._sd_nama_wilayah(company)},
            'kecamatan': [{'kode': k.kode or None, 'nama': k.name} for k in kecamatan],
        })

    @rute('/referensi')
    def referensi(self, **_kw):
        """Nilai yang bisa dipakai untuk menyaring ``/data`` (instansi, topik, urusan, tahun)."""
        if respons := self._batas():
            return respons
        _hasil, faset = request.env['satu_data.data']._sd_cari_publik(self._company())

        def daftar(counter, label):
            return [{'id': r.id, 'nama': label(r), 'jumlah_data': n}
                    for r, n in sorted(counter.items(), key=lambda x: label(x[0]))]

        return _json({
            'instansi': daftar(faset['instansi'], lambda r: r.name),
            'topik': daftar(faset['topik'], lambda r: r.name),
            'urusan': daftar(faset['urusan'], lambda r: r.display_name),
            'tahun': sorted(faset['tahun'], reverse=True),
        })
