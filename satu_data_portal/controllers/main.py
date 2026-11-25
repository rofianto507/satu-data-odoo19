import json
import re
from urllib.parse import urlencode

from odoo import http
from odoo.http import content_disposition, request

from odoo.addons.satu_data_portal.models.daftar_data import URUTAN

from . import batas
from .unduhan import FORMAT, isi_csv, isi_json, isi_xlsx

PER_HALAMAN = 20
BULAN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus',
         'September', 'Oktober', 'November', 'Desember']
# Perayap mesin pencari dan pratinjau tautan tidak dihitung sebagai kunjungan/unduhan.
POLA_BOT = re.compile(r'bot|crawl|spider|slurp|facebookexternalhit|preview|lighthouse',
                      re.IGNORECASE)


def angka_param(nilai):
    """Parameter URL ke int positif; selain itu None (parameter asal-asalan diabaikan)."""
    try:
        nilai = int(nilai)
    except (TypeError, ValueError):
        return None
    return nilai if nilai > 0 else None


def tanggal_id(dt):
    if not dt:
        return False
    return f'{dt.day} {BULAN[dt.month - 1]} {dt.year}'


def catat_statistik(data, jenis):
    """Catat kunjungan/unduhan, kecuali dari perayap."""
    if POLA_BOT.search(request.httprequest.user_agent.string or ''):
        return
    request.env['satu_data.portal.statistik'].sudo()._sd_catat(data, jenis)


def terlalu_sering():
    """Respons 429 bila IP ini melebihi batas permintaan per menit, selain itu None."""
    if not batas.melebihi_batas(request.httprequest.remote_addr):
        return None
    return request.make_response(
        'Terlalu banyak permintaan. Coba lagi sebentar lagi.', status=429,
        headers=[('Content-Type', 'text/plain; charset=utf-8'),
                 ('Retry-After', str(batas.detik_ke_menit_berikutnya()))])


class SatuDataPortal(http.Controller):

    def _company(self):
        return request.website.company_id

    # ── Katalog ──────────────────────────────────────────────────────────────

    @http.route(['/data', '/data/page/<int:page>'], type='http', auth='public', website=True,
                sitemap=True, readonly=True)
    def katalog(self, page=1, q='', instansi=None, urusan=None, topik=None, tahun=None,
                urut='terbaru', **_kw):
        company = self._company()
        q = (q or '').strip()[:100]
        saringan = {'instansi': angka_param(instansi), 'urusan': angka_param(urusan),
                    'topik': angka_param(topik), 'tahun': angka_param(tahun)}
        urut = urut if urut in URUTAN else 'terbaru'
        Data = request.env['satu_data.data']
        hasil, faset = Data._sd_cari_publik(company, cari=q, urut=urut, **saringan)

        param = {'q': q, 'urut': urut if urut != 'terbaru' else '', **saringan}
        param = {k: v for k, v in param.items() if v}

        def url(ubah=None):
            """URL katalog dengan parameter sekarang diubah (nilai kosong = dihapus);
            halaman selalu kembali ke 1."""
            baru = {k: v for k, v in dict(param, **(ubah or {})).items() if v}
            return '/data' + (f'?{urlencode(baru)}' if baru else '')

        pager = request.website.pager(url='/data', url_args=param, total=len(hasil),
                                      page=page, step=PER_HALAMAN, scope=5)
        halaman = hasil[pager['offset']:pager['offset'] + PER_HALAMAN]
        frekuensi = dict(Data._fields['frekuensi']._description_selection(request.env))
        dilihat = Data._sd_popularitas(company)

        def item_faset(nama, counter, label, kunci):
            return [{'nama': nama, 'id': rec if nama == 'tahun' else rec.id,
                     'label': label(rec), 'jumlah': n}
                    for rec, n in sorted(counter.items(), key=lambda x: kunci(x[0]))]

        def ringkas(teks, batas_huruf=220):
            teks = ' '.join((teks or '').split())
            if len(teks) <= batas_huruf:
                return teks
            return teks[:batas_huruf].rsplit(' ', 1)[0] + '…'

        def rentang(tahun_list):
            if len(tahun_list) > 1:
                return f'{tahun_list[-1]}–{tahun_list[0]}'
            return str(tahun_list[0])

        return request.render('satu_data_portal.katalog', {
            'q': q,
            'urut': urut,
            'saringan': saringan,
            'url': url,
            'pager': pager,
            'jumlah': len(hasil),
            'daftar': [{
                'data': d,
                'ringkasan': ringkas(d.definisi),
                'frekuensi': frekuensi.get(d.frekuensi, ''),
                'tahun': rentang(info['tahun']),
                'terakhir': tanggal_id(info['terakhir']),
                'dilihat': dilihat.get(d.id, 0),
            } for d, info in halaman],
            'faset': [
                ('Produsen Data', item_faset('instansi', faset['instansi'],
                                             lambda r: r.singkatan or r.name,
                                             lambda r: (r.sequence, r.name))),
                ('Topik', item_faset('topik', faset['topik'], lambda r: r.name,
                                     lambda r: (r.sequence, r.name))),
                ('Urusan', item_faset('urusan', faset['urusan'], lambda r: r.name,
                                      lambda r: r.kode or '')),
                ('Tahun', item_faset('tahun', faset['tahun'], str, lambda t: -t)),
            ],
            'ada_filter': any(saringan.values()) or bool(q),
            'nama_wilayah': Data._sd_nama_wilayah(company),
        })

    # ── Halaman data ─────────────────────────────────────────────────────────

    def _data_atau_404(self, kode):
        data, info = request.env['satu_data.data']._sd_cari_kode_publik(self._company(), kode)
        if not data:
            raise request.not_found()
        return data, info

    @http.route('/data/<string:kode>', type='http', auth='public', website=True, sitemap=False)
    def halaman_data(self, kode, tahun=None, **_kw):
        data, info = self._data_atau_404(kode)
        catat_statistik(data, 'kunjungan')
        Data = request.env['satu_data.data']
        tabel = data._sd_tabel_publik(angka_param(tahun))
        return request.render('satu_data_portal.halaman_data', {
            'data': data,
            'tabel': tabel,
            'metadata': data._sd_metadata_publik(info),
            'terakhir': tanggal_id(info['terakhir']),
            'grafik_json': json.dumps(data._sd_grafik_publik(tabel)),
            'frekuensi': dict(Data._fields['frekuensi']._description_selection(request.env)).get(
                data.frekuensi, ''),
            'nama_wilayah': Data._sd_nama_wilayah(data.company_id),
            'statistik': request.env['satu_data.portal.statistik']._sd_jumlah(data),
            'url_api': f'/api/satu-data/v1/data/{data.kode}/nilai',
        })

    @http.route('/data/<string:kode>/unduh/<string:format_>', type='http', auth='public',
                website=True, sitemap=False)
    def unduh(self, kode, format_, **_kw):
        if format_ not in FORMAT:
            raise request.not_found()
        data, info = self._data_atau_404(kode)
        if respons := terlalu_sering():
            return respons
        baris = data._sd_baris_publik()
        if format_ == 'csv':
            isi = isi_csv(baris)
        elif format_ == 'json':
            isi = isi_json(data._sd_metadata_json(info), baris)
        else:
            Data = request.env['satu_data.data']
            sumber = (f'Sumber: {data.instansi_id.name or "Produsen Data"}, diperiksa Walidata. '
                      f'Portal Satu Data {Data._sd_nama_wilayah(data.company_id)}.')
            metadata = [(label, teks) for _k, label, teks in data._sd_metadata_publik(info)]
            isi = isi_xlsx(data.name, metadata, data._sd_tabel_publik(semua=True), baris, sumber)
        catat_statistik(data, 'unduhan')
        jenis, ekstensi = FORMAT[format_]
        return request.make_response(isi, headers=[
            ('Content-Type', jenis),
            ('Content-Disposition', content_disposition(f'{data.kode}.{ekstensi}')),
            ('Cache-Control', 'no-store'),
        ])

    # ── Dokumentasi API ──────────────────────────────────────────────────────

    @http.route('/data/api', type='http', auth='public', website=True, sitemap=True,
                readonly=True)
    def dokumentasi_api(self, **_kw):
        hasil, _faset = request.env['satu_data.data']._sd_cari_publik(self._company())
        return request.render('satu_data_portal.dokumentasi_api', {
            'dasar': request.httprequest.host_url.rstrip('/') + '/api/satu-data/v1',
            'contoh': hasil[0][0].kode if hasil else 'kependudukan.jumlah_penduduk',
            'batas': batas.BATAS_PER_MENIT,
        })
