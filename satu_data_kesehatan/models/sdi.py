from odoo import api, fields, models

from .indikator import INDIKATOR_BY_KODE, nilai_indikator

SEKTOR = [
    ('kesehatan',         'Kesehatan: Rekap Bulanan'),
    ('kesehatan_sasaran', 'Kesehatan: Sasaran Tahunan'),
]
MODEL_SEKTOR = {
    'kesehatan':         'satu_data.kesehatan.rekap',
    'kesehatan_sasaran': 'satu_data.kesehatan.sasaran',
}
VIEW_ISIAN = {
    'kesehatan':         'satu_data_kesehatan.view_rekap_list_isian',
    'kesehatan_sasaran': 'satu_data_kesehatan.view_sasaran_list_isian',
}
ONDELETE_PENGAJUAN = {kode: 'cascade' for kode, _l in SEKTOR}
ONDELETE_DATA = {kode: 'set null' for kode, _l in SEKTOR}


class SatuDataPengajuan(models.Model):
    _inherit = 'satu_data.pengajuan'

    sektor = fields.Selection(selection_add=SEKTOR, ondelete=ONDELETE_PENGAJUAN)
    kesehatan_ids = fields.One2many('satu_data.kesehatan.rekap', 'pengajuan_id',
                                    string='Rekap Bulanan per Desa')
    sasaran_kesehatan_ids = fields.One2many('satu_data.kesehatan.sasaran', 'pengajuan_id',
                                            string='Sasaran per Desa')

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
            model = MODEL_SEKTOR.get(rec.sektor)
            if not model or rec.state != 'draf':
                continue
            Baris = self.env[model].with_context(tracking_disable=True, mail_create_nolog=True)
            ada = Baris.search([('periode_id', '=', rec.periode_id.id),
                                ('company_id', '=', rec.company_id.id)]).desa_id
            kosong = self.env['satu_data.desa'].search(
                [('company_id', '=', rec.company_id.id)]) - ada
            if kosong:
                Baris.create([{'desa_id': d.id, 'periode_id': rec.periode_id.id} for d in kosong])
        return res

    def action_lihat_data(self):
        """Tabel isian per puskesmas (dikelompokkan), selain tabel di form laporan."""
        self.ensure_one()
        model = MODEL_SEKTOR.get(self.sektor)
        if not model:
            return super().action_lihat_data()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': model,
            'views': [(self.env.ref(VIEW_ISIAN[self.sektor]).id, 'list'), (False, 'form')],
            'domain': [('periode_id', '=', self.periode_id.id),
                       ('company_id', '=', self.company_id.id)],
            'context': {'default_periode_id': self.periode_id.id,
                        'search_default_group_puskesmas': 1},
        }

    @api.model
    def _sd_info_sektor(self):
        info = super()._sd_info_sektor()
        umum = {
            'grup': 'satu_data_kesehatan.group_produsen_kesehatan',
            'instansi': 'satu_data_kesehatan.instansi_dinkes',
        }
        info['kesehatan'] = dict(
            umum, model='satu_data.kesehatan.rekap', frekuensi='bulanan',
            # Laporan bulanan puskesmas: paling lambat tanggal 10 bulan berikutnya.
            batas_hari=10, acuan_batas='akhir')
        info['kesehatan_sasaran'] = dict(
            umum, model='satu_data.kesehatan.sasaran', frekuensi='tahunan',
            # Sasaran ditetapkan di awal tahun.
            batas_hari=31, acuan_batas='awal')
        return info


class SatuDataData(models.Model):
    _inherit = 'satu_data.data'

    sektor = fields.Selection(selection_add=SEKTOR, ondelete=ONDELETE_DATA)

    def _sd_indikator_kesehatan(self):
        """Definisi indikator (lihat ``indikator.INDIKATOR``) untuk data ini, bila ada."""
        self.ensure_one()
        if self.sektor != 'kesehatan':
            return None
        return INDIKATOR_BY_KODE.get(self.kode.rpartition('.')[2])

    def _sd_nilai_publik(self, periode):
        ind = self._sd_indikator_kesehatan()
        if not ind:
            return super()._sd_nilai_publik(periode)
        # Sama dengan dashboard (mode kumulatif): Januari s.d. bulan tersebut.
        Dashboard = self.env['satu_data.kesehatan.dashboard'].sudo()
        dasar = Dashboard._sd_angka_dasar(periode, 'kumulatif', self.company_id)
        return self._sd_nilai_per_kecamatan(dasar, lambda angka: nilai_indikator(ind, angka))

    def _sd_catatan_publik(self):
        ind = self._sd_indikator_kesehatan()
        if not ind:
            return super()._sd_catatan_publik()
        if ind.get('tanpa_mode'):
            return self.env._('Memakai hasil pengukuran terakhir tiap desa/kelurahan dalam '
                              '12 bulan terakhir sampai bulan tersebut.')
        return self.env._('Angka kumulatif Januari sampai bulan tersebut pada tahun yang sama.')
