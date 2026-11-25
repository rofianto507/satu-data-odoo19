from collections import defaultdict

from odoo import api, fields, models

from .indikator import INDIKATOR_BY_KODE, nilai_indikator
from .rekap import KELOMPOK_REKAP

SEKTOR = [
    ('pendidikan',               'Pendidikan: Rekap Semester'),
    ('pendidikan_usia_sekolah',  'Pendidikan: Penduduk Usia Sekolah'),
]
MODEL_SEKTOR = {
    'pendidikan':              'satu_data.pendidikan.rekap',
    'pendidikan_usia_sekolah': 'satu_data.pendidikan.usia_sekolah',
}
VIEW_ISIAN = {
    'pendidikan':              'satu_data_pendidikan.view_rekap_list_isian',
    'pendidikan_usia_sekolah': 'satu_data_pendidikan.view_usia_sekolah_list_isian',
}
ONDELETE_PENGAJUAN = {kode: 'cascade' for kode, _l in SEKTOR}
ONDELETE_DATA = {kode: 'set null' for kode, _l in SEKTOR}


class SatuDataPengajuan(models.Model):
    _inherit = 'satu_data.pengajuan'

    sektor = fields.Selection(selection_add=SEKTOR, ondelete=ONDELETE_PENGAJUAN)
    usia_sekolah_ids = fields.One2many('satu_data.pendidikan.usia_sekolah', 'pengajuan_id',
                                       string='Penduduk Usia Sekolah per Desa')
    rekap_pendidikan_ids = fields.One2many('satu_data.pendidikan.rekap', 'pengajuan_id',
                                           string='Rekap Semester per Desa dan Jenjang')

    @api.model
    def _sd_info_sektor(self):
        info = super()._sd_info_sektor()
        umum = {
            'grup': 'satu_data_pendidikan.group_produsen_pendidikan',
            'instansi': 'satu_data_pendidikan.instansi_disdik',
        }
        # Rekap semester: jadwal bawaan (30 hari setelah semester berakhir).
        info['pendidikan'] = dict(umum, model='satu_data.pendidikan.rekap', frekuensi='semesteran')
        # Penduduk usia sekolah ditetapkan di awal tahun.
        info['pendidikan_usia_sekolah'] = dict(
            umum, model='satu_data.pendidikan.usia_sekolah', frekuensi='tahunan',
            batas_hari=31, acuan_batas='awal')
        return info

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for sektor, model in MODEL_SEKTOR.items():
            laporan = records.filtered(lambda r, k=sektor: r.sektor == k)
            if laporan:
                # Baris yang sudah ada lebih dulu ikut masuk ke laporan barunya.
                Baris = self.env[model].sudo()
                ada = Baris.search([('periode_id', 'in', laporan.periode_id.ids)])
                if ada:
                    self.env.add_to_compute(Baris._fields['pengajuan_id'], ada)
        return records

    def _sd_siapkan_baris(self):
        res = super()._sd_siapkan_baris()
        for rec in self:
            if rec.state != 'draf':
                continue
            if rec.sektor == 'pendidikan_usia_sekolah':
                self._siapkan_baris_usia_sekolah(rec)
            elif rec.sektor == 'pendidikan':
                self._siapkan_baris_rekap(rec)
        return res

    def _siapkan_baris_usia_sekolah(self, rec):
        Baris = self.env['satu_data.pendidikan.usia_sekolah'].with_context(
            tracking_disable=True, mail_create_nolog=True)
        ada = Baris.search([('periode_id', '=', rec.periode_id.id),
                            ('company_id', '=', rec.company_id.id)]).desa_id
        kosong = self.env['satu_data.desa'].search([('company_id', '=', rec.company_id.id)]) - ada
        if kosong:
            Baris.create([{'desa_id': d.id, 'periode_id': rec.periode_id.id} for d in kosong])

    def _siapkan_baris_rekap(self, rec):
        """Satu baris per desa dan kelompok jenjang; jumlah sekolah diisi dari master."""
        Baris = self.env['satu_data.pendidikan.rekap'].with_context(
            tracking_disable=True, mail_create_nolog=True)
        ada = {(b.desa_id.id, b.kelompok) for b in Baris.search([
            ('periode_id', '=', rec.periode_id.id), ('company_id', '=', rec.company_id.id)])}
        hitung = defaultdict(int)
        for desa, kelompok, status, n in self.env['satu_data.sekolah']._read_group(
                [('company_id', '=', rec.company_id.id)],
                ['desa_id', 'kelompok', 'status'], ['__count']):
            hitung[(desa.id, kelompok, status)] = n
        baru = []
        for desa in self.env['satu_data.desa'].search([('company_id', '=', rec.company_id.id)]):
            for kelompok, _label in KELOMPOK_REKAP:
                if (desa.id, kelompok) in ada:
                    continue
                baru.append({
                    'desa_id': desa.id, 'periode_id': rec.periode_id.id, 'kelompok': kelompok,
                    'sekolah_negeri': hitung[(desa.id, kelompok, 'negeri')],
                    'sekolah_swasta': hitung[(desa.id, kelompok, 'swasta')],
                })
        if baru:
            Baris.create(baru)

    def action_lihat_data(self):
        """Tabel isian (dikelompokkan), selain tabel di form laporan."""
        self.ensure_one()
        model = MODEL_SEKTOR.get(self.sektor)
        if not model:
            return super().action_lihat_data()
        konteks = {'default_periode_id': self.periode_id.id}
        if self.sektor == 'pendidikan':
            # Isi per jenjang, lalu per kecamatan.
            konteks.update({'search_default_group_kelompok': 1,
                            'search_default_group_kecamatan': 1})
        else:
            konteks['search_default_group_kecamatan'] = 1
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': model,
            'views': [(self.env.ref(VIEW_ISIAN[self.sektor]).id, 'list'), (False, 'form')],
            'domain': [('periode_id', '=', self.periode_id.id),
                       ('company_id', '=', self.company_id.id)],
            'context': konteks,
        }


class SatuDataData(models.Model):
    _inherit = 'satu_data.data'

    sektor = fields.Selection(selection_add=SEKTOR, ondelete=ONDELETE_DATA)

    def _sd_indikator_pendidikan(self):
        """Definisi indikator (lihat ``indikator.INDIKATOR``) untuk data ini, bila ada."""
        self.ensure_one()
        if self.sektor != 'pendidikan':
            return None
        return INDIKATOR_BY_KODE.get(self.kode.rpartition('.')[2])

    def _sd_nilai_publik(self, periode):
        ind = self._sd_indikator_pendidikan()
        if not ind:
            return super()._sd_nilai_publik(periode)
        # Sama dengan dashboard tanpa pilihan jenjang (semua jenjang, kecuali partisipasi
        # yang jenjangnya sudah tertentu).
        Dashboard = self.env['satu_data.pendidikan.dashboard'].sudo()
        dasar = Dashboard._sd_angka_dasar(periode, ind.get('jenjang_tetap') or False,
                                          self.company_id)
        return self._sd_nilai_per_kecamatan(dasar, lambda angka: nilai_indikator(ind, angka))

    def _sd_catatan_publik(self):
        ind = self._sd_indikator_pendidikan()
        if not ind:
            return super()._sd_catatan_publik()
        if ind['kelompok'] == 'Partisipasi':
            return self.env._('Peserta didik dihitung menurut lokasi sekolah, bukan tempat '
                              'tinggal siswa. Penyebut: penduduk usia sekolah tahun yang sama.')
        if ind['kelompok'] == 'Keberlanjutan':
            return self.env._('Angka tahun ajaran dari rekap Semester I tahun yang sama.')
        return self.env._('Seluruh jenjang (PAUD/TK sampai SMA/SMK/MA), negeri dan swasta.')
