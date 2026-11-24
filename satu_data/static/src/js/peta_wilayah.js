/** @odoo-module **/

import { Component, onMounted, onWillUnmount, toRaw, useEffect, useRef, useState } from "@odoo/owl";
import { escape } from "@web/core/utils/strings";

// Tampilan awal sebelum batas wilayah dimuat: seluruh Indonesia.
const PUSAT_AWAL = [-2.5, 118];
const ZOOM_AWAL = 5;
const fmtAngka = new Intl.NumberFormat("id-ID");
// Tebal garis batas wilayah saat disorot (hover) atau dipilih, dalam piksel.
const TEBAL_SOROT = 2;
// Warna garis batas antarwilayah (abu-abu, terbaca di atas semua warna kelas).
const WARNA_BATAS = "#8b93a1";
// Penanda titik (mis. puskesmas): lencana putih berpinggir ungu dengan salib merah.
// Putih dan ungu tetap terbaca di atas semua warna kelas peta.
const UKURAN_TITIK = 20;
const IKON_TITIK =
    '<svg viewBox="0 0 32 32" width="100%" height="100%" aria-hidden="true">' +
    '<circle cx="16" cy="16" r="13.5" fill="#fff" stroke="#5b21b6" stroke-width="3"/>' +
    '<rect x="13" y="8" width="6" height="16" rx="1.5" fill="#ff005c"/>' +
    '<rect x="8" y="13" width="16" height="6" rx="1.5" fill="#ff005c"/>' +
    "</svg>";

// Penanda satuan pendidikan: lencana putih berpinggir biru dengan topi toga.
const IKON_SEKOLAH =
    '<svg viewBox="0 0 32 32" width="100%" height="100%" aria-hidden="true">' +
    '<circle cx="16" cy="16" r="13.5" fill="#fff" stroke="#1d4ed8" stroke-width="3"/>' +
    '<path d="M16 8 5.5 13.5 16 19l10.5-5.5z" fill="#f59e0b"/>' +
    '<path d="M10 17v4.2c0 1.4 2.7 2.8 6 2.8s6-1.4 6-2.8V17l-6 3.2z" fill="#f59e0b"/>' +
    "</svg>";
const IKON = { puskesmas: IKON_TITIK, sekolah: IKON_SEKOLAH };

/**
 * Peta choropleth wilayah (Leaflet).
 *
 * Komponen ini hanya menggambar: warna diambil dari `kelas` yang dihitung server,
 * klik area diteruskan ke induk lewat `onKlik(id)`.
 */
export class SatuDataPeta extends Component {
    static template = "satu_data.PetaWilayah";
    static props = {
        wilayah:        Array,
        kelas:          Array,
        warnaTanpaData: String,
        terpilihId:     { type: [Number, Boolean], optional: true },
        // {kode, url, subdomain, atribusi, abu, maks_zoom} atau false (tanpa peta dasar)
        petaDasar:      { type: [Object, Boolean] },
        petunjukKlik:   String,
        judulLegenda:   String,
        onKlik:         Function,
        // Teks angka di tooltip wilayah: (w) => string. Bawaan: jumlah penduduk.
        teksNilai:      { type: Function, optional: true },
        // Titik di atas wilayah (mis. puskesmas): [{id, nama, lat, lng, keterangan: [string]}]
        titik:          { type: Array, optional: true },
        judulTitik:     { type: String, optional: true },
        // Gambar penanda titik: "puskesmas" (bawaan) atau "sekolah".
        ikonTitik:      { type: String, optional: true },
        // Bila ada, jendela info titik memuat tombol "Lihat detail data" yang memanggil (id titik).
        onDetailTitik:  { type: Function, optional: true },
    };

    setup() {
        this.petaRef = useRef("peta");
        this.state = useState({ tanpaLeaflet: false });
        this._map = null;
        this._lapisan = null;
        this._tile = null;
        this._lapisanTitik = null;
        this._byId = new Map();

        onMounted(() => this._init());
        useEffect(() => this._gambar(), () => [this.props.wilayah]);
        useEffect(() => this._gambarTitik(), () => [this.props.titik, this.props.ikonTitik]);
        useEffect(() => this._sorot(), () => [this.props.terpilihId]);
        useEffect(() => this._aturPetaDasar(), () => [this.props.petaDasar && this.props.petaDasar.kode]);
        onWillUnmount(() => {
            this._resizeObs?.disconnect();
            if (this._map) {
                this._map.remove();
                this._map = null;
            }
        });
    }

    get adaGeometri() {
        return this.props.wilayah.some((w) => w.geometri);
    }

    // ── Leaflet ──────────────────────────────────────────────────────────────

    _init() {
        const el = this.petaRef.el;
        if (!el || typeof L === "undefined") {
            this.state.tanpaLeaflet = true;
            return;
        }
        this._map = L.map(el, { zoomSnap: 0.25, zoomControl: true }).setView(PUSAT_AWAL, ZOOM_AWAL);
        // Ukuran kontainer berubah saat layar penuh, rotasi ponsel, atau panel dilipat.
        this._resizeObs = new ResizeObserver(() => this._map && this._map.invalidateSize());
        this._resizeObs.observe(el);
    }

    _aturPetaDasar() {
        if (!this._map) {
            return;
        }
        // Ganti lapisan tile setiap kali pilihan peta dasar berubah.
        if (this._tile) {
            this._tile.remove();
            this._tile = null;
        }
        const pd = toRaw(this.props.petaDasar);
        if (!pd || !pd.url) {
            return;
        }
        const opsi = {
            attribution: pd.atribusi || "",
            maxZoom: pd.maks_zoom || 19,
            // Peta dasar berwarna ramai (OSM standar) dibuat abu-abu lewat CSS agar
            // tidak bercampur dengan warna data.
            className: pd.abu ? "sd-tile-abu" : "",
        };
        if (pd.subdomain) {
            opsi.subdomains = pd.subdomain;
        }
        if (pd.maks_zoom_asli) {
            opsi.maxNativeZoom = pd.maks_zoom_asli; // zoom di atasnya: tile diperbesar
        }
        this._tile = L.tileLayer(pd.url, opsi).addTo(this._map);
        this._tile.bringToBack();
    }

    _gambar() {
        if (!this._map) {
            return;
        }
        if (this._lapisan) {
            this._lapisan.remove();
            this._lapisan = null;
        }
        // Data mentah (bukan proxy reaktif) agar Leaflet tidak membaca lewat proxy OWL.
        const wilayah = toRaw(this.props.wilayah);
        this._byId = new Map(wilayah.map((w) => [w.id, w]));
        const features = wilayah
            .filter((w) => w.geometri)
            .map((w) => ({ type: "Feature", properties: { id: w.id }, geometry: toRaw(w.geometri) }));
        if (!features.length) {
            return;
        }
        this._lapisan = L.geoJSON(
            { type: "FeatureCollection", features },
            {
                style: (f) => this._gaya(f.properties.id),
                onEachFeature: (f, layer) => {
                    const w = this._byId.get(f.properties.id);
                    layer.bindTooltip(this._isiTooltip(w), {
                        sticky: true,
                        direction: "top",
                        className: "sd-tooltip",
                    });
                    layer.on({
                        mouseover: (e) => {
                            e.target.setStyle({ weight: TEBAL_SOROT, color: "#111827" });
                            e.target.bringToFront();
                        },
                        mouseout: (e) => this._lapisan && this._lapisan.resetStyle(e.target),
                        click: () => this.props.onKlik(w.id),
                    });
                },
            }
        ).addTo(this._map);
        this._map.fitBounds(this._lapisan.getBounds(), { padding: [16, 16] });
    }

    _gambarTitik() {
        if (!this._map) {
            return;
        }
        if (this._lapisanTitik) {
            this._lapisanTitik.remove();
            this._lapisanTitik = null;
        }
        const titik = toRaw(this.props.titik || []).filter((t) => t.lat || t.lng);
        if (!titik.length) {
            return;
        }
        // Penanda HTML (bukan circleMarker) agar bisa bergambar; pane markerPane selalu di
        // atas pane wilayah, jadi titik tidak tertutup saat wilayah digambar ulang atau disorot.
        const ikon = L.divIcon({
            className: "sd-marker-titik",
            html: IKON[this.props.ikonTitik] || IKON_TITIK,
            iconSize: [UKURAN_TITIK, UKURAN_TITIK],
            iconAnchor: [UKURAN_TITIK / 2, UKURAN_TITIK / 2],
            popupAnchor: [0, -UKURAN_TITIK / 2],
        });
        const adaDetail = Boolean(this.props.onDetailTitik);
        // Info titik tampil di jendela info setelah diklik (bukan saat hover).
        const markers = (
            titik.map((t) => {
                const isi =
                    `<div class="sd-popup-nama">${escape(t.nama)}</div>` +
                    (t.keterangan || [])
                        .map((k) => `<div class="sd-popup-baris">${escape(k)}</div>`)
                        .join("") +
                    (adaDetail
                        ? '<button type="button" class="btn btn-sm btn-primary sd-popup-detail">' +
                          '<i class="fa fa-table" aria-hidden="true"></i> Lihat detail data</button>'
                        : "");
                const marker = L.marker([t.lat, t.lng], {
                    icon: ikon,
                    keyboard: false,
                    riseOnHover: true,
                }).bindPopup(isi, { className: "sd-popup", minWidth: 190, maxWidth: 280, autoPanPadding: [24, 24] });
                // Tombol ada di dalam jendela info (Leaflet menghentikan perambatan klik di sana),
                // jadi pasang langsung saat dibuka; onclick menimpa, tidak menumpuk.
                marker.on("popupopen", (e) => {
                    const tombol = e.popup.getElement()?.querySelector(".sd-popup-detail");
                    if (tombol) {
                        tombol.onclick = () => {
                            this._map.closePopup();
                            this.props.onDetailTitik(t.id);
                        };
                    }
                });
                return marker;
            })
        );
        // Titik yang berdekatan digabung menjadi lingkaran berangka (klik = perbesar, atau
        // pada zoom maksimum titik disebar). Tanpa plugin markercluster, titik digambar apa adanya.
        if (L.markerClusterGroup) {
            const warna = this.props.ikonTitik === "sekolah" ? "sd-cluster--sekolah" : "sd-cluster--puskesmas";
            this._lapisanTitik = L.markerClusterGroup({
                showCoverageOnHover: false,
                maxClusterRadius: 42,
                spiderfyOnMaxZoom: true,
                iconCreateFunction: (cluster) => {
                    const n = cluster.getChildCount();
                    const ukuran = n < 10 ? 30 : n < 100 ? 36 : 44;
                    return L.divIcon({
                        html: `<span>${n}</span>`,
                        className: `sd-cluster ${warna}`,
                        iconSize: [ukuran, ukuran],
                    });
                },
            });
            this._lapisanTitik.addLayers(markers);
        } else {
            this._lapisanTitik = L.layerGroup(markers);
        }
        this._lapisanTitik.addTo(this._map);
    }

    _sorot() {
        if (!this._lapisan) {
            return;
        }
        this._lapisan.setStyle((f) => this._gaya(f.properties.id));
        this._lapisan.eachLayer((layer) => {
            if (layer.feature.properties.id === this.props.terpilihId) {
                layer.bringToFront();
            }
        });
    }

    _gaya(id) {
        const w = this._byId.get(id);
        const kelas = toRaw(this.props.kelas);
        const terpilih = id === this.props.terpilihId;
        const adaData = w && w.kelas >= 0;
        return {
            color: terpilih ? "#111827" : WARNA_BATAS,
            weight: terpilih ? TEBAL_SOROT : 1.2,
            dashArray: adaData ? null : "4 3",
            fillColor: adaData ? kelas[w.kelas].warna : this.props.warnaTanpaData,
            fillOpacity: 0.70,
        };
    }

    _isiTooltip(w) {
        let angka;
        if (this.props.teksNilai) {
            angka = this.props.teksNilai(w);
        } else {
            angka = w.angka ? `${fmtAngka.format(w.angka.penduduk)} jiwa` : "Belum ada data";
        }
        return (
            `<div class="sd-tooltip-nama">${escape(w.nama)}</div>` +
            `<div class="sd-tooltip-angka">${angka}</div>` +
            `<div class="sd-tooltip-petunjuk">${escape(this.props.petunjukKlik)}</div>`
        );
    }
}
