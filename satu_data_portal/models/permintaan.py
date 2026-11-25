import re
import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError

JENIS = [
    ('data',      'Data yang belum tersedia'),
    ('kunci_api', 'Kunci API'),
    ('lain',      'Lainnya'),
]
PEMOHON = [
    ('perorangan', 'Perorangan'),
    ('akademisi',  'Akademisi/Peneliti'),
    ('pemerintah', 'Instansi Pemerintah'),
    ('swasta',     'Swasta/LSM'),
    ('media',      'Media'),
]
STATUS = [
    ('baru',     'Baru'),
    ('diproses', 'Diproses'),
    ('selesai',  'Selesai'),
    ('ditolak',  'Ditolak'),
]
# Batas panjang isian (dipakai formulir publik dan validasi model).
MAKS = {'nama': 100, 'email': 254, 'telepon': 30, 'organisasi': 150, 'uraian': 2000, 'tujuan': 1000}
MIN_URAIAN = 10
POLA_EMAIL = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,}$')
POLA_TELEPON = re.compile(r'^[0-9+()\-.\s]{5,30}$')


class SatuDataPermintaan(models.Model):
    """Permintaan data dari publik: data yang belum ada di katalog, kunci API, atau lainnya.

    Dibuat oleh formulir portal (tanpa login) dan ditangani Walidata. Pemohon memantau status
    lewat tautan berisi token acak (tanpa menampilkan data kontaknya).
    """
    _name        = 'satu_data.permintaan'
    _description = 'Permintaan Data'
    _inherit     = ['mail.thread']
    _order       = 'id desc'

    name         = fields.Char('Nomor', readonly=True, copy=False, default='Baru')
    company_id   = fields.Many2one('res.company', string='Wilayah (Kab/Kota)', required=True,
                                   index=True, default=lambda self: self.env.company)
    jenis        = fields.Selection(JENIS, string='Jenis Permintaan', required=True,
                                    default='data', tracking=True)
    pemohon_jenis = fields.Selection(PEMOHON, string='Jenis Pemohon', required=True,
                                     default='perorangan')
    nama_pemohon = fields.Char('Nama Pemohon', required=True)
    email        = fields.Char('Email', required=True)
    telepon      = fields.Char('Telepon')
    organisasi   = fields.Char('Organisasi')
    uraian       = fields.Text('Uraian Permintaan', required=True)
    tujuan       = fields.Text('Tujuan Penggunaan', required=True)
    data_id      = fields.Many2one('satu_data.data', string='Data Terkait', ondelete='set null',
                                   domain="[('company_id', '=', company_id)]",
                                   help='Diisi bila permintaan berawal dari satu data di katalog.')
    instansi_id  = fields.Many2one(related='data_id.instansi_id', string='Produsen Data',
                                   store=True, index=True)
    state        = fields.Selection(STATUS, string='Status', required=True, default='baru',
                                    tracking=True, copy=False, index=True)
    tanggapan    = fields.Text('Tanggapan', tracking=True,
                               help='Tampil kepada pemohon di halaman status.')
    tanggal_selesai = fields.Datetime('Tanggal Selesai', readonly=True, copy=False)
    token        = fields.Char('Token Akses', readonly=True, copy=False, index=True,
                               groups='base.group_system')
    kunci_api_ids = fields.One2many('satu_data.api.key', 'permintaan_id', string='Kunci API')

    _token_uniq = models.Constraint('UNIQUE(token)', 'Token akses harus unik.')

    @api.model_create_multi
    def create(self, vals_list):
        Sequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            if vals.get('name', 'Baru') == 'Baru':
                vals['name'] = Sequence.next_by_code('satu_data.permintaan') or 'Baru'
            vals.setdefault('token', secrets.token_urlsafe(24))
        return super().create(vals_list)

    @api.constrains('email', 'telepon', 'nama_pemohon', 'organisasi', 'uraian', 'tujuan')
    def _check_isian(self):
        for rec in self:
            if not POLA_EMAIL.match(rec.email or '') or len(rec.email) > MAKS['email']:
                raise ValidationError(self.env._('Alamat email tidak valid.'))
            if rec.telepon and not POLA_TELEPON.match(rec.telepon):
                raise ValidationError(self.env._('Nomor telepon tidak valid.'))
            for kunci in ('nama_pemohon', 'organisasi', 'uraian', 'tujuan'):
                maks = MAKS['nama' if kunci == 'nama_pemohon' else kunci]
                if len(rec[kunci] or '') > maks:
                    raise ValidationError(self.env._('Isian terlalu panjang (maksimal %s karakter).', maks))

    # ── Penanganan Walidata ──────────────────────────────────────────────────

    def action_proses(self):
        self.write({'state': 'diproses'})

    def action_selesai(self):
        self._tutup('selesai')

    def action_tolak(self):
        self._tutup('ditolak')

    def _tutup(self, status):
        for rec in self:
            if not (rec.tanggapan or '').strip():
                raise ValidationError(self.env._(
                    'Isi tanggapan lebih dulu: pemohon akan membacanya di halaman status.'))
        self.write({'state': status, 'tanggal_selesai': fields.Datetime.now()})

    def action_buka_kembali(self):
        self.write({'state': 'diproses', 'tanggal_selesai': False})

    def action_buat_kunci_api(self):
        """Siapkan kunci API untuk pemohon (permintaan jenis Kunci API)."""
        self.ensure_one()
        kunci = self.env['satu_data.api.key'].create({
            'name': self.organisasi or self.nama_pemohon,
            'organisasi': self.organisasi,
            'email': self.email,
            'permintaan_id': self.id,
            'company_id': self.company_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'satu_data.api.key',
            'res_id': kunci.id,
            'view_mode': 'form',
        }
