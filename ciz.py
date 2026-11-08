"""Kanzi'nin Claude'u için: ekranın üstüne birkaç saniyeliğine Kanzi'nin renginde, ışımalı işaret çizer, tıklamaları engellemez.

    python ciz.py daire X Y [R]          (X, Y: ekran görüntüsü pikseli; R yarıçap, varsayılan 60)
    python ciz.py ok X1 Y1 X2 Y2         (X1,Y1'den X2,Y2'ye ok; ucu X2,Y2)
    python ciz.py alti X1 X2 Y           (X1..X2 arası Y hizasında altını çiz)
    birden çok şekil: "daire 100 200 ; ok 50 50 100 200"   --sure 8 (saniye; yoksa Kanzi kapatana kadar, en çok 15 dk)
"""
import ctypes
import json
import math
import os
import sys
import tkinter as tk

ctypes.windll.shcore.SetProcessDpiAwareness(2)  # ekran görüntüsüyle aynı fiziksel piksel
from PIL import Image, ImageDraw  # noqa: E402
import gorunum as g  # noqa: E402

u = ctypes.windll.user32
PAY = 40  # ışıma için kenar payı


def sekiller(argv):
    """['daire','1','2',';','ok',...] -> [('daire', [1.0, 2.0]), ('ok', [...])]; bozuksa ValueError."""
    sonuc, parca = [], []
    for a in " ".join(argv).replace(";", " ; ").split() + [";"]:
        if a == ";":
            if parca:
                ad, sayi = parca[0], [float(v) for v in parca[1:]]
                if (ad, len(sayi)) not in (("daire", 2), ("daire", 3), ("ok", 4), ("alti", 3)):
                    raise ValueError(" ".join(parca))
                sonuc.append((ad, sayi))
            parca = []
        else:
            parca.append(a)
    return sonuc


def ciz_resmi(liste, olcek=1.0):
    """Şekilleri Kanzi'nin ok/halka tarzında çizer: tema rengi, ışıma, ince açık iç çizgi.
    -> (RGBA resim, sol, üst) ekran görüntüsü pikseli cinsinden."""
    nok = []
    for ad, s in liste:
        if ad == "daire":
            r = s[2] if len(s) == 3 else 60
            nok += [(s[0] - r, s[1] - r), (s[0] + r, s[1] + r)]
        elif ad == "ok":
            nok += [(s[0], s[1]), (s[2], s[3])]
        else:
            nok += [(s[0], s[2]), (s[1], s[2])]
    sol, ust = min(x for x, _ in nok) - PAY, min(y for _, y in nok) - PAY
    gen, boy = max(x for x, _ in nok) + PAY - sol, max(y for _, y in nok) + PAY - ust
    S = g.SS  # büyük çizip küçült: yumuşak kenar
    d = lambda x, y: ((x - sol) * S, (y - ust) * S)
    uc = 22 * olcek * S  # ok ucunun boyu

    def maske(kal):
        """Şekiller, kal kalınlığında (yuvarlak uçlu) tek renk maske."""
        mk = Image.new("L", (int(gen * S), int(boy * S)), 0)
        m = ImageDraw.Draw(mk)
        nokta = lambda x, y: m.ellipse([x - kal / 2, y - kal / 2, x + kal / 2, y + kal / 2], fill=255)
        for ad, s in liste:
            if ad == "daire":
                r = s[2] if len(s) == 3 else 60
                (x, y), rr = d(s[0], s[1]), r * S + kal / 2  # PIL kalınlığı içe çizer: kenar yarıçapta ortalansın
                m.ellipse([x - rr, y - rr, x + rr, y + rr], outline=255, width=round(kal))
            elif ad == "ok":
                (x1, y1), (x2, y2) = d(s[0], s[1]), d(s[2], s[3])
                a = math.atan2(y2 - y1, x2 - x1)
                kose = [(x2, y2), *((x2 - uc * math.cos(a + t), y2 - uc * math.sin(a + t)) for t in (0.45, -0.45))]
                m.line([(x1, y1), (x2 - uc * 0.7 * math.cos(a), y2 - uc * 0.7 * math.sin(a))], fill=255, width=round(kal))
                nokta(x1, y1)
                m.polygon(kose, fill=255)
                for x, y in kose:  # uç da aynı kalınlıkta kenar alsın
                    nokta(x, y)
                m.line(kose + kose[:1], fill=255, width=round(kal), joint="curve")
            else:
                m.line([d(s[0], s[2]), d(s[1], s[2])], fill=255, width=round(kal))
                nokta(*d(s[0], s[2]))
                nokta(*d(s[1], s[2]))
        return mk

    kal = 5 * olcek * S
    govde, ic, cizgi = maske(kal * 1.9), maske(kal), maske(max(S, kal / 3))
    im = g.isima(ic, g.DINLE, 5 * S, 1.4)  # Kanzi'nin göz ışığı gibi parıltı

    def boya(mk, renk, oran=1.0):
        katman = Image.new("RGBA", mk.size, (*renk, 0))
        katman.putalpha(mk if oran == 1.0 else mk.point(lambda v: int(v * oran)))
        im.alpha_composite(katman)

    boya(govde, g.GOVDE)  # koyu cam kenar: açık zeminde de seçilsin
    boya(ic, g.DINLE)
    boya(cizgi, (240, 250, 255), 0.8)  # ortadaki parlak şerit
    return im.resize((int(gen), int(boy)), Image.LANCZOS), sol, ust


def goster(liste, sure):
    try:  # Kanzi'nin seçili rengi (kanzi_v2'yi içe aktarmak yavaş: ayarı doğrudan oku)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ayarlar.json"), encoding="utf-8") as f:
            g.tema(json.load(f).get("renk", "Mavi"), "Küre")
    except (OSError, ValueError):
        pass
    im, sol, ust = ciz_resmi(liste, ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100)
    k = tk.Tk()
    k.title("KanziCizim")  # Kanzi bu adla bulup kapatır
    k.overrideredirect(True)
    k.attributes("-topmost", True)
    k.geometry("1x1+0+0")
    k.update()  # pencere ekrana çıkmadan UpdateLayeredWindow işe yaramaz
    hwnd = u.GetParent(k.winfo_id()) or k.winfo_id()
    u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20 | 0x80 | 0x8 | 0x8000000)
    # katmanlı, tık geçirir, görev çubuğunda yok, en üstte, odak almaz
    g.katmana_bas(hwnd, im, sol + u.GetSystemMetrics(76), ust + u.GetSystemMetrics(77))
    k.after(int(sure * 1000), k.destroy)
    k.mainloop()


if __name__ == "__main__":
    arg = sys.argv[1:]
    sure = 900.0  # Kanzi baloncuk kapanınca "KanziCizim" pencerelerini kapatır; bu yalnız emniyet
    if "--sure" in arg:
        i = arg.index("--sure")
        sure = float(arg[i + 1])
        del arg[i:i + 2]
    try:
        liste = sekiller(arg)
    except (ValueError, IndexError) as e:
        sys.exit(f"anlaşılmadı: {e}\n{__doc__}")
    if not liste:
        sys.exit(__doc__)
    goster(liste, sure)
