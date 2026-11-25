import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const JEDA_KATA_MS = 2600;
const DURASI_HITUNG_MS = 1400;
const JEDA_ANAK_MS = 90;

/**
 * Animasi beranda: muncul saat digulir, angka berhitung naik, dan kata yang berganti.
 * Tanpa JavaScript, atau bagi pengguna yang mengurangi gerakan, semua isi tetap tampil
 * (kelas .sd-siap yang menyembunyikan elemen baru dipasang di sini).
 */
export class Beranda extends Interaction {
    static selector = ".sd-beranda";

    setup() {
        this.kurangiGerak = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        this.pengamat = null;
        this.pewaktu = null;
        this.bingkai = [];
    }

    start() {
        if (this.kurangiGerak) {
            return;
        }
        this.el.classList.add("sd-siap");
        this._siapkanMunculSaatGulir();
        this._siapkanKata();
    }

    destroy() {
        this.pengamat?.disconnect();
        clearInterval(this.pewaktu);
        this.bingkai.forEach((id) => cancelAnimationFrame(id));
        this.el.classList.remove("sd-siap");
    }

    // ── Muncul saat digulir ──────────────────────────────────────────────────

    _siapkanMunculSaatGulir() {
        const unsur = this.el.querySelectorAll(".sd-reveal");
        // Anak dalam grup muncul bergiliran.
        this.el.querySelectorAll(".sd-reveal-grup").forEach((grup) => {
            grup.querySelectorAll(".sd-reveal-anak").forEach((anak, i) => {
                anak.style.setProperty("--tunda", `${i * JEDA_ANAK_MS}ms`);
            });
        });
        this.pengamat = new IntersectionObserver(
            (entri) => {
                for (const e of entri) {
                    if (e.isIntersecting) {
                        e.target.classList.add("sd-terlihat");
                        this._mulaiAngka(e.target);
                        this.pengamat.unobserve(e.target);
                    }
                }
            },
            { threshold: 0.18, rootMargin: "0px 0px -6% 0px" }
        );
        unsur.forEach((el) => this.pengamat.observe(el));
    }

    // ── Angka berhitung naik ─────────────────────────────────────────────────

    _mulaiAngka(wadah) {
        const format = new Intl.NumberFormat("id-ID");
        wadah.querySelectorAll(".sd-hitung").forEach((el) => {
            const akhir = Number(el.dataset.nilai);
            if (!Number.isFinite(akhir) || akhir <= 0) {
                return;
            }
            const awal = performance.now();
            const langkah = (sekarang) => {
                const t = Math.min(1, (sekarang - awal) / DURASI_HITUNG_MS);
                const mudah = 1 - Math.pow(1 - t, 3); // easeOutCubic
                el.textContent = format.format(Math.round(akhir * mudah));
                if (t < 1) {
                    this.bingkai.push(requestAnimationFrame(langkah));
                }
            };
            el.textContent = "0";
            this.bingkai.push(requestAnimationFrame(langkah));
        });
    }

    // ── Kata yang berganti di bawah judul ────────────────────────────────────

    _siapkanKata() {
        const el = this.el.querySelector(".sd-kata");
        if (!el) {
            return;
        }
        let kata;
        try {
            kata = JSON.parse(el.dataset.kata || "[]");
        } catch {
            return;
        }
        if (kata.length < 2) {
            return;
        }
        let i = 0;
        this.pewaktu = setInterval(() => {
            el.classList.add("sd-kata--keluar");
            setTimeout(() => {
                i = (i + 1) % kata.length;
                el.textContent = kata[i];
                el.classList.remove("sd-kata--keluar");
            }, 320);
        }, JEDA_KATA_MS);
    }
}

registry.category("public.interactions").add("satu_data_portal.beranda", Beranda);
