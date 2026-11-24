from odoo import api, fields, models

MODEL_KESEHATAN = ['satu_data.kesehatan.sasaran', 'satu_data.kesehatan.rekap']


class SatuDataPeriode(models.Model):
    _inherit = 'satu_data.periode'

    jumlah_sasaran_kesehatan = fields.Integer('Sasaran Kesehatan',
                                              compute='_compute_jumlah_kesehatan')
    jumlah_rekap_kesehatan   = fields.Integer('Rekap Kesehatan',
                                              compute='_compute_jumlah_kesehatan')

    @api.model
    def _sd_model_berperiode(self):
        return super()._sd_model_berperiode() + MODEL_KESEHATAN

    def _compute_jumlah_kesehatan(self):
        hitung = {}
        for model in MODEL_KESEHATAN:
            hitung[model] = dict(self.env[model]._read_group(
                [('periode_id', 'in', self.ids)], ['periode_id'], ['__count']))
        for rec in self:
            rec.jumlah_sasaran_kesehatan = hitung['satu_data.kesehatan.sasaran'].get(rec, 0)
            rec.jumlah_rekap_kesehatan = hitung['satu_data.kesehatan.rekap'].get(rec, 0)

    def _aksi_lihat(self, model):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': model,
            'view_mode': 'list,form',
            'domain': [('periode_id', '=', self.id)],
            'context': {'default_periode_id': self.id, 'search_default_group_puskesmas': 1},
        }

    def action_lihat_sasaran_kesehatan(self):
        return self._aksi_lihat('satu_data.kesehatan.sasaran')

    def action_lihat_rekap_kesehatan(self):
        return self._aksi_lihat('satu_data.kesehatan.rekap')
