"""Formulir permintaan data (tanpa login) dan halaman status permintaan.

Lapisan pengaman: token CSRF (bawaan Odoo), kolom jebakan (honeypot), tanda waktu bertanda
tangan (terlalu cepat atau kedaluwarsa ditolak), batas kiriman per IP, batas panjang isian,
dan keluaran selalu di-escape. Halaman status hanya bisa dibuka dengan token acak 192 bit dan
tidak menampilkan data kontak pemohon.
"""
import hmac
import re
import time

from odoo import http
from odoo.http import request
from odoo.tools import misc

from odoo.addons.satu_data_portal.models.permintaan import (
    JENIS, MAKS, MIN_URAIAN, PEMOHON, POLA_EMAIL, POLA_TELEPON, STATUS)

from . import batas

MIN_DETIK = 3              # dikirim lebih cepat dari ini dianggap robot
MAKS_UMUR_DETIK = 7200     # formulir yang dibuka lebih dari 2 jam lalu kedaluwarsa
BATAS_KIRIM = 5            # permintaan per IP per jam
JENDELA_DETIK = 3600
RUANG_HMAC = 'satu_data_portal.permintaan'
POLA_TOKEN = re.compile(r'^[A-Za-z0-9_\-]{20,64}$')
POLA_KONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def bersih(teks, maks, satu_baris=True):
    """Hapus karakter kontrol, rapikan spasi, dan potong ke ``maks`` + 1 (agar kelebihan
    terdeteksi oleh validasi, bukan terpotong diam-diam)."""
    teks = POLA_KONTROL.sub('', str(teks or '')).replace('\r\n', '\n').replace('\r', '\n')
    if satu_baris:
        teks = ' '.join(teks.split())
    else:
        teks = '\n'.join(' '.join(baris.split()) for baris in teks.split('\n')).strip()
    return teks[:maks + 1]


def tanda_waktu():
    """Nilai kolom tersembunyi ``dibuka``: waktu pembukaan formulir + tanda tangan HMAC."""
    ts = int(time.time())
    return f'{ts}.{_tanda(ts)}'


def _tanda(ts):
    return misc.hmac(request.env(su=True), RUANG_HMAC, str(ts))


def periksa_tanda_waktu(nilai):
    """``'ok'``, ``'cepat'``, ``'kedaluwarsa'``, atau ``'salah'``."""
    try:
        ts_teks, tanda = str(nilai or '').split('.', 1)
        ts = int(ts_teks)
    except ValueError:
        return 'salah'
    if not hmac.compare_digest(tanda, _tanda(ts)):
        return 'salah'
    umur = time.time() - ts
    if umur < MIN_DETIK:
        return 'cepat'
    if umur > MAKS_UMUR_DETIK:
        return 'kedaluwarsa'
    return 'ok'


class SatuDataPermintaan(http.Controller):

    def _company(self):
        return request.website.company_id

    def _data_terkait(self, kode):
        if not kode:
            return None
        data, _info = request.env['satu_data.data']._sd_cari_kode_publik(self._company(), kode)
        return data

    def _render_form(self, nilai, galat, data, status=200):
        respons = request.render('satu_data_portal.permintaan_form', {
            'nilai': nilai,
            'galat': galat,
            'data': data,
            'jenis_daftar': JENIS,
            'pemohon_daftar': PEMOHON,
            'dibuka': tanda_waktu(),
            'maks': MAKS,
            'min_uraian': MIN_URAIAN,
        })
        respons.status_code = status
        respons.headers['Cache-Control'] = 'no-store'
        return respons

    @http.route('/permintaan', type='http', auth='public', methods=['GET', 'POST'],
                website=True, sitemap=True)
    def permintaan(self, **post):
        if request.httprequest.method == 'POST':
            return self._kirim(post)
        data = self._data_terkait(post.get('data'))
        jenis = post.get('jenis') if post.get('jenis') in dict(JENIS) else 'data'
        awal = {'jenis': jenis}
        if data:
            awal['uraian'] = f'Data: {data.name} ({data.kode})\n'
        return self._render_form(awal, {}, data)

    def _kirim(self, post):
        if batas.melebihi_batas_jendela(request.httprequest.remote_addr, 'permintaan',
                                        BATAS_KIRIM, JENDELA_DETIK):
            return request.make_response(
                'Terlalu banyak permintaan dari alamat ini. Coba lagi nanti.', status=429,
                headers=[('Content-Type', 'text/plain; charset=utf-8'),
                         ('Retry-After', str(JENDELA_DETIK))])
        # Kolom jebakan: manusia tidak melihatnya, robot biasanya mengisinya. Pura-pura berhasil.
        if post.get('situs_web'):
            return request.render('satu_data_portal.permintaan_terima_kasih', {})

        nilai = {
            'jenis': post.get('jenis'),
            'pemohon_jenis': post.get('pemohon_jenis'),
            'nama_pemohon': bersih(post.get('nama_pemohon'), MAKS['nama']),
            'email': bersih(post.get('email'), MAKS['email']),
            'telepon': bersih(post.get('telepon'), MAKS['telepon']),
            'organisasi': bersih(post.get('organisasi'), MAKS['organisasi']),
            'uraian': bersih(post.get('uraian'), MAKS['uraian'], satu_baris=False),
            'tujuan': bersih(post.get('tujuan'), MAKS['tujuan'], satu_baris=False),
            'data': post.get('data'),
            'setuju': bool(post.get('setuju')),
        }
        data = self._data_terkait(nilai['data'])
        galat = {}

        waktu = periksa_tanda_waktu(post.get('dibuka'))
        if waktu != 'ok':
            galat['_umum'] = {
                'cepat': 'Formulir dikirim terlalu cepat. Silakan kirim sekali lagi.',
                'kedaluwarsa': 'Formulir sudah kedaluwarsa. Silakan periksa isian lalu kirim ulang.',
                'salah': 'Formulir tidak valid. Muat ulang halaman lalu coba lagi.',
            }[waktu]
        if nilai['jenis'] not in dict(JENIS):
            galat['jenis'] = 'Pilih jenis permintaan.'
        if nilai['pemohon_jenis'] not in dict(PEMOHON):
            galat['pemohon_jenis'] = 'Pilih jenis pemohon.'
        if len(nilai['nama_pemohon']) < 2:
            galat['nama_pemohon'] = 'Isi nama Anda.'
        elif len(nilai['nama_pemohon']) > MAKS['nama']:
            galat['nama_pemohon'] = f'Maksimal {MAKS["nama"]} karakter.'
        if not POLA_EMAIL.match(nilai['email']) or len(nilai['email']) > MAKS['email']:
            galat['email'] = 'Isi alamat email yang valid.'
        if nilai['telepon'] and not POLA_TELEPON.match(nilai['telepon']):
            galat['telepon'] = 'Nomor telepon tidak valid.'
        if len(nilai['organisasi']) > MAKS['organisasi']:
            galat['organisasi'] = f'Maksimal {MAKS["organisasi"]} karakter.'
        for kunci, label in (('uraian', 'uraian permintaan'), ('tujuan', 'tujuan penggunaan')):
            if len(nilai[kunci]) < MIN_URAIAN:
                galat[kunci] = f'Jelaskan {label} (minimal {MIN_URAIAN} karakter).'
            elif len(nilai[kunci]) > MAKS[kunci]:
                galat[kunci] = f'Maksimal {MAKS[kunci]} karakter.'
        if not nilai['setuju']:
            galat['setuju'] = 'Centang persetujuan penggunaan data kontak.'
        if galat:
            return self._render_form(nilai, galat, data, status=400)

        rec = request.env['satu_data.permintaan'].sudo().create({
            'company_id': self._company().id,
            'jenis': nilai['jenis'],
            'pemohon_jenis': nilai['pemohon_jenis'],
            'nama_pemohon': nilai['nama_pemohon'],
            'email': nilai['email'],
            'telepon': nilai['telepon'] or False,
            'organisasi': nilai['organisasi'] or False,
            'uraian': nilai['uraian'],
            'tujuan': nilai['tujuan'],
            'data_id': data.id if data else False,
        })
        return request.redirect(f'/permintaan/{rec.token}')

    @http.route('/permintaan/<string:token>', type='http', auth='public', website=True,
                sitemap=False, readonly=True)
    def status(self, token, **_kw):
        if not POLA_TOKEN.match(token):
            raise request.not_found()
        rec = request.env['satu_data.permintaan'].sudo().search([
            ('token', '=', token), ('company_id', '=', self._company().id)], limit=1)
        if not rec:
            raise request.not_found()
        respons = request.render('satu_data_portal.permintaan_status', {
            'rec': rec,
            'status_label': dict(STATUS)[rec.state],
            'jenis_label': dict(JENIS)[rec.jenis],
            'tanggal': rec.create_date.strftime('%d-%m-%Y'),
            'tanggal_selesai': rec.tanggal_selesai.strftime('%d-%m-%Y') if rec.tanggal_selesai else False,
        })
        # Token ada di URL: jangan di-cache, diindeks mesin pencari, atau dibocorkan lewat Referer.
        respons.headers['Cache-Control'] = 'no-store'
        respons.headers['X-Robots-Tag'] = 'noindex, nofollow'
        respons.headers['Referrer-Policy'] = 'no-referrer'
        return respons
