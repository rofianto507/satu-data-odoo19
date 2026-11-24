/** @odoo-module **/

import { Component, onMounted, onWillUnmount, toRaw, useEffect, useRef, useState } from "@odoo/owl";
import { muatEcharts } from "@satu_data/js/echarts_loader";

/**
 * Grafik ECharts umum untuk dashboard sektor.
 *
 * Induk menyusun `opsi` (objek option ECharts) dan memberi `adaData`; komponen ini
 * memuat pustaka, menggambar ulang saat `opsi` berganti, dan menyesuaikan ukuran.
 * Klik elemen grafik diteruskan lewat `onKlik(params)`.
 */
export class SatuDataGrafik extends Component {
    static template = "satu_data.Grafik";
    static props = {
        opsi: Object,
        adaData: { type: Boolean, optional: true },
        pesanKosong: { type: String, optional: true },
        kelasKanvas: { type: String, optional: true },
        onKlik: { type: Function, optional: true },
    };

    setup() {
        this.grafikRef = useRef("grafik");
        this.state = useState({ galat: false });
        this._grafik = null;

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
            this._grafik.on("click", (p) => this.props.onKlik && this.props.onKlik(p));
            this._resizeObs = new ResizeObserver(() => this._grafik?.resize());
            this._resizeObs.observe(el);
            this._gambar();
        });
        useEffect(() => this._gambar(), () => [this.props.opsi]);
        onWillUnmount(() => {
            this._resizeObs?.disconnect();
            this._grafik?.dispose();
            this._grafik = null;
        });
    }

    get adaData() {
        return this.props.adaData !== false;
    }

    _gambar() {
        if (this._grafik) {
            this._grafik.setOption(toRaw(this.props.opsi), true);
        }
    }
}
