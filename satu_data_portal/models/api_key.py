import hashlib
import hmac
import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError

AWALAN = 'sdk_'
PANJANG_PREFIX = 12          # "sdk_" + 8 karakter pertama (untuk mengenali kunci)
BATAS_BAWAAN = 600           # permintaan per menit, lebih longgar daripada tanpa kunci
BATAS_MIN, BATAS_MAKS = 10, 6000


def hash_kunci(kunci):
    """SHA-256 heksa. Kunci acak 256 bit, jadi hash cepat sudah cukup (bukan kata sandi)."""
    return hashlib.sha256(kunci.encode()).hexdigest()


class SatuDataApiKey(models.Model):
    """Kunci API untuk instansi/aplikasi lain (interoperabilitas Satu Data).

    Kunci TIDAK membuka data yang tertutup: data publik tetap sama dengan tanpa kunci. Gunanya
    mengenali pemakai dan memberi batas permintaan yang lebih longgar. Hanya hash yang
    disimpan; kunci lengkap tampil sekali saat dibuat/diputar.
    """
    _name        = 'satu_data.api.key'
    _description = 'Kunci API Publik'
    _order       = 'name'

    name        = fields.Char('Nama Aplikasi/Instansi', required=True)
    organisasi  = fields.Char('Organisasi')
    email       = fields.Char('Email Kontak')
    catatan     = fields.Text('Catatan')
    company_id  = fields.Many2one('res.company', string='Wilayah (Kab/Kota)', required=True,
                                  index=True, default=lambda self: self.env.company)
    active      = fields.Boolean(default=True)
    prefix      = fields.Char('Awalan Kunci', readonly=True, copy=False, index=True)
    key_hash    = fields.Char('Hash Kunci', readonly=True, copy=False, groups='base.group_system')
    batas_per_menit = fields.Integer('Batas per Menit', default=BATAS_BAWAAN, required=True)
    terakhir_dipakai = fields.Datetime('Terakhir Dipakai', readonly=True, copy=False)
    jumlah_panggilan = fields.Integer('Jumlah Panggilan', readonly=True, copy=False)
    permintaan_id = fields.Many2one('satu_data.permintaan', string='Permintaan Asal',
                                    ondelete='set null')

    _prefix_uniq = models.Constraint('UNIQUE(prefix)', 'Awalan kunci harus unik.')

    @api.constrains('batas_per_menit')
    def _check_batas(self):
        for rec in self:
            if not BATAS_MIN <= rec.batas_per_menit <= BATAS_MAKS:
                raise ValidationError(self.env._(
                    'Batas per menit harus antara %(min)s dan %(maks)s.',
                    min=BATAS_MIN, maks=BATAS_MAKS))

    def action_buat_kunci(self):
        """Buat kunci baru (atau putar yang lama; kunci lama langsung tidak berlaku).

        Kunci lengkap hanya ditampilkan sekali di notifikasi ini.
        """
        self.ensure_one()
        kunci = AWALAN + secrets.token_urlsafe(32)
        self.write({'prefix': kunci[:PANJANG_PREFIX], 'key_hash': hash_kunci(kunci), 'active': True})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Kunci API dibuat'),
                'message': self.env._(
                    'Salin dan kirimkan kunci ini ke pemohon. Kunci tidak dapat ditampilkan lagi: %s',
                    kunci),
                'type': 'success',
                'sticky': True,
                # Muat ulang formulir agar awalan kunci dan tombolnya ikut diperbarui.
                'next': {'type': 'ir.actions.act_window', 'res_model': self._name,
                         'res_id': self.id, 'view_mode': 'form', 'views': [(False, 'form')]},
            },
        }

    @api.model
    def _sd_verifikasi(self, kunci, company):
        """Kunci aktif milik ``company`` yang cocok, atau recordset kosong."""
        kunci = (kunci or '').strip()
        if not kunci.startswith(AWALAN) or not 20 <= len(kunci) <= 100:
            return self.browse()
        rec = self.sudo().search([('prefix', '=', kunci[:PANJANG_PREFIX]),
                                  ('company_id', '=', company.id)], limit=1)
        if not rec or not rec.sudo().key_hash:
            return self.browse()
        if not hmac.compare_digest(hash_kunci(kunci), rec.sudo().key_hash):
            return self.browse()
        return rec

    def _sd_catat_pemakaian(self):
        """Catat satu panggilan (SQL langsung: tanpa jejak perubahan, aman untuk permintaan
        bersamaan)."""
        self.ensure_one()
        self.env.cr.execute(
            """UPDATE satu_data_api_key
                  SET jumlah_panggilan = COALESCE(jumlah_panggilan, 0) + 1,
                      terakhir_dipakai = NOW() AT TIME ZONE 'UTC'
                WHERE id = %s""", (self.id,))
        self.invalidate_recordset(['jumlah_panggilan', 'terakhir_dipakai'])
