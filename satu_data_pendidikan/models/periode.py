from odoo import api, fields, models

MODEL_PENDIDIKAN = ['satu_data.pendidikan.usia_sekolah', 'satu_data.pendidikan.rekap']


class SatuDataPeriode(models.Model):
    _inherit = 'satu_data.periode'

    jumlah_usia_sekolah = fields.Integer('Usia Sekolah', compute='_compute_jumlah_pendidikan')
    jumlah_rekap_pendidikan = fields.Integer('Rekap Pendidikan', compute='_compute_jumlah_pendidikan')

    @api.model
    def _sd_model_berperiode(self):
        return super()._sd_model_berperiode() + MODEL_PENDIDIKAN

    def _compute_jumlah_pendidikan(self):
        hitung = {m: dict(self.env[m]._read_group(
            [('periode_id', 'in', self.ids)], ['periode_id'], ['__count'])) for m in MODEL_PENDIDIKAN}
        for rec in self:
            rec.jumlah_usia_sekolah = hitung['satu_data.pendidikan.usia_sekolah'].get(rec, 0)
            rec.jumlah_rekap_pendidikan = hitung['satu_data.pendidikan.rekap'].get(rec, 0)

    def _aksi_lihat(self, model, konteks=None):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': model,
            'view_mode': 'list,form',
            'domain': [('periode_id', '=', self.id)],
            'context': dict({'default_periode_id': self.id}, **(konteks or {})),
        }

    def action_lihat_usia_sekolah(self):
        return self._aksi_lihat('satu_data.pendidikan.usia_sekolah',
                                {'search_default_group_kecamatan': 1})

    def action_lihat_rekap_pendidikan(self):
        return self._aksi_lihat('satu_data.pendidikan.rekap',
                                {'search_default_group_kelompok': 1})
