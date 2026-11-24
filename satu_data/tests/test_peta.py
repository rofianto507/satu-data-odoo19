from odoo.tests import tagged

from .common import SatuDataCase


@tagged('post_install', '-at_install', 'satu_data')
class TestPetaMixin(SatuDataCase):
    """Pembagian kelas warna choropleth (satu_data.peta.mixin)."""

    def test_langkah_bulat(self):
        Pdd = self.env['satu_data.peta.mixin']
        self.assertEqual(Pdd._langkah_bulat(64), 100)
        self.assertEqual(Pdd._langkah_bulat(12), 20)
        self.assertEqual(Pdd._langkah_bulat(2.4), 5, '2,5 dilewati karena bukan bilangan bulat')
        self.assertEqual(Pdd._langkah_bulat(230), 250)
        self.assertEqual(Pdd._langkah_bulat(0.6), 1)

    def test_kelas_tanpa_data(self):
        kelas = self.env['satu_data.peta.mixin']._hitung_kelas([])
        self.assertEqual(len(kelas), 5)
        self.assertEqual(kelas[0]['label'], '≤ 1')

    def test_label_kelas(self):
        kelas = self.env['satu_data.peta.mixin']._hitung_kelas([48000])
        self.assertEqual(kelas[0]['label'], '≤ 10.000')
        self.assertEqual(kelas[1]['label'], '10.001 – 20.000')

    def test_kelas_kuantil(self):
        Pdd = self.env['satu_data.peta.mixin']
        kelas = Pdd._hitung_kelas([v * 1000 for v in range(1, 11)])
        self.assertEqual([k['atas'] for k in kelas], [2000, 4000, 6000, 8000, 10000])
        self.assertEqual(kelas[1]['label'], '2.001 – 4.000')
        self.assertEqual(kelas[0]['warna'], '#ffffb2')

        # Sebaran timpang (banyak desa kecil, sedikit kota besar): semua warna tetap terpakai.
        nilai = [30800, 32900, 33100, 35100, 38100, 41100, 41800, 44600, 45500, 46200,
                 48000, 52700, 54400, 56000, 58700, 61000, 72700, 84400, 97500, 112700,
                 131000, 153900, 165200, 173700]
        kelas = Pdd._hitung_kelas(nilai)
        terpakai = {Pdd._kelas_index(v, kelas) for v in nilai}
        self.assertEqual(terpakai, {0, 1, 2, 3, 4})
        self.assertGreaterEqual(kelas[-1]['atas'], max(nilai))

        # Nilai berbeda kurang dari 5: kembali ke interval sama.
        kelas = Pdd._hitung_kelas([10, 10, 10, 20, 30])
        self.assertEqual([k['atas'] for k in kelas], [10, 20, 30, 40, 50])

    def test_bulat_penting(self):
        Pdd = self.env['satu_data.peta.mixin']
        self.assertEqual(Pdd._bulat_penting(45321), 45000)
        self.assertEqual(Pdd._bulat_penting(173700, ke_atas=True), 180000)
        self.assertEqual(Pdd._bulat_penting(45), 45)

    def test_label_kelas_nilai_kecil(self):
        kelas = self.env['satu_data.peta.mixin']._hitung_kelas([3])
        self.assertEqual([k['label'] for k in kelas], ['≤ 1', '2', '3', '4', '5'])
