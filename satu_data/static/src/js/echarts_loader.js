/** @odoo-module **/

import { loadJS } from "@web/core/assets";

// Apache ECharts 5.6.1 (salinan lokal, lisensi Apache 2.0: static/lib/echarts/LICENSE).
// Sengaja tidak dimasukkan ke bundel aset: ~1 MB, hanya dimuat saat grafik dibuka.
const URL_ECHARTS = "/satu_data/static/lib/echarts/echarts.min.js";

/** Muat ECharts sekali (pakai window.echarts bila modul lain sudah memuatnya). */
export async function muatEcharts() {
    if (!window.echarts) {
        await loadJS(URL_ECHARTS);
    }
    return window.echarts;
}
