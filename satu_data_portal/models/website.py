import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

PARAM_DISIAPKAN = 'satu_data_portal.website_disiapkan'
BERANDA = '/beranda'
BAHASA = 'id_ID'


class Website(models.Model):
    _inherit = 'website'

    # ── Dipakai template (nama tanpa garis bawah agar bisa dipanggil QWeb) ──

    def sd_nama_wilayah(self):
        """Mis. "Kabupaten Jember" (dari company website)."""
        self.ensure_one()
        return self.env['satu_data.data']._sd_nama_wilayah(self.company_id)

    def sd_instansi(self, peran):
        """Instansi aktif wilayah website ini dengan peran tertentu (mis. walidata)."""
        self.ensure_one()
        return self.env['satu_data.instansi'].sudo().search([
            ('company_id', '=', self.company_id.id), ('peran', '=', peran)])

    # ── Penyiapan sekali saat modul dipasang ─────────────────────────────────

    @api.model
    def _sd_siapkan_portal(self):
        """Jadikan website sebagai portal Satu Data berbahasa Indonesia (sekali saja).

        Bahasa Indonesia sebagai satu-satunya bahasa website, nama website, beranda portal,
        menu "Home" menjadi "Beranda", dan menu "Contact us" dihapus. Tidak dijalankan ulang
        saat modul diperbarui, agar pengaturan Admin sesudahnya tidak tertimpa.
        """
        param = self.env['ir.config_parameter'].sudo()
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
            website.write(vals)

        Menu = self.env['website.menu'].sudo()
        Menu.search([('url', '=', '/contactus')]).unlink()
        for menu in Menu.search([('url', '=', '/'), ('parent_id', '!=', False)]):
            menu.update_field_translations('name', {'en_US': 'Beranda', BAHASA: 'Beranda'})
        param.set_param(PARAM_DISIAPKAN, '1')
        _logger.info('Website disiapkan sebagai portal Satu Data (%s website).', len(websites))
