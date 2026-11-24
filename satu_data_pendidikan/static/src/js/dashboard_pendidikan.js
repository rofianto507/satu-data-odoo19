/** @odoo-module **/

import { Component, onMounted, useExternalListener, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SatuDataPeta } from "@satu_data/js/peta_wilayah";
import { SatuDataGrafik } from "@satu_data/js/grafik_echarts";

const fmtAngka = new Intl.NumberFormat("id-ID");
const KUNCI_PETA_DASAR = "satu_data.peta_dasar";
const KUNCI_SEKOLAH = "satu_data.pendidikan_tampil_sekolah";
const LABEL_JENIS = { kabupaten: "Kabupaten", kota: "Kota", desa: "Desa", kelurahan: "Kelurahan" };
// Kartu ringkas di bawah kartu utama.
const KPI = [
    { kode: "jml_siswa", ikon: "fa-users" },
    { kode: "rasio_murid_guru", ikon: "fa-exchange" },
    { kode: "kelas_baik", ikon: "fa-home" },
    { kode: "guru_s1", ikon: "fa-graduation-cap" },
    { kode: "angka_putus", ikon: "fa-sign-out" },
];
// Grafik partisipasi: (jenjang, kode APK, kode APM)
const PARTISIPASI = [
    { label: "PAUD/TK", apk: "apk_paud", apm: null },
    { label: "SD/MI", apk: "apk_sd", apm: "apm_sd" },
    { label: "SMP/MTs", apk: "apk_smp", apm: "apm_smp" },
    { label: "SMA/SMK/MA", apk: "apk_sma", apm: "apm_sma" },
];
const WARNA_TEKS = "#374151";
const WARNA_TEKS_2 = "#5b6474";

/**
 * Dashboard pendidikan: peta indikator per kecamatan/desa, titik satuan pendidikan (saat
 * dirinci per kecamatan), partisipasi per jenjang, dan tren semester. Semua angka dari satu
 * endpoint: satu_data.pendidikan.dashboard.get_dashboard_pendidikan (hanya data terbit).
 */
export class DashboardPendidikan extends Component {
    static template = "satu_data_pendidikan.Dashboard";
    static components = { SatuDataPeta, SatuDataGrafik };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this._permintaanKe = 0;
        let tampilSekolah = true;
        try {
            tampilSekolah = localStorage.getItem(KUNCI_SEKOLAH) !== "0";
        } catch {
            // abaikan
        }
        this.state = useState({
            memuat: true,
            galat: false,
            data: null,
            indikator: false,
            periodeId: false,
            kecamatanId: false,
            jenjang: false,
            terpilihId: false,
            petaDasar: null,
            layarPenuh: false,
            tampilSekolah,
        });
        useExternalListener(document, "fullscreenchange", () => {
            this.state.layarPenuh = document.fullscreenElement === this.rootRef.el;
        });
        onMounted(() => this.muat());
    }

    // ── Data ─────────────────────────────────────────────────────────────────

    async muat() {
        const ke = ++this._permintaanKe;
        this.state.memuat = true;
        this.state.galat = false;
        try {
            const data = await this.orm.call("satu_data.pendidikan.dashboard", "get_dashboard_pendidikan", [], {
                indikator: this.state.indikator || false,
                periode_id: this.state.periodeId || false,
                kecamatan_id: this.state.kecamatanId || false,
                jenjang: this.state.jenjang || false,
            });
            if (ke !== this._permintaanKe) {
                return;
            }
            this.state.data = data;
            if (this.state.petaDasar === null) {
                this.state.petaDasar = this._petaDasarAwal(data.peta_dasar);
            }
            this.state.indikator = data.indikator.kode;
            this.state.periodeId = data.periode.id || false;
            this.state.terpilihId = false;
        } catch (e) {
            if (ke === this._permintaanKe) {
                this.state.galat = e?.data?.message || e?.message || "Terjadi kesalahan saat memuat data.";
            }
        } finally {
            if (ke === this._permintaanKe) {
                this.state.memuat = false;
            }
        }
    }

    // ── Interaksi ────────────────────────────────────────────────────────────

    klikWilayah(id) {
        if (!this.state.data || this.state.memuat) {
            return;
        }
        if (this.state.data.level === "kecamatan") {
            this.state.kecamatanId = id;
            this.muat();
        } else {
            this.state.terpilihId = this.state.terpilihId === id ? false : id;
        }
    }

    kembali() {
        this.state.kecamatanId = false;
        this.muat();
    }

    tutupDetail() {
        this.state.terpilihId = false;
    }

    pilihIndikator(kode) {
        if (kode && kode !== this.state.indikator) {
            this.state.indikator = kode;
            this.muat();
        }
    }

    pilihPeriode(ev) {
        this.state.periodeId = parseInt(ev.target.value) || false;
        this.muat();
    }

    pilihJenjang(ev) {
        this.state.jenjang = ev.target.value || false;
        this.muat();
    }

    toggleSekolah(ev) {
        this.state.tampilSekolah = ev.target.checked;
        try {
            localStorage.setItem(KUNCI_SEKOLAH, ev.target.checked ? "1" : "0");
        } catch {
            // abaikan
        }
    }

    pilihPetaDasar(ev) {
        this.state.petaDasar = ev.target.value;
        try {
            localStorage.setItem(KUNCI_PETA_DASAR, ev.target.value);
        } catch {
            // abaikan
        }
    }

    _petaDasarAwal(info) {
        let tersimpan = null;
        try {
            tersimpan = localStorage.getItem(KUNCI_PETA_DASAR);
        } catch {
            // abaikan
        }
        const valid = tersimpan === "tanpa" || info.pilihan.some((p) => p.kode === tersimpan);
        return valid ? tersimpan : info.bawaan;
    }

    get petaDasarAktif() {
        const info = this.state.data?.peta_dasar;
        return (info && info.pilihan.find((p) => p.kode === this.state.petaDasar)) || false;
    }

    async toggleLayarPenuh() {
        try {
            if (document.fullscreenElement) {
                await document.exitFullscreen();
            } else {
                await this.rootRef.el.requestFullscreen();
            }
        } catch {
            // Browser menolak: abaikan.
        }
    }

    bukaData() {
        const d = this.state.data;
        const domain = [];
        if (d.periode.id) {
            domain.push(["periode_id", "=", d.periode.id]);
        }
        if (d.jenjang_dipakai) {
            domain.push(["kelompok", "=", d.jenjang_dipakai]);
        }
        if (this.state.terpilihId) {
            domain.push(["desa_id", "=", this.state.terpilihId]);
        } else if (d.kecamatan) {
            domain.push(["kecamatan_id", "=", d.kecamatan.id]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Rekap Pendidikan Semester",
            res_model: "satu_data.pendidikan.rekap",
            views: [[false, "list"], [false, "form"]],
            domain,
        });
    }

    /** Tombol "Lihat detail data" di jendela info sekolah: formulir satuan pendidikan. */
    bukaSekolah(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Satuan Pendidikan",
            res_model: "satu_data.sekolah",
            res_id: id,
            views: [[false, "form"]],
        });
    }

    bukaRekap() {
        this.action.doAction("satu_data_pendidikan.action_laporan_rekap");
    }

    // ── Tampilan ─────────────────────────────────────────────────────────────

    get ind() {
        return this.state.data.indikator;
    }

    get kelompokIndikator() {
        const kelompok = [];
        for (const i of this.state.data.daftar_indikator) {
            let k = kelompok.find((x) => x.nama === i.kelompok);
            if (!k) {
                k = { nama: i.kelompok, isi: [] };
                kelompok.push(k);
            }
            k.isi.push(i);
        }
        return kelompok;
    }

    get adaDataPeriode() {
        return Boolean(this.state.data?.periode?.id);
    }

    /** Format nilai indikator (null = belum ada data). */
    nilai(v, ind = this.ind) {
        if (v === null || v === undefined) {
            return "–";
        }
        const des = ind.desimal ?? 0;
        return new Intl.NumberFormat("id-ID", { minimumFractionDigits: des, maximumFractionDigits: des }).format(v);
    }

    satuan(ind = this.ind) {
        return ind.satuan === "%" ? "%" : ` ${ind.satuan}`;
    }

    angka(n) {
        return n === null || n === undefined ? "–" : fmtAngka.format(n);
    }

    infoIndikator(kode) {
        return this.state.data.daftar_indikator.find((i) => i.kode === kode);
    }

    /** Kartu KPI kecil: nilai indikator lain pada cakupan yang sama. */
    get kpi() {
        const semua = this.state.data.semua_indikator;
        return KPI.filter((k) => k.kode in semua).map((k) => {
            const info = this.infoIndikator(k.kode);
            const des = info.satuan === "%" ? (k.kode === "angka_putus" ? 2 : 1) : k.kode === "rasio_murid_guru" ? 1 : 0;
            return { ...k, nama: info.nama, satuan: info.satuan,
                     teks: this.nilai(semua[k.kode], { desimal: des }) };
        });
    }

    get detail() {
        const d = this.state.data;
        if (this.state.terpilihId) {
            const w = d.wilayah.find((x) => x.id === this.state.terpilihId);
            if (w) {
                return { jenis: LABEL_JENIS[w.jenis] || "Desa/Kelurahan", nama: w.nama, kode: w.kode,
                         nilai: w.nilai, pembilang: w.pembilang, penyebut: w.penyebut, desa: null };
            }
        }
        const r = d.ringkasan;
        const dasar = { nilai: r.nilai, pembilang: r.pembilang, penyebut: r.penyebut, desa: d.jumlah_desa };
        if (d.kecamatan) {
            return { ...dasar, jenis: "Kecamatan", nama: d.kecamatan.nama, kode: d.kecamatan.kode };
        }
        return { ...dasar, jenis: LABEL_JENIS[d.wilayah_induk.jenis] || "Wilayah",
                 nama: d.wilayah_induk.nama, kode: d.wilayah_induk.kode };
    }

    /** Urutan daftar: yang perlu perhatian lebih dulu (capaian terendah / beban tertinggi). */
    get daftarUrut() {
        const naik = this.ind.arah === "naik";
        const kunci = (w) => (w.nilai === null ? Infinity : naik ? w.nilai : -w.nilai);
        return [...this.state.data.wilayah].sort((a, b) => kunci(a) - kunci(b) || a.nama.localeCompare(b.nama));
    }

    warnaWilayah(w) {
        const d = this.state.data;
        return w.kelas >= 0 ? d.kelas[w.kelas].warna : d.warna_tanpa_data;
    }

    teksNilai = (w) => {
        if (this.state.data.tersembunyi) {
            return "Tidak dirinci (disajikan per kecamatan)";
        }
        return w.nilai === null ? "Belum ada data" : `${this.nilai(w.nilai)}${this.satuan()}`;
    };

    get titikSekolah() {
        if (!this.state.tampilSekolah || !this.state.data.sekolah) {
            return [];
        }
        return this.state.data.sekolah;
    }

    get petunjukKlik() {
        return this.state.data.level === "kecamatan" ? "Klik untuk melihat desa/kelurahan" : "Klik untuk melihat detail";
    }

    get judulLegenda() {
        return `${this.ind.singkat} (${this.ind.satuan})`;
    }

    get judulCakupan() {
        const d = this.state.data;
        return d.kecamatan ? `Kecamatan ${d.kecamatan.nama}` : d.wilayah_induk.nama;
    }

    get labelJenjang() {
        const d = this.state.data;
        const kel = d.jenjang_dipakai;
        return kel ? d.daftar_jenjang.find((j) => j.kode === kel)?.label : "Semua jenjang";
    }

    // ── Grafik ───────────────────────────────────────────────────────────────

    get opsiPartisipasi() {
        const semua = this.state.data.semua_indikator;
        const nilaiKe = (k) => (k ? semua[k] ?? null : null);
        const bar = (nama, kunci, warna) => ({
            name: nama, type: "bar", barMaxWidth: 26, itemStyle: { color: warna },
            data: PARTISIPASI.map((p) => nilaiKe(p[kunci])),
            label: {
                show: true, position: "top", color: WARNA_TEKS, fontSize: 11,
                formatter: (p) => (p.value === null || p.value === undefined ? "" : `${this.nilai(p.value, { desimal: 1 })}%`),
            },
        });
        return {
            animationDuration: 300,
            textStyle: { fontFamily: "inherit" },
            legend: { top: 0, textStyle: { color: WARNA_TEKS_2 } },
            grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
            tooltip: {
                trigger: "axis", axisPointer: { type: "shadow" },
                formatter: (ps) => `${ps[0].name}<br/>` + ps.filter((p) => p.value !== null && p.value !== undefined)
                    .map((p) => `${p.marker} ${p.seriesName}: <b>${this.nilai(p.value, { desimal: 1 })}%</b>`).join("<br/>"),
            },
            xAxis: { type: "category", data: PARTISIPASI.map((p) => p.label), axisLabel: { color: WARNA_TEKS },
                     axisTick: { show: false } },
            yAxis: {
                type: "value", min: 0, max: (v) => Math.max(100, Math.ceil(v.max / 10) * 10),
                axisLabel: { formatter: "{value}%", color: WARNA_TEKS_2 },
                splitLine: { lineStyle: { color: "#eef0f4" } },
            },
            series: [
                { ...bar("APK", "apk", "#2c7fb8"),
                  markLine: { silent: true, symbol: "none", lineStyle: { color: "#9ca3af", type: "dashed" },
                              label: { formatter: "100%", color: WARNA_TEKS_2 }, data: [{ yAxis: 100 }] } },
                bar("APM", "apm", "#f59e0b"),
            ],
        };
    }

    get adaPartisipasi() {
        const semua = this.state.data.semua_indikator;
        return PARTISIPASI.some((p) => semua[p.apk] !== null && semua[p.apk] !== undefined);
    }

    get opsiTren() {
        const tren = this.state.data.tren;
        return {
            animationDuration: 300,
            textStyle: { fontFamily: "inherit" },
            grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
            tooltip: {
                trigger: "axis",
                formatter: (ps) => `${ps[0].name}<br/><b>${this.nilai(ps[0].value)}${this.satuan()}</b>`,
            },
            xAxis: {
                type: "category", data: tren.map((t) => t.label), boundaryGap: false,
                axisLabel: { color: WARNA_TEKS_2, hideOverlap: true },
                axisLine: { lineStyle: { color: "#cfd5de" } },
            },
            yAxis: {
                type: "value", scale: true, name: this.ind.satuan, nameTextStyle: { color: WARNA_TEKS_2 },
                axisLabel: { color: WARNA_TEKS_2 }, splitLine: { lineStyle: { color: "#eef0f4" } },
            },
            series: [{
                type: "line", smooth: false, symbolSize: 7, connectNulls: false,
                lineStyle: { width: 2.5, color: "#2c7fb8" }, itemStyle: { color: "#2c7fb8" },
                areaStyle: { color: "rgba(44,127,184,0.08)" },
                data: tren.map((t) => t.nilai),
            }],
        };
    }

    get adaTren() {
        return this.state.data.tren.some((t) => t.nilai !== null);
    }

    klikPartisipasi = (p) => {
        const info = PARTISIPASI[p?.dataIndex];
        const kode = info && (p.seriesName === "APM" ? info.apm : info.apk);
        if (kode) {
            this.pilihIndikator(kode);
        }
    };
}

registry.category("satu_data_dashboard").add("pendidikan", {
    nama: "Pendidikan",
    ikon: "fa-graduation-cap",
    urutan: 30,
    Component: DashboardPendidikan,
});
