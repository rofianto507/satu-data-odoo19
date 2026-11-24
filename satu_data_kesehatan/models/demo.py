"""Pembuat data demo kesehatan (CONTOH FIKTIF, bukan data resmi).

Dipanggil sekali dari ``demo/satu_data_kesehatan_demo_rekap.xml`` (hanya di database
dengan data demo). Angka dibangkitkan acak tetapi deterministik (seed tetap) dengan
pola yang masuk akal: capaian berbeda per puskesmas, skrining anak sekolah di
Agustus–November, penimbangan balita Februari dan Agustus, DBD memuncak di musim
hujan, kematian ibu/bayi jarang (Poisson).
"""
import math
import random
from datetime import datetime, time, timedelta

from odoo import api, fields, models

SUMBER_DEMO = 'CONTOH (fiktif), bukan data resmi'
TAHUN_DEMO = (2025, 2026)
BULAN_TERAKHIR_DEMO = (2026, 10)     # rekap demo s.d. Oktober 2026

# Sasaran per penduduk (estimasi lazim untuk proyeksi sasaran program kesehatan).
RASIO_SASARAN = {
    'bayi_baru_lahir': 0.0155,
    'ibu_bersalin':    0.0163,
    'ibu_hamil':       0.0171,
    'bayi':            0.0152,
    'balita':          0.0780,
    'usia_dasar':      0.1400,
    'usia_produktif':  0.6600,
    'usia_lanjut':     0.1150,
    'hipertensi':      0.2770,
    'diabetes':        0.0154,
    'odgj_berat':      0.0011,
    'terduga_tbc':     0.0100,
}
# Capaian tahunan khas per SPM (dikali faktor puskesmas/desa).
CAPAIAN_SPM = {
    'ibu_hamil': 0.90, 'ibu_bersalin': 0.92, 'bayi_baru_lahir': 0.95, 'balita': 0.86,
    'usia_dasar': 0.82, 'usia_produktif': 0.58, 'usia_lanjut': 0.72, 'hipertensi': 0.42,
    'diabetes': 0.76, 'odgj_berat': 0.86, 'terduga_tbc': 0.62, 'risiko_hiv': 0.71,
}
# Bobot musim DBD per bulan (Januari = indeks 0); musim hujan lebih tinggi.
MUSIM_DBD = [2.2, 2.5, 2.2, 1.6, 0.9, 0.5, 0.3, 0.2, 0.2, 0.3, 0.6, 1.5]
KECAMATAN_KOTA = ('Kaliwates', 'Sumbersari', 'Patrang')


def _poisson(rng, lam):
    """Bilangan acak Poisson (Knuth; lam kecil) atau pendekatan normal (lam besar)."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    batas, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= batas:
            return k
        k += 1


class SatuDataKesehatanDemo(models.AbstractModel):
    _name        = 'satu_data.kesehatan.demo'
    _description = 'Pembuat Data Demo Kesehatan'

    @api.model
    def _sd_demo_kesehatan(self):
        company = self.env.ref('base.main_company')
        Rekap = self.env['satu_data.kesehatan.rekap'].with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
        Sasaran = self.env['satu_data.kesehatan.sasaran'].with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
        if Rekap.search_count([('company_id', '=', company.id)], limit=1):
            return False   # sudah ada data: jangan menimpa
        Periode = self.env['satu_data.periode']
        for tahun in TAHUN_DEMO:
            Periode.sd_buat_periode_baku(tahun, 'bulanan')
            Periode.sd_buat_periode_baku(tahun, 'tahunan')

        rng = random.Random(3509)
        desa_semua = self.env['satu_data.desa'].search(
            [('company_id', '=', company.id)], order='kode')
        puskesmas = {d.id: d.sd_puskesmas_id.id for d in desa_semua}
        penduduk = self._sd_demo_penduduk(company, desa_semua, rng)

        # Faktor kinerja: puskesmas (0,85–1,08) x desa (0,92–1,06)
        faktor_pkm = {p: rng.uniform(0.85, 1.08) for p in set(puskesmas.values())}
        faktor = {d.id: faktor_pkm[puskesmas[d.id]] * rng.uniform(0.92, 1.06)
                  for d in desa_semua}
        # Prevalensi stunting dasar per kecamatan (8–24%), turun ~12% per tahun.
        stunting_kec = {k.id: rng.uniform(0.08, 0.24) for k in desa_semua.kecamatan_id}
        kota = {d.id: d.kecamatan_id.name in KECAMATAN_KOTA for d in desa_semua}

        # ── Sasaran tahunan ──────────────────────────────────────────────────
        sasaran = {}
        nilai_sasaran = []
        for tahun in TAHUN_DEMO:
            periode = Periode.search([('frekuensi', '=', 'tahunan'),
                                      ('tanggal_mulai', '=', f'{tahun}-01-01')], limit=1)
            for d in desa_semua:
                pdd = penduduk[d.id] * (1.006 ** (tahun - TAHUN_DEMO[0]))
                s = {k: max(1, round(pdd * r)) for k, r in RASIO_SASARAN.items()}
                s['risiko_hiv'] = s['ibu_hamil'] + max(1, round(pdd * 0.004))
                sasaran[(tahun, d.id)] = s
                vals = {f'sasaran_{k}': v for k, v in s.items()}
                vals.update({'desa_id': d.id, 'periode_id': periode.id,
                             'puskesmas_id': puskesmas[d.id], 'sumber': SUMBER_DEMO})
                nilai_sasaran.append(vals)
        Sasaran.create(nilai_sasaran)

        # ── Rekap bulanan ────────────────────────────────────────────────────
        bulan_list = Periode.search([('frekuensi', '=', 'bulanan'),
                                     ('tanggal_mulai', '>=', f'{TAHUN_DEMO[0]}-01-01'),
                                     ('tanggal_mulai', '<=', '%d-%02d-01' % BULAN_TERAKHIR_DEMO)],
                                    order='tanggal_mulai')
        nilai_rekap = []
        for bulan in bulan_list:
            tahun, b = bulan.tanggal_mulai.year, bulan.tanggal_mulai.month
            for d in desa_semua:
                s = sasaran[(tahun, d.id)]
                f = faktor[d.id]
                vals = {'desa_id': d.id, 'periode_id': bulan.id,
                        'puskesmas_id': puskesmas[d.id], 'sumber': SUMBER_DEMO}
                for kode, capaian in CAPAIAN_SPM.items():
                    if kode == 'usia_dasar':
                        # Penjaringan kesehatan anak sekolah: Agustus–November.
                        bobot = 0.25 if 8 <= b <= 11 else 0.0
                    else:
                        bobot = 1 / 12
                    harapan = s[kode] * min(capaian * f, 1.02) * bobot * rng.uniform(0.85, 1.15)
                    vals[f'layanan_{kode}'] = max(0, round(harapan))
                vals['bayi_idl'] = max(0, round(s['bayi'] / 12 * min(0.91 * f, 1.0)
                                                * rng.uniform(0.85, 1.15)))
                if b in (2, 8):
                    diukur = round(s['balita'] * min(0.88 * f, 0.98))
                    prev = stunting_kec[d.kecamatan_id.id] * (0.88 ** (tahun - TAHUN_DEMO[0])) \
                        * (0.97 if b == 8 else 1.0) * rng.uniform(0.8, 1.2) / f
                    vals['balita_diukur'] = diukur
                    vals['balita_stunting'] = min(diukur, round(diukur * prev))
                lahir = _poisson(rng, s['bayi_baru_lahir'] / 12)
                vals['lahir_hidup'] = lahir
                vals['kematian_bayi'] = _poisson(rng, lahir * 0.0065)
                vals['kematian_ibu'] = _poisson(rng, lahir * 0.0009)
                pdd = penduduk[d.id]
                kasus = _poisson(rng, pdd * 32e-5 / 12 * MUSIM_DBD[b - 1]
                                 * (1.8 if kota[d.id] else 1.0) * (1.25 if tahun == 2025 else 0.9))
                vals['kasus_dbd'] = kasus
                vals['kematian_dbd'] = sum(1 for _ in range(kasus) if rng.random() < 0.009)
                nilai_rekap.append(vals)
        Rekap.create(nilai_rekap)

        # ── Pengajuan: semua terbit; sebagian kecil terlambat ────────────────
        instansi = self.env.ref('satu_data_kesehatan.instansi_dinkes')
        admin = self.env.ref('base.user_admin')
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        tahunan = Periode.search([('frekuensi', '=', 'tahunan'),
                                  ('tanggal_mulai', 'in', [f'{t}-01-01' for t in TAHUN_DEMO])])
        for sektor, daftar in (('kesehatan_sasaran', tahunan), ('kesehatan', bulan_list)):
            for periode in daftar:
                p = Pengajuan.sd_siapkan(sektor, periode, company, instansi)
                telat = rng.random() < 0.15
                selisih = rng.randint(1, 12) if telat else -rng.randint(0, 8)
                diajukan = datetime.combine(p.batas_pengajuan + timedelta(days=selisih), time(3))
                p.write({'state': 'terbit', 'diajukan_oleh': admin.id,
                         'tanggal_diajukan_pertama': diajukan, 'tanggal_diajukan': diajukan,
                         'diperiksa_oleh': admin.id,
                         'tanggal_diperiksa': diajukan + timedelta(days=rng.randint(1, 4))})
        return True

    @api.model
    def _sd_demo_penduduk(self, company, desa_semua, rng):
        """Penduduk per desa: dari rekap kependudukan terbaru bila ada, selain itu perkiraan."""
        hasil = {}
        if 'satu_data.kependudukan' in self.env:
            Pdd = self.env['satu_data.kependudukan'].sudo()
            terbaru = Pdd.search([('company_id', '=', company.id)], order='periode_id', limit=1)
            if terbaru:
                for desa, jumlah in Pdd._read_group(
                        [('company_id', '=', company.id), ('periode_id', '=', terbaru.periode_id.id)],
                        ['desa_id'], ['jumlah_penduduk:sum']):
                    hasil[desa.id] = jumlah
        for d in desa_semua:
            if not hasil.get(d.id):
                hasil[d.id] = round(rng.uniform(4000, 9000))
        return hasil
