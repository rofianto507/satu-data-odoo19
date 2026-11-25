"""Isi berkas unduhan data publik: CSV, Excel (xlsx), dan JSON.

Kolom format panjang mengikuti ``satu_data.data._sd_baris_publik``. Angka memakai titik
desimal (bukan format tampilan Indonesia) agar mudah dibaca program pengolah data.
"""
import csv
import io
import json

import xlsxwriter

KOLOM = [
    ('kode_wilayah', 'Kode Wilayah'),
    ('nama_wilayah', 'Nama Wilayah'),
    ('tingkat_wilayah', 'Tingkat Wilayah'),
    ('periode', 'Periode'),
    ('tahun', 'Tahun'),
    ('tanggal_mulai', 'Tanggal Mulai'),
    ('tanggal_akhir', 'Tanggal Akhir'),
    ('nilai', 'Nilai'),
    ('satuan', 'Satuan'),
]
FORMAT = {
    'csv':  ('text/csv; charset=utf-8', 'csv'),
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'),
    'json': ('application/json; charset=utf-8', 'json'),
}


def isi_csv(baris):
    buf = io.StringIO()
    tulis = csv.writer(buf, lineterminator='\n')
    tulis.writerow([k for k, _l in KOLOM])
    for b in baris:
        tulis.writerow(['' if b[k] is None else b[k] for k, _l in KOLOM])
    # BOM agar Excel membuka UTF-8 (nama wilayah ber-aksen) dengan benar.
    return ('﻿' + buf.getvalue()).encode('utf-8')


def isi_json(metadata, baris):
    return json.dumps({'metadata': metadata, 'data': baris}, ensure_ascii=False,
                      indent=2).encode('utf-8')


def isi_xlsx(judul, metadata_label, tabel, baris, sumber):
    """Tiga lembar: Tabel (wilayah x periode), Data (format panjang), Metadata."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {'in_memory': True})
    tebal = wb.add_format({'bold': True})
    kepala = wb.add_format({'bold': True, 'bg_color': '#E2E8F0', 'border': 1, 'text_wrap': True,
                            'valign': 'top'})
    judul_fmt = wb.add_format({'bold': True, 'font_size': 13})
    kecil = wb.add_format({'italic': True, 'font_color': '#4B5563'})
    bungkus = wb.add_format({'text_wrap': True, 'valign': 'top'})
    angka = wb.add_format({'num_format': '#,##0.' + '0' * tabel['desimal']
                           if tabel['desimal'] else '#,##0'})
    angka_tebal = wb.add_format({'bold': True, 'num_format': '#,##0.' + '0' * tabel['desimal']
                                 if tabel['desimal'] else '#,##0'})

    # Lembar 1: tabel seperti di halaman (semua periode)
    ws = wb.add_worksheet('Tabel')
    ws.write(0, 0, judul, judul_fmt)
    ws.write(1, 0, sumber, kecil)
    ws.write_row(3, 0, ['Wilayah'] + [p['label'] for p in tabel['periode']], kepala)
    for i, b in enumerate(tabel['baris'], start=4):
        ws.write(i, 0, b['nama'], tebal if b['total'] else None)
        for j, v in enumerate(b['nilai'], start=1):
            if v is not None:
                ws.write_number(i, j, v, angka_tebal if b['total'] else angka)
    ws.set_column(0, 0, 32)
    ws.set_column(1, max(1, len(tabel['periode'])), 16)
    ws.freeze_panes(4, 1)

    # Lembar 2: format panjang
    ws = wb.add_worksheet('Data')
    ws.write_row(0, 0, [k for k, _l in KOLOM], kepala)
    for i, b in enumerate(baris, start=1):
        for j, (k, _l) in enumerate(KOLOM):
            v = b[k]
            if v is None:
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                ws.write_number(i, j, v)
            else:
                ws.write_string(i, j, str(v))
    ws.set_column(0, len(KOLOM) - 1, 18)
    ws.freeze_panes(1, 0)
    if baris:
        ws.autofilter(0, 0, len(baris), len(KOLOM) - 1)

    # Lembar 3: metadata
    ws = wb.add_worksheet('Metadata')
    ws.write_row(0, 0, ['Isian', 'Keterangan'], kepala)
    for i, (label, teks) in enumerate(metadata_label, start=1):
        ws.write(i, 0, label, tebal)
        ws.write(i, 1, teks, bungkus)
    ws.set_column(0, 0, 28)
    ws.set_column(1, 1, 90)

    wb.close()
    return buf.getvalue()
