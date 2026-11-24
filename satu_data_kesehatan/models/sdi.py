from odoo import api, fields, models

SEKTOR = [
    ('kesehatan',         'Kesehatan: Rekap Bulanan'),
    ('kesehatan_sasaran', 'Kesehatan: Sasaran Tahunan'),
]
ONDELETE_PENGAJUAN = {kode: 'cascade' for kode, _l in SEKTOR}
ONDELETE_DATA = {kode: 'set null' for kode, _l in SEKTOR}


class SatuDataPengajuan(models.Model):
    _inherit = 'satu_data.pengajuan'

    sektor = fields.Selection(selection_add=SEKTOR, ondelete=ONDELETE_PENGAJUAN)

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
