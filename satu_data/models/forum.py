from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GRUP_WALIDATA = 'satu_data.group_satu_data_walidata'


class SatuDataUrusan(models.Model):
    """Urusan pemerintahan daerah (UU 23/2014; kode mengikuti Permendagri 90/2019).

    Dipakai mengelompokkan Daftar Data dan Produsen Data, seperti filter
    "Urusan" di portal Satu Data daerah.
    """
    _name        = 'satu_data.urusan'
    _description = 'Urusan Pemerintahan'
    _order       = 'kode, name'

    kode     = fields.Char('Kode', required=True, help='Mis. 1.02 untuk urusan Kesehatan.')
    name     = fields.Char('Nama Urusan', required=True)
    jenis    = fields.Selection([
        ('wajib_dasar',     'Wajib Pelayanan Dasar'),
        ('wajib_non_dasar', 'Wajib Non-Pelayanan Dasar'),
        ('pilihan',         'Pilihan'),
        ('penunjang',       'Penunjang dan Lainnya'),
    ], string='Jenis Urusan', required=True, default='wajib_dasar')
    active   = fields.Boolean(default=True)
    data_ids = fields.One2many('satu_data.data', 'urusan_id', string='Daftar Data')
    jumlah_data = fields.Integer('Jumlah Data', compute='_compute_jumlah_data')

    _kode_uniq = models.Constraint('UNIQUE(kode)', 'Kode urusan sudah dipakai.')

    @api.depends('kode', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.kode} {rec.name}' if rec.kode else rec.name or ''

    @api.model
    def _search_display_name(self, operator, value):
        if operator in ('ilike', 'not ilike', '=ilike') and value:
            dom = ['|', ('kode', operator, value), ('name', operator, value)]
            return dom if operator != 'not ilike' else ['!', *dom]
        return super()._search_display_name(operator, value)

    def _compute_jumlah_data(self):
        hitung = dict(self.env['satu_data.data']._read_group(
            [('urusan_id', 'in', self.ids)], ['urusan_id'], ['__count']))
        for rec in self:
            rec.jumlah_data = hitung.get(rec, 0)


class SatuDataForum(models.Model):
    """Forum Satu Data: menyepakati Daftar Data, data prioritas, dan jadwal pemutakhiran.

    Walidata menyusun usulan Daftar Data; Forum (Walidata, Sekretariat Satu Data,
    Produsen Data, Pembina Data) menyepakatinya untuk satu tahun. Berita acara
    hasil forum diunggah di sini.
    """
    _name        = 'satu_data.forum'
    _description = 'Forum Satu Data'
    _inherit     = ['mail.thread']
    _order       = 'tahun desc'

    name        = fields.Char('Nama Forum', required=True,
                              default=lambda self: self.env._('Forum Satu Data'))
    tahun       = fields.Integer('Tahun Daftar Data', required=True, tracking=True,
                                 default=lambda self: fields.Date.context_today(self).year + 1,
                                 help='Tahun berlakunya Daftar Data yang disepakati.')
    tanggal     = fields.Date('Tanggal Pelaksanaan', tracking=True)
    tempat      = fields.Char('Tempat')
    company_id  = fields.Many2one('res.company', string='Wilayah (Kab/Kota)', required=True,
                                  index=True, default=lambda self: self.env.company)
    state       = fields.Selection([
        ('draf',        'Penyusunan'),
        ('ditetapkan',  'Ditetapkan'),
    ], string='Status', required=True, default='draf', tracking=True, copy=False)
    keterangan  = fields.Html('Hasil dan Kesepakatan')
    berita_acara      = fields.Binary('Berita Acara', attachment=True, copy=False)
    berita_acara_nama = fields.Char('Nama Berkas Berita Acara', copy=False)
    data_ids    = fields.One2many('satu_data.data', 'forum_id', string='Daftar Data',
                                  domain=[('active', '=', True)])
    jumlah_data      = fields.Integer('Jumlah Data', compute='_compute_jumlah')
    jumlah_prioritas = fields.Integer('Data Prioritas', compute='_compute_jumlah')

    _tahun_company_uniq = models.Constraint(
        'UNIQUE(company_id, tahun)',
        'Forum Satu Data untuk tahun ini sudah ada di wilayah ini.',
    )

    @api.depends('name', 'tahun')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'{rec.name} {rec.tahun}' if rec.tahun else rec.name or ''

    @api.depends('data_ids', 'data_ids.prioritas')
    def _compute_jumlah(self):
        for rec in self:
            rec.jumlah_data = len(rec.data_ids)
            rec.jumlah_prioritas = len(rec.data_ids.filtered('prioritas'))

    def _cek_walidata(self):
        if not self.env.user.has_group(GRUP_WALIDATA):
            raise AccessError(self.env._('Hanya Walidata yang bisa menetapkan hasil Forum Satu Data.'))

    def action_tetapkan(self):
        """Tetapkan hasil forum: data di dalamnya berstatus Disepakati."""
        self._cek_walidata()
        for rec in self:
            if not rec.data_ids:
                raise UserError(self.env._('Pilih dulu data yang disepakati dalam forum ini.'))
        self.data_ids.write({'status_daftar': 'disepakati'})
        self.write({'state': 'ditetapkan'})

    def action_buka_kembali(self):
        self._cek_walidata()
        self.write({'state': 'draf'})

    def action_lihat_data(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name,
            'res_model': 'satu_data.data',
            'view_mode': 'list,form',
            'domain': [('forum_id', '=', self.id)],
            'context': {'default_forum_id': self.id},
        }
