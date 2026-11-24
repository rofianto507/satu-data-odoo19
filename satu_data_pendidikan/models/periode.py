from odoo import api, fields, models

MODEL_PENDIDIKAN = ['satu_data.pendidikan.usia_sekolah']


class SatuDataPeriode(models.Model):
    _inherit = 'satu_data.periode'

    jumlah_usia_sekolah = fields.Integer('Usia Sekolah', compute='_compute_jumlah_usia_sekolah')

    @api.model
    def _sd_model_berperiode(self):
        return super()._sd_model_berperiode() + MODEL_PENDIDIKAN

    def _compute_jumlah_usia_sekolah(self):
        hitung = dict(self.env['satu_data.pendidikan.usia_sekolah']._read_group(
            [('periode_id', 'in', self.ids)], ['periode_id'], ['__count']))
        for rec in self:
            rec.jumlah_usia_sekolah = hitung.get(rec, 0)

    def action_lihat_usia_sekolah(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'satu_data.pendidikan.usia_sekolah',
            'view_mode': 'list,form',
            'domain': [('periode_id', '=', self.id)],
            'context': {'default_periode_id': self.id, 'search_default_group_kecamatan': 1},
        }
