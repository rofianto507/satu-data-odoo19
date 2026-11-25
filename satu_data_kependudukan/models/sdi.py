from odoo import api, fields, models


class SatuDataPengajuan(models.Model):
    _inherit = 'satu_data.pengajuan'

    sektor = fields.Selection(selection_add=[('kependudukan', 'Kependudukan')],
                              ondelete={'kependudukan': 'cascade'})
    kependudukan_ids = fields.One2many('satu_data.kependudukan', 'pengajuan_id',
                                       string='Data per Desa/Kelurahan')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        laporan = records.filtered(lambda r: r.sektor == 'kependudukan')
        if laporan:
            # Baris yang sudah ada lebih dulu ikut masuk ke laporan barunya.
            Rekap = self.env['satu_data.kependudukan'].sudo()
            baris = Rekap.search([('periode_id', 'in', laporan.periode_id.ids)])
            if baris:
                self.env.add_to_compute(Rekap._fields['pengajuan_id'], baris)
        return records

    def _sd_siapkan_baris(self):
        res = super()._sd_siapkan_baris()
        Rekap = self.env['satu_data.kependudukan'].with_context(
            tracking_disable=True, mail_create_nolog=True)
        for rec in self.filtered(lambda r: r.sektor == 'kependudukan' and r.state == 'draf'):
            ada = Rekap.search([('periode_id', '=', rec.periode_id.id),
                                ('company_id', '=', rec.company_id.id)]).desa_id
            desa = self.env['satu_data.desa'].search([('company_id', '=', rec.company_id.id)])
            kosong = desa - ada
            if kosong:
                Rekap.create([{'desa_id': d.id, 'periode_id': rec.periode_id.id} for d in kosong])
        return res

    @api.model
    def _sd_info_sektor(self):
        info = super()._sd_info_sektor()
        info['kependudukan'] = {
            'model': 'satu_data.kependudukan',
            'grup': 'satu_data_kependudukan.group_produsen_kependudukan',
            'instansi': 'satu_data_kependudukan.instansi_dukcapil',
            'frekuensi': 'semesteran',
        }
        return info


class SatuDataData(models.Model):
    _inherit = 'satu_data.data'

    sektor = fields.Selection(selection_add=[('kependudukan', 'Kependudukan')],
                              ondelete={'kependudukan': 'set null'})

    def _sd_nilai_publik(self, periode):
        if self.sektor != 'kependudukan' or self.kode != 'kependudukan.kepadatan':
            return super()._sd_nilai_publik(periode)
        # Kepadatan = penduduk / luas, hanya bila semua desa berdata punya luas (sama dengan
        # dashboard).
        Rekap = self.env['satu_data.kependudukan'].sudo()
        company = self.company_id
        domain = ([('company_id', '=', company.id), ('periode_id', '=', periode.id)]
                  + Rekap._sd_domain_terbit(company) + Rekap._sd_domain_terisi())
        hasil = {kec: angka['kepadatan'] or None
                 for kec, angka in Rekap._sd_agregat(domain, 'kecamatan_id').items() if kec}
        if hasil:
            total = Rekap._sd_agregat(domain, False).get(None)
            hasil[False] = (total or {}).get('kepadatan') or None
        return hasil
