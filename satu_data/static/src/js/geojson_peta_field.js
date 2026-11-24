/** @odoo-module **/

import { Component, onMounted, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const KUNCI_PETA_DASAR = "satu_data.peta_dasar"; // sama dengan dashboard
const PUSAT_AWAL = [-2.5, 118];
const ZOOM_AWAL = 5;
const DESIMAL = 6; // ~0,1 m
const MAKS_RIWAYAT = 50;
// Titik hanya digambar bila jumlah yang terlihat di layar tidak lebih dari ini;
// selebihnya pengguna diminta memperbesar peta (agar tetap ringan dan mudah diklik).
const MAKS_TITIK_TAMPIL = 1500;
const WARNA = "#2563eb";
const WARNA_PILIH = "#dc2626";

function bulat(x) {
    const f = 10 ** DESIMAL;
    return Math.round(x * f) / f;
}

function idMany2one(v) {
    if (!v) {
        return false;
    }
    return Array.isArray(v) ? v[0] : v.id || false;
}

/**
 * Teks GeoJSON -> {tipe, poligon}. `poligon` = daftar poligon, tiap poligon = daftar
 * ring, tiap ring = daftar titik [bujur, lintang] TANPA titik penutup.
 * Melempar Error bila isi tidak bisa dibaca.
 */
function bacaGeometri(teks) {
    if (!teks || !teks.trim()) {
        return { tipe: "Polygon", poligon: [] };
    }
    let data = JSON.parse(teks);
    if (data && data.type === "Feature") {
        data = data.geometry;
    }
    if (!data || !["Polygon", "MultiPolygon"].includes(data.type)) {
        throw new Error(_t("Tipe geometri harus Polygon atau MultiPolygon."));
    }
    const daftar = data.type === "Polygon" ? [data.coordinates] : data.coordinates;
    if (!Array.isArray(daftar)) {
        throw new Error(_t("Koordinat geometri tidak sah."));
    }
    const poligon = daftar.map((p) =>
        p.map((ring) => {
            const titik = ring.map((t) => [Number(t[0]), Number(t[1])]);
            const n = titik.length;
            if (n > 1 && titik[0][0] === titik[n - 1][0] && titik[0][1] === titik[n - 1][1]) {
                titik.pop();
            }
            return titik;
        })
    );
    return { tipe: data.type, poligon };
}

/** {tipe, poligon} -> teks GeoJSON (ring ditutup kembali), atau false bila kosong. */
function tulisGeometri(geo) {
    // Ring luar < 3 titik: poligon belum jadi (sedang digambar), tidak disimpan.
    const poligon = geo.poligon
        .filter((p) => p.length && p[0].length >= 3)
        .map((p) => p.filter((r) => r.length >= 3).map((r) => [...r, r[0]]));
    if (!poligon.length) {
        return false;
    }
    if (poligon.length === 1) {
        return JSON.stringify({ type: "Polygon", coordinates: poligon[0] });
    }
    return JSON.stringify({ type: "MultiPolygon", coordinates: poligon });
}

/**
 * Widget field Text berisi GeoJSON: peta dengan titik yang bisa digeser,
 * ditambah (titik tengah) dan dihapus, plus teks GeoJSON mentah.
 *
 * Pakai: <field name="geojson" widget="sd_geojson_peta"/>
 */
export class GeojsonPetaField extends Component {
    static template = "satu_data.GeojsonPetaField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.petaRef = useRef("peta");
        this.state = useState({
            galat: false,
            modeTeks: false,
            menggambar: false,
            terpilih: false,
            bisaUndo: false,
            terlaluBanyak: false,
            jumlahTitik: 0,
            jumlahPoligon: 0,
            pilihanPetaDasar: [],
            petaDasar: null,
            tanpaLeaflet: false,
        });

        this._geo = { tipe: "Polygon", poligon: [] };
        this._riwayat = [];
        this._teksTerakhir = undefined; // teks yang terakhir ditulis widget ini
        this._terpilih = null; // {p, r, v}
        this._seret = null;
        this._sudahPaskan = false;

        this._bacaNilai(this.nilai);

        onMounted(() => {
            this._init();
            this._muatInfo(this.props);
        });
        onWillUpdateProps((next) => {
            const nilaiBaru = next.record.data[next.name] || false;
            const ganti = next.record.resId !== this.props.record.resId;
            if (ganti || nilaiBaru !== this._teksTerakhir) {
                if (ganti) {
                    this._riwayat = [];
                    this._sudahPaskan = false;
                }
                this._bacaNilai(nilaiBaru);
                this._gambar();
            }
            const kunci = (p) => [p.record.resId, this._idCompany(p), this._idKecamatan(p)].join("/");
            if (kunci(next) !== kunci(this.props)) {
                this._muatInfo(next);
            }
        });
        onWillUnmount(() => {
            this._resizeObs?.disconnect();
            this._lepasPendengar();
            if (this._map) {
                this._map.remove();
                this._map = null;
            }
        });
    }

    get nilai() {
        return this.props.record.data[this.props.name] || false;
    }

    get bisaEdit() {
        return !this.props.readonly;
    }

    _idCompany(props) {
        return idMany2one(props.record.data.company_id);
    }

    _idKecamatan(props) {
        return props.record.resModel === "satu_data.desa"
            ? idMany2one(props.record.data.kecamatan_id)
            : false;
    }

    // ── Data ─────────────────────────────────────────────────────────────────

    _bacaNilai(teks) {
        this._teksTerakhir = teks;
        this._terpilih = null;
        this.state.terpilih = false;
        try {
            this._geo = bacaGeometri(teks);
            this.state.galat = false;
        } catch (e) {
            this._geo = { tipe: "Polygon", poligon: [] };
            this.state.galat = _t("Teks GeoJSON tidak bisa dibaca: %s", e.message);
        }
        this._hitungRingkas();
    }

    _hitungRingkas() {
        this.state.jumlahPoligon = this._geo.poligon.length;
        this.state.jumlahTitik = this._geo.poligon.reduce(
            (n, p) => n + p.reduce((m, r) => m + r.length, 0), 0);
        this.state.bisaUndo = this._riwayat.length > 0;
    }

    async _simpan() {
        const teks = tulisGeometri(this._geo);
        this._teksTerakhir = teks;
        this.state.galat = false;
        this._hitungRingkas();
        await this.props.record.update({ [this.props.name]: teks });
    }

    _catatRiwayat() {
        this._riwayat.push(JSON.stringify(this._geo.poligon));
        if (this._riwayat.length > MAKS_RIWAYAT) {
            this._riwayat.shift();
        }
        this.state.bisaUndo = true;
    }

    async _muatInfo(props) {
        if (!this._map) {
            return;
        }
        let info;
        try {
            info = await this.orm.call(props.record.resModel, "sd_info_editor_peta", [], {
                record_id: props.record.resId || false,
                company_id: this._idCompany(props),
                kecamatan_id: this._idKecamatan(props),
            });
        } catch {
            return; // acuan hanya pelengkap; editor tetap bisa dipakai
        }
        if (!this._map) {
            return;
        }
        this._lapisAcuan.clearLayers();
        for (const w of info.pembanding) {
            L.geoJSON(w.geometri, {
                interactive: false,
                style: { color: "#6b7280", weight: 1, fill: true, fillOpacity: 0.04, dashArray: "3 3" },
            }).addTo(this._lapisAcuan);
        }
        if (info.induk) {
            L.geoJSON(info.induk, {
                interactive: false,
                style: { color: "#111827", weight: 2, fill: false, opacity: 0.6 },
            }).addTo(this._lapisAcuan);
        }
        this.state.pilihanPetaDasar = info.peta_dasar.pilihan;
        if (this.state.petaDasar === null) {
            let tersimpan = null;
            try {
                tersimpan = localStorage.getItem(KUNCI_PETA_DASAR);
            } catch {
                // abaikan
            }
            const valid = tersimpan === "tanpa" || info.peta_dasar.pilihan.some((p) => p.kode === tersimpan);
            this.state.petaDasar = valid ? tersimpan : info.peta_dasar.bawaan;
        }
        this._aturPetaDasar();
        if (!this._geo.poligon.length && !this._sudahPaskan) {
            const b = this._lapisAcuan.getBounds();
            if (b.isValid()) {
                this._map.fitBounds(b, { padding: [16, 16] });
            }
        }
    }

    // ── Leaflet ──────────────────────────────────────────────────────────────

    _init() {
        const el = this.petaRef.el;
        if (!el || typeof L === "undefined") {
            this.state.tanpaLeaflet = true;
            return;
        }
        this._renderer = L.canvas({ padding: 0.3, tolerance: 4 });
        this._map = L.map(el, { zoomSnap: 0.25, doubleClickZoom: false, boxZoom: false })
            .setView(PUSAT_AWAL, ZOOM_AWAL);
        this._lapisAcuan = L.layerGroup().addTo(this._map);
        this._poli = null;
        this._lapisTitik = L.layerGroup().addTo(this._map);

        this._map.on("moveend", () => this._gambarTitik());
        this._map.on("click", (e) => this._onKlikPeta(e));
        // Selama menyeret, gerak dan lepas mouse didengar di dokumen agar tetap
        // tertangkap walau kursor berada di atas titik lain atau keluar dari peta.
        this._onGerakDokumen = (ev) => this._onGerak(ev);
        this._onLepasDokumen = () => this._onLepas();
        el.addEventListener("keydown", (ev) => this._onTombol(ev));

        // Peta di tab notebook bisa lahir dengan ukuran 0: paskan setelah tampil.
        this._resizeObs = new ResizeObserver(() => {
            if (!this._map) {
                return;
            }
            this._map.invalidateSize();
            if (!this._sudahPaskan && el.clientWidth > 0) {
                this.paskan();
            }
        });
        this._resizeObs.observe(el);
        this._gambar();
    }

    _aturPetaDasar() {
        if (!this._map) {
            return;
        }
        if (this._tile) {
            this._tile.remove();
            this._tile = null;
        }
        const pd = this.state.pilihanPetaDasar.find((p) => p.kode === this.state.petaDasar);
        if (!pd) {
            return;
        }
        const opsi = {
            attribution: pd.atribusi || "",
            maxZoom: pd.maks_zoom || 19,
            className: pd.abu ? "sd-tile-abu" : "",
        };
        if (pd.subdomain) {
            opsi.subdomains = pd.subdomain;
        }
        if (pd.maks_zoom_asli) {
            opsi.maxNativeZoom = pd.maks_zoom_asli;
        }
        this._tile = L.tileLayer(pd.url, opsi).addTo(this._map);
        this._tile.bringToBack();
    }

    _latlngs() {
        return this._geo.poligon.map((p) => p.map((r) => r.map(([x, y]) => [y, x])));
    }

    /** Gambar ulang poligon dan titik. */
    _gambar() {
        if (!this._map) {
            return;
        }
        const latlngs = this._latlngs();
        if (this._poli) {
            this._poli.setLatLngs(latlngs);
        } else {
            this._poli = L.polygon(latlngs, {
                color: WARNA, weight: 2, fillColor: WARNA, fillOpacity: 0.15, interactive: false,
            }).addTo(this._map);
        }
        this._gambarTitik();
    }

    /** Titik sudut (bisa digeser) dan titik tengah (untuk menambah), hanya yang terlihat. */
    _gambarTitik() {
        if (!this._map) {
            return;
        }
        this._lapisTitik.clearLayers();
        if (!this.bisaEdit) {
            return;
        }
        const batas = this._map.getBounds().pad(0.1);
        const terlihat = [];
        this._geo.poligon.forEach((p, pi) =>
            p.forEach((r, ri) =>
                r.forEach(([x, y], vi) => {
                    if (batas.contains([y, x])) {
                        terlihat.push([pi, ri, vi]);
                    }
                })
            )
        );
        this.state.terlaluBanyak = terlihat.length > MAKS_TITIK_TAMPIL;
        if (this.state.terlaluBanyak) {
            return;
        }
        const pilih = this._terpilih;
        for (const [pi, ri, vi] of terlihat) {
            const ring = this._geo.poligon[pi][ri];
            // Titik tengah ke titik berikutnya
            const [x1, y1] = ring[vi];
            const [x2, y2] = ring[(vi + 1) % ring.length];
            const sedangGambarRingIni = this.state.menggambar && pi === this._idxGambar;
            if (ring.length >= 2 && !(sedangGambarRingIni && vi === ring.length - 1)) {
                const tengah = L.circleMarker([(y1 + y2) / 2, (x1 + x2) / 2], {
                    renderer: this._renderer, radius: 3.5, weight: 1, color: WARNA,
                    fillColor: "#ffffff", fillOpacity: 0.6, opacity: 0.6,
                    bubblingMouseEvents: false,
                });
                tengah.on("mousedown", (e) => this._mulaiTambah(e, pi, ri, vi + 1));
                tengah.addTo(this._lapisTitik);
            }
        }
        for (const [pi, ri, vi] of terlihat) {
            const [x, y] = this._geo.poligon[pi][ri][vi];
            const dipilih = pilih && pilih.p === pi && pilih.r === ri && pilih.v === vi;
            const titik = L.circleMarker([y, x], {
                renderer: this._renderer, radius: dipilih ? 6 : 4.5, weight: 2,
                color: dipilih ? WARNA_PILIH : WARNA, fillColor: dipilih ? WARNA_PILIH : "#ffffff",
                fillOpacity: 1, bubblingMouseEvents: false,
            });
            titik.on("mousedown", (e) => this._mulaiSeret(e, { p: pi, r: ri, v: vi }, titik, false));
            titik.on("contextmenu", (e) => {
                L.DomEvent.preventDefault(e.originalEvent);
                this._hapusTitik({ p: pi, r: ri, v: vi });
            });
            titik.addTo(this._lapisTitik);
        }
    }

    // ── Interaksi titik ──────────────────────────────────────────────────────

    _mulaiSeret(e, alamat, marker, sudahDicatat) {
        if (!this.bisaEdit || e.originalEvent.button !== 0) {
            return;
        }
        L.DomEvent.preventDefault(e.originalEvent);
        this.petaRef.el?.focus({ preventScroll: true }); // agar tombol Delete/Ctrl+Z diterima
        this._map.dragging.disable();
        this._seret = { alamat, marker, bergerak: sudahDicatat };
        document.addEventListener("mousemove", this._onGerakDokumen);
        document.addEventListener("mouseup", this._onLepasDokumen);
    }

    _lepasPendengar() {
        if (this._onGerakDokumen) {
            document.removeEventListener("mousemove", this._onGerakDokumen);
            document.removeEventListener("mouseup", this._onLepasDokumen);
        }
    }

    _mulaiTambah(e, p, r, v) {
        if (!this.bisaEdit || e.originalEvent.button !== 0) {
            return;
        }
        this._catatRiwayat();
        const ll = e.target.getLatLng();
        this._geo.poligon[p][r].splice(v, 0, [bulat(ll.lng), bulat(ll.lat)]);
        this._poli.setLatLngs(this._latlngs());
        const marker = L.circleMarker(ll, {
            renderer: this._renderer, radius: 5, weight: 2, color: WARNA_PILIH,
            fillColor: "#ffffff", fillOpacity: 1, interactive: false,
        }).addTo(this._lapisTitik);
        this._mulaiSeret(e, { p, r, v }, marker, true);
    }

    _onGerak(ev) {
        const s = this._seret;
        if (!s || !this._map) {
            return;
        }
        if (!s.bergerak) {
            this._catatRiwayat();
            s.bergerak = true;
        }
        const ll = this._map.mouseEventToLatLng(ev);
        const { p, r, v } = s.alamat;
        this._geo.poligon[p][r][v] = [bulat(ll.lng), bulat(ll.lat)];
        s.marker.setLatLng(ll);
        this._poli.setLatLngs(this._latlngs());
    }

    _onLepas() {
        const s = this._seret;
        if (!s) {
            return;
        }
        this._seret = null;
        this._lepasPendengar();
        this._map?.dragging.enable();
        // Browser mengirim "click" setelah mouseup; jangan dianggap klik peta.
        this._waktuLepas = Date.now();
        const { p, r, v } = s.alamat;
        // Menggambar: klik titik pertama menutup poligon.
        if (!s.bergerak && this.state.menggambar && p === this._idxGambar && v === 0) {
            this.selesaiGambar();
            return;
        }
        this._terpilih = { p, r, v };
        this.state.terpilih = true;
        if (s.bergerak) {
            this._simpan();
        }
        this._gambarTitik();
    }

    _onKlikPeta(e) {
        if (this._waktuLepas && Date.now() - this._waktuLepas < 300) {
            return;
        }
        if (this.state.menggambar) {
            this._catatRiwayat();
            this._geo.poligon[this._idxGambar][0].push([bulat(e.latlng.lng), bulat(e.latlng.lat)]);
            this._gambar();
            this._hitungRingkas();
            if (this._geo.poligon[this._idxGambar][0].length >= 3) {
                this._simpan();
            }
            return;
        }
        if (this._terpilih) {
            this._terpilih = null;
            this.state.terpilih = false;
            this._gambarTitik();
        }
    }

    _onTombol(ev) {
        if (!this.bisaEdit) {
            return;
        }
        if ((ev.key === "Delete" || ev.key === "Backspace") && this._terpilih) {
            ev.preventDefault();
            this.hapusTitikTerpilih();
        } else if (ev.key === "z" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.batalkan();
        } else if (ev.key === "Escape" && this.state.menggambar) {
            this.selesaiGambar();
        }
    }

    _hapusTitik(alamat) {
        if (!this.bisaEdit) {
            return;
        }
        const ring = this._geo.poligon[alamat.p][alamat.r];
        const sedangGambar = this.state.menggambar && alamat.p === this._idxGambar;
        if (ring.length <= 3 && !sedangGambar) {
            this.notification.add(
                _t("Satu bagian area minimal 3 titik. Untuk membuang seluruh bagian ini, pakai \"Hapus bagian\"."),
                { type: "warning" });
            return;
        }
        this._catatRiwayat();
        ring.splice(alamat.v, 1);
        this._terpilih = null;
        this.state.terpilih = false;
        this._gambar();
        this._simpan();
    }

    // ── Tombol toolbar ───────────────────────────────────────────────────────

    hapusTitikTerpilih() {
        if (this._terpilih) {
            this._hapusTitik(this._terpilih);
        }
    }

    /** Buang bagian (poligon, atau lubang bila yang dipilih ring dalam) dari titik terpilih. */
    hapusBagian() {
        const t = this._terpilih;
        if (!t || !this.bisaEdit) {
            return;
        }
        this._catatRiwayat();
        if (t.r === 0) {
            this._geo.poligon.splice(t.p, 1);
        } else {
            this._geo.poligon[t.p].splice(t.r, 1);
        }
        this._terpilih = null;
        this.state.terpilih = false;
        this._gambar();
        this._simpan();
    }

    mulaiGambar() {
        if (!this.bisaEdit) {
            return;
        }
        this._catatRiwayat();
        this._geo.poligon.push([[]]);
        this._idxGambar = this._geo.poligon.length - 1;
        this._terpilih = null;
        this.state.terpilih = false;
        this.state.menggambar = true;
        this.petaRef.el?.focus();
    }

    selesaiGambar() {
        const ring = this._geo.poligon[this._idxGambar]?.[0];
        this.state.menggambar = false;
        if (ring && ring.length < 3) {
            this._geo.poligon.splice(this._idxGambar, 1);
        }
        this._idxGambar = null;
        this._gambar();
        this._simpan();
    }

    batalkan() {
        if (!this._riwayat.length || !this.bisaEdit) {
            return;
        }
        this._geo.poligon = JSON.parse(this._riwayat.pop());
        if (this.state.menggambar && !this._geo.poligon[this._idxGambar]) {
            this.state.menggambar = false;
            this._idxGambar = null;
        }
        this._terpilih = null;
        this.state.terpilih = false;
        this._gambar();
        this._simpan();
    }

    paskan() {
        if (!this._map || !this._poli) {
            return;
        }
        const b = this._poli.getBounds();
        if (b.isValid()) {
            this._map.fitBounds(b, { padding: [24, 24] });
            this._sudahPaskan = true;
        }
    }

    pilihPetaDasar(ev) {
        this.state.petaDasar = ev.target.value;
        try {
            localStorage.setItem(KUNCI_PETA_DASAR, ev.target.value);
        } catch {
            // abaikan
        }
        this._aturPetaDasar();
    }

    toggleTeks() {
        this.state.modeTeks = !this.state.modeTeks;
    }

    async ubahTeks(ev) {
        const teks = ev.target.value.trim() || false;
        this._riwayat = [];
        this._bacaNilai(teks);
        this._gambar();
        this.paskan();
        await this.props.record.update({ [this.props.name]: teks });
    }
}

registry.category("fields").add("sd_geojson_peta", {
    component: GeojsonPetaField,
    displayName: _t("Editor Peta GeoJSON"),
    supportedTypes: ["text"],
});
