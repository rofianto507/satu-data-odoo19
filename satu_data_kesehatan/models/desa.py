from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataDesa(models.Model):
    _inherit = 'satu_data.desa'

    sd_puskesmas_id = fields.Many2one(
        'satu_data.faskes', string='Puskesmas', compute='_compute_sd_puskesmas_id',
        search='_search_sd_puskesmas_id',
        help='Puskesmas yang wilayah kerjanya mencakup desa/kelurahan ini.')
    sd_faskes_ids = fields.One2many('satu_data.faskes', 'desa_id', string='Fasilitas Kesehatan')

    def _compute_sd_puskesmas_id(self):
        puskesmas = self.env['satu_data.faskes'].search([
            ('jenis', '=', 'puskesmas'), ('wilayah_kerja_ids', 'in', self.ids)])
        peta = {}
        for p in puskesmas:
            for desa in p.wilayah_kerja_ids:
                peta.setdefault(desa.id, p)
        for rec in self:
            rec.sd_puskesmas_id = peta.get(rec.id, False)

    def _search_sd_puskesmas_id(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        puskesmas = self.env['satu_data.faskes'].search([
            ('jenis', '=', 'puskesmas'), ('id', 'in', list(value))])
        return [('id', operator, puskesmas.wilayah_kerja_ids.ids)]

    @api.constrains('company_id')
    def _check_company_kesehatan(self):
        # Sasaran menyimpan kecamatan saat dicatat, dan puskesmas/wilayah kerjanya harus
        # satu kab/kota; memindahkan desa ke kab/kota lain merusak keduanya.
        Faskes = self.env['satu_data.faskes'].sudo().with_context(active_test=False)
        Rekap = [self.env[m].sudo() for m in
                 ('satu_data.kesehatan.sasaran', 'satu_data.kesehatan.rekap')]
        for rec in self:
            faskes = Faskes.search(['|', ('desa_id', '=', rec.id),
                                    ('wilayah_kerja_ids', 'in', rec.ids)])
            campur = any(f.wilayah_kerja_ids.company_id - f.company_id for f in faskes) or \
                any(f.company_id != rec.company_id for f in faskes)
            if campur or any(Model.search_count([
                    ('desa_id', '=', rec.id),
                    ('kecamatan_id.company_id', '!=', rec.company_id.id)], limit=1)
                    for Model in Rekap):
                raise ValidationError(self.env._(
                    'Desa/kelurahan %(desa)s sudah punya data kesehatan (fasilitas, wilayah kerja '
                    'puskesmas, atau sasaran), sehingga wilayah (kab/kota)-nya tidak bisa diubah.',
                    desa=rec.name))
