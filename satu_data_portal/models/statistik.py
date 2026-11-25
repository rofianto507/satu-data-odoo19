from odoo import api, fields, models
from odoo.tools import SQL

JENIS_CATATAN = ('kunjungan', 'unduhan')


class SatuDataPortalStatistik(models.Model):
    """Jumlah kunjungan dan unduhan per data per hari.

    Hanya angka agregat: tidak menyimpan alamat IP, perangkat, atau identitas pengunjung.
    """
    _name        = 'satu_data.portal.statistik'
    _description = 'Statistik Portal Publik'
    _order       = 'tanggal desc, data_id'
    _rec_name    = 'data_id'

    data_id    = fields.Many2one('satu_data.data', string='Data', required=True, index=True,
                                 ondelete='cascade', readonly=True)
    company_id = fields.Many2one(related='data_id.company_id', store=True, index=True)
    instansi_id = fields.Many2one(related='data_id.instansi_id', string='Produsen Data',
                                  store=True)
    tanggal    = fields.Date('Tanggal', required=True, index=True, readonly=True)
    kunjungan  = fields.Integer('Kunjungan', readonly=True)
    unduhan    = fields.Integer('Unduhan', readonly=True)

    _data_tanggal_uniq = models.Constraint(
        'UNIQUE(data_id, tanggal)', 'Statistik per data per hari hanya satu baris.')

    @api.model
    def _sd_catat(self, data, jenis):
        """Tambah 1 kunjungan atau unduhan hari ini (aman untuk permintaan bersamaan)."""
        if jenis not in JENIS_CATATAN:
            raise ValueError(jenis)
        kolom = SQL.identifier(jenis)
        self.env.cr.execute(SQL(
            """INSERT INTO satu_data_portal_statistik
                   (data_id, company_id, instansi_id, tanggal, kunjungan, unduhan,
                    create_date, write_date)
               VALUES (%(data)s, %(company)s, %(instansi)s, %(tanggal)s, %(k)s, %(u)s,
                       NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
               ON CONFLICT (data_id, tanggal)
               DO UPDATE SET %(kolom)s = satu_data_portal_statistik.%(kolom)s + 1,
                             write_date = NOW() AT TIME ZONE 'UTC'""",
            data=data.id, company=data.company_id.id, instansi=data.instansi_id.id or None,
            tanggal=fields.Date.today(), k=int(jenis == 'kunjungan'), u=int(jenis == 'unduhan'),
            kolom=kolom))
        self.invalidate_model(['kunjungan', 'unduhan'])

    @api.model
    def _sd_jumlah(self, data):
        """Total kunjungan dan unduhan sepanjang waktu untuk satu data."""
        (kunjungan, unduhan), = self.sudo()._read_group(
            [('data_id', '=', data.id)], [], ['kunjungan:sum', 'unduhan:sum'])
        return {'kunjungan': kunjungan or 0, 'unduhan': unduhan or 0}
