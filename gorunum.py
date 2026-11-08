"""Kanzi v2 görünümü: koyu mavi buzlu cam. Sesli Komut'taki cam topun koyu mavi hali.

Karakter ve baloncuk PIL ile piksel başına saydamlıkla çizilip UpdateLayeredWindow ile ekrana basılır
(Tk'nin tek renk saydamlığı yumuşak kenar ve yarı saydam cam veremez).
"""
import ctypes
import ctypes.wintypes as wt
import functools
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# Tema: menü, komut kutusu ve Kanzi aynı paleti kullanır
ZEMIN, KART, KART2 = "#0a1428", "#11213f", "#19305a"
YAZI, SOLUK, VURGU, CIZGI = "#e6f0ff", "#8ea5c9", "#5cc8ff", "#2a4677"
GOVDE = (34, 84, 168)        # kürenin cam rengi
DINLE, DUSUN = (92, 200, 255), (140, 170, 255)
SS = 3                       # yumuşak kenar için kaç kat büyük çizilir
KR = 22                      # kürenin yarıçapı (1x)
KW = 64                      # karakter resminin kenarı (halkalar için pay), 100% ölçekte
OLCEK = 1.0                  # ekran ölçeği (125% -> 1.25); uygulama açılışta bir kez ayarlar
# Ayarlar > Görünüm: (gövde, dinleme/göz ışığı, düşünme yayı)
RENKLER = {"Mavi": ((34, 84, 168), (92, 200, 255), (140, 170, 255)),
           "Mor": ((92, 52, 170), (190, 140, 255), (215, 175, 255)),
           "Yeşil": ((18, 118, 96), (80, 230, 180), (140, 240, 205)),
           "Turuncu": ((178, 88, 22), (255, 190, 90), (255, 214, 150)),
           "Pembe": ((170, 40, 112), (255, 130, 200), (255, 175, 222)),
           "Gece": ((38, 42, 54), (205, 215, 235), (175, 185, 210))}
SEKILLER = {"Küre": 2.0, "Yumuşak kare": 4.0, "Elmas": 1.3, "Yıldız": 0.0}  # kenar üssü |x|^p+|y|^p=r^p; 0: yıldız
SEKIL = 2.0


KRAVAT = True


def tema(renk, sekil, kravat=True):
    """Kanzi'nin rengini/şeklini/kravatını değiştirir; önbellekteki eski çizimler atılır."""
    global GOVDE, DINLE, DUSUN, SEKIL, KRAVAT
    KRAVAT = kravat
    GOVDE, DINLE, DUSUN = RENKLER.get(renk, RENKLER["Mavi"])
    SEKIL = SEKILLER.get(sekil, 2.0)
    karakter.cache_clear()
    ok_resmi.cache_clear()


def logo_kaydet(png, ico):
    """Seçili tasarımla (renk, şekil, kravat) sırıtan Kanzi'yi logo yapar: masaüstü kısayolu ve pencere simgesi."""
    global OLCEK
    eski = OLCEK
    OLCEK = 4  # büyük çiz, küçültürken keskin kalsın
    karakter.cache_clear()  # önbellek ölçeği bilmiyor: başka ölçekteki çizimler karışmasın
    try:
        im = karakter("bos", False, (0.0, 0.0), 0, 0.0, "sirit")
    finally:
        OLCEK = eski
        karakter.cache_clear()
    im = im.crop(im.getbbox())
    kenar = max(im.size) + 8
    kare_ = Image.new("RGBA", (kenar, kenar), (0, 0, 0, 0))
    kare_.alpha_composite(im, ((kenar - im.width) // 2, (kenar - im.height) // 2))
    kare_ = kare_.resize((256, 256), Image.LANCZOS)
    kare_.save(png)
    kare_.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def kw():
    return round(KW * OLCEK)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


@functools.lru_cache(maxsize=8)
def kure(renk, r=KR, p=2.0):
    """Buzlu cam gövde (p=2 küre, büyük p yumuşak kare, küçük p elmas), SS kat büyük RGBA: üstte dolu altta saydam, ince kenar ışığı, sol üst parlama."""
    W = int((r + 2) * 2 * SS)
    yy, xx = np.mgrid[0:W, 0:W].astype(np.float32)
    c, R = W / 2, r * SS
    if p:
        dn = (np.abs(xx - c) ** p + np.abs(yy - c) ** p) ** (1 / p) / R
    else:  # beş köşeli yumuşak yıldız: yarıçap açıya göre, bir ucu yukarıda; içi gözlere yer bırakır
        aci = np.arctan2(xx - c, c - yy)
        dn = np.hypot(xx - c, yy - c) / (R * (0.64 + 0.36 * ((np.cos(5 * aci) + 1) / 2) ** 2.2))
    ic = dn <= 1
    uzak = (1 - dn) * R
    t = np.clip((yy - (c - R)) / (2 * R), 0, 1)
    taban = np.array(renk, np.float32) * (0.62 + 0.38 * (1 - t))[..., None]  # alta doğru koyulaşır
    a = np.where(ic, 236 - 46 * t, 0)
    kenar_isik = (ic & (uzak < 1.2 * SS)) * (0.75 - 0.55 * t)
    alt_isik = ic * 0.22 * np.exp(-(((xx - c) / (0.55 * R)) ** 2 + ((yy - (c + 0.78 * R)) / (0.16 * R)) ** 2))
    parlama = ic * 0.6 * np.exp(-(((xx - (c - 0.32 * R)) / (0.4 * R)) ** 2 + ((yy - (c - 0.5 * R)) / (0.22 * R)) ** 2))
    beyaz = np.maximum(np.maximum(kenar_isik, parlama), alt_isik)[..., None]
    renkli = taban * (1 - beyaz) + np.array([210, 235, 255], np.float32) * beyaz
    a = a + (255 - a) * beyaz[..., 0] * ic
    return Image.fromarray(np.dstack([renkli, a]).clip(0, 255).astype(np.uint8), "RGBA")


def isima(maske, renk, bulanik, guc=1.0):
    """Tek renkli ışıma: yalnızca saydamlık bulanıklaşır, kenarda koyu/gri hale kalmaz."""
    a = maske.filter(ImageFilter.GaussianBlur(bulanik))
    if guc != 1.0:
        a = a.point(lambda v: min(255, int(v * guc)))
    im = Image.new("RGBA", maske.size, (*renk, 0))
    im.putalpha(a)
    return im


IFADELER = ("normal", "mutlu", "saskin", "uzgun", "uykulu", "dusunceli", "kizgin", "bikkin", "suphe", "sirit")


@functools.lru_cache(maxsize=2048)
def karakter(durum, kirp, bak, aci, halka, ifade="normal"):
    """durum: bos|dusunuyor|dinliyor|cozuyor|konusuyor; kirp: göz kapalı; bak: (x, y) bakış yönü, -3..3 (1x px);
    aci: düşünürken dönen yayın açısı; halka: dinlerken ses seviyesi / konuşurken ağız açıklığı (0..1);
    ifade: IFADELER'den biri. KW*OLCEK kenarlı RGBA döner."""
    Q = SS * OLCEK
    im = Image.new("RGBA", (round(KW * Q), round(KW * Q)), (0, 0, 0, 0))
    c = ImageDraw.Draw(im)
    s = lambda *v: [n * Q for n in v]
    m = KW / 2
    if durum == "dinliyor":  # sese göre büyüyen parlak halka + hafif dış ışıma
        r = KR + 3 + 7 * halka
        halka_m = Image.new("L", im.size, 0)
        ImageDraw.Draw(halka_m).ellipse(s(m - r, m - r, m + r, m + r), outline=150, width=round(4 * Q))
        im.alpha_composite(isima(halka_m, DINLE, 3 * Q))
        c.ellipse(s(m - r, m - r, m + r, m + r), outline=(*DINLE, 230), width=int(1.6 * Q))
    govde = kure(tuple(int(g * 0.8 + d * 0.2) for g, d in zip(GOVDE, DINLE)) if durum == "dinliyor" else GOVDE,
                 KR * OLCEK, SEKIL)
    im.alpha_composite(govde, (int(m * Q - govde.width / 2), int(m * Q - govde.height / 2)))
    if KRAVAT:
        im.alpha_composite(kravat(GOVDE, Q))
    if durum in ("dusunuyor", "cozuyor"):  # kürenin etrafında dönen ışık yayı
        r = KR + 4
        c.arc(s(m - r, m - r, m + r, m + r), aci, aci + 110, fill=(*DUSUN, 235), width=int(2 * Q))
        c.arc(s(m - r, m - r, m + r, m + r), aci + 180, aci + 230, fill=(*DUSUN, 120), width=int(2 * Q))
    bx, by = bak if isinstance(bak, tuple) else (bak, 0)
    kx, ky = bx * 0.45, by * 0.45  # gözler de bakışa doğru biraz kayar: baş çeviriyormuş gibi
    goz = Image.new("L", im.size, 0)  # göz akları (bebekler bunun içinde kalır)
    agiz = Image.new("L", im.size, 0)
    gd, ad = ImageDraw.Draw(goz), ImageDraw.Draw(agiz)
    bebekler = []
    for i, gx in enumerate((m - 7 + kx, m + 7 + kx)):
        gy = m - 1 + ky
        if kirp:
            gd.rounded_rectangle(s(gx - 4, gy - 0.5, gx + 4, gy + 1.5), radius=round(Q), fill=250)
            continue
        if ifade == "mutlu":  # ^ ^ gülen gözler
            gd.arc(s(gx - 4, gy - 2, gx + 4, gy + 6), 200, 340, fill=250, width=round(2.2 * Q))
            continue
        gen, ust, alt, br = {"saskin": (4.3, 6.8, 5.6, 1.7), "uykulu": (3.7, 0.2, 5, 2.1)}.get(ifade, (3.7, 5.6, 5, 2.2))
        gd.rounded_rectangle(s(gx - gen, gy - ust, gx + gen, gy + alt), radius=round(min(gen, (ust + alt) / 2) * Q),
                             fill=250)
        dis = -1 if i == 0 else 1  # gözün dış tarafı
        if ifade == "uzgun":  # dışa doğru düşen göz kapağı
            gd.polygon(s(gx - 6, gy - 9, gx + 6, gy - 9, *((gx + 6, gy - 1.5, gx - 6, gy - 5.5) if dis > 0
                                                          else (gx + 6, gy - 5.5, gx - 6, gy - 1.5))), fill=0)
        elif ifade == "kizgin":  # içe doğru inen göz kapağı: çatık kaş
            gd.polygon(s(gx - 6, gy - 9, gx + 6, gy - 9, *((gx + 6, gy - 5.5, gx - 6, gy - 0.5) if dis > 0
                                                          else (gx + 6, gy - 0.5, gx - 6, gy - 5.5))), fill=0)
        elif ifade in ("bikkin", "sirit", "suphe") or (ifade == "dusunceli" and dis > 0):  # düz inik göz kapağı
            kapak = {"bikkin": -1.2, "sirit": -2.6, "dusunceli": -2.0}.get(ifade, 0.3 if dis > 0 else -3.6)
            gd.rectangle(s(gx - 6, gy - 9, gx + 6, gy + kapak), fill=0)
        bebekler.append((gx + bx * 0.55, gy + 0.4 + by * 0.6, br))
    ax = m + kx
    if durum == "konusuyor":  # konuşurken sese göre açılıp kapanan ağız (halka: açıklık 0..1)
        ad.rounded_rectangle(s(ax - 4, m + 7 + ky, ax + 4, m + 8.5 + 3.5 * halka + ky), radius=round(1.5 * Q), fill=230)
    elif ifade == "mutlu":
        ad.arc(s(ax - 4.5, m + 3 + ky, ax + 4.5, m + 10 + ky), 25, 155, fill=230, width=round(1.7 * Q))
    elif ifade == "saskin":
        ad.ellipse(s(ax - 1.7, m + 7 + ky, ax + 1.7, m + 10.8 + ky), outline=230, width=round(1.3 * Q))
    elif ifade == "uzgun":
        ad.arc(s(ax - 3.8, m + 8.5 + ky, ax + 3.8, m + 14 + ky), 205, 335, fill=230, width=round(1.6 * Q))
    elif ifade == "kizgin":  # sıkılmış, aşağı kıvrık ağız
        ad.arc(s(ax - 4, m + 8.5 + ky, ax + 4, m + 12.5 + ky), 215, 325, fill=230, width=round(1.8 * Q))
    elif ifade == "bikkin":  # düz çizgi
        ad.line(s(ax - 3.2, m + 9 + ky, ax + 3.2, m + 9 + ky), fill=230, width=round(1.6 * Q))
    elif ifade == "suphe":  # yana kaymış, eğik çizgi
        ad.line(s(ax - 1, m + 9.6 + ky, ax + 4, m + 8.4 + ky), fill=230, width=round(1.6 * Q))
    elif ifade == "sirit":  # tek yana kıvrılan sırıtma
        ad.line(s(ax - 3.5, m + 9 + ky, ax, m + 9 + ky), fill=230, width=round(1.6 * Q))
        ad.arc(s(ax - 2, m + 3 + ky, ax + 4.5, m + 9.6 + ky), 0, 110, fill=230, width=round(1.6 * Q))
    isik = ImageChops.lighter(goz, agiz)
    im.alpha_composite(isima(isik, DINLE, 2 * Q, 1.4))  # göz ve ağzın renkli ışıması
    im.alpha_composite(isima(isik, (228, 244, 255), 0))
    if bebekler:  # koyu gözbebekleri + küçük parıltı; göz akının dışına taşmaz
        bm, pm = Image.new("L", im.size, 0), Image.new("L", im.size, 0)
        bd, pd = ImageDraw.Draw(bm), ImageDraw.Draw(pm)
        for px, py, br in bebekler:
            bd.ellipse(s(px - br, py - br, px + br, py + br), fill=255)
            pd.ellipse(s(px - br * 0.75, py - br * 0.8, px - br * 0.15, py - br * 0.2), fill=235)
        koyu = tuple(int(v * 0.25) for v in GOVDE)
        im.alpha_composite(isima(ImageChops.multiply(bm, goz), koyu, 0))
        im.alpha_composite(isima(ImageChops.multiply(pm, goz), (255, 255, 255), 0))
    if ifade == "kizgin":  # sağ üstte kırmızı sinir işareti
        sx, sy, e = m + 11, m - 15, 2.2
        for dx, dy, bas in ((-1, -1, 270), (1, -1, 0), (1, 1, 90), (-1, 1, 180)):
            c.arc(s(sx + dx * e - e, sy + dy * e - e, sx + dx * e + e, sy + dy * e + e), bas, bas + 90,
                  fill=(255, 92, 92, 255), width=round(1.3 * Q))
    return im.resize((kw(), kw()), Image.LANCZOS)


@functools.lru_cache(maxsize=16)
def kravat(govde, Q):
    """Göğüste beyaz yaka + çizgili kravat. Gövde kırmızımsıysa lacivert, değilse bordo."""
    m = KW / 2
    s = lambda *v: [n * Q for n in v]
    kirmizimsi = govde[0] > govde[2] + 40
    ana, koyu = ((28, 40, 96), (16, 24, 62)) if kirmizimsi else ((176, 28, 44), (118, 16, 30))
    im = Image.new("RGBA", (round(KW * Q), round(KW * Q)), (0, 0, 0, 0))
    c = ImageDraw.Draw(im)
    y = m + 14  # düğümün üstü: ağızdan uzak dursun, yaka diş gibi görünmesin
    for yon in (-1, 1):  # yaka uçları
        c.polygon(s(m + yon * 1.2, y + 0.4, m + yon * 7, y - 0.6, m + yon * 4.6, y + 4.6), fill=(232, 240, 252, 255))
    bicak = s(m - 2, y + 3.4, m + 2, y + 3.4, m + 4.4, y + 11.2, m, y + 15, m - 4.4, y + 11.2)
    c.polygon(bicak, fill=(*ana, 255))
    serit = Image.new("L", im.size, 0)  # çapraz çizgiler, yalnızca kravatın içinde
    sd = ImageDraw.Draw(serit)
    for k in range(-2, 6):
        sd.line(s(m - 6, y + 4 + k * 3.2, m + 6, y + 1 + k * 3.2), fill=255, width=max(1, round(0.9 * Q)))
    maske = Image.new("L", im.size, 0)
    ImageDraw.Draw(maske).polygon(bicak, fill=255)
    im.paste((*koyu, 255), mask=ImageChops.multiply(serit, maske))
    c.polygon(s(m - 3, y - 0.2, m + 3, y - 0.2, m + 2.1, y + 3.8, m - 2.1, y + 3.8), fill=(*koyu, 255))  # düğüm
    c.line(s(m - 1.6, y + 1.1, m + 0.6, y + 1.1), fill=(255, 255, 255, 110), width=max(1, round(0.7 * Q)))  # parıltı
    return im


KOLTUK_G, KOLTUK_Y = 96, 84  # 1x boyut; Kanzi'nin gövde merkezi koltukta (48, 38)'de oturur


def koltuk_boyutu():
    return round(KOLTUK_G * OLCEK), round(KOLTUK_Y * OLCEK)


@functools.lru_cache(maxsize=2)
def koltuk(olcek):
    """Kanzi'nin bordo kadife berjeri: kapitone sırtlık, minder, kollar, ahşap ayaklar, altında gölge."""
    Q = SS * olcek
    W, H = round(KOLTUK_G * Q), round(KOLTUK_Y * Q)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s = lambda *v: [n * Q for n in v]
    golge = Image.new("L", im.size, 0)
    ImageDraw.Draw(golge).ellipse(s(10, 74, 86, 83), fill=150)
    im.alpha_composite(isima(golge, (0, 0, 0), 3 * Q))
    c = ImageDraw.Draw(im)
    kadife, koyu, acik, ahsap = (128, 30, 44), (88, 18, 30), (160, 52, 66), (70, 42, 26)
    for x in (16, 74):  # ayaklar
        c.rounded_rectangle(s(x, 70, x + 6, 79), radius=round(1.5 * Q), fill=(*ahsap, 255))
    c.rounded_rectangle(s(14, 6, 82, 58), radius=round(16 * Q), fill=(*kadife, 255))  # sırtlık
    c.rounded_rectangle(s(17, 9, 79, 30), radius=round(13 * Q), fill=(*acik, 120))  # sırtlığın üst ışığı
    for bx, by in ((32, 22), (48, 18), (64, 22), (40, 34), (56, 34)):  # kapitone düğmeler
        c.ellipse(s(bx - 1.6, by - 1.6, bx + 1.6, by + 1.6), fill=(*koyu, 255))
    c.rounded_rectangle(s(18, 50, 78, 70), radius=round(7 * Q), fill=(*acik, 255))  # minder
    c.rounded_rectangle(s(18, 61, 78, 72), radius=round(6 * Q), fill=(*kadife, 255))  # minderin önü
    for x in (4, 74):  # kollar
        c.rounded_rectangle(s(x, 38, x + 18, 74), radius=round(8 * Q), fill=(*koyu, 255))
        c.rounded_rectangle(s(x + 2, 39, x + 16, 47), radius=round(6 * Q), fill=(*kadife, 255))
    return im.resize((round(KOLTUK_G * olcek), round(KOLTUK_Y * olcek)), Image.LANCZOS)


@functools.lru_cache(maxsize=1)
def ok_resmi():
    """'Buraya tıkla' oku: ucu (0,0)'da, parlak mavi, ışımalı."""
    W = 28
    im = Image.new("RGBA", (W * SS, W * SS), (0, 0, 0, 0))
    nokta = [(2 * SS, 2 * SS), (22 * SS, 9 * SS), (13 * SS, 13 * SS), (9 * SS, 22 * SS)]
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).polygon(nokta, fill=200)
    im.alpha_composite(isima(m, DINLE, 3 * SS))
    ImageDraw.Draw(im).polygon(nokta, fill=(*DINLE, 255), outline=(230, 248, 255, 255))
    return im.resize((W, W), Image.LANCZOS)


@functools.lru_cache(maxsize=4)
def yazi_tipi(boy, kalin=False):
    for ad in (("seguisb.ttf" if kalin else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(ad, boy)
        except OSError:
            pass
    return ImageFont.load_default()


def sar(metin, font, gen):
    """Metni piksel genişliğine göre satırlara böler (uzun kelimeyi de keser)."""
    satirlar = []
    for paragraf in metin.split("\n"):
        satir = ""
        for kelime in paragraf.split(" "):
            dene = f"{satir} {kelime}".strip()
            if font.getlength(dene) <= gen:
                satir = dene
                continue
            if satir:
                satirlar.append(satir)
            while font.getlength(kelime) > gen:  # tek kelime sığmıyorsa böl
                k = max(1, int(len(kelime) * gen / font.getlength(kelime)))
                satirlar.append(kelime[:k])
                kelime = kelime[k:]
            satir = kelime
        satirlar.append(satir)
    return satirlar


@functools.lru_cache(maxsize=16)
def baloncuk(metin, gen, boy, sol=False):
    """Buzlu koyu mavi cam baloncuk; küreye bakan kuyruk solda (sol=True: baloncuk kürenin solunda, kuyruk sağda).
    (resim, kuyruk ucunun y'si)."""
    font = yazi_tipi(boy)
    pad, kuyruk = int(boy * 0.85), 9
    satirlar = sar(metin, font, gen - 2 * pad - kuyruk)
    satir_y = int(boy * 1.4)
    tw = max(font.getlength(s_) for s_ in satirlar) if satirlar else 0
    w, h = int(tw + 2 * pad + kuyruk) + 1, len(satirlar) * satir_y + 2 * pad - int(boy * 0.25)
    golge = 10
    W, H = w + 2 * golge, h + 2 * golge
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    s = lambda *v: [n * SS for n in v]
    x0, y0, x1, y1 = (golge, golge, golge + w - kuyruk, golge + h) if sol else (golge + kuyruk, golge, golge + w, golge + h)
    ky = y0 + min(24 * OLCEK, h / 2)  # kuyruk küre hizasında
    sekil = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(sekil)
    d.rounded_rectangle(s(x0, y0, x1, y1), radius=14 * SS, fill=255)
    d.polygon(s(golge + w, ky, x1 - 1, ky - 7, x1 - 1, ky + 7) if sol else s(golge, ky, x0 + 1, ky - 7, x0 + 1, ky + 7),
              fill=255)
    # gölge: altta yumuşak koyu leke
    g = Image.new("RGBA", im.size, (2, 6, 18, 0))
    g.putalpha(sekil.point(lambda v: v * 120 // 255).filter(ImageFilter.GaussianBlur(5 * SS)))
    im.alpha_composite(g, (0, 3 * SS))
    # cam gövde: yukarıdan aşağı açıktan koyuya, yarı saydam
    yy = np.linspace(0, 1, im.height, dtype=np.float32)[:, None]
    ust, alt = np.array([30, 56, 104], np.float32), np.array([12, 26, 56], np.float32)
    renk = np.broadcast_to(ust * (1 - yy[..., None]) + alt * yy[..., None], (im.height, im.width, 3))
    maske = np.asarray(sekil, np.float32) / 255
    alfa = maske * (226 - 26 * yy)
    cam = Image.fromarray(np.dstack([renk, alfa]).clip(0, 255).astype(np.uint8), "RGBA")
    im.alpha_composite(cam)
    # kenar ışığı: üstte belirgin, altta sönük ince çizgi + üst iç parlama
    kenar = Image.new("RGBA", im.size, (0, 0, 0, 0))
    k = ImageDraw.Draw(kenar)
    k.rounded_rectangle(s(x0, y0, x1, y1), radius=14 * SS, outline=(150, 200, 255, 120), width=int(1.2 * SS))
    k.line(s(x0 + 14, y0 + 1.2, x1 - 14, y0 + 1.2), fill=(220, 238, 255, 110), width=SS)
    kenar_a = np.asarray(kenar).astype(np.float32)
    kenar_a[..., 3] *= np.clip(1.15 - yy * 1.0, 0.35, 1)
    im.alpha_composite(Image.fromarray(kenar_a.astype(np.uint8), "RGBA"))
    im = im.resize((W, H), Image.LANCZOS)
    c = ImageDraw.Draw(im)
    for i, satir in enumerate(satirlar):  # yazı 1x'te çizilir, keskin kalsın
        c.text((x0 + pad, y0 + pad - int(boy * 0.15) + i * satir_y), satir, font=font, fill=rgb(YAZI))
    return im, int(ky)


def kare(durum, kirp, bak, aci, halka, zip_, metin, gen, boy, ok, ifade="normal", sol=False):
    """Tek ekran karesi. ok: None ya da (alt, sag): okun ucu pencerenin o köşesinde, gösterilen noktada.
    sol: baloncuk kürenin solunda (koltuk ekranın sağ kenarındayken); küre resmin sağ ucunda durur."""
    kar = karakter(durum, kirp, bak, int(aci) // 15 * 15, round(halka, 1), ifade)
    oy = 6 if ok and not ok[0] else 0
    ay = 6 if ok and ok[0] else 0
    if metin:
        bal, ky = baloncuk(metin, gen, boy, sol)
        W, H = kw() + bal.width - 14, max(kw() + 8, bal.height) + oy + ay
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        im.alpha_composite(bal, (0 if sol else kw() - 14, max(0, oy + kw() // 2 - ky)))
    else:
        im = Image.new("RGBA", (kw() + 8, kw() + 8 + oy + ay), (0, 0, 0, 0))
    im.alpha_composite(kar, (im.width - kw() if sol and metin else 0, oy + 4 + int(round(zip_))))
    if ok:
        o = ok_resmi()
        if ok[0]:
            o = o.transpose(Image.FLIP_TOP_BOTTOM)
        if ok[1]:
            o = o.transpose(Image.FLIP_LEFT_RIGHT)
        im.alpha_composite(o, (im.width - o.width if ok[1] else 0, im.height - o.height if ok[0] else 0))
    return im


class _BMI(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("w", wt.LONG), ("h", wt.LONG), ("planes", wt.WORD), ("bits", wt.WORD),
                ("comp", wt.DWORD), ("isize", wt.DWORD), ("xp", wt.LONG), ("yp", wt.LONG), ("used", wt.DWORD),
                ("imp", wt.DWORD)]


_u32, _gdi = ctypes.windll.user32, ctypes.windll.gdi32
for _f in (_u32.GetDC, _gdi.CreateCompatibleDC, _gdi.CreateDIBSection, _gdi.SelectObject):
    _f.restype = ctypes.c_void_p
_gdi.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
                                  ctypes.c_void_p, wt.DWORD]
_gdi.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
_gdi.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_gdi.DeleteObject.argtypes = [ctypes.c_void_p]
_gdi.DeleteDC.argtypes = [ctypes.c_void_p]
_u32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_u32.UpdateLayeredWindow.argtypes = [ctypes.c_void_p] * 9


def katmana_bas(hwnd, im, x, y):
    """Piksel başına saydamlıkla pencereyi (x, y)'ye çizer; boyut resmin boyutu olur (Sesli Komut'tan)."""
    a = np.asarray(im).astype(np.uint16)
    a[..., :3] = a[..., :3] * a[..., 3:4] // 255  # Windows önceden çarpılmış BGRA ister
    veri = np.ascontiguousarray(a[..., [2, 1, 0, 3]].astype(np.uint8)).tobytes()
    w, h = im.size
    ekran = _u32.GetDC(None)
    dc = _gdi.CreateCompatibleDC(ekran)
    bmi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bitler = ctypes.c_void_p()
    bmp = _gdi.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bitler), None, 0)
    ctypes.memmove(bitler, veri, len(veri))
    eski = _gdi.SelectObject(dc, bmp)
    boyut, kaynak, hedef = wt.SIZE(w, h), wt.POINT(0, 0), wt.POINT(int(x), int(y))
    karisim = ctypes.c_uint32(0x01FF0000)  # AC_SRC_OVER, alfa 255, AC_SRC_ALPHA
    _u32.UpdateLayeredWindow(hwnd, ekran, ctypes.byref(hedef), ctypes.byref(boyut), dc, ctypes.byref(kaynak),
                             None, ctypes.byref(karisim), 2)  # ULW_ALPHA
    _gdi.SelectObject(dc, eski)
    _gdi.DeleteObject(bmp)
    _gdi.DeleteDC(dc)
    _u32.ReleaseDC(None, ekran)


def koyu_pencere(hwnd):
    """Windows 11: koyu başlık çubuğu, tema renginde başlık ve kenar, yuvarlak köşe. Eski Windows'ta sessizce geçer."""
    bgr = lambda h: int(h[5:7] + h[3:5] + h[1:3], 16)
    for ozellik, deger in ((20, 1), (33, 2), (34, bgr(CIZGI)), (35, bgr(ZEMIN)), (36, bgr(YAZI))):
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, ozellik, ctypes.byref(ctypes.c_int(deger)),
                                                       ctypes.sizeof(ctypes.c_int))
        except Exception:
            pass


def ikon_yap(yol_ico, yol_png):
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    k = karakter("bos", False, 0, 0, 0).resize((256, 256), Image.LANCZOS)
    im.alpha_composite(k)
    im.save(yol_ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)])
    im.save(yol_png)


def zip_hesapla(t):
    return math.sin(t * 2.6) * 2.5  # yavaş nefes alır gibi süzülme
