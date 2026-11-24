/** @odoo-module **/

import { Component, onMounted, useExternalListener, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SatuDataPeta } from "@satu_data/js/peta_wilayah";
import { GrafikPenduduk } from "./grafik_penduduk";

const fmtAngka = new Intl.NumberFormat("id-ID");
const fmtDesimal = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const KUNCI_PETA_DASAR = "satu_data.peta_dasar";

const LABEL_JENIS = {
    kabupaten: "Kabupaten",
    kota: "Kota",
    desa: "Desa",
    kelurahan: "Kelurahan",
};

/**
 * Dashboard peta kependudukan.
 *
 * Semua angka berasal dari satu endpoint: satu_data.kependudukan.get_dashboard_peta.
 * Level 1 = kecamatan, klik kecamatan = level 2 (desa/kelurahan di kecamatan itu).
 */
export class SatuDataDashboard extends Component {
    static template = "satu_data_kependudukan.DashboardPeta";
    static components = { SatuDataPeta, GrafikPenduduk };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this._permintaanKe = 0;

        this.state = useState({
            memuat: true,
            galat: false,
            data: null,
            kecamatanId: false,
            periodeId: false,    // id satu_data.periode; false = periode terbaru
            terpilihId: false,   // desa yang dipilih pada level 2
            petaDasar: null,     // kode peta dasar ("positron", "tanpa", ...); null = belum dipilih
            layarPenuh: false,
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
            const data = await this.orm.call("satu_data.kependudukan", "get_dashboard_peta", [], {
                kecamatan_id: this.state.kecamatanId || false,
                periode_id: this.state.periodeId || false,
            });
            if (ke !== this._permintaanKe) {
                return; // sudah ada permintaan yang lebih baru
            }
            this.state.data = data;
            if (this.state.petaDasar === null) {
                this.state.petaDasar = this._petaDasarAwal(data.peta_dasar);
            }
            this.state.periodeId = data.periode.id || false;
            this.state.terpilihId = false;
        } catch (e) {
            if (ke !== this._permintaanKe) {
                return;
            }
            this.state.galat = e?.data?.message || e?.message || "Terjadi kesalahan saat memuat data.";
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

    tutupDetail() {
        this.state.terpilihId = false;
    }

    kembali() {
        this.state.kecamatanId = false;
        this.muat();
    }

    pilihPeriode(ev) {
        this.state.periodeId = parseInt(ev.target.value) || false;
        this.muat();
    }

    pilihPetaDasar(ev) {
        this.state.petaDasar = ev.target.value;
        try {
            localStorage.setItem(KUNCI_PETA_DASAR, ev.target.value);
        } catch {
            // Penyimpanan browser tidak tersedia: pilihan hanya berlaku di sesi ini.
        }
    }

    /** Pilihan terakhir pengguna di browser ini, atau bawaan dari server. */
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
            // Browser menolak (mis. iOS Safari): abaikan, tampilan biasa tetap jalan.
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
            name: "Rekap Kependudukan",
            res_model: "satu_data.kependudukan",
            views: [[false, "list"], [false, "form"]],
            domain,
        });
    }

    bukaKecamatan() {
        this.action.doAction("satu_data.action_kecamatan");
    }

    // ── Tampilan ─────────────────────────────────────────────────────────────

    /** Isi panel detail: desa terpilih, atau ringkasan kecamatan/kabupaten. */
    get detail() {
        const d = this.state.data;
        if (!d) {
            return null;
        }
        // Angka tanpa satu pun data desa ditampilkan sebagai "–", bukan 0.
        const adaAngka = (a) => (a && a.jumlah_data ? a : null);
        if (this.state.terpilihId) {
            const w = d.wilayah.find((x) => x.id === this.state.terpilihId);
            if (w) {
                return { jenis: LABEL_JENIS[w.jenis] || "Desa/Kelurahan", nama: w.nama, kode: w.kode,
                         angka: adaAngka(w.angka), cakupan: null };
            }
        }
        if (d.level === "desa") {
            return {
                jenis: "Kecamatan", nama: d.kecamatan.nama, kode: d.kecamatan.kode,
                angka: adaAngka(d.ringkasan),
                cakupan: { ada: d.ringkasan.jumlah_data, total: d.ringkasan.jumlah_wilayah },
            };
        }
        const totalDesa = d.wilayah.reduce((n, w) => n + (w.jumlah_desa || 0), 0);
        return {
            jenis: LABEL_JENIS[d.wilayah_induk.jenis] || "Wilayah", nama: d.wilayah_induk.nama,
            kode: d.wilayah_induk.kode, angka: adaAngka(d.kabupaten),
            cakupan: { ada: d.kabupaten.jumlah_data, total: totalDesa },
        };
    }

    get daftarUrut() {
        const nilai = (w) => (w.angka ? w.angka.penduduk : -1);
        return [...this.state.data.wilayah].sort((a, b) => nilai(b) - nilai(a) || a.nama.localeCompare(b.nama));
    }

    get adaDataPeriode() {
        return Boolean(this.state.data?.periode?.id);
    }

    get petunjukKlik() {
        return this.state.data.level === "kecamatan"
            ? "Klik untuk melihat desa/kelurahan"
            : "Klik untuk melihat detail";
    }

    warnaWilayah(w) {
        const d = this.state.data;
        return w.kelas >= 0 ? d.kelas[w.kelas].warna : d.warna_tanpa_data;
    }

    angka(n) {
        return fmtAngka.format(n || 0);
    }

    desimal(n) {
        return fmtDesimal.format(n || 0);
    }

    persen(bagian, total) {
        return total ? fmtDesimal.format((bagian / total) * 100) : "0";
    }
}

// Ditampilkan di panel sidebar Dashboard modul inti (satu_data).
registry.category("satu_data_dashboard").add("kependudukan", {
    nama: "Kependudukan",
    ikon: "fa-users",
    urutan: 10,
    Component: SatuDataDashboard,
});
