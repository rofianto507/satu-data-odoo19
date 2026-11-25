import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { loadJS } from "@web/core/assets";

// Apache ECharts dari modul inti (salinan lokal, lisensi Apache 2.0).
const URL_ECHARTS = "/satu_data/static/lib/echarts/echarts.min.js";
const WARNA_UTAMA = "#1d4ed8";
const WARNA_TEKS = "#4b5563";
const WARNA_GARIS = "#e5e7eb";
const TINGGI_BATANG = 20;

/**
 * Grafik halaman data publik: tren kab/kota per periode dan sebaran per kecamatan.
 * Data dari atribut data-grafik (JSON yang disiapkan server).
 */
export class GrafikData extends Interaction {
    static selector = ".sd-data-grafik";

    async willStart() {
        if (!window.echarts) {
            await loadJS(URL_ECHARTS);
        }
    }

    start() {
        let data;
        try {
            data = JSON.parse(this.el.dataset.grafik || "{}");
        } catch {
            return;
        }
        const desimal = data.desimal || 0;
        const fmt = new Intl.NumberFormat("id-ID", {
            minimumFractionDigits: desimal,
            maximumFractionDigits: desimal,
        });
        const satuan = data.satuan || "";
        const teks = (v) => {
            if (v === null || v === undefined) {
                return "Belum ada data";
            }
            return satuan === "%" ? `${fmt.format(v)}%` : `${fmt.format(v)} ${satuan}`.trim();
        };
        this.grafik = [];

        const elTren = this.el.querySelector('[data-jenis="tren"]');
        if (elTren && data.periode?.length) {
            this._gambar(elTren, {
                grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
                tooltip: { trigger: "axis", valueFormatter: teks },
                xAxis: {
                    type: "category",
                    data: data.periode,
                    axisLabel: { color: WARNA_TEKS, hideOverlap: true },
                    axisLine: { lineStyle: { color: WARNA_GARIS } },
                },
                yAxis: {
                    type: "value",
                    axisLabel: { color: WARNA_TEKS, formatter: (v) => fmt.format(v) },
                    splitLine: { lineStyle: { color: WARNA_GARIS } },
                },
                series: [
                    data.periode.length > 2
                        ? {
                              name: data.nama_total,
                              type: "line",
                              data: data.total,
                              symbolSize: 7,
                              lineStyle: { width: 2.5, color: WARNA_UTAMA },
                              itemStyle: { color: WARNA_UTAMA },
                              areaStyle: { color: "rgba(29, 78, 216, 0.08)" },
                          }
                        : {
                              name: data.nama_total,
                              type: "bar",
                              data: data.total,
                              barMaxWidth: 56,
                              itemStyle: { color: WARNA_UTAMA, borderRadius: [4, 4, 0, 0] },
                          },
                ],
            });
        }

        const elKec = this.el.querySelector('[data-jenis="kecamatan"]');
        if (elKec && data.kecamatan?.length) {
            const judul = this.el.querySelector(".sd-periode-kecamatan");
            if (judul) {
                judul.textContent = data.periode_kecamatan || "";
            }
            // Terbesar di atas: sumbu kategori ECharts digambar dari bawah.
            const isi = [...data.kecamatan].reverse();
            elKec.style.height = `${Math.max(240, isi.length * TINGGI_BATANG + 40)}px`;
            this._gambar(elKec, {
                grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
                tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: teks },
                xAxis: { type: "value", show: false },
                yAxis: {
                    type: "category",
                    data: isi.map((k) => k.nama),
                    axisLabel: { color: WARNA_TEKS },
                    axisLine: { lineStyle: { color: WARNA_GARIS } },
                    axisTick: { show: false },
                },
                series: [
                    {
                        type: "bar",
                        data: isi.map((k) => k.nilai),
                        barMaxWidth: 14,
                        itemStyle: { color: WARNA_UTAMA, borderRadius: [0, 3, 3, 0] },
                        label: {
                            show: true,
                            position: "right",
                            color: WARNA_TEKS,
                            formatter: (p) => fmt.format(p.value),
                        },
                    },
                ],
            });
        }

        this.addListener(window, "resize", () => this.grafik.forEach((g) => g.resize()));
    }

    _gambar(el, opsi) {
        const grafik = window.echarts.init(el, null, { renderer: "svg" });
        grafik.setOption({ animation: false, textStyle: { fontFamily: "inherit" }, ...opsi });
        this.grafik.push(grafik);
    }

    destroy() {
        (this.grafik || []).forEach((g) => g.dispose());
    }
}

registry.category("public.interactions").add("satu_data_portal.grafik_data", GrafikData);
