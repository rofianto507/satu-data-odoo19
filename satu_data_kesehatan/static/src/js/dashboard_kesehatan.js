/** @odoo-module **/

import { Component, onMounted, useExternalListener, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SatuDataPeta } from "@satu_data/js/peta_wilayah";
import { SatuDataGrafik } from "@satu_data/js/grafik_echarts";

const fmtAngka = new Intl.NumberFormat("id-ID");
const KUNCI_PETA_DASAR = "satu_data.peta_dasar";
const KUNCI_PUSKESMAS = "satu_data.kesehatan_tampil_puskesmas";
const LABEL_JENIS = { kabupaten: "Kabupaten", kota: "Kota", desa: "Desa", kelurahan: "Kelurahan" };
// Kartu ringkas di bawah kartu utama (indikator terpilih).
const KPI = [
    { kode: "stunting", ikon: "fa-child" },
    { kode: "idl", ikon: "fa-shield" },
    { kode: "kematian_ibu", ikon: "fa-female" },
    { kode: "kematian_bayi", ikon: "fa-heart" },
    { kode: "kasus_dbd", ikon: "fa-bug" },
];
const WARNA_TEKS = "#374151";
const WARNA_TEKS_2 = "#5b6474";

/**
 * Dashboard kesehatan: peta indikator per kecamatan/desa, titik puskesmas, capaian
 * 12 SPM, dan tren bulanan. Semua angka dari satu endpoint:
 * satu_data.kesehatan.dashboard.get_dashboard_kesehatan (hanya data terbit).
 */
export class DashboardKesehatan extends Component {
    static template = "satu_data_kesehatan.Dashboard";
    static components = { SatuDataPeta, SatuDataGrafik };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this._permintaanKe = 0;
        let tampilPuskesmas = true;
        try {
            tampilPuskesmas = localStorage.getItem(KUNCI_PUSKESMAS) !== "0";
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
            mode: "kumulatif",
            terpilihId: false,
            petaDasar: null,
            layarPenuh: false,
            tampilPuskesmas,
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
            const data = await this.orm.call("satu_data.kesehatan.dashboard", "get_dashboard_kesehatan", [], {
                indikator: this.state.indikator || false,
                periode_id: this.state.periodeId || false,
                kecamatan_id: this.state.kecamatanId || false,
                mode: this.state.mode,
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

    pilihMode(mode) {
        if (mode !== this.state.mode) {
            this.state.mode = mode;
            this.muat();
        }
    }

    togglePuskesmas(ev) {
        this.state.tampilPuskesmas = ev.target.checked;
        try {
            localStorage.setItem(KUNCI_PUSKESMAS, ev.target.checked ? "1" : "0");
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
        if (this.state.terpilihId) {
            domain.push(["desa_id", "=", this.state.terpilihId]);
        } else if (d.kecamatan) {
            domain.push(["kecamatan_id", "=", d.kecamatan.id]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Rekap Kesehatan Bulanan",
            res_model: "satu_data.kesehatan.rekap",
            views: [[false, "list"], [false, "form"]],
            domain,
        });
    }

    bukaRekap() {
        this.action.doAction("satu_data_kesehatan.action_rekap");
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
            const des = info.satuan === "%" ? 1 : 0;
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
                         puskesmas: w.puskesmas, nilai: w.nilai, pembilang: w.pembilang,
                         penyebut: w.penyebut, lapor: null, desa: null };
            }
        }
        const r = d.ringkasan;
        const dasar = { nilai: r.nilai, pembilang: r.pembilang, penyebut: r.penyebut,
                        lapor: r.lapor, desa: d.jumlah_desa, puskesmas: false };
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
            return "Tidak dirinci (data terbatas)";
        }
        return w.nilai === null ? "Belum ada data" : `${this.nilai(w.nilai)}${this.satuan()}`;
    };

    get titikPuskesmas() {
        if (!this.state.tampilPuskesmas) {
            return [];
        }
        return this.state.data.puskesmas.map((p) => ({
            id: p.id, nama: p.nama, lat: p.lat, lng: p.lng,
            keterangan: [
                `${this.ind.singkat}: ${p.nilai === null ? "belum ada data" : this.nilai(p.nilai) + this.satuan()}`,
                `${p.jumlah_desa} desa/kelurahan binaan${p.kategori ? " · " + p.kategori : ""}`,
            ],
        }));
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

    get labelMode() {
        if (this.ind.tanpa_mode) {
            return "pengukuran terakhir";
        }
        return this.state.data.mode === "bulan" ? "bulan ini" : "kumulatif s.d. bulan ini";
    }

    // ── Grafik ───────────────────────────────────────────────────────────────

    get opsiSpm() {
        const semua = this.state.data.semua_indikator;
        const spm = this.state.data.daftar_indikator.filter((i) => i.kode.startsWith("spm_"));
        const warna = (v) => (v === null ? "#d9d9d9" : v >= 100 ? "#1a9641" : v >= 75 ? "#a6d96a"
            : v >= 50 ? "#fdae61" : v >= 25 ? "#f46d43" : "#d7191c");
        const urut = [...spm].reverse(); // SPM 1 di atas
        return {
            animationDuration: 300,
            textStyle: { fontFamily: "inherit" },
            grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
            tooltip: {
                trigger: "item",
                formatter: (p) => `${p.name}<br/><b>${this.nilai(p.value, { desimal: 1 })}%</b>`,
            },
            xAxis: {
                type: "value", min: 0, max: (v) => Math.max(100, Math.ceil(v.max / 10) * 10),
                axisLabel: { formatter: "{value}%", color: WARNA_TEKS_2 },
                splitLine: { lineStyle: { color: "#eef0f4" } },
            },
            yAxis: {
                type: "category",
                data: urut.map((i) => i.nama.replace("Pelayanan Kesehatan ", "")),
                axisLabel: { color: WARNA_TEKS, width: 170, overflow: "truncate" },
                axisTick: { show: false },
            },
            series: [{
                type: "bar",
                barMaxWidth: 18,
                data: urut.map((i) => ({
                    value: semua[i.kode], kode: i.kode,
                    itemStyle: {
                        color: warna(semua[i.kode]),
                        borderColor: i.kode === this.ind.kode ? "#111827" : undefined,
                        borderWidth: i.kode === this.ind.kode ? 2 : 0,
                    },
                })),
                label: {
                    show: true, position: "right", color: WARNA_TEKS,
                    formatter: (p) => (p.value === null ? "–" : `${this.nilai(p.value, { desimal: 1 })}%`),
                },
                markLine: {
                    silent: true, symbol: "none", lineStyle: { color: "#1a9641", type: "dashed" },
                    label: { formatter: "Target", color: "#1a9641" }, data: [{ xAxis: 100 }],
                },
            }],
        };
    }

    get adaSpm() {
        const semua = this.state.data.semua_indikator;
        return Object.keys(semua).some((k) => k.startsWith("spm_") && semua[k] !== null);
    }

    klikSpm = (p) => {
        if (p?.data?.kode) {
            this.pilihIndikator(p.data.kode);
        }
    };

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
                type: "value", name: this.ind.satuan, nameTextStyle: { color: WARNA_TEKS_2 },
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
}

registry.category("satu_data_dashboard").add("kesehatan", {
    nama: "Kesehatan",
    ikon: "fa-heartbeat",
    urutan: 20,
    Component: DashboardKesehatan,
});
