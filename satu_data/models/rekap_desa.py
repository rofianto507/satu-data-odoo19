from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SatuDataRekapDesaMixin(models.AbstractModel):
    """Dasar model rekap per desa/kelurahan untuk modul sektor.

    Menyatukan hal yang sama di tiap sektor: desa, kecamatan yang dicatat saat data dibuat
    (snapshot), wilayah (company), laporan induk, dan penanda "terisi". Model pewaris
    menambahkan ``periode_id`` (domain frekuensinya sendiri), mengisi ``_sd_sektor`` dan
    ``_sd_field_angka`` (field angka yang diisi petugas), lalu bergantung pada
    ``mail.thread``:

        _inherit = ['mail.thread', 'satu_data.rekap.desa.mixin']

    Baris desa dibuat kosong saat laporan dibuka; angka nol yang diketik petugas sah
    (mis. tidak ada kasus), sehingga "terisi" tidak ditebak dari angkanya melainkan
    menyala otomatis saat petugas menyentuh salah satu field angka. Baris yang belum
    terisi tidak tampil di dashboard.
    """
    _name        = 'satu_data.rekap.desa.mixin'
    _inherit     = ['satu_data.rekap.mixin']
    _description = 'Mixin Rekap per Desa/Kelurahan'

    # Tanpa check_company: company_id justru diturunkan dari desa_id, jadi pada record baru
    # company_id masih kosong dan domain otomatis check_company membuat desa tak bisa dipilih.
    desa_id      = fields.Many2one(
        'satu_data.desa', string='Desa/Kelurahan', required=True, index=True,
        ondelete='restrict', tracking=True,
        domain="[('company_id', 'in', allowed_company_ids)]")
    kecamatan_id = fields.Many2one(
        'satu_data.kecamatan', string='Kecamatan', compute='_compute_wilayah',
        store=True, precompute=True, index=True, readonly=True,
        help='Kecamatan desa/kelurahan pada saat data ini dicatat.')
    company_id   = fields.Many2one(related='desa_id.company_id', store=True, index=True,
                                   string='Wilayah (Kab/Kota)')
    sumber       = fields.Char('Sumber Data')
    # Laporan (pengajuan) tempat baris ini berada: satu laporan per periode dan wilayah.
    pengajuan_id = fields.Many2one(
        'satu_data.pengajuan', string='Laporan', compute='_compute_pengajuan_id',
        store=True, index=True, ondelete='set null')
    terisi       = fields.Boolean(
        'Terisi', default=False, copy=False, index=True,
        help='Menyala otomatis saat petugas mengisi angka di baris ini. '
             'Baris yang belum terisi tidak tampil di dashboard.')

    _sd_field_angka = ()    # diisi model pewaris
    # Baris per desa pada laporan (mis. 4 untuk desa x jenjang) dan satuannya di peringatan
    # "x dari y ... belum terisi".
    _sd_baris_per_desa = 1
    _sd_satuan_baris = 'desa/kelurahan'

    @api.depends('desa_id')
    def _compute_wilayah(self):
        # Sengaja hanya bergantung pada desa_id (snapshot saat data dicatat).
        for rec in self:
            rec.kecamatan_id = rec.desa_id.kecamatan_id

    @api.depends('periode_id', 'company_id')
    def _compute_pengajuan_id(self):
        laporan = {
            (p.periode_id.id, p.company_id.id): p.id
            for p in self.env['satu_data.pengajuan'].sudo().search([
                ('sektor', '=', self._sd_sektor), ('periode_id', 'in', self.periode_id.ids)])
        }
        for rec in self:
            rec.pengajuan_id = laporan.get((rec.periode_id.id, rec.company_id.id), False)

    @api.depends('desa_id.name', 'periode_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ' – '.join(filter(None, [rec.desa_id.name, rec.periode_id.name]))

    @api.model
    def _sd_domain_terisi(self):
        return [('terisi', '=', True)]

    def _cek_tidak_negatif(self, nama_field, pesan):
        for rec in self:
            if any(rec[f] < 0 for f in nama_field):
                raise ValidationError(pesan)

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(v) for v in vals_list]
        for vals in vals_list:
            if 'terisi' not in vals and any(f in vals for f in self._sd_field_angka):
                vals['terisi'] = True
        return super().create(vals_list)

    def write(self, vals):
        if 'terisi' not in vals and any(f in vals for f in self._sd_field_angka):
            vals = dict(vals, terisi=True)
        return super().write(vals)
