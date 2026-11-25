import base64
import logging

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

PARAM_DISIAPKAN = 'satu_data_portal.website_disiapkan'
PARAM_FAVICON = 'satu_data_portal.favicon_disiapkan'
PARAM_WARNA = 'satu_data_portal.warna_disiapkan'
# Palet website mengikuti ikon aplikasi: ungu tua, merah muda, dan lavender.
PALET_IKON = {
    'o-color-1': '#5b21b6',   # primer (ungu tua)
    'o-color-2': '#ff005c',   # sekunder (merah muda)
    'o-color-3': '#f5f3ff',   # latar terang (lavender sangat muda)
    'o-color-4': '#ffffff',
    'o-color-5': '#1e1033',   # gelap (ungu kehitaman)
}
IKON_APLIKASI = 'satu_data/static/description/icon.png'
PARAM_PENGUMUMAN = 'satu_data_portal.pengumuman'
BERANDA = '/beranda'
BAHASA = 'id_ID'


class Website(models.Model):
    _inherit = 'website'

    # ── Dipakai template (nama tanpa garis bawah agar bisa dipanggil QWeb) ──

    def sd_nama_wilayah(self):
        """Mis. "Kabupaten Jember" (dari company website)."""
        self.ensure_one()
        return self.env['satu_data.data']._sd_nama_wilayah(self.company_id)

    def sd_pengumuman(self):
        """Teks pengumuman di atas semua halaman portal (parameter sistem
        ``satu_data_portal.pengumuman``); kosong = tanpa pengumuman. Dipakai, mis., untuk
        menandai bahwa data masih contoh/uji coba."""
        teks = (self.env['ir.config_parameter'].sudo().get_param(PARAM_PENGUMUMAN) or '').strip()
        return teks[:300] or False

    def sd_instansi(self, peran):
        """Instansi aktif wilayah website ini dengan peran tertentu (mis. walidata)."""
        self.ensure_one()
        return self.env['satu_data.instansi'].sudo().search([
            ('company_id', '=', self.company_id.id), ('peran', '=', peran)])

    @api.model
    def _sd_siapkan_favicon(self):
        """Favicon website = ikon aplikasi Satu Data (bukan logo Odoo); sekali saja."""
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param(PARAM_FAVICON):
            return
        with file_open(IKON_APLIKASI, 'rb') as f:
            ikon = base64.b64encode(f.read())
        self.sudo().search([]).write({'favicon': ikon})
        param.set_param(PARAM_FAVICON, '1')

    @api.model
    def _sd_siapkan_warna(self):
        """Palet warna website mengikuti ikon aplikasi (Color 1 ungu, Color 2 merah muda); sekali saja."""
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param(PARAM_WARNA):
            return
        self.env['website.assets'].make_scss_customization(
            '/website/static/src/scss/options/colors/user_color_palette.scss', PALET_IKON)
        param.set_param(PARAM_WARNA, '1')

    # ── Penyiapan sekali saat modul dipasang ─────────────────────────────────

    @api.model
    def _sd_siapkan_portal(self):
        """Jadikan website sebagai portal Satu Data berbahasa Indonesia (sekali saja).

        Bahasa Indonesia sebagai satu-satunya bahasa website, nama website, beranda portal,
        menu "Home" menjadi "Beranda", dan menu "Contact us" dihapus. Tidak dijalankan ulang
        saat modul diperbarui, agar pengaturan Admin sesudahnya tidak tertimpa.
        """
        param = self.env['ir.config_parameter'].sudo()
        self._sd_siapkan_favicon()
        self._sd_siapkan_warna()
        if param.get_param(PARAM_DISIAPKAN):
            return
        websites = self.sudo().search([])
        lang = self.env['res.lang']._activate_lang(BAHASA)
        if lang and websites:
            # Muat terjemahan bahasa Indonesia untuk modul yang terpasang.
            self.env['base.language.install'].create({
                'lang_ids': [(6, 0, lang.ids)], 'website_ids': [(6, 0, websites.ids)],
                'overwrite': False,
            }).lang_install()
        for website in websites:
            vals = {}
            if lang:
                vals.update({'language_ids': [(6, 0, lang.ids)], 'default_lang_id': lang.id})
            if not website.homepage_url:
                vals['homepage_url'] = BERANDA
            if (website.name or '').startswith('My Website'):
                vals['name'] = f'Satu Data {website.sd_nama_wilayah()}'
            # Logo kab/kota di header (bukan "Your Logo").
            if website.company_id.logo:
                vals['logo'] = website.company_id.logo
            website.write(vals)

        # Header bawaan memuat nomor telepon contoh dan tombol "Hubungi Kami"; portal
        # tidak memakai keduanya (Admin dapat mengaktifkannya lagi di penyunting website).
        for xmlid in ('website.header_text_element', 'website.header_call_to_action'):
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if view:
                view.sudo().active = False

        Menu = self.env['website.menu'].sudo()
        Menu.search([('url', '=', '/contactus')]).unlink()
        for menu in Menu.search([('url', '=', '/'), ('parent_id', '!=', False)]):
            menu.update_field_translations('name', {'en_US': 'Beranda', BAHASA: 'Beranda'})
        param.set_param(PARAM_DISIAPKAN, '1')
        _logger.info('Website disiapkan sebagai portal Satu Data (%s website).', len(websites))
