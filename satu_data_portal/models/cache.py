"""Pembersihan cache nilai portal (``satu_data.data._sd_nilai_publik_cache``).

Nilai publik hanya berubah bila: laporan terbit/ditarik, wilayah (kecamatan/desa, termasuk
luas dan kecamatan induk) berubah, atau Daftar Data diubah. Baris rekap yang sudah terbit
terkunci sehingga tidak perlu dipantau. Pembersihan berlaku di semua worker (sinyal registry).
"""
from odoo import api, models


class SatuDataCacheMixin(models.AbstractModel):
    _name        = 'satu_data.portal.cache.mixin'
    _description = 'Bersihkan cache portal saat data sumber berubah'

    def _sd_bersihkan_cache_portal(self):
        self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sd_bersihkan_cache_portal()
        return records

    def write(self, vals):
        res = super().write(vals)
        if self._sd_perlu_bersihkan(vals):
            self._sd_bersihkan_cache_portal()
        return res

    def unlink(self):
        res = super().unlink()
        self._sd_bersihkan_cache_portal()
        return res

    def _sd_perlu_bersihkan(self, vals):
        return True


class SatuDataPengajuan(models.Model):
    _name    = 'satu_data.pengajuan'
    _inherit = ['satu_data.pengajuan', 'satu_data.portal.cache.mixin']

    def _sd_perlu_bersihkan(self, vals):
        return bool({'state', 'periode_id', 'sektor', 'company_id'} & set(vals))


class SatuDataKecamatan(models.Model):
    _name    = 'satu_data.kecamatan'
    _inherit = ['satu_data.kecamatan', 'satu_data.portal.cache.mixin']


class SatuDataDesa(models.Model):
    _name    = 'satu_data.desa'
    _inherit = ['satu_data.desa', 'satu_data.portal.cache.mixin']


class SatuDataData(models.Model):
    _name    = 'satu_data.data'
    _inherit = ['satu_data.data', 'satu_data.portal.cache.mixin']
