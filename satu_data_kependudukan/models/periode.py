from odoo import api, fields, models


class SatuDataPeriode(models.Model):
    _inherit = 'satu_data.periode'

    jumlah_kependudukan = fields.Integer('Rekap Kependudukan',
                                         compute='_compute_jumlah_kependudukan')

    @api.model
    def _sd_model_berperiode(self):
        return super()._sd_model_berperiode() + ['satu_data.kependudukan']

    def _compute_jumlah_kependudukan(self):
        hitung = dict(self.env['satu_data.kependudukan']._read_group(
            [('periode_id', 'in', self.ids)], ['periode_id'], ['__count']))
        for rec in self:
            rec.jumlah_kependudukan = hitung.get(rec, 0)

    def action_lihat_kependudukan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'satu_data.kependudukan',
            'view_mode': 'list,form',
            'domain': [('periode_id', '=', self.id)],
            'context': {'default_periode_id': self.id, 'search_default_group_kecamatan': 1},
        }
