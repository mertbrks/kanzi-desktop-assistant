"""Kanzi'nin Claude'u için: ekran görüntüsündeki bir kutuya tıklar ve yazıyı yazar. Enter'a BASMAZ.

    python tikla_yaz.py X Y "yazı"        (X, Y: ekran görüntüsü pikseli; sol/üst monitör kayması kendisi eklenir)
    python tikla_yaz.py X Y --dosya yol   (uzun ya da tırnaklı yazı UTF-8 dosyadan)
    --degistir ekle: kutudaki eski yazı seçilip yerine yazılır (yoksa eski yazının sonuna eklenir)
Panoya dokunmaz.
İş bitince fare eski yerine döner.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

ctypes.windll.shcore.SetProcessDpiAwareness(2)  # koordinatlar ekran görüntüsüyle aynı fiziksel piksel olsun
import isler  # noqa: E402

u = ctypes.windll.user32


def tikla_yaz(x, y, metin, degistir=False):
    eski = wt.POINT()
    u.GetCursorPos(ctypes.byref(eski))
    gx, gy = isler.gercek_nokta(x, y)  # görüntü küçültme oranı + sanal ekranın sol-üstü
    u.SetCursorPos(gx, gy)
    time.sleep(0.05)
    u.mouse_event(0x0002, 0, 0, 0, 0)  # sol tuş bas
    u.mouse_event(0x0004, 0, 0, 0, 0)  # bırak
    time.sleep(0.35)  # kutu odağı alsın
    if degistir:  # Ctrl+A: hepsini seç, yazınca yerine geçer
        for v, f in ((0x11, 0), (0x41, 0), (0x41, 2), (0x11, 2)):
            u.keybd_event(v, 0, f, 0)
    else:  # tıklanan yer yazının ortası olabilir: sona git
        u.keybd_event(0x23, 0, 1, 0)
        u.keybd_event(0x23, 0, 3, 0)
    time.sleep(0.05)
    isler.klavyeye_yaz(metin)
    u.SetCursorPos(eski.x, eski.y)


if __name__ == "__main__":
    arg = [a for a in sys.argv[1:] if a != "--degistir"]
    if len(arg) < 3:
        sys.exit(__doc__)
    yazi = open(arg[3], encoding="utf-8").read() if arg[2] == "--dosya" else arg[2]
    tikla_yaz(int(float(arg[0])), int(float(arg[1])), yazi, "--degistir" in sys.argv)
    print(f"yazıldı ({len(yazi)} karakter), Enter'a basılmadı")
