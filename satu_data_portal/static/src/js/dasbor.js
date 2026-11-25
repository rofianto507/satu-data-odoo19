import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { loadCSS, loadJS } from "@web/core/assets";

// Pustaka dari modul inti (salinan lokal): Leaflet 1.7.1 (BSD-2) dan Apache ECharts 5.6.1.
const URL_LEAFLET_CSS = "/satu_data/static/lib/leaflet/leaflet.css";
const URL_LEAFLET_JS = "/satu_data/static/lib/leaflet/leaflet.js";
const URL_ECHARTS = "/satu_data/static/lib/echarts/echarts.min.js";
const WARNA_TEKS = "#4b5563";
const WARNA_GARIS = "#e5e7eb";
const WARNA_BATAS = "#8b93a1";
// Warna utama website (bisa diubah Admin di penyunting website); cadangan biru bila tak terbaca.
function warnaUtama() {
    const w = getComputedStyle(document.documentElement).getPropertyValue("--bs-primary").trim();
    return w || "#1d4ed8";
}
function warnaTipis(hex, alfa) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) {
        return "rgba(29, 78, 216, " + alfa + ")";
    }
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
}
const WARNA_UTAMA = warnaUtama();
const TINGGI_BATANG = 20;

// "Januari 2025" -> "Jan 2025" agar label sumbu tidak saling menimpa di panel sempit.
function labelSingkat(label) {
    return /^[A-Za-z]{4,} \d{4}$/.test(label) ? label.replace(/^([A-Za-z]{3})\w*/, "$1") : label;
}

function escapeHtml(teks) {
    const el = document.createElement("span");
    el.textContent = teks ?? "";
    return el.innerHTML;
}

/**
 * Dashboard tematik publik: satu data dipilih, periode dipilih di peramban.
 * Peta kecamatan (sekali muat), nilai dari /dashboard/data/<kode>.json.
 */
export class DasborPublik extends Interaction {
    static selector = ".sd-dasbor-halaman";

    setup() {
        this.konf = JSON.parse(this.el.dataset.konfigurasi || "{}");
        this.kode = this.el.dataset.kode;
        this.data = null;
        this.indeks = -1;
        this.grafik = [];
        this.q = (s) => this.el.querySelector(s);
    }

    async willStart() {
        const tugas = [];
        if (!window.L) {
            tugas.push(loadCSS(URL_LEAFLET_CSS), loadJS(URL_LEAFLET_JS));
        }
        if (!window.echarts) {
            tugas.push(loadJS(URL_ECHARTS));
        }
        const peta = fetch(this.konf.url_peta).then((r) => r.json());
        await Promise.all(tugas);
        this.geojson = await peta;
    }

    start() {
        this._buatPeta();
        this.tren = window.echarts.init(this.q(".sd-dasbor-tren"), null, { renderer: "svg" });
        this.peringkat = window.echarts.init(this.q(".sd-dasbor-peringkat"), null, { renderer: "svg" });
        this.grafik.push(this.tren, this.peringkat);

        this.pilihData = this.q("#sd-pilih-data");
        this.pilihPeriode = this.q("#sd-pilih-periode");
        this.addListener(this.pilihData, "change", () => this._muat(this.pilihData.value));
        this.addListener(this.pilihPeriode, "change", () => {
            this.indeks = Number(this.pilihPeriode.value);
            this._gambar();
        });
        this.addListener(window, "resize", () => this.grafik.forEach((g) => g.resize()));
        this._muat(this.kode);
    }

    destroy() {
        this.grafik.forEach((g) => g.dispose());
        this.peta?.remove();
    }

    // ── Peta ─────────────────────────────────────────────────────────────────

    _buatPeta() {
        const el = this.q(".sd-dasbor-peta");
        this.peta = L.map(el, { zoomSnap: 0.25, maxZoom: 19, scrollWheelZoom: false });
        const pd = this.konf.peta_dasar;
        if (pd && pd.url) {
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
            L.tileLayer(pd.url, opsi).addTo(this.peta);
        }
        this.lapisan = L.geoJSON(this.geojson, {
            style: () => ({ color: WARNA_BATAS, weight: 1, fillOpacity: 0.75 }),
            onEachFeature: (fitur, layer) => {
                layer.bindTooltip(() => this._isiTooltip(fitur.properties), {
                    sticky: true,
                    direction: "top",
                    className: "sd-tooltip",
                });
                layer.on({
                    mouseover: (e) => {
                        e.target.setStyle({ weight: 2.5, color: "#111827" });
                        e.target.bringToFront();
                    },
                    mouseout: (e) => e.target.setStyle({ weight: 1, color: WARNA_BATAS }),
                });
            },
        }).addTo(this.peta);
        if (this.geojson.features?.length) {
            this.peta.fitBounds(this.lapisan.getBounds(), { padding: [12, 12] });
        } else {
            this.peta.setView([-2.5, 118], 5);
        }
    }

    _isiTooltip(prop) {
        const w = this.data?.wilayah[String(prop.id)];
        const v = w ? w.nilai[this.indeks] : null;
        return `<strong>${escapeHtml(prop.nama)}</strong><br/>${escapeHtml(this._teks(v))}`;
    }

    // ── Data ─────────────────────────────────────────────────────────────────

    async _muat(kode) {
        this._status("Memuat data…");
        let data;
        try {
            const res = await this.waitFor(fetch(`/dashboard/data/${encodeURIComponent(kode)}.json`));
            if (!res.ok) {
                throw new Error(res.status === 429 ? "Terlalu banyak permintaan, coba lagi sebentar." : "Data gagal dimuat.");
            }
            data = await this.waitFor(res.json());
        } catch (err) {
            this._status(err.message || "Data gagal dimuat.");
            return;
        }
        this.data = data;
        this.kode = kode;
        this.fmt = new Intl.NumberFormat("id-ID", {
            minimumFractionDigits: data.desimal,
            maximumFractionDigits: data.desimal,
        });
        // Pilihan periode: terbaru sebagai bawaan.
        this.pilihPeriode.replaceChildren(
            ...data.periode.map((label, i) => new Option(label, String(i)))
        );
        this.indeks = data.periode.length - 1;
        this.pilihPeriode.value = String(this.indeks);
        this.pilihPeriode.disabled = data.periode.length < 2;
        const url = new URL(window.location.href);
        url.searchParams.set("data", kode);
        window.history.replaceState(null, "", url);
        this._status("");
        this._gambar();
    }

    _teks(v) {
        if (v === null || v === undefined) {
            return "Belum ada data";
        }
        const satuan = this.data.satuan;
        return satuan === "%" ? `${this.fmt.format(v)}%` : `${this.fmt.format(v)} ${satuan}`.trim();
    }

    _kelas(v) {
        if (v === null || v === undefined) {
            return null;
        }
        const kelas = this.data.kelas[this.indeks] || [];
        return kelas.find((k) => k.atas === null || v < k.atas) || kelas[kelas.length - 1];
    }

    _status(teks) {
        const el = this.q(".sd-dasbor-status");
        el.textContent = teks;
        el.classList.toggle("d-none", !teks);
    }

    // ── Tampilan ─────────────────────────────────────────────────────────────

    _gambar() {
        const d = this.data;
        const i = this.indeks;
        this.q(".sd-dasbor-judul").textContent = d.nama;
        this.q(".sd-dasbor-catatan").textContent = d.rinci
            ? d.catatan || d.definisi
            : "Data ini hanya disajikan untuk tingkat kabupaten/kota.";
        this.q(".sd-dasbor-tautan").href = d.url;

        // Peta
        this.lapisan.setStyle((fitur) => {
            const w = d.wilayah[String(fitur.properties.id)];
            const k = d.rinci && w ? this._kelas(w.nilai[i]) : null;
            return {
                color: WARNA_BATAS,
                weight: 1,
                dashArray: k ? null : "4 3",
                fillColor: k ? k.warna : d.warna_tanpa_data,
                fillOpacity: 0.75,
            };
        });
        this._legenda();

        // Angka kab/kota dan perubahan dari periode sebelumnya
        const nilai = d.total.nilai;
        this.q(".sd-dasbor-kpi-label").textContent = `${d.total.nama}, ${d.periode[i] || ""}`;
        this.q(".sd-dasbor-kpi").textContent = this._teks(nilai[i]);
        const elUbah = this.q(".sd-dasbor-kpi-ubah");
        const sebelum = i > 0 ? nilai[i - 1] : null;
        if (nilai[i] !== null && sebelum !== null && sebelum !== undefined) {
            const selisih = nilai[i] - sebelum;
            const arahTeks = selisih > 0 ? "naik" : "turun";
            const baik = d.arah === "netral" || selisih === 0 ? null : (selisih > 0) === (d.arah === "naik");
            elUbah.textContent = selisih === 0
                ? `Tidak berubah dari ${d.periode[i - 1]}`
                : `${arahTeks[0].toUpperCase()}${arahTeks.slice(1)} ${this.fmt.format(Math.abs(selisih))} dari ${d.periode[i - 1]}`;
            elUbah.className = `small mb-0 sd-dasbor-kpi-ubah ${baik === null ? "text-muted" : baik ? "text-success" : "text-danger"}`;
        } else {
            elUbah.textContent = "";
        }

        this._grafikTren();
        this._grafikPeringkat();
    }

    _legenda() {
        const d = this.data;
        const el = this.q(".sd-dasbor-legenda");
        if (!d.rinci) {
            el.innerHTML = "";
            return;
        }
        const f = (v) => this.fmt.format(v);
        const baris = (this.data.kelas[this.indeks] || []).map((k) => {
            const label = k.bawah === null ? `< ${f(k.atas)}` : k.atas === null ? `≥ ${f(k.bawah)}` : `${f(k.bawah)} – < ${f(k.atas)}`;
            return `<span class="sd-legenda-item"><span class="sd-legenda-warna" style="background:${k.warna}"></span>${escapeHtml(label)}</span>`;
        });
        baris.push(
            `<span class="sd-legenda-item"><span class="sd-legenda-warna sd-legenda-warna--kosong" style="background:${d.warna_tanpa_data}"></span>Belum ada data</span>`
        );
        el.innerHTML = (d.satuan ? `<span class="sd-legenda-item fw-semibold">${escapeHtml(d.satuan)}</span>` : "") + baris.join("");
    }

    _grafikTren() {
        const d = this.data;
        // Satu seri per tahun bila data bulanan/triwulanan (kumulatif per tahun): garis
        // putus saat tahun berganti. Selain itu satu seri.
        const kelompok = d.putus_tahun ? [...new Set(d.tahun)] : [null];
        const seri = kelompok.map((tahun) => ({
            type: d.periode.length > 2 ? "line" : "bar",
            data: d.total.nilai.map((v, j) => ({
                value: tahun === null || d.tahun[j] === tahun ? v : null,
                symbolSize: j === this.indeks ? 11 : 6,
                itemStyle: { color: WARNA_UTAMA },
            })),
            connectNulls: false,
            barMaxWidth: 48,
            lineStyle: { width: 2.5, color: WARNA_UTAMA },
            areaStyle: d.periode.length > 2 ? { color: warnaTipis(WARNA_UTAMA, 0.08) } : undefined,
        }));
        this.tren.setOption(
            {
                animation: false,
                textStyle: { fontFamily: "inherit" },
                grid: { left: 8, right: 28, top: 16, bottom: 8, containLabel: true },
                tooltip: { trigger: "axis", valueFormatter: (v) => this._teks(v) },
                xAxis: {
                    type: "category",
                    data: d.periode,
                    axisLabel: { color: WARNA_TEKS, hideOverlap: true, formatter: labelSingkat },
                    axisLine: { lineStyle: { color: WARNA_GARIS } },
                },
                yAxis: {
                    type: "value",
                    axisLabel: { color: WARNA_TEKS, formatter: (v) => this.fmt.format(v) },
                    splitLine: { lineStyle: { color: WARNA_GARIS } },
                },
                series: seri,
            },
            true
        );
    }

    _grafikPeringkat() {
        const d = this.data;
        const panel = this.q(".sd-dasbor-peringkat").closest(".col-12");
        const isi = Object.values(d.wilayah)
            .filter((w) => w.nilai[this.indeks] !== null && w.nilai[this.indeks] !== undefined)
            .map((w) => ({ nama: w.nama, nilai: w.nilai[this.indeks] }))
            .sort((a, b) => a.nilai - b.nilai); // terbesar di atas (sumbu kategori digambar dari bawah)
        panel.classList.toggle("d-none", !d.rinci || !isi.length);
        if (!d.rinci || !isi.length) {
            return;
        }
        const el = this.q(".sd-dasbor-peringkat");
        el.style.height = `${Math.max(240, isi.length * TINGGI_BATANG + 40)}px`;
        this.peringkat.resize();
        this.peringkat.setOption(
            {
                animation: false,
                textStyle: { fontFamily: "inherit" },
                grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => this._teks(v) },
                xAxis: { type: "value", show: false },
                yAxis: {
                    type: "category",
                    data: isi.map((k) => k.nama),
                    axisLabel: { color: WARNA_TEKS },
                    axisTick: { show: false },
                    axisLine: { lineStyle: { color: WARNA_GARIS } },
                },
                series: [
                    {
                        type: "bar",
                        barMaxWidth: 14,
                        data: isi.map((k) => ({
                            value: k.nilai,
                            itemStyle: { color: this._kelas(k.nilai)?.warna || WARNA_UTAMA, borderColor: WARNA_BATAS, borderWidth: 0.5 },
                        })),
                        label: {
                            show: true,
                            position: "right",
                            color: WARNA_TEKS,
                            formatter: (p) => this.fmt.format(p.value),
                        },
                    },
                ],
            },
            true
        );
    }
}

registry.category("public.interactions").add("satu_data_portal.dasbor", DasborPublik);
