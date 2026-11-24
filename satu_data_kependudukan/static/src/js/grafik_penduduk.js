/** @odoo-module **/

import { Component, onMounted, onWillUnmount, toRaw, useEffect, useRef, useState } from "@odoo/owl";
import { escape } from "@web/core/utils/strings";
import { muatEcharts } from "@satu_data/js/echarts_loader";

const fmtAngka = new Intl.NumberFormat("id-ID");
const fmtSingkat = new Intl.NumberFormat("id-ID", { notation: "compact", maximumFractionDigits: 1 });
const WARNA_LAKI = "#2c7fb8";
const WARNA_PEREMPUAN = "#d95f8e";

/**
 * Grafik batang bertumpuk laki-laki/perempuan per wilayah (ECharts).
 * Level kecamatan: satu batang per kecamatan; level desa: per desa/kelurahan.
 * Klik batang diteruskan ke induk lewat `onKlik(id)`.
 */
export class GrafikPenduduk extends Component {
    static template = "satu_data_kependudukan.GrafikPenduduk";
    static props = {
        wilayah: Array,
        onKlik: Function,
    };

    setup() {
        this.grafikRef = useRef("grafik");
        this.state = useState({ galat: false });
        this._grafik = null;
        this._urut = [];

        onMounted(async () => {
            let echarts;
            try {
                echarts = await muatEcharts();
            } catch {
                this.state.galat = true;
                return;
            }
            const el = this.grafikRef.el;
            if (!el || !echarts) {
                this.state.galat = !echarts;
                return;
            }
            this._grafik = echarts.init(el, null, { renderer: "canvas" });
            this._grafik.on("click", (p) => {
                const w = this._urut[p.dataIndex];
                if (w) {
                    this.props.onKlik(w.id);
                }
            });
            // Lebar berubah saat sidebar diciutkan, layar penuh, atau rotasi ponsel.
            this._resizeObs = new ResizeObserver(() => this._grafik?.resize());
            this._resizeObs.observe(el);
            this._gambar();
        });
        useEffect(() => this._gambar(), () => [this.props.wilayah]);
        onWillUnmount(() => {
            this._resizeObs?.disconnect();
            this._grafik?.dispose();
            this._grafik = null;
        });
    }

    get adaData() {
        return this.props.wilayah.some((w) => w.angka && w.angka.penduduk > 0);
    }

    _gambar() {
        if (!this._grafik) {
            return;
        }
        // Terbanyak di kiri; wilayah tanpa data tidak ditampilkan.
        this._urut = toRaw(this.props.wilayah)
            .filter((w) => w.angka && w.angka.penduduk > 0)
            .sort((a, b) => b.angka.penduduk - a.angka.penduduk);
        const nama = this._urut.map((w) => w.nama);
        const huruf = parseFloat(getComputedStyle(this.grafikRef.el).fontSize) || 13;
        const kecil = Math.round(huruf * 0.85);
        const banyak = nama.length > 12;

        this._grafik.setOption(
            {
                animationDuration: 400,
                color: [WARNA_LAKI, WARNA_PEREMPUAN],
                textStyle: { fontFamily: "inherit", fontSize: kecil },
                legend: {
                    top: 0,
                    right: 0,
                    itemWidth: 12,
                    itemHeight: 12,
                    textStyle: { fontSize: kecil, color: "#5b6474" },
                },
                tooltip: {
                    trigger: "axis",
                    axisPointer: { type: "shadow" },
                    textStyle: { fontSize: kecil },
                    formatter: (params) => {
                        const w = this._urut[params[0]?.dataIndex];
                        if (!w) {
                            return "";
                        }
                        const baris = params.map(
                            (p) => `${p.marker} ${escape(p.seriesName)}: <b>${fmtAngka.format(p.value)}</b>`
                        );
                        return (
                            `<div style="font-weight:600;margin-bottom:4px">${escape(w.nama)}</div>` +
                            baris.join("<br/>") +
                            `<br/>Total: <b>${fmtAngka.format(w.angka.penduduk)}</b>`
                        );
                    },
                },
                grid: { left: 8, right: 8, top: kecil * 3, bottom: 8, containLabel: true },
                xAxis: {
                    type: "category",
                    data: nama,
                    axisTick: { alignWithLabel: true },
                    axisLine: { lineStyle: { color: "#cfd5de" } },
                    axisLabel: {
                        interval: 0,
                        rotate: banyak ? 40 : 0,
                        fontSize: kecil,
                        color: "#374151",
                        width: banyak ? undefined : 90,
                        overflow: "truncate",
                    },
                },
                yAxis: {
                    type: "value",
                    axisLabel: { fontSize: kecil, color: "#5b6474", formatter: (v) => fmtSingkat.format(v) },
                    splitLine: { lineStyle: { color: "#eef0f4" } },
                },
                series: [
                    {
                        name: "Laki-laki",
                        type: "bar",
                        stack: "jenis_kelamin",
                        barMaxWidth: 40,
                        emphasis: { focus: "series" },
                        data: this._urut.map((w) => w.angka.laki_laki),
                    },
                    {
                        name: "Perempuan",
                        type: "bar",
                        stack: "jenis_kelamin",
                        barMaxWidth: 40,
                        emphasis: { focus: "series" },
                        itemStyle: { borderRadius: [2, 2, 0, 0] },
                        data: this._urut.map((w) => w.angka.perempuan),
                    },
                ],
            },
            true
        );
    }
}
