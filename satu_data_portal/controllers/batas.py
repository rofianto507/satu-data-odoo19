"""Pembatas permintaan sederhana per alamat IP (jendela 1 menit, di memori tiap worker).

Bukan pengaman utama: dengan beberapa worker, batas efektif = batas x jumlah worker.
Tujuannya meredam pemanggilan berlebihan ke API/unduhan yang menghitung ulang angka.
"""
import threading
import time

BATAS_PER_MENIT = 120
_kunci = threading.Lock()
_hitungan = {}


def melebihi_batas(ip, batas=None):
    """Catat satu permintaan dari ``ip``; True bila sudah melebihi batas menit ini."""
    batas = BATAS_PER_MENIT if batas is None else batas
    menit = int(time.time() // 60)
    with _kunci:
        if len(_hitungan) > 10000:
            _hitungan.clear()
        awal, n = _hitungan.get(ip, (menit, 0))
        if awal != menit:
            n = 0
        n += 1
        _hitungan[ip] = (menit, n)
    return n > batas


def detik_ke_menit_berikutnya():
    return 60 - int(time.time()) % 60
