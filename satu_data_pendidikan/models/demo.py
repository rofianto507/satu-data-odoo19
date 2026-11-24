"""Pembuat data demo pendidikan (CONTOH FIKTIF, bukan data resmi).

Dipanggil sekali dari ``demo/satu_data_pendidikan_demo.xml`` (hanya di database dengan
data demo). Nama sekolah mengikuti nama desa/kecamatan lokasinya ("SDN Pontang 1"),
NPSN sintetis berawalan 9 (bukan NPSN sungguhan), dan koordinat acak di dalam desa
(di bagian daratan bila desa terdiri dari beberapa bagian, mis. dengan pulau).
Deterministik (seed tetap).
"""
import json
import math
import random
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, models

SUMBER_DEMO = 'CONTOH (fiktif), bukan data resmi'
TAHUN_DEMO = (2025, 2026)

# Rekap semester demo: Semester I dan II 2025, Semester I 2026 (tanggal mulai periode).
SEMESTER_DEMO = ('2025-01-01', '2025-07-01', '2026-01-01')
# Per kelompok jenjang: kelompok usia penyebut, APK sasaran, porsi siswa usia resmi, kapasitas
# siswa per rombel, siswa per guru, porsi guru S1/D4 dan bersertifikat, porsi lulusan terhadap
# siswa, porsi lulusan yang melanjutkan, porsi putus sekolah, porsi siswa laki-laki.
KONFIG_JENJANG = {
    'paud':       dict(usia='usia_5_6',   apk=0.62, resmi=0.92,  kelas=18, rasio=12, s1=0.58, sert=0.22,
                       lulus=0.50, lanjut=0.97, putus=0.0010, laki=0.505),
    'sd_mi':      dict(usia='usia_7_12',  apk=1.04, resmi=0.88, kelas=24, rasio=17, s1=0.86, sert=0.58,
                       lulus=1 / 6, lanjut=0.97, putus=0.0015, laki=0.513),
    'smp_mts':    dict(usia='usia_13_15', apk=0.97, resmi=0.90,  kelas=31, rasio=15, s1=0.92, sert=0.62,
                       lulus=1 / 3, lanjut=0.88, putus=0.0050, laki=0.505),
    'sma_smk_ma': dict(usia='usia_16_18', apk=0.80, resmi=0.86,  kelas=33, rasio=14, s1=0.95, sert=0.64,
                       lulus=1 / 3, lanjut=0.35, putus=0.0090, laki=0.485),
}

# Porsi kelompok usia terhadap seluruh penduduk (rata-rata nasional kasar).
RASIO_USIA = {'usia_5_6': 0.027, 'usia_7_12': 0.084, 'usia_13_15': 0.042, 'usia_16_18': 0.040}


# ── Geometri ringan (tanpa pustaka luar) ─────────────────────────────────────

def _bagian(geo):
    g = json.loads(geo) if isinstance(geo, str) else geo
    if g.get('type') == 'Feature':
        g = g['geometry']
    polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
    hasil = []
    for p in polys:
        ring = p[0]
        luas = cx = cy = 0.0
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            c = x1 * y2 - x2 * y1
            luas += c
            cx += (x1 + x2) * c
            cy += (y1 + y2) * c
        if luas:
            hasil.append({'poligon': p, 'luas': abs(luas) / 2,
                          'lat': cy / (3 * luas), 'lng': cx / (3 * luas)})
    return hasil


def _di_dalam(x, y, poligon):
    def dalam(ring):
        masuk, j = False, len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                masuk = not masuk
            j = i
        return masuk
    return dalam(poligon[0]) and not any(dalam(h) for h in poligon[1:])


def _titik_acak(rng, bagian):
    xs = [c[0] for c in bagian['poligon'][0]]
    ys = [c[1] for c in bagian['poligon'][0]]
    for _ in range(300):
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if _di_dalam(x, y, bagian['poligon']):
            return round(y, 6), round(x, 6)
    return round(bagian['lat'], 6), round(bagian['lng'], 6)


class SatuDataPendidikanDemo(models.AbstractModel):
    _name        = 'satu_data.pendidikan.demo'
    _description = 'Pembuat Data Demo Pendidikan'

    @api.model
    def _sd_demo_pendidikan(self):
        company = self.env.ref('base.main_company')
        Sekolah = self.env['satu_data.sekolah'].with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
        Usia = self.env['satu_data.pendidikan.usia_sekolah'].with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
        if Sekolah.search_count([('company_id', '=', company.id)], limit=1):
            return False   # sudah ada data: jangan menimpa
        Periode = self.env['satu_data.periode']
        for tahun in TAHUN_DEMO:
            Periode.sd_buat_periode_baku(tahun, 'tahunan')

        rng = random.Random(3510)
        desa_semua = self.env['satu_data.desa'].search(
            [('company_id', '=', company.id)], order='kode')
        penduduk = self._sd_demo_penduduk(company, desa_semua, rng)
        titik_bagian = self._sd_demo_bagian_daratan(desa_semua)

        # Desa terbesar tiap kecamatan: pasti punya SMA negeri.
        terbesar = {}
        for d in desa_semua:
            k = d.kecamatan_id.id
            if k not in terbesar or penduduk[d.id] > penduduk[terbesar[k]]:
                terbesar[k] = d.id

        def jumlah(rata, minimal=0):
            return max(minimal, round(rata * rng.uniform(0.6, 1.4)))

        nilai_sekolah = []
        urut = [90000000]
        hitung_kec = defaultdict(int)

        def tambah(d, jenjang, status, nama):
            urut[0] += 1
            lat, lng = (0.0, 0.0)
            bagian = titik_bagian.get(d.id)
            if bagian:
                lat, lng = _titik_acak(rng, bagian)
            akreditasi = rng.choices(['a', 'b', 'c', 'belum'], weights=[35, 45, 12, 8])[0]
            nilai_sekolah.append({
                'name': nama, 'npsn': str(urut[0]), 'jenjang': jenjang, 'status': status,
                'akreditasi': akreditasi, 'desa_id': d.id, 'latitude': lat, 'longitude': lng,
                'alamat': f'Desa/Kel. {d.name}, Kec. {d.kecamatan_id.name}',
            })

        for d in desa_semua:
            p = penduduk[d.id]
            kec = d.kecamatan_id.name
            kunci_kec = d.kecamatan_id.id

            def nomor_kec(jenjang):
                hitung_kec[(kunci_kec, jenjang)] += 1
                return hitung_kec[(kunci_kec, jenjang)]

            for n in range(1, jumlah(p / 2800, 1) + 1):
                tambah(d, 'paud', 'swasta', f'{"TK" if n % 2 else "PAUD"} {d.name} {n}')
            for n in range(1, jumlah(p / 3800, 1) + 1):
                negeri = rng.random() < 0.85
                tambah(d, 'sd', 'negeri' if negeri else 'swasta',
                       f'SDN {d.name} {n}' if negeri else f'SDS {d.name} {n}')
            if rng.random() < min(0.9, p / 12000):
                if rng.random() < 0.08:
                    tambah(d, 'mi', 'negeri', f'MIN {nomor_kec("mi")} {kec}')
                else:
                    tambah(d, 'mi', 'swasta', f'MI {d.name}')
            if rng.random() < min(0.9, p / 9000):
                if rng.random() < 0.65:
                    tambah(d, 'smp', 'negeri', f'SMPN {nomor_kec("smp")} {kec}')
                else:
                    tambah(d, 'smp', 'swasta', f'SMP Swasta {d.name}')
            if rng.random() < min(0.8, p / 14000):
                if rng.random() < 0.12:
                    tambah(d, 'mts', 'negeri', f'MTsN {nomor_kec("mts")} {kec}')
                else:
                    tambah(d, 'mts', 'swasta', f'MTs {d.name}')
            if terbesar[kunci_kec] == d.id or rng.random() < p / 30000:
                tambah(d, 'sma', 'negeri', f'SMAN {nomor_kec("sma")} {kec}')
            if rng.random() < p / 36000:
                if rng.random() < 0.4:
                    tambah(d, 'smk', 'negeri', f'SMKN {nomor_kec("smk")} {kec}')
                else:
                    tambah(d, 'smk', 'swasta', f'SMK Swasta {d.name}')
            if rng.random() < p / 26000:
                tambah(d, 'ma', 'swasta', f'MA {d.name}')
            if p > 12000 and rng.random() < 0.1:
                tambah(d, 'slb', 'swasta', f'SLB {d.name}')
            if p > 9000 and rng.random() < 0.12:
                tambah(d, 'pkbm', 'swasta', f'PKBM {d.name}')
        Sekolah.create(nilai_sekolah)

        # ── Penduduk usia sekolah tahunan ────────────────────────────────────
        tahunan = {p.tanggal_mulai.year: p for p in Periode.search([
            ('frekuensi', '=', 'tahunan'),
            ('tanggal_mulai', 'in', [f'{t}-01-01' for t in TAHUN_DEMO])])}
        nilai_usia = []
        for tahun in TAHUN_DEMO:
            for d in desa_semua:
                pdd = penduduk[d.id] * (1.006 ** (tahun - TAHUN_DEMO[0]))
                vals = {k: max(1, round(pdd * r * rng.uniform(0.92, 1.08)))
                        for k, r in RASIO_USIA.items()}
                vals.update({'desa_id': d.id, 'periode_id': tahunan[tahun].id,
                             'sumber': SUMBER_DEMO})
                nilai_usia.append(vals)
        Usia.create(nilai_usia)

        # ── Pengajuan: semua terbit; sebagian kecil terlambat ────────────────
        instansi = self.env.ref('satu_data_pendidikan.instansi_disdik')
        admin = self.env.ref('base.user_admin')
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        for tahun in TAHUN_DEMO:
            p = Pengajuan.sd_siapkan('pendidikan_usia_sekolah', tahunan[tahun], company, instansi)
            selisih = rng.randint(1, 10) if rng.random() < 0.3 else -rng.randint(0, 12)
            diajukan = datetime.combine(p.batas_pengajuan + timedelta(days=selisih), time(3))
            p.write({'state': 'terbit', 'diajukan_oleh': admin.id,
                     'tanggal_diajukan_pertama': diajukan, 'tanggal_diajukan': diajukan,
                     'diperiksa_oleh': admin.id,
                     'tanggal_diperiksa': diajukan + timedelta(days=rng.randint(1, 4))})
        return True

    @api.model
    def _sd_demo_rekap_semester(self):
        """Rekap semester demo per desa dan jenjang; jumlah sekolah dari master."""
        company = self.env.ref('base.main_company')
        Rekap = self.env['satu_data.pendidikan.rekap'].with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
        Sekolah = self.env['satu_data.sekolah']
        Usia = self.env['satu_data.pendidikan.usia_sekolah']
        if Rekap.search_count([('company_id', '=', company.id)], limit=1) or \
                not Sekolah.search_count([('company_id', '=', company.id)], limit=1):
            return False   # sudah ada data, atau belum ada sekolah demo
        Periode = self.env['satu_data.periode']
        for tahun in TAHUN_DEMO:
            Periode.sd_buat_periode_baku(tahun, 'semesteran')
        semester = [Periode.search([('frekuensi', '=', 'semesteran'), ('tanggal_mulai', '=', t)], limit=1)
                    for t in SEMESTER_DEMO]

        rng = random.Random(3511)
        desa_semua = self.env['satu_data.desa'].search([('company_id', '=', company.id)], order='kode')
        per_kec = defaultdict(list)
        for d in desa_semua:
            per_kec[d.kecamatan_id.id].append(d.id)
        n_sekolah = defaultdict(lambda: {'negeri': 0, 'swasta': 0})
        for desa, kelompok, status, n in Sekolah._read_group(
                [('company_id', '=', company.id)], ['desa_id', 'kelompok', 'status'], ['__count']):
            n_sekolah[(desa.id, kelompok)][status] = n
        usia = {(u.periode_id.tanggal_mulai.year, u.desa_id.id): u
                for u in Usia.search([('company_id', '=', company.id)])}

        def klip(x, a, b):
            return max(a, min(b, x))

        nilai = []
        for idx, periode in enumerate(semester):
            tahun = periode.tanggal_mulai.year
            akhir_tahun_ajaran = periode.tanggal_mulai.month == 1     # Semester I = Januari–Juni
            for kelompok, cfg in KONFIG_JENJANG.items():
                for kec_id, daftar in per_kec.items():
                    sasaran = sum(usia[(tahun, d)][cfg['usia']] for d in daftar if (tahun, d) in usia)
                    target = sasaran * cfg['apk'] * rng.uniform(0.93, 1.07) * (1 + 0.004 * idx)
                    bobot = {d: sum(n_sekolah[(d, kelompok)].values()) * rng.uniform(0.6, 1.5)
                             for d in daftar}
                    total_bobot = sum(bobot.values())
                    for d in daftar:
                        siswa = round(target * bobot[d] / total_bobot) if total_bobot else 0
                        laki = int(klip(round(siswa * rng.gauss(cfg['laki'], 0.01)), 0, siswa))
                        resmi = min(siswa, round(siswa * cfg['resmi'] * rng.uniform(0.97, 1.02)))
                        rombel = math.ceil(siswa / (cfg['kelas'] * rng.uniform(0.85, 1.1))) if siswa else 0
                        guru = max(1 if siswa else 0,
                                   round(siswa / (cfg['rasio'] * rng.uniform(0.85, 1.15))))
                        s1 = min(guru, round(guru * min(0.99, cfg['s1'] + 0.012 * idx) * rng.uniform(0.95, 1.03)))
                        sert = min(guru, round(guru * min(0.95, cfg['sert'] + 0.015 * idx) * rng.uniform(0.9, 1.08)))
                        kelas = round(rombel * rng.uniform(0.95, 1.12))
                        baik = round(kelas * klip(0.66 + 0.01 * idx + rng.gauss(0, 0.04), 0.4, 0.95))
                        ringan = min(kelas - baik, round(kelas * 0.22 * rng.uniform(0.7, 1.3)))
                        berat = kelas - baik - ringan
                        putus = lulus = lanjut = 0
                        if akhir_tahun_ajaran and siswa:
                            putus = round(siswa * cfg['putus'] * rng.uniform(0.5, 1.5))
                            lulus = round(siswa * cfg['lulus'] * rng.uniform(0.93, 1.05))
                            lanjut = min(lulus, round(lulus * cfg['lanjut'] * rng.uniform(0.95, 1.03)))
                        nilai.append({
                            'desa_id': d, 'periode_id': periode.id, 'kelompok': kelompok,
                            'sumber': SUMBER_DEMO,
                            'sekolah_negeri': n_sekolah[(d, kelompok)]['negeri'],
                            'sekolah_swasta': n_sekolah[(d, kelompok)]['swasta'],
                            'siswa_l': laki, 'siswa_p': siswa - laki, 'siswa_usia_resmi': resmi,
                            'rombel': rombel, 'guru': guru, 'guru_s1': s1, 'guru_sertifikasi': sert,
                            'kelas_baik': baik, 'kelas_rusak_ringan': ringan, 'kelas_rusak_berat': berat,
                            'putus_sekolah': putus, 'lulusan': lulus, 'melanjutkan': lanjut,
                        })
        Rekap.create(nilai)

        # Pengajuan: semua semester terbit; sebagian kecil terlambat.
        instansi = self.env.ref('satu_data_pendidikan.instansi_disdik')
        admin = self.env.ref('base.user_admin')
        Pengajuan = self.env['satu_data.pengajuan'].sudo()
        for periode in semester:
            p = Pengajuan.sd_siapkan('pendidikan', periode, company, instansi)
            selisih = rng.randint(1, 12) if rng.random() < 0.2 else -rng.randint(0, 10)
            diajukan = datetime.combine(p.batas_pengajuan + timedelta(days=selisih), time(3))
            p.write({'state': 'terbit', 'diajukan_oleh': admin.id,
                     'tanggal_diajukan_pertama': diajukan, 'tanggal_diajukan': diajukan,
                     'diperiksa_oleh': admin.id,
                     'tanggal_diperiksa': diajukan + timedelta(days=rng.randint(1, 4))})
        return True

    @api.model
    def _sd_demo_penduduk(self, company, desa_semua, rng):
        """Penduduk per desa: dari rekap kependudukan terbaru bila modulnya ada, selain itu acak."""
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

    @api.model
    def _sd_demo_bagian_daratan(self, desa_semua):
        """{desa_id: bagian poligon tempat sekolah boleh diletakkan}.

        Desa berbagian tunggal: bagian itu. Desa berbagian banyak (mis. dengan pulau tidak
        berpenduduk): bagian yang terdekat ke desa-desa lain sekecamatan, bukan yang terluas.
        """
        per_desa = {d.id: _bagian(d.geojson_peta) for d in desa_semua if d.geojson_peta}
        per_kec = defaultdict(list)
        for d in desa_semua:
            per_kec[d.kecamatan_id.id].append(d.id)
        hasil = {}
        for d in desa_semua:
            bag = per_desa.get(d.id)
            if not bag:
                continue
            if len(bag) == 1:
                hasil[d.id] = bag[0]
                continue
            lain = [b for x in per_kec[d.kecamatan_id.id] if x != d.id for b in per_desa.get(x, [])]
            if not lain:
                hasil[d.id] = max(bag, key=lambda b: b['luas'])
                continue
            mlat = sum(b['lat'] for b in lain) / len(lain)
            mlng = sum(b['lng'] for b in lain) / len(lain)
            hasil[d.id] = min(bag, key=lambda b: (b['lat'] - mlat) ** 2 + (b['lng'] - mlng) ** 2)
        return hasil
