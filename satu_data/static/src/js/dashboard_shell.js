/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

/**
 * Registry dashboard sektor. Modul sektor mendaftarkan dashboard-nya:
 *
 *   registry.category("satu_data_dashboard").add("kependudukan", {
 *       nama: "Kependudukan",   // label di panel sidebar
 *       ikon: "fa-users",       // kelas Font Awesome
 *       urutan: 10,             // urutan di sidebar (kecil di atas)
 *       Component: KomponenDashboard,
 *   });
 */
export const dashboardSektor = registry.category("satu_data_dashboard");

const KUNCI_SEKTOR = "satu_data.dashboard_sektor";
const KUNCI_LIPAT = "satu_data.dashboard_sidebar_lipat";

function baca(kunci) {
    try {
        return localStorage.getItem(kunci);
    } catch {
        return null; // penyimpanan browser tidak tersedia
    }
}

function simpan(kunci, nilai) {
    try {
        localStorage.setItem(kunci, nilai);
    } catch {
        // abaikan: pilihan hanya berlaku di sesi ini
    }
}

/**
 * Client action "Dashboard": panel sidebar kiri berisi dashboard tiap sektor yang
 * terpasang, isi dashboard sektor terpilih di kanan.
 */
export class SatuDataDashboardShell extends Component {
    static template = "satu_data.DashboardShell";
    static props = ["*"];

    setup() {
        const daftar = this.daftarSektor;
        const tersimpan = baca(KUNCI_SEKTOR);
        this.state = useState({
            aktif: daftar.some((s) => s.kode === tersimpan) ? tersimpan : daftar[0]?.kode || false,
            lipat: baca(KUNCI_LIPAT) === "1",
            tanpaLogo: false,
        });
    }

    /** Logo company (wilayah) yang sedang aktif; berganti bila company diganti. */
    get urlLogo() {
        const id = user.activeCompany?.id;
        return id ? `/web/binary/company_logo?company=${id}` : "/web/binary/company_logo";
    }

    get namaWilayah() {
        return user.activeCompany?.name || "";
    }

    get daftarSektor() {
        return dashboardSektor
            .getEntries()
            .map(([kode, s]) => ({ kode, ...s }))
            .sort((a, b) => (a.urutan ?? 100) - (b.urutan ?? 100) || a.nama.localeCompare(b.nama));
    }

    get sektorAktif() {
        return this.daftarSektor.find((s) => s.kode === this.state.aktif) || false;
    }

    pilih(kode) {
        this.state.aktif = kode;
        simpan(KUNCI_SEKTOR, kode);
    }

    toggleLipat() {
        this.state.lipat = !this.state.lipat;
        simpan(KUNCI_LIPAT, this.state.lipat ? "1" : "0");
    }
}

registry.category("actions").add("satu_data.dashboard", SatuDataDashboardShell);
