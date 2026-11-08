"""Kanzi'nin Claude'u için: ekranın üstüne mavi, dalgalı, kuyruğu silikleşen işaretler çizer (örnek.jpg tarzı);
tıklamaları engellemez, Kanzi anlatımı kapatana kadar kalır.

    python ciz.py daire X Y [R]          (X, Y: ekran görüntüsü pikseli; R yarıçap, varsayılan 60)
    python ciz.py ok X1 Y1 X2 Y2         (X1,Y1'den X2,Y2'ye ok; ucu X2,Y2)
    python ciz.py alti X1 X2 Y           (X1..X2 arası Y hizasında altını çiz)
    birden çok şekil: "daire 100 200 ; ok 50 50 100 200"   --sure 8 (saniye; yoksa Kanzi kapatana kadar, en çok 15 dk)
"""
import ctypes
import math
import sys
import tkinter as tk

ctypes.windll.shcore.SetProcessDpiAwareness(2)  # ekran görüntüsüyle aynı fiziksel piksel
from PIL import Image, ImageDraw  # noqa: E402
import gorunum as g  # noqa: E402

u = ctypes.windll.user32
PAY = 70  # dalga ve ok kanatları için kenar payı
MAVI = (58, 141, 240)  # örnekteki düz mavi
EN_KISA_OK = 150  # px (100% ölçekte); Mert kısayı beğenmedi, 240 da fazla uzun geldi


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


def serit(m, noktalar, kalinlik, saydamlik):
    """Noktalar boyunca kalınlığı ve saydamlığı değişen dolu şerit (dörtgen dörtgen) maskeye çizer."""
    for i in range(len(noktalar) - 1):
        (x1, y1), (x2, y2) = noktalar[i], noktalar[i + 1]
        boy = math.hypot(x2 - x1, y2 - y1) or 1
        nx, ny = -(y2 - y1) / boy, (x2 - x1) / boy  # dik yön
        w1, w2 = kalinlik[i] / 2, kalinlik[i + 1] / 2
        m.polygon([(x1 + nx * w1, y1 + ny * w1), (x2 + nx * w2, y2 + ny * w2),
                   (x2 - nx * w2, y2 - ny * w2), (x1 - nx * w1, y1 - ny * w1)], fill=int(saydamlik[i]),
                  outline=int(saydamlik[i]))
        if i:  # eğride dörtgenlerin dış köşesinde kama boşluğu kalmasın: eklemi yuvarlak doldur
            m.ellipse([x1 - w1, y1 - w1, x1 + w1, y1 + w1], fill=int(saydamlik[i]))


def uzat(s, en_kisa):
    """Ok kısa kaldıysa başlangıcı aynı yönde geri çeker (uç, gösterilen yerde kalır)."""
    x1, y1, x2, y2 = s
    L = math.hypot(x2 - x1, y2 - y1)
    if L >= en_kisa:
        return s
    gx, gy = ((x2 - x1) / L, (y2 - y1) / L) if L else (0.8, -0.6)  # nokta verildiyse sol alttan gelsin
    return [x2 - gx * en_kisa, y2 - gy * en_kisa, x2, y2]


def ok_ucu(x, y, a, H):
    """Geriye kıvrık kanatlı sivri uç (örnekteki gibi): uç (x,y), yön a, boy H."""
    yerel = [(0, 0), (-1.5 * H, -0.58 * H)]  # uzun, sivri uç
    yerel += [(-1.5 * H + 0.7 * H * t, -0.58 * H * (1 - t) ** 1.6) for t in (0.2, 0.4, 0.6, 0.8, 1.0)]  # içe kıvrık, ince kanat
    yerel += [(x_, -y_) for x_, y_ in reversed(yerel[1:-1])]  # alt kanat: ayna
    ca, sa = math.cos(a), math.sin(a)
    return [(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in yerel]


def ciz_resmi(liste, olcek=1.0):
    """Şekilleri örnek.jpg tarzında çizer: düz mavi, dalgalı gövde, kuyrukta silikleşme, uca doğru kalınlaşma.
    -> (RGBA resim, sol, üst) ekran görüntüsü pikseli cinsinden."""
    liste = [(ad, uzat(s, EN_KISA_OK * olcek) if ad == "ok" else s) for ad, s in liste]
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
    mk = Image.new("L", (int(gen * S), int(boy * S)), 0)
    m = ImageDraw.Draw(mk)
    H, N = 38 * olcek * S, 64  # ok ucu boyu, şeritteki nokta sayısı
    for ad, s in liste:
        ts = [i / N for i in range(N + 1)]
        if ad == "ok":
            (x1, y1), (x2, y2) = d(s[0], s[1]), d(s[2], s[3])
            a = math.atan2(y2 - y1, x2 - x1)
            ex, ey = x2 - 0.7 * H * math.cos(a), y2 - 0.7 * H * math.sin(a)  # gövde ucun çentiğinde biter
            L = math.hypot(ex - x1, ey - y1)
            gx, gy, nx, ny = (ex - x1) / (L or 1), (ey - y1) / (L or 1), -math.sin(a), math.cos(a)
            gen_ = min(18 * olcek * S, L * 0.09)  # dalga genliği; uçta sıfır: ok düz girsin
            nk = [(x1 + gx * L * t + nx * gen_ * math.sin(2 * math.pi * t) * (1 - t),
                   y1 + gy * L * t + ny * gen_ * math.sin(2 * math.pi * t) * (1 - t)) for t in ts]
            serit(m, nk, [1.5 * S + 0.36 * H * t ** 0.8 for t in ts], [255 * min(1, t / 0.6) ** 1.4 for t in ts])
            m.polygon(ok_ucu(x2, y2, a, H), fill=255)
        elif ad == "daire":
            r = (s[2] if len(s) == 3 else 60) * S
            (cx, cy), b = d(s[0], s[1]), -2.4  # başlangıç açısı (sol üst); fırça darbesi gibi biraz fazla döner
            nk = [(cx + r * (1 + 0.08 * (t - 0.5)) * math.cos(b + t * 2.25 * math.pi),
                   cy + r * 0.92 * (1 + 0.08 * (t - 0.5)) * math.sin(b + t * 2.25 * math.pi)) for t in ts]
            serit(m, nk, [S + 7 * olcek * S * math.sin(math.pi * min(1, t * 1.15)) ** 0.5 for t in ts],
                  [255 * min(1, t / 0.35) ** 1.2 for t in ts])
        else:
            (x1, y), (x2, _) = d(s[0], s[2]), d(s[1], s[2])
            nk = [(x1 + (x2 - x1) * t, y + 4 * olcek * S * math.sin(2 * math.pi * t)) for t in ts]
            serit(m, nk, [S + 8 * olcek * S * min(1, t / 0.5) * (1 - t ** 6) for t in ts],
                  [255 * min(1, t / 0.4) ** 1.2 for t in ts])
    im = Image.new("RGBA", mk.size, (*MAVI, 0))
    im.putalpha(mk)
    return im.resize((int(gen), int(boy)), Image.LANCZOS), sol, ust


def goster(liste, sure):
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
