"""Beranda portal, dashboard tematik publik, dan halaman Tentang."""
import json

from odoo import http
from odoo.http import request

from odoo.addons.satu_data.models.peta import PETA_DASAR
from odoo.addons.satu_data_portal.models.daftar_data import format_angka

from .main import tanggal_id, terlalu_sering

JUMLAH_SOROTAN = 5


def _json(isi, status=200, max_age=300):
    return request.make_json_response(isi, status=status, headers=[
        ('Cache-Control', f'public, max-age={max_age}')])


class SatuDataBeranda(http.Controller):

    def _company(self):
        return request.website.company_id

    def _peta_dasar(self):
        """Peta dasar bawaan (sama dengan dashboard internal) untuk peta publik."""
        info = request.env['satu_data.peta.mixin']._sd_peta_dasar()
        pilihan = {p['kode']: p for p in info['pilihan']}
        return pilihan.get(info['bawaan']) or next(
            (p for p in PETA_DASAR if p['kode'] == 'osm'), False)

    # ── Beranda ──────────────────────────────────────────────────────────────

    @http.route('/beranda', type='http', auth='public', website=True, sitemap=False,
                readonly=True)
    def beranda(self, **_kw):
        company = self._company()
        Data = request.env['satu_data.data']
        hasil, faset = Data._sd_cari_publik(company)
        skor = Data._sd_popularitas(company)
        populer = sorted((di for di in hasil if skor.get(di[0].id)),
                         key=lambda di: skor[di[0].id], reverse=True)[:JUMLAH_SOROTAN]
        statistik = request.env['satu_data.portal.statistik']._sd_total(company)
        return request.render('satu_data_portal.beranda', {
            'nama_wilayah': Data._sd_nama_wilayah(company),
            'logo': f'/logo.png?company={company.id}' if company.sudo().logo else False,
            'angka': {k: format_angka(v) for k, v in {
                'data': len(hasil),
                'produsen': len(faset['instansi']),
                'topik': len(faset['topik']),
                **statistik,
            }.items()},
            'tema': Data._sd_tema_publik(company),
            'terbaru': [{'data': d, 'terakhir': tanggal_id(i['terakhir'])}
                        for d, i in hasil[:JUMLAH_SOROTAN]],
            'populer': [{'data': d, 'skor': skor[d.id]} for d, _i in populer],
            'produsen': sorted(faset['instansi'].items(), key=lambda x: (x[0].sequence, x[0].name)),
        })

    # ── Dashboard tematik ────────────────────────────────────────────────────

    @http.route('/dashboard', type='http', auth='public', website=True, sitemap=True,
                readonly=True)
    def daftar_dashboard(self, **_kw):
        company = self._company()
        Data = request.env['satu_data.data']
        tema = Data._sd_tema_publik(company)
        return request.render('satu_data_portal.daftar_dashboard', {
            'nama_wilayah': Data._sd_nama_wilayah(company),
            'tema': tema,
            'ada_peta': any(t['jumlah_peta'] for t in tema),
        })

    @http.route('/dashboard/<int:topik_id>', type='http', auth='public', website=True,
                sitemap=False, readonly=True)
    def dashboard(self, topik_id, data=None, **_kw):
        company = self._company()
        Data = request.env['satu_data.data']
        topik = request.env['satu_data.topik'].sudo().browse(topik_id).exists()
        if not topik:
            raise request.not_found()
        hasil, _faset = Data._sd_cari_publik(company, topik=topik.id, urut='abjad')
        if not hasil:
            raise request.not_found()
        pilihan = [d for d, _i in hasil]
        terpilih = next((d for d in pilihan if d.kode == data), None) or next(
            (d for d in pilihan if d.jenis == 'indikator' and d.tingkat_penyajian != 'kabupaten'),
            pilihan[0])
        kelompok = [
            ('Indikator', [d for d in pilihan if d.jenis == 'indikator']),
            ('Data dasar', [d for d in pilihan if d.jenis != 'indikator']),
        ]
        return request.render('satu_data_portal.dashboard', {
            'topik': topik,
            'nama_wilayah': Data._sd_nama_wilayah(company),
            'kelompok': [(label, isi) for label, isi in kelompok if isi],
            'terpilih': terpilih,
            'tema_lain': [t for t in Data._sd_tema_publik(company) if t['topik'] != topik],
            'konfigurasi': json.dumps({
                'peta_dasar': self._peta_dasar(),
                'url_peta': '/dashboard/peta.json',
            }),
        })

    @http.route('/dashboard/peta.json', type='http', auth='public', website=True,
                sitemap=False, readonly=True)
    def peta(self, **_kw):
        company = self._company()
        return _json(request.env['satu_data.kecamatan']._sd_peta_publik(company.id), max_age=3600)

    @http.route('/dashboard/data/<string:kode>.json', type='http', auth='public', website=True,
                sitemap=False, readonly=True)
    def data_dashboard(self, kode, **_kw):
        if respons := terlalu_sering():
            return respons
        data, _info = request.env['satu_data.data']._sd_cari_kode_publik(self._company(), kode)
        if not data:
            return _json({'error': {'code': 404, 'message': 'Data tidak ditemukan.'}}, status=404)
        return _json(data._sd_dasbor_publik())

    # ── Tentang ──────────────────────────────────────────────────────────────

    @http.route('/tentang', type='http', auth='public', website=True, sitemap=True,
                readonly=True)
    def tentang(self, **_kw):
        company = self._company()
        Data = request.env['satu_data.data']
        _hasil, faset = Data._sd_cari_publik(company)
        Instansi = request.env['satu_data.instansi'].sudo()
        peran = dict(Instansi._fields['peran']._description_selection(request.env))
        instansi = Instansi.search([('company_id', '=', company.id)], order='sequence, name')
        jumlah = {i.id: n for i, n in faset['instansi'].items()}
        return request.render('satu_data_portal.tentang', {
            'nama_wilayah': Data._sd_nama_wilayah(company),
            'penyelenggara': [{
                'peran': label,
                'instansi': [{'rec': i, 'jumlah': jumlah.get(i.id, 0)}
                             for i in instansi if i.peran == kode],
            } for kode, label in peran.items() if any(i.peran == kode for i in instansi)],
            'walidata': instansi.filtered(lambda i: i.peran == 'walidata')[:1],
        })
