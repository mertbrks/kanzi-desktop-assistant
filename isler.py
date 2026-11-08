"""Kanzi'nin Claude'suz küçük işleri: hatırlatıcı, müzik tuşları, bilgisayar sesi ölçer, boşta kalma süresi."""
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import re
import tempfile
import time

user32 = ctypes.windll.user32

# ---------- Claude'un gördüğü ekran görüntüsü <-> gerçek ekran ----------
# Claude büyük görüntüyü kendisi küçültüyor (1920x1200 -> ~1356x848) ve küçük görüntünün pikseliyle cevap veriyordu:
# işaretler sola-yukarı kayıyordu. Görüntüyü biz küçültürüz, oranı dosyaya yazarız; tikla_yaz/ciz/HEDEF geri büyütür.
EKRAN_BILGI = os.path.join(tempfile.gettempdir(), "kanzi_v2_ekran.json")


def kucultme_orani(w, h):
    """Claude'un görüntüyü kendisi küçültmeyeceği oran (uzun kenar ≤1568, ≤1,15 MP)."""
    return min(1.0, 1568 / max(w, h), (1.15e6 / (w * h)) ** 0.5)


def goruntu_orani():
    """Son Claude ekran görüntüsünün oranı (gerçek piksel × oran = görüntü pikseli); bilgi yoksa 1."""
    try:
        with open(EKRAN_BILGI, encoding="utf-8") as f:
            return float(json.load(f)["oran"])
    except (OSError, ValueError, KeyError, TypeError):
        return 1.0


def gercek_nokta(x, y):
    """Claude'un verdiği görüntü pikseli -> gerçek ekran koordinatı (sanal ekranın sol-üstü eklenir)."""
    oran = goruntu_orani()
    return round(user32.GetSystemMetrics(76) + x / oran), round(user32.GetSystemMetrics(77) + y / oran)


# ---------- hatırlatıcı ----------
SAYI = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
        "on beş": 15, "yirmi": 20, "yirmi beş": 25, "otuz": 30, "kırk": 40, "kırk beş": 45, "elli": 50, "yarım": 0.5}
_SAYI = r"(\d+(?:[.,]\d+)?|" + "|".join(sorted(SAYI, key=len, reverse=True)) + ")"
BIRIM = {"sn": 1, "saniye": 1, "dk": 60, "dakika": 60, "saat": 3600}
_BIRIM = r"(saniye|sn|dakika|dk|saat)\w*"
SURE = re.compile(_SAYI + r"\s*" + _BIRIM + r"(\s+(sonra|içinde))?", re.I)
SAAT = re.compile(r"\bsaat\s+(\d{1,2})[:.](\d{2})(?:'?\s*(?:d[ae]|t[ae]))?|\b(\d{1,2})[:.](\d{2})'?\s*(?:d[ae]|t[ae])\b", re.I)
ZAMANLAYICI = re.compile(r"(zamanlayıcı|sayaç|alarm|pomodoro|odak|geri\s+sayım)", re.I)
HATIRLAT = re.compile(r"hatırlat|haber\s+ver|söyle\s+bana|uyar|seslen", re.I)
LISTE = re.compile(r"^(hatırlatma\w*|zamanlayıcı\w*|alarm\w*)\s+(göster|listele|neler|ne\s+var|var\s+mı)", re.I)
SIL = re.compile(r"^(hatırlatma\w*|zamanlayıcı\w*|alarm\w*)\s+(iptal|sil|kaldır|temizle|kapat)", re.I)
_DOLGU = re.compile(r"\b(bana|beni|lütfen|kanka|kanzi|hadi|bir|bi|olarak|sonra|içinde|ve|da|de|kur|başlat|"
                    r"hatırlat\w*|haber\s+ver\w*|söyle\s+bana|uyar\w*|seslen\w*|mısın|misin|musun|müsün|"
                    r"zamanlayıcı\w*|sayaç\w*|alarm\w*|geri\s+sayım\w*)\b", re.I)


def _sayi(s):
    return SAYI[s.lower()] if s.lower() in SAYI else float(s.replace(",", "."))


def hatirlatma(metin, simdi=None):
    """'20 dakika sonra çamaşırı hatırlat' -> (saniye, mesaj); 'hatırlatmaları göster' -> ('liste', '');
    'hatırlatmaları iptal et' -> ('sil', ''); hatırlatma değilse None."""
    m = metin.strip().rstrip(".!?")
    if LISTE.search(m):
        return "liste", ""
    if SIL.search(m):
        return "sil", ""
    if not (HATIRLAT.search(m) or ZAMANLAYICI.search(m)):
        return None
    sure = SURE.search(m)
    saat = SAAT.search(m)
    if sure:
        saniye = _sayi(sure.group(1)) * BIRIM[next(b for b in BIRIM if sure.group(2).lower().startswith(b))]
        kalan = m[:sure.start()] + " " + m[sure.end():]
    elif saat:
        s, d = int(saat.group(1) or saat.group(3)), int(saat.group(2) or saat.group(4))
        if s > 23 or d > 59:
            return None
        simdi = simdi or datetime.datetime.now()
        hedef = simdi.replace(hour=s, minute=d, second=0, microsecond=0)
        if hedef <= simdi:
            hedef += datetime.timedelta(days=1)
        saniye = (hedef - simdi).total_seconds()
        kalan = m[:saat.start()] + " " + m[saat.end():]
    else:
        return None
    if not 0 < saniye <= 7 * 86400:
        return None
    mesaj = re.sub(r"\s+", " ", _DOLGU.sub(" ", re.sub(r"\b\w*lık\b|\b\w*lik\b", " ", kalan))).strip(" ,:;-'")
    if ZAMANLAYICI.search(m) and re.search(r"odak|pomodoro", m, re.I):
        mesaj = "Odak süresi bitti, biraz mola ver."
    return saniye, mesaj


def sure_yazi(saniye):
    saniye = int(round(saniye))
    if saniye < 60:
        return f"{saniye} saniye"
    if saniye < 3600:
        return f"{round(saniye / 60)} dakika"
    s, d = divmod(round(saniye / 60), 60)
    return f"{s} saat" + (f" {d} dakika" if d else "")


def turkce_mi(metin):
    # re.I kullanılmaz: o zaman "ı" İngilizcedeki "i"yi de tutuyor
    return bool(re.search(r"[çğıöşüÇĞÖŞÜİ]|\b([Vv]e|[Bb]ir|[Bb]u|için|ile|ama|değil|çok|ne|nasıl)\b", metin))


# ---------- müzik ----------
MEDYA = (("sonraki", 0xB0, 1, r"(şarkı\w*|müzi\w*|parça\w*)\s+(geç|atla|değiştir)|sonraki\s+(şarkı|parça)|"
                              r"sıradaki\s+(şarkı|parça)"),
         ("önceki", 0xB1, 1, r"önceki\s+(şarkı|parça)|(şarkı\w*|parça\w*)\s+(geri\s+al|başa\s+sar)"),
         ("oynat", 0xB3, 1, r"(şarkı\w*|müzi\w*|parça\w*)\s+(durdur|duraklat|devam|başlat|aç|oynat|kapat)|"
                            r"^duraklat"),
         ("sessiz", 0xAD, 1, r"^ses\w*\s+(kapat|sustur)|^sessize\s+al"),
         ("kıs", 0xAE, 5, r"^ses\w*\s+(kıs|azalt|düşür)"),
         ("aç", 0xAF, 5, r"^ses\w*\s+(aç|yükselt|artır|arttır)"))
CEVAP = {"sonraki": "Geçtim.", "önceki": "Bir önceki.", "oynat": "Tamam.", "sessiz": "Sustu.",
         "kıs": "Kıstım.", "aç": "Açtım."}


def medya_komutu(metin):
    """Kısa müzik/ses komutu -> (ad, sanal tuş, kaç kez) ya da None."""
    m = re.sub(r"[^\w\s]", "", metin.strip().lower())
    m = re.sub(r"^(kanzi|kanka|hadi)\s+", "", m)
    if len(m) > 30:
        return None
    return next(((ad, tus, kez) for ad, tus, kez, desen in MEDYA if re.search(desen, m)), None)


def tusa_bas(tus, kez=1):
    for _ in range(kez):
        user32.keybd_event(tus, 0, 1, 0)  # KEYEVENTF_EXTENDEDKEY
        user32.keybd_event(tus, 0, 3, 0)  # + KEYUP


SABAH = re.compile(r"^(?:(?:kanzi|kanka)[\s,]+)?(günaydın(\s+(kanka|kanzi))?\W*$|bugün\s+(ne(ler)?\s+var|program\w*|takvim\w*)|"
                   r"sabah\s+özet\w*|günün\s+özet\w*)")
PANO = re.compile(r"^(?:(?:kanzi|kanka)\s+)?(pano\w*\s+(geçmiş\w*|göster|aç)|kopyaladık\w*\s+(göster|listele|neler)|"
                  r"son\s+kopyaladık\w*|pano\s+geçmişi)")


def pano_gecmisi():
    """Win+V: Windows'un pano geçmişi açılır; seçilen, odaktaki kutuya yapıştırılır."""
    for v, f in ((0x5B, 0), (0x56, 0), (0x56, 2), (0x5B, 2)):
        user32.keybd_event(v, 0, f, 0)


# ---------- öğrendiklerim: Mert'in kalıcı tercihleri ----------
OGREN = re.compile(r"^(?:(?:kanzi|kanka)[\s,]+)?(?:bunu\s+)?(?:unutma|aklında\s+(?:tut|olsun)|şunu\s+bil)\s*[:,]?\s*(.+)$",
                   re.I | re.S)
BUNDAN_SONRA = re.compile(r"^(?:(?:kanzi|kanka)[\s,]+)?((?:bundan\s+(?:sonra|böyle))\s.+)$", re.I | re.S)
OGRENDIKLERIN = re.compile(r"^(?:(?:kanzi|kanka)[\s,]+)?(?:ne(?:ler)?\s+(?:biliyorsun|öğrendin)|aklında\s+ne(?:ler)?\s+var|"
                           r"öğrendikler\w*\s+(?:göster|neler|listele|oku))", re.I)


def ogrenme_komutu(metin):
    """'unutma: kahveyi şekersiz içerim' / 'bundan sonra kısa cevap ver' -> ('ekle', not);
    'neler biliyorsun' -> ('liste', ''); değilse None. 'bundan sonra …' yalnız kısa cümlede sayılır."""
    m = metin.strip().rstrip(".!")
    if OGRENDIKLERIN.match(m):
        return "liste", ""
    o = OGREN.match(m) or (len(m) < 90 and BUNDAN_SONRA.match(m))
    return ("ekle", o.group(1).strip()) if o and o.group(1).strip() else None


def ogrendiklerim(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return [s.strip() for s in f if s.strip()]
    except OSError:
        return []


def ogrendiklerim_metni(yol, sinir=1500):
    """Sistem istemine eklenecek blok; boşsa ''. En yeni notlar önce sığdırılır."""
    notlar, secilen, boy = ogrendiklerim(yol), [], 0
    for n in reversed(notlar):
        if boy + len(n) > sinir:
            break
        secilen.insert(0, n)
        boy += len(n) + 3
    if not secilen:
        return ""
    return ("\nMert'in sana öğrettikleri (kalıcı tercihleri ve bilgileri; bunlara uy):\n"
            + "\n".join(f"- {n}" for n in secilen))


# ---------- dikte: söyleneni aynen yaz ----------
DIKTE = re.compile(r"^(?:(?:kanzi|kanka)[\s,]+)?(?:(?:aynen|olduğu\s+gibi)\s+yaz|dikte(?:\s+et)?|yaz)\s*[:,]\s*(.+)$",
                   re.I | re.S)
_DIKTE_SADE = re.compile(r"^(?:(?:kanzi|kanka)[\s,]+)?(?:aynen|olduğu\s+gibi)\s+yaz\s+(.+)$", re.I | re.S)


def dikte_komutu(metin):
    """'yaz: yarın görüşürüz' / 'aynen yaz yarın görüşürüz' -> yazılacak metin; değilse None.
    Düz 'yaz' iki nokta/virgülsüz sayılmaz: 'yaz bakalım bir şiir' Claude'a gitsin."""
    m = DIKTE.match(metin.strip()) or _DIKTE_SADE.match(metin.strip())
    return m.group(1).strip() if m and m.group(1).strip() else None


class _KI(ctypes.Structure):
    _fields_ = [("vk", wt.WORD), ("scan", wt.WORD), ("flags", wt.DWORD), ("time", wt.DWORD),
                ("extra", ctypes.c_void_p)]


class _GIRDI(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("ki", _KI), ("pad", ctypes.c_byte * 8)]


def klavyeye_yaz(metin):
    """Odaktaki kutuya harf harf yazar (Unicode: Türkçe harfler sorunsuz). Satır sonu boşluk olur: Enter gönderebilir."""
    for v in (0x10, 0x11, 0x12, 0x5B):  # kısayoldan basılı kalmış Shift/Ctrl/Alt/Win bırakılsın
        user32.keybd_event(v, 0, 2, 0)
    for ch in re.sub(r"\s*\n\s*", " ", metin):
        b = ch.encode("utf-16-le")  # emoji gibi iki parçalı harfler iki kod olarak gider
        for kod in (int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)):
            for bayrak in (4, 6):  # KEYEVENTF_UNICODE, + KEYUP
                g = _GIRDI(1, _KI(0, kod, bayrak, 0, None))
                user32.SendInput(1, ctypes.byref(g), ctypes.sizeof(g))
        time.sleep(0.004)


def one_getir(hwnd):
    """Pencereyi öne alır. Kanzi'nin kendi kutusu/penceresi öndeyken çağrılır, Windows buna izin verir."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


# ---------- bilgisayar sesi (dans için) ----------
class SesOlcer:
    """Hoparlöre giden sesin anlık tepe değeri (0..1). Ek paket yok: Core Audio IAudioMeterInformation, ctypes ile.
    Aynı iş parçacığında oluşturulup kullanılmalı (COM)."""
    def __init__(self):
        ole = ctypes.windll.ole32
        ole.CoInitialize(None)
        guid = lambda s: (ctypes.c_byte * 16).from_buffer_copy(_guid(s))
        self.ole, enum, cihaz, self.olcer = ole, ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        hr = ole.CoCreateInstance(guid("BCDE0395-E52F-467C-8E3D-C4579291692E"), None, 23,
                                  guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), ctypes.byref(enum))
        if hr:
            raise OSError(f"MMDeviceEnumerator {hr:#x}")
        # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia)
        if self._cagir(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)(enum, 0, 1, ctypes.byref(cihaz)):
            raise OSError("hoparlör yok")
        # IMMDevice::Activate(IID_IAudioMeterInformation, CLSCTX_ALL)
        if self._cagir(cihaz, 3, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)(
                cihaz, guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), 23, None, ctypes.byref(self.olcer)):
            raise OSError("ses ölçer açılamadı")
        self._tepe = self._cagir(self.olcer, 3, ctypes.POINTER(ctypes.c_float))

    @staticmethod
    def _cagir(nesne, sira, *argumanlar):
        vtablo = ctypes.cast(nesne, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argumanlar)(vtablo[sira])

    def tepe(self):
        v = ctypes.c_float()
        return 0.0 if self._tepe(self.olcer, ctypes.byref(v)) else v.value


def _guid(s):
    import uuid
    return uuid.UUID(s).bytes_le


# ---------- boşta kalma ----------
class _LII(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def bosta_saniye():
    """Klavye ya da fareye en son dokunulandan beri geçen saniye."""
    lii = _LII(ctypes.sizeof(_LII), 0)
    user32.GetLastInputInfo(ctypes.byref(lii))
    return ((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000
