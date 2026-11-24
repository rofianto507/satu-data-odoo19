def format_angka(nilai):
    """Format bilangan bulat dengan pemisah ribuan titik: 12500 -> '12.500'."""
    return f'{int(nilai):,}'.replace(',', '.')
