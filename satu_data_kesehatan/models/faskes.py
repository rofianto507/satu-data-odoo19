import json

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

JENIS_FASKES = [
    ('puskesmas',   'Puskesmas'),
    ('pustu',       'Puskesmas Pembantu'),
    ('rumah_sakit', 'Rumah Sakit'),
    ('klinik',      'Klinik'),
    ('lainnya',     'Lainnya'),
]


def titik_tengah(geojson):
    """(lintang, bujur) titik tengah bagian terluas sebuah Polygon/MultiPolygon GeoJSON.

    Centroid luas cincin luar (rumus shoelace). Cukup untuk menaruh penanda di peta;
    bukan titik yang dijamin berada di dalam poligon cekung.
    """
    try:
        geo = json.loads(geojson) if isinstance(geojson, str) else geojson
    except (TypeError, ValueError):
        return None
    if not geo:
        return None
    if geo.get('type') == 'Feature':
        geo = geo.get('geometry') or {}
    if geo.get('type') == 'Polygon':
        poligon = [geo.get('coordinates') or []]
    elif geo.get('type') == 'MultiPolygon':
        poligon = geo.get('coordinates') or []
    else:
        return None
    terbaik = None
    for cincin in (p[0] for p in poligon if p and len(p[0]) >= 3):
        luas = cx = cy = 0.0
        for (x1, y1), (x2, y2) in zip(cincin, cincin[1:] + cincin[:1]):
            silang = x1 * y2 - x2 * y1
            luas += silang
            cx += (x1 + x2) * silang
            cy += (y1 + y2) * silang
        if not luas:
            continue
        hasil = (abs(luas), cy / (3 * luas), cx / (3 * luas))
        if terbaik is None or hasil[0] > terbaik[0]:
            terbaik = hasil
    return (round(terbaik[1], 6), round(terbaik[2], 6)) if terbaik else None


class SatuDataFaskes(models.Model):
    """Fasilitas pelayanan kesehatan dan wilayah kerja puskesmas.

    Wilayah kerja = desa/kelurahan binaan puskesmas; satu desa hanya masuk wilayah
    kerja satu puskesmas aktif. Data kesehatan per desa mencatat puskesmasnya.
    """
    _name        = 'satu_data.faskes'
    _description = 'Fasilitas Kesehatan'
    _inherit     = ['mail.thread']
    _order       = 'jenis, name'

    name       = fields.Char('Nama Fasilitas', required=True, tracking=True)
    kode       = fields.Char('Kode Faskes', tracking=True,
                             help='Kode fasilitas kesehatan dari Kementerian Kesehatan, bila ada.')
    jenis      = fields.Selection(JENIS_FASKES, string='Jenis', required=True,
                                  default='puskesmas', tracking=True, index=True)
    kategori   = fields.Selection([
        ('rawat_inap',     'Rawat Inap'),
        ('non_rawat_inap', 'Non Rawat Inap'),
    ], string='Kategori Puskesmas')
    induk_id   = fields.Many2one('satu_data.faskes', string='Puskesmas Induk', index=True,
                                 ondelete='restrict',
                                 domain="[('jenis', '=', 'puskesmas'), ('company_id', '=', company_id)]",
                                 help='Untuk puskesmas pembantu.')
    # Tanpa check_company: company_id diturunkan dari desa_id (lihat rekap kependudukan).
    desa_id    = fields.Many2one('satu_data.desa', string='Lokasi (Desa/Kelurahan)', required=True,
                                 index=True, ondelete='restrict', tracking=True,
                                 domain="[('company_id', 'in', allowed_company_ids)]")
    kecamatan_id = fields.Many2one(related='desa_id.kecamatan_id', store=True, index=True,
                                   string='Kecamatan')
    company_id = fields.Many2one(related='desa_id.company_id', store=True, index=True,
                                 string='Wilayah (Kab/Kota)')
    alamat     = fields.Char('Alamat')
    telepon    = fields.Char('Telepon')
    latitude   = fields.Float('Lintang', digits=(10, 6))
    longitude  = fields.Float('Bujur', digits=(10, 6))
    active     = fields.Boolean(default=True)

    wilayah_kerja_ids = fields.Many2many(
        'satu_data.desa', 'satu_data_faskes_desa_rel', 'faskes_id', 'desa_id',
        string='Wilayah Kerja', domain="[('company_id', '=', company_id)]",
        help='Desa/kelurahan binaan puskesmas. Satu desa hanya masuk satu puskesmas.')
    jumlah_desa = fields.Integer('Desa Binaan', compute='_compute_jumlah_desa')
    pustu_ids   = fields.One2many('satu_data.faskes', 'induk_id', string='Puskesmas Pembantu')

    _kode_company_uniq = models.Constraint(
        'UNIQUE(company_id, kode)',
        'Kode faskes sudah dipakai di wilayah ini.',
    )

    @api.depends('wilayah_kerja_ids')
    def _compute_jumlah_desa(self):
        for rec in self:
            rec.jumlah_desa = len(rec.wilayah_kerja_ids)

    @api.onchange('jenis')
    def _onchange_jenis(self):
        if self.jenis != 'puskesmas':
            self.kategori = False
            self.wilayah_kerja_ids = False
        if self.jenis != 'pustu':
            self.induk_id = False

    # ── Constraint ───────────────────────────────────────────────────────────

    @api.constrains('jenis', 'wilayah_kerja_ids', 'active', 'induk_id')
    def _check_wilayah_kerja(self):
        for rec in self:
            if rec.wilayah_kerja_ids and rec.jenis != 'puskesmas':
                raise ValidationError(self.env._('Wilayah kerja hanya untuk puskesmas.'))
            if rec.induk_id and (rec.induk_id.jenis != 'puskesmas' or rec.induk_id == rec):
                raise ValidationError(self.env._('Puskesmas induk harus puskesmas lain.'))
            if rec.wilayah_kerja_ids.filtered(lambda d: d.company_id != rec.company_id):
                raise ValidationError(self.env._(
                    'Wilayah kerja harus desa/kelurahan di wilayah yang sama dengan puskesmas.'))
            if not (rec.active and rec.wilayah_kerja_ids):
                continue
            bentrok = self.search([('id', '!=', rec.id), ('jenis', '=', 'puskesmas'),
                                   ('wilayah_kerja_ids', 'in', rec.wilayah_kerja_ids.ids)], limit=1)
            if bentrok:
                desa = rec.wilayah_kerja_ids & bentrok.wilayah_kerja_ids
                raise ValidationError(self.env._(
                    '%(desa)s sudah masuk wilayah kerja %(lain)s. Satu desa/kelurahan hanya '
                    'boleh masuk wilayah kerja satu puskesmas.',
                    desa=', '.join(desa.mapped('name')), lain=bentrok.name))

    @api.constrains('latitude', 'longitude')
    def _check_koordinat(self):
        for rec in self:
            if not (-90 <= rec.latitude <= 90 and -180 <= rec.longitude <= 180):
                raise ValidationError(self.env._('Koordinat tidak valid.'))

    # ── Aksi ─────────────────────────────────────────────────────────────────

    def action_koordinat_dari_desa(self):
        """Isi koordinat dengan titik tengah batas desa lokasi (perkiraan)."""
        for rec in self:
            titik = titik_tengah(rec.desa_id.geojson_peta)
            if not titik:
                raise UserError(self.env._(
                    'Desa/kelurahan %(desa)s belum punya batas wilayah.', desa=rec.desa_id.name))
            rec.write({'latitude': titik[0], 'longitude': titik[1]})
