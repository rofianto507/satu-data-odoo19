from odoo import api, fields, models

SEKTOR = [('pendidikan_usia_sekolah', 'Pendidikan: Penduduk Usia Sekolah')]
MODEL_SEKTOR = {'pendidikan_usia_sekolah': 'satu_data.pendidikan.usia_sekolah'}
VIEW_ISIAN = {'pendidikan_usia_sekolah': 'satu_data_pendidikan.view_usia_sekolah_list_isian'}


class SatuDataPengajuan(models.Model):
    _inherit = 'satu_data.pengajuan'

    sektor = fields.Selection(selection_add=SEKTOR,
                              ondelete={'pendidikan_usia_sekolah': 'cascade'})
    usia_sekolah_ids = fields.One2many('satu_data.pendidikan.usia_sekolah', 'pengajuan_id',
                                       string='Penduduk Usia Sekolah per Desa')

    @api.model
    def _sd_info_sektor(self):
        info = super()._sd_info_sektor()
        info['pendidikan_usia_sekolah'] = {
            'model': 'satu_data.pendidikan.usia_sekolah',
            'grup': 'satu_data_pendidikan.group_produsen_pendidikan',
            'instansi': 'satu_data_pendidikan.instansi_disdik',
            'frekuensi': 'tahunan',
            # Penduduk usia sekolah ditetapkan di awal tahun.
            'batas_hari': 31,
            'acuan_batas': 'awal',
        }
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
        """Tabel isian dikelompokkan per kecamatan, selain tabel di form laporan."""
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
                        'search_default_group_kecamatan': 1},
        }


class SatuDataData(models.Model):
    _inherit = 'satu_data.data'

    sektor = fields.Selection(selection_add=SEKTOR,
                              ondelete={'pendidikan_usia_sekolah': 'set null'})
