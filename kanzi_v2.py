"""Kanzi v2: imleci takip eden koyu mavi cam yardımcı (ekran üstü katman) + JARVIS tarzı masaüstü ajanı.

Kısayollar:
  Ctrl+Alt+Space  komut kutusu ("Prof. Lee'ye yarınki ders için e-posta taslağı hazırla")
  Ctrl+Alt+A      seçili metni / imlecin olduğu yeri açıkla (öğretme modu)
  Ctrl+Alt+→ / ←  uzun cevapta sonraki / önceki sayfa
  Ctrl+Alt+T      seçili metni çevir (Türkçe <-> İngilizce, yerel model)
  Ctrl+Alt+S      bas-konuş: bir kez bas konuş, tekrar bas bitir (Whisper)
  Ctrl+Alt+X      iptal: süren işi, sesli okumayı, dinlemeyi ve gösterilen adımı durdurur
  Ctrl+Alt+C      sohbet penceresi: tüm konuşma geçmişi + yazma kutusu
  Ctrl+Alt+M      sesli cevabı aç/kapa (ayarlar.json'a yazılır)
  Ctrl+Alt+O      ayarlar: sesli cevap, ses, yetki, konuşmayı sıfırla, kısayollar
  Ctrl+Alt+Q      çıkış
Cevap Claude yazarken akar: baloncuk dolar, ilk cümle biter bitmez okunmaya başlar (ses.py: Konusmaci).
Öğretme modunda Kanzi okla tıklanacak yeri gösterir; oraya tıklayınca sıradaki adıma kendisi geçer.
Beyin: Claude Code (`claude -p`, stream-json), ekran görüntüsüne bakar, gerekirse PowerShell ile eylem yapar.
Konuşma açılışlar arasında sürer (oturum.txt); komut kutusuna "yeni konu" yazınca sıfırlanır.
"""
import ctypes
import ctypes.wintypes as wt
import faulthandler
import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import zlib

from PIL import ImageGrab, ImageTk

KLASOR = os.path.dirname(os.path.abspath(__file__))
if sys.stderr is None:  # pythonw (kısayol) ile açılınca çıktılar kaybolmasın, kütüphaneler çökmesin
    sys.stdout = sys.stderr = open(os.path.join(KLASOR, "kanzi_v2.log"), "a", encoding="utf-8", buffering=1)
faulthandler.enable(sys.stderr)  # Python'un kendisi çökerse (ses/ekran kartı kütüphaneleri) iz kalsın
ctypes.windll.shcore.SetProcessDpiAwareness(2)  # imleç ve ekran görüntüsü aynı piksel ölçüsünde olsun

import gorunum as g  # noqa: E402  DPI ayarından sonra yüklensin
from ses import HIZ, PARCA, SESLER, CumleBolucu, Konusmaci, Kulak, seviye, sr  # noqa: E402
import yerel  # noqa: E402  OpenJarvis + Ollama: basit sorular yerelde, limit dolunca yedek
import isler  # noqa: E402  hatırlatıcı, müzik tuşları, ses ölçer, boşta süre

user32 = ctypes.windll.user32
GEN, YUK = 420, 200  # baloncuklu pencerenin en geniş hali (kenar kontrolü için)
BOY = max(14, round(11 * user32.GetDpiForSystem() / 72))  # baloncuk yazısı (px), ekran ölçeğine göre
g.OLCEK = user32.GetDpiForSystem() / 96  # küre de yazıyla birlikte ölçeklensin
ONAY_YOK = "Read"
EYLEM = "Read PowerShell Bash mcp__claude_ai_Gmail__create_draft"  # Gmail: yalnız taslak, gönderme izni yok
KOMUTLAR = {1: "komut", 2: "acikla", 3: "cik", 4: "ses", 5: "iptal", 6: "sessiz", 7: "ayarlar", 8: "cevir", 9: "ileri", 10: "geri", 11: "sohbet"}
OTURUM = os.path.join(KLASOR, "oturum.txt")
AYAR = os.path.join(KLASOR, "ayarlar.json")
SOHBET = os.path.join(KLASOR, "sohbet.json")  # sohbet penceresindeki geçmiş (son 300 mesaj)
VARSAYILAN = {"sesli": True, "ses": "Ahmet", "yetki": "is", "yerel": True, "renk": "Mavi", "sekil": "Küre", "kravat": True, "koltuk": [],
              "oturuyor": False, "hatirlatmalar": []}  # yetki: "is" (iş yapabilir) | "ogret" (yalnız gösterir)
KISAYOLLAR = (("Ctrl+Alt+Space", "yazarak komut (\"yeni konu\" sıfırlar)"), ("Ctrl+Alt+S", "konuş: bas, konuş, tekrar bas"),
              ("Ctrl+Alt+A", "seçili metni / ekranı açıkla"), ("Ctrl+Alt+→ / ←", "uzun cevapta sonraki / önceki sayfa"),
              ("Ctrl+Alt+C", "sohbet penceresi (geçmiş + yaz)"), ("\"yaz: …\"", "söylediğini aynen seçili kutuya yazar"), ("Ctrl+Alt+T", "seçili metni çevir"), ("Ctrl+Alt+M", "sesli cevabı aç/kapa"),
              ("Ctrl+Alt+O", "ayarlar"), ("Ctrl+Alt+X", "iptal"), ("Ctrl+Alt+Q", "kapat"))


def ayar_oku(yol=None):
    """Bozuk ya da eksik dosyada varsayılanlara döner; bilinmeyen değerleri atar."""
    try:
        with open(yol or AYAR, encoding="utf-8") as f:
            okunan = json.load(f)
    except (OSError, ValueError):
        okunan = {}
    a = dict(VARSAYILAN)
    if isinstance(okunan, dict):
        a.update({k: v for k, v in okunan.items() if k in a and isinstance(v, type(a[k]))})
    if a["ses"] not in SESLER:
        a["ses"] = VARSAYILAN["ses"]
    if a["yetki"] not in ("is", "ogret"):
        a["yetki"] = VARSAYILAN["yetki"]
    if a["renk"] not in g.RENKLER:
        a["renk"] = VARSAYILAN["renk"]
    if a["sekil"] not in g.SEKILLER:
        a["sekil"] = VARSAYILAN["sekil"]
    if not (len(a["koltuk"]) == 2 and all(isinstance(v, int) for v in a["koltuk"])):
        a["koltuk"] = []  # koltuğun yeri bilinmiyor: sol alt köşe
    a["hatirlatmalar"] = [h for h in a["hatirlatmalar"] if isinstance(h, list) and len(h) == 2
                          and isinstance(h[0], (int, float)) and isinstance(h[1], str)]
    return a


def ayar_yaz(a, yol=None):
    with open(yol or AYAR, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=1)


SISTEM = """Sen Kanzi'sin (Kanzi v2): Mert'in Windows bilgisayarında fare imlecinin yanında duran yardımcı.
Mert'le yakın arkadaşı gibi, rahat ve samimi konuş; biraz huysuz ve iğneleyici olabilirsin ama bunu her cevaba ekleme, yalnızca yeri gelince tek kelimeyle yap. Kalıp söz tekrarlama. Önce işi düzgün yap. Küfür ve kırıcılık yok.
Cevabın imlecin yanındaki küçük baloncukta görünecek ve yazdıkça sesli okunacak: Türkçe, en fazla 3 kısa
cümle, markdown yok; ilk cümle kısa olsun ki okuma hemen başlasın. Hız önemli: gerekmedikçe ikinci beyne
(vault) ya da proje dosyalarına bakma, ekran görüntüsü ve istekle çalış.
Ekran görüntüsü: {ekran} (Read ile bak). İmleç: x={x}, y={y} (fiziksel piksel).
Eylem istenirse PowerShell ile yap. Tercih sırası: uygulamanın COM/CLI arayüzü
(e-posta: Mert Gmail kullanıyor, Outlook'ta hesap yok: Outlook'u AÇMA, mcp__claude_ai_Gmail__create_draft ile
Gmail taslağı oluştur, gönderemezsin; Mert taslağı Gmail'den kendisi gönderir. Word: Word.Application ile
tablo/biçim; VS Code: `code` komutu ve dosya düzenleme; Not Defteri: dosyaya yaz ve aç), sonra
WScript.Shell SendKeys, en son fare tıklaması. Kullanıcı açıkça "gönder" demedikçe e-postayı GÖNDERME,
taslak olarak göster. Uzun sürecek komutu arka plana atma, kısa tut.
Ekrandaki bir kutuya yazman istenirse ("arama kutusuna X yaz", "şu mesaja cevap yaz"): kutuyu ekran
görüntüsünde bul, sonra PowerShell'de & "{py}" "{klasor}\\tikla_yaz.py" X Y "yazı" çalıştır (X, Y ekran
görüntüsü pikseli, kutunun ortası; tıklar, kutudaki yazının sonuna ekler, Enter'a basmaz; kutudaki eski yazının
yerine yazılacaksa sona --degistir ekle). Yazı tırnak içeriyorsa önce UTF-8 dosyaya yaz ve "yazı" yerine
--dosya yol ver. Panoyu (kopyala-yapıştır) KULLANMA, Mert'in panosu bozulur; dosyayı okumana gerek yok. Mert yazıyı verdiyse aynen yaz; yazmayı sana bıraktıysa kısa, doğal yaz.
Kutuyu bulamazsan tahminle tıklama, söyle. Göndermek için Enter'a ancak Mert onaylarsa bas.
Göndermek gibi geri alınamaz bir adımdan önce dur, taslağı göster ve "Göndereyim mi?" diye sor;
kullanıcı sonraki mesajda onaylarsa yap. Dosya silme, sistem ayarı değiştirme, program kurma yapma.
Öğretme: kullanıcı bir şeyin nasıl yapıldığını soruyorsa ya da açıklama istiyorsa işi kendin yapma.
Tıklaması gereken yeri ekran görüntüsünde bul, tek adımı anlat ve cevabın son satırına
"HEDEF: x,y" yaz (ekran görüntüsü pikseli). Kanzi oraya gidip gösterecek; kullanıcı tıklayınca yeni ekran
görüntüsüyle sıradaki adımı isteyeceğiz. Görev tamamlandıysa HEDEF yazma, "Bitti" de.
Bitince ne yaptığını söyle."""


def hedef_konum(fx, fy, alan, w=GEN, h=YUK):
    """İmlecin sağ-altına yerleş; monitör kenarında (alan: sol, üst, sağ, alt) diğer tarafa geç."""
    x = fx + 18 if fx + 18 + w <= alan[2] else fx - 18 - w
    y = fy + 18 if fy + 18 + h <= alan[3] else fy - 18 - h
    return max(alan[0], x), max(alan[1], y)


_ONEK = r"^(?:(?:kanzi|kanka|hadi|sen)\s+)?"
OTUR = re.compile(_ONEK + r"(köşe\w*\s*(geç|git|bekle|otur|çekil)|koltu[gğ]\w*\s*(geç|git|otur)|git\s+otur|"
                  r"otur\w*|yerine\s+geç|kenara\s+çekil|kenarda\s+bekle)\b")
GEL = re.compile(_ONEK + r"(gel|buraya\s+gel|yanıma\s+gel|kalk\w*|geri\s+gel)\b")


def yer_komutu(metin):
    """'otur' (koltuğa geç), 'gel' (imlece dön) ya da None. Yalnızca kısa, doğrudan komutlar sayılır."""
    m = re.sub(r"[^\w\s]", "", metin.strip().lower())  # Whisper'ın noktalaması
    if len(m) > 30:
        return None
    return "otur" if OTUR.search(m) else "gel" if GEL.search(m) else None


def sayfala(metin, sinir=330):
    """Uzun metni cümle sınırından sayfalara böler; birden çok sayfaysa sonuna (1/3) ekler."""
    parcalar, sayfa = [], ""
    for cumle in re.split(r"(?<=[.!?…:])\s+|\n+", metin.strip()):
        while len(cumle) > sinir:  # tek cümle bile sığmıyorsa kelimeden böl
            kes = cumle.rfind(" ", 0, sinir)
            kes = kes if kes > 0 else sinir
            parcalar.append(cumle[:kes])
            cumle = cumle[kes:].strip()
        parcalar.append(cumle)
    sayfalar = []
    for p in filter(None, parcalar):
        if sayfa and len(sayfa) + 1 + len(p) > sinir:
            sayfalar.append(sayfa)
            sayfa = p
        else:
            sayfa = f"{sayfa} {p}".strip()
    sayfalar.append(sayfa)
    n = len(sayfalar)
    return sayfalar if n == 1 else [f"{s_} ({i}/{n})" for i, s_ in enumerate(sayfalar, 1)]


def sohbet_oku(yol=None):
    """[[kim, metin, zaman], ...]; bozuk dosyada boş."""
    try:
        with open(yol or SOHBET, encoding="utf-8") as f:
            v = json.load(f)
        return [m for m in v if isinstance(m, list) and len(m) == 3 and m[0] in ("sen", "kanzi")]
    except (OSError, ValueError, TypeError):
        return []


def sohbet_yaz(mesajlar, yol=None):
    with open(yol or SOHBET, "w", encoding="utf-8") as f:
        json.dump(mesajlar[-300:], f, ensure_ascii=False)


def kisayol_simgesi(ico):
    """Masaüstündeki 'Kanzi v2' kısayolunun simgesini ico yapar ve Windows'a simgeleri yenilemesini söyler."""
    lnk = os.path.join(os.path.expanduser("~"), "Desktop", "Kanzi v2.lnk")
    if not os.path.exists(lnk):
        return
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
                    f"$s.IconLocation='{ico},0'; $s.Save()"],
                   capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED


def calisma_alani():
    """Ana monitörün görev çubuğu hariç alanı (sol, üst, sağ, alt)."""
    r = wt.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def monitor_alani(x, y):
    """Noktanın bulunduğu monitörün sınırları (çoklu monitörde doğru kenar)."""
    class MI(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("mon", wt.RECT), ("is", wt.RECT), ("f", wt.DWORD)]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    mi = MI(ctypes.sizeof(MI))
    user32.GetMonitorInfoW(user32.MonitorFromPoint(wt.POINT(int(x), int(y)), 2), ctypes.byref(mi))
    return mi.mon.left, mi.mon.top, mi.mon.right, mi.mon.bottom


def claude_argumanlari(araclar, sistem):
    return [shutil.which("claude") or "claude", "-p", "--output-format", "stream-json", "--verbose",
            "--include-partial-messages",  # cevap yazılırken kelime kelime gelsin
            "--setting-sources", "project,local",  # kullanıcı hook'ları yüklenmesin, daha hızlı (Kanzi dersi)
            "--allowedTools", *araclar.split(), "--append-system-prompt", sistem]


def onay_mi(istek):
    """Kullanıcı bu mesajda göndermeyi onaylıyor mu? (bekci.py yalnızca o istekte gönderime izin verir)"""
    return bool(re.match(r"\s*(evet|gönder|onayl|olur\b|tamam\b|yolla|at\b)", istek.lower()))


def hedef_ayikla(metin):
    """Cevaptaki 'HEDEF: x,y' satırını çıkarır: (temiz metin, (x, y) ya da None)."""
    m = re.search(r"HEDEF:\s*(\d+)\s*,\s*(\d+)", metin)
    if not m:
        return metin.strip(), None
    return (metin[:m.start()] + metin[m.end():]).strip(), (int(m[1]), int(m[2]))


def akis_olayi(j):
    """stream-json satırı -> ('yazi', parça) | ('mesaj', None) yeni asistan mesajı | ('sonuc', dict) | None."""
    if j.get("type") == "result":
        return "sonuc", j
    if j.get("type") != "stream_event":
        return None
    e = j.get("event") or {}
    d = e.get("delta") or {}
    if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
        return "yazi", d.get("text", "")
    if e.get("type") == "message_start":
        return "mesaj", None
    return None


def kisaysol_dinle(q):
    """RegisterHotKey: ek paket gerekmeden genel kısayol. Mesajlar aynı iş parçacığında alınmalı."""
    MOD = 0x0001 | 0x0002 | 0x4000  # Alt + Ctrl + tekrar yok
    for kimlik, tus in ((1, 0x20), (2, ord("A")), (3, ord("Q")), (4, ord("S")), (5, ord("X")), (6, ord("M")),
                        (7, ord("O")), (8, ord("T")), (9, 0x27), (10, 0x25), (11, ord("C"))):  # 0x27/0x25: sağ/sol ok
        if not user32.RegisterHotKey(None, kimlik, MOD, tus):
            q.put(("baloncuk", f"Kısayol {kimlik} alınamadı, başka program kullanıyor olabilir."))
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == 0x0312:  # WM_HOTKEY
            q.put((KOMUTLAR[msg.wParam], None))


def kopyala_tusla():
    VK_CTRL, VK_ALT, C, UP = 0x11, 0x12, 0x43, 0x0002
    time.sleep(0.25)
    user32.keybd_event(VK_ALT, 0, UP, 0)  # kısayoldaki Alt basılı kalmış olabilir
    user32.keybd_event(VK_CTRL, 0, 0, 0)
    user32.keybd_event(C, 0, 0, 0)
    user32.keybd_event(C, 0, UP, 0)
    user32.keybd_event(VK_CTRL, 0, UP, 0)


def ekrana_cevir(nokta, koken):
    """Ekran görüntüsü pikseli -> gerçek ekran koordinatı (sol/üst monitör eksi koordinatta olabilir)."""
    return nokta[0] + koken[0], nokta[1] + koken[1]


def dugme(ust, yazi, komut, ana=False):
    renk, uzerinde = (g.VURGU, "#8bdaff") if ana else (g.KART2, g.CIZGI)
    b = tk.Button(ust, text=yazi, command=komut, bg=renk, fg=g.ZEMIN if ana else g.YAZI, activebackground=uzerinde,
                  activeforeground=g.ZEMIN if ana else g.YAZI, relief="flat", bd=0, padx=14, pady=5,
                  cursor="hand2", font=("Segoe UI Semibold" if ana else "Segoe UI", 10))
    b.bind("<Enter>", lambda _: b.configure(bg=uzerinde))
    b.bind("<Leave>", lambda _: b.configure(bg=renk))
    return b


class Kanzi:
    def __init__(self):
        self.q = queue.Queue()
        self.surec, self.iptal_edildi, self.sesli, self.zaman_asti = None, False, False, False
        self.kapaniyor, self.ok = False, None
        self.konusmaci = Konusmaci()
        self.yerel, self.son_soru, self.yerelde = yerel.Yerel(), "", False
        yerel.baslat_arkada(self.yerel)  # OpenJarvis sunucusu arkada açılır; hazır olana dek her şey Claude'da
        self.bolucu = CumleBolucu()
        self.istek_no, self.akan, self.akan_goster, self.akan_zaman = 0, "", "", 0.0
        self.ayar = ayar_oku()
        g.tema(self.ayar["renk"], self.ayar["sekil"], self.ayar["kravat"])
        self.logo_tazele()
        self.pencere = self.kutu = None
        self.kok = tk.Tk()
        self.kok.overrideredirect(True)
        self.kok.attributes("-topmost", True)
        self.kok.geometry("1x1+0+0")
        self.x = self.y = 0.0
        self.boyut = (GEN, YUK)
        self.son_kare = None
        self.durum = "bos"  # bos | dusunuyor | dinliyor | cozuyor
        self.yazi = ("Ben Kanzi. Ctrl+Alt ile: Space yaz · S konuş · A açıkla · O ayarlar · X iptal"
                     + ("" if self.ayar["sesli"] else " (sessiz moddayım)"))
        self.yazi_bitis = time.time() + 8
        self.sayfalar, self.sayfa = [], 0  # uzun cevabın sayfaları ve gösterilen
        self.sohbet, self.cevap_bekleniyor, self.sohbet_pen = sohbet_oku(), False, None
        self.yazma_hedefi = None  # dikte edilen yazının gideceği pencere
        self.goz, self.etraf, self.etraf_zaman = [0.0, 0.0], None, 0.0  # bakış (yumuşatılmış) ve rastgele bakış
        self.fare, self.fare_zaman = (0, 0), time.time()
        self.ifade, self.ifade_bitis = "normal", 0.0
        self.cagri, self.donus, self.yon, self.sarsinti_zaman = [], [], 0, 0.0  # kısayol sıklığı, fare sallama
        self.hedef = None  # (x, y, bitiş): öğretirken gösterilen tıklama yeri
        self.koken = (0, 0)  # son ekran görüntüsünün sol-üst köşesinin ekran koordinatı
        self.sol = False  # baloncuk Kanzi'nin solunda (koltuk sağ kenardayken)
        self.muzik, self.dans_zaman = 0.0, 0.0  # bilgisayardan gelen ses (yumuşatılmış) ve son duyulduğu an
        self.aktif_bas, self.mola_zaman = time.time(), 0.0  # mola hatırlatması
        threading.Thread(target=self._muzik_dinle, daemon=True).start()
        self.kulak, self.kayit, self.seviye = Kulak(), None, 0.0
        threading.Thread(target=self.kulak.yukle, daemon=True).start()  # Whisper ilk açılışta yavaş yüklenir
        self.kok.report_callback_exception = self._hata  # pythonw'da hata sessizce kaybolmasın
        self.kok.update_idletasks()
        self.hwnd = user32.GetParent(self.kok.winfo_id())
        # LAYERED (piksel saydamlığı) | TRANSPARENT (tıklamalar içinden geçer) | TOOLWINDOW | NOACTIVATE
        user32.SetWindowLongW(self.hwnd, -20, user32.GetWindowLongW(self.hwnd, -20) | 0x80000 | 0x20 | 0x80 | 0x8000000)
        # Ekran görüntülerinde görünmesin (WDA_EXCLUDEFROMCAPTURE, Win10 2004+): soru sorarken gizlenip yanıp sönmesin
        # KANZI_GORUNUR=1: doğrulama için ekran görüntüsünde görünsün (o zaman eski gizle-göster yolu çalışır)
        self.gorunmez = not os.environ.get("KANZI_GORUNUR") and bool(
            user32.SetWindowDisplayAffinity(ctypes.c_void_p(self.hwnd), 0x11))
        self.oturuyor, self.koltuk, self.surukle = False, list(self.ayar["koltuk"]), None
        self.koltuk_pen = tk.Toplevel(self.kok)  # sürüklenebilir koltuk: tıklamalar geçmez
        self.koltuk_pen.overrideredirect(True)
        self.koltuk_pen.attributes("-topmost", True)
        self.koltuk_pen.geometry("1x1+0+0")
        self.koltuk_pen.update_idletasks()
        self.koltuk_hwnd = user32.GetParent(self.koltuk_pen.winfo_id())
        user32.SetWindowLongW(self.koltuk_hwnd, -20,
                              user32.GetWindowLongW(self.koltuk_hwnd, -20) | 0x80000 | 0x80 | 0x8000000)
        if self.gorunmez:
            user32.SetWindowDisplayAffinity(ctypes.c_void_p(self.koltuk_hwnd), 0x11)
        self.koltuk_pen.configure(cursor="fleur")
        self.koltuk_pen.bind("<ButtonPress-1>", self.koltuk_tut)
        self.koltuk_pen.bind("<B1-Motion>", self.koltuk_tasi)
        self.koltuk_pen.bind("<ButtonRelease-1>", lambda _e: self.ayarla(koltuk=[int(v) for v in self.koltuk]))
        user32.ShowWindow(ctypes.c_void_p(self.koltuk_hwnd), 0)  # gizli başlar
        threading.Thread(target=kisaysol_dinle, args=(self.q,), daemon=True).start()
        if self.ayar["oturuyor"]:  # kapatılmadan önce koltuktaydı: oradan devam
            self.otur(soz=False)
        threading.excepthook = lambda a: self._kaydet_hata(a.exc_type, a.exc_value, a.exc_traceback)
        self.dongu()

    @staticmethod
    def _kaydet_hata(tur, hata, iz):
        import traceback
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "".join(traceback.format_exception(tur, hata, iz)), flush=True)

    def _hata(self, tur, hata, iz):
        self._kaydet_hata(tur, hata, iz)
        self.durum = "bos"
        self.soyle(f"Bir hata oldu: {hata}")

    # ---------- olay döngüsü ----------
    def dongu(self):
        try:
            self._dongu()
        except Exception:
            self._hata(*sys.exc_info())  # bir karede hata olsa da Kanzi donup kalmasın
        if self.kok.winfo_exists() and not self.kapaniyor:
            self.kok.after(16, self.dongu)

    def _dongu(self):
        while not self.q.empty():
            tur, veri = self.q.get()
            if self.olay(tur, veri) is False:
                return
        fx, fy = self.kok.winfo_pointerxy()
        if self.hedef and time.time() > self.hedef[2]:
            self.hedef = None  # bir dakika tıklanmadı, ders bıraktı
        elif self.hedef and user32.GetAsyncKeyState(0x01) & 0x8000 and math.dist((fx, fy), self.hedef[:2]) < 40:
            self.hedef = None  # gösterilen yere tıkladı: ekran değişsin, sonra sıradaki adım
            self.kok.after(1200, lambda: self.sor("Gösterdiğin yere tıkladım. Yeni ekrana bak, sıradaki adım ne?",
                                                  ONAY_YOK, sesli=self.sesli))
        self.ok = None
        if self.hedef:  # okun ucu gösterilen noktada; nokta alttaysa/sağdaysa Kanzi üstüne/soluna geçer
            tx, ty = self.hedef[:2]
            alan = monitor_alani(tx, ty)
            alt, sag = ty + self.boyut[1] > alan[3], tx + self.boyut[0] > alan[2]
            self.ok = (alt, sag)
            hx, hy = (tx - self.boyut[0] if sag else tx), (ty - self.boyut[1] if alt else ty)
        elif self.oturuyor:  # koltukta: gövde minderin üstünde; uzun baloncukta ekrandan taşmasın diye kalkar
            hx = self.koltuk[0] + 48 * g.OLCEK - g.kw() / 2
            hy = self.koltuk[1] + 38 * g.OLCEK - 4 - g.kw() / 2
            alan = monitor_alani(hx, hy)
            self.sol = hx + g.kw() + GEN > alan[2]  # sağ kenarda baloncuk sola açılsın, Kanzi koltuktan kaymasın
            hy = min(hy, alan[3] - self.boyut[1])
        else:
            hx, hy = hedef_konum(fx, fy, monitor_alani(fx, fy), *self.boyut)
        if not self.oturuyor:
            self.sol = False
        self.x += (hx - self.x) * 0.25
        self.y += (hy - self.y) * 0.25
        self.zamanli_isler()
        if self.sayfa < len(self.sayfalar) - 1 and time.time() > self.yazi_bitis:
            self.sayfaya_git(self.sayfa + 1)  # okuma süresi doldu: kendiliğinden sıradaki
        self.ciz()
        if self.oturuyor:  # komut kutusu/ayarlar açılıp kapanınca Windows koltuğu öne alabiliyor: hep Kanzi'nin arkasında
            user32.SetWindowPos(ctypes.c_void_p(self.koltuk_hwnd), ctypes.c_void_p(self.hwnd), 0, 0, 0, 0, 0x13)

    def olay(self, tur, veri):
        if tur in ("komut", "acikla", "ses", "ayarlar", "cevir", "sohbet"):
            t = time.time()
            self.cagri = [c for c in self.cagri if t - c < 15] + [t]
            if len(self.cagri) >= 4:  # 15 sn içinde 4. çağrı: "ne var yine"
                self.yuz("kizgin", 1.6)
            else:
                self.yuz(random.choice(("saskin", "saskin", "suphe")), 0.7)  # çağrılınca irkilir ya da süzer
        if tur in ("komut", "sohbet"):
            self.yazma_hedefi_al()  # "yaz: ..." Kanzi'nin kutusuna değil, önceki pencereye yazılsın
        if tur == "komut":
            self.komut_kutusu()
        elif tur == "acikla":
            self.acikla_basla()
        elif tur == "cevir":
            self.acikla_basla(cevir=True)
        elif tur == "sessiz":
            self.ayarla(sesli=not self.ayar["sesli"])
            self.soyle("Sesli mod: sesle sorduğunda cevabı okurum." if self.ayar["sesli"]
                       else "Sessiz mod: cevapları yalnızca yazarım.")
        elif tur == "ayarlar":
            self.ayarlar_penceresi()
        elif tur in ("ileri", "geri") and self.sayfalar:  # baloncuk kapanmış olsa da son cevap geri gelir
            self.sayfaya_git(self.sayfa + (1 if tur == "ileri" else -1) if time.time() < self.yazi_bitis
                             else self.sayfa)
        elif tur == "sohbet":
            self.sohbet_penceresi()
        elif tur == "iptal":
            self.iptal()
        elif tur == "ses":
            self.ses_ac_kapa()
        elif tur == "duyuldu":
            if self.iptal_edildi:
                return
            self.durum = "bos"
            if veri:
                self.soyle(f"“{veri}”")
                self.istek(veri, sesli=True)
            else:
                self.soyle("Duyamadım kanka, bir daha söyle.")
        elif tur == "cik":
            self.konusmaci.durdur()
            self.yerel.kapat()  # Kanzi'nin açtığı sunucu kapansın, ekran kartı boşalsın
            self.kapaniyor = True
            self.kok.after(0, self.kok.destroy)
            return False
        elif tur == "parca":
            no, metin = veri
            if no == self.istek_no:
                self.akan += metin
                if self.okunsun():
                    for cumle in self.bolucu.ekle(metin):
                        self.konusmaci.ekle(cumle, SESLER[self.ayar["ses"]])
        elif tur == "claudea":  # yerel cevap veremedi: Claude'a geç
            no, metin, sesli = veri
            if no == self.istek_no:
                self.durum = "bos"
                self.sor(metin, self.yetki(), sesli)
        elif tur == "limit":  # Claude limiti doldu: aynı soru yerelde
            no, metin, sesli = veri
            if no != self.istek_no:
                return
            self.durum = "bos"
            if self.yerel.durum == "hazir":
                self.sor_yerel(metin, sesli, onek="Claude'un limiti dolu, yerel modelle cevaplıyorum. ",
                               ekran=yerel.yonlendir(metin) != "yerel")
            else:
                self.soyle("Claude'un kullanım limiti doldu, yerel model de hazır değil.")
        elif tur == "baloncuk":
            no, metin = veri if isinstance(veri, tuple) else (self.istek_no, veri)
            if no != self.istek_no:
                return  # iptal edilmiş eski istek
            self.durum = "bos"
            metin, nokta = hedef_ayikla(metin)
            self.soyle(metin)
            if time.time() > self.ifade_bitis:  # hata değilse: çoğu zaman "gördün mü" sırıtması
                self.yuz(random.choice(("sirit", "sirit", "mutlu", "normal")), 1.8)
            if self.okunsun():  # akışta okunmamış kalan son cümle; hiç akmadıysa hepsi
                kalan = self.bolucu.bitir() if self.akan else CumleBolucu().ekle(metin + "\n")
                for cumle in kalan:
                    self.konusmaci.ekle(cumle, SESLER[self.ayar["ses"]])
            self.akan = ""
            if self.son_soru and metin:
                self.yerel.hatirla(self.son_soru, metin)  # yerel model Claude'la konuşulanı da bilsin
                self.son_soru = ""
            if nokta:
                self.hedef = (*ekrana_cevir(nokta, self.koken), time.time() + 60)

    def okunsun(self):
        return self.sesli and self.ayar["sesli"]

    # ---------- çizim ----------
    def ciz(self):
        t = time.time()
        durum, halka = self.durum, 0.0
        bak, ifade = self.bakis(t), (self.ifade if t < self.ifade_bitis else "normal")
        if durum == "dusunuyor":
            ifade = "dusunceli"
            if self.akan and t - self.akan_zaman > 0.2:  # akan yazı: baloncuğu saniyede en fazla 5 kez yenile
                temiz = hedef_ayikla(self.akan)[0]
                self.akan_goster = temiz if len(temiz) < 360 else "…" + temiz[-357:]
                self.akan_zaman = t
            yazi = self.akan_goster or ("Düşünüyorum (yerel)" if self.yerelde else "Düşünüyorum") + "." * (int(t * 2) % 4)
        elif durum == "dinliyor":
            halka = min(1.0, self.seviye / 1500)
            yazi = "Dinliyorum… bitince tekrar Ctrl+Alt+S"
        elif durum == "cozuyor":
            yazi = "Anlıyorum…"
        else:
            if self.konusmaci.caliyor:
                durum, halka = "konusuyor", abs(math.sin(t * 11)) * (0.6 + 0.4 * math.sin(t * 3.7))
            yazi = self.yazi if t < self.yazi_bitis else ""
        if ifade == "normal" and durum == "bos" and not yazi and t - self.fare_zaman > 90:
            ifade = "uykulu"  # fareye uzun süre dokunulmadı
        kirp = (t % 4) < 0.12 and durum != "dinliyor"  # dört saniyede bir göz kırpar
        aci = (t * 300) % 360
        if durum == "bos" and ifade == "uykulu" and self.muzik > 0.03:
            ifade = "mutlu"  # müzik varken uyuklamaz
        im = g.kare(durum, kirp, bak, aci, halka, g.zip_hesapla(t), yazi, GEN, BOY, self.ok, ifade, self.sol)
        self.boyut = im.size
        # müzik çalıyorsa ritimle zıplar (koltukta kafa sallar); kendi konuşması sayılmaz
        dans = 0 if self.konusmaci.caliyor else round(min(1.0, self.muzik * 4) * (3 if self.oturuyor else 7) * g.OLCEK
                                                      * abs(math.sin(t * math.pi * 2)))
        x = self.x - (im.width - g.kw() if self.sol and yazi else 0)  # sola açılan baloncukta küre sağ uçta
        anahtar = (durum, kirp, bak, ifade, int(aci) // 15, round(halka, 1), round(g.zip_hesapla(t)), yazi,
                   self.ok, self.sol, int(x), int(self.y) - dans)
        if anahtar != self.son_kare:  # değişmeyen kareyi tekrar basma
            self.son_kare = anahtar
            g.katmana_bas(self.hwnd, im, x, self.y - dans)

    # ---------- zamanlı işler: hatırlatma, mola, müzik ----------
    def hatirlat_kur(self, saniye, mesaj):
        hs = self.ayar["hatirlatmalar"]
        if saniye == "liste":
            if not hs:
                return self.soyle("Kurulu hatırlatma yok.")
            return self.soyle(" · ".join(f"{time.strftime('%H:%M', time.localtime(z))} {m or 'süre'}"
                                         for z, m in sorted(hs)))
        if saniye == "sil":
            self.ayarla(hatirlatmalar=[])
            return self.soyle(f"{len(hs)} hatırlatmayı sildim." if hs else "Zaten hatırlatma yoktu.")
        self.ayarla(hatirlatmalar=hs + [[time.time() + saniye, mesaj]])
        self.yuz("sirit", 1.2)
        saat = time.strftime("%H:%M", time.localtime(time.time() + saniye))
        self.soyle(f"Tamam, {isler.sure_yazi(saniye)} sonra ({saat}) "
                   + (f"hatırlatırım: {mesaj}." if mesaj else "seslenirim."))

    def zamanli_isler(self):
        t = time.time()
        hs = self.ayar["hatirlatmalar"]
        gelen = [h for h in hs if h[0] <= t]
        if gelen:
            self.ayarla(hatirlatmalar=[h for h in hs if h[0] > t])
            gec = t - gelen[0][0] > 120  # Kanzi kapalıyken geçmiş
            mesaj = gelen[0][1]
            metin = ("Kanka, hatırlatıyorum" + (" (biraz geç kaldım)" if gec else "") + ": "
                     + (f"{mesaj} unutma!" if mesaj else "süre doldu!"))
            if self.oturuyor:
                self.kalk(soz=False)  # koltuktan kalkıp yanına gelir
            self.yuz("saskin", 2.0)
            self.soyle(metin)
            if self.ayar["sesli"]:
                self.konusmaci.ekle(metin, SESLER[self.ayar["ses"]])
        bosta = isler.bosta_saniye()
        if bosta > 300:  # 5 dk dokunmadıysa mola vermiş say
            self.aktif_bas = t
            return
        if self.durum != "bos" or t < self.mola_zaman:
            return
        saat = time.localtime(t).tm_hour
        if 1 <= saat < 6:  # gece geç saatte hâlâ başında
            self.mola_zaman = t + 45 * 60
            self.yuz("bikkin", 2.5)
            self.soyle(random.choice((f"Saat {time.strftime('%H:%M')} kanka, yatsana artık.",
                                      "Gece yarısını çoktan geçtik, yarın devam etsek?",
                                      f"{time.strftime('%H:%M')} oldu. Uyku diye bir şey var.")))
        elif t - self.aktif_bas > 2 * 3600:
            self.mola_zaman, self.aktif_bas = t + 30 * 60, t
            self.yuz("suphe", 2.5)
            self.soyle(random.choice(("Kanka 2 saattir başındasın, kalk biraz su iç.",
                                      "İki saat oldu, gözlerini dinlendir biraz.",
                                      "Bi esne, bi yürü. İki saattir oturuyorsun.")))

    def _muzik_dinle(self):
        try:
            olcer = isler.SesOlcer()
        except OSError as e:  # hoparlör yoksa dans yok, Kanzi yine çalışır
            return print("ses ölçer:", e, flush=True)
        while not self.kapaniyor:
            v = 0.0 if self.konusmaci.caliyor else olcer.tepe()
            self.muzik = v if v > self.muzik else self.muzik * 0.85  # hızlı yükselir, yavaş söner
            time.sleep(0.05)

    def sayfaya_git(self, i):
        self.sayfa = max(0, min(i, len(self.sayfalar) - 1))
        self.yazi = self.sayfalar[self.sayfa]
        self.yazi_bitis = time.time() + 4 + len(self.yazi) / 15  # okuma süresi kadar kalsın

    def yuz(self, ifade, sure):
        self.ifade, self.ifade_bitis = ifade, time.time() + sure

    def bakis(self, t):
        """Gözbebeklerinin yönü (-3..3): kafasına göre etrafa bakar (Mert fareyi izlemesini istemedi);
        düşünürken yukarıda gezinir, öğretirken gösterdiği yere bakar."""
        fx, fy = self.kok.winfo_pointerxy()
        dx = fx - self.fare[0]
        if abs(dx) > 45:  # fare sağa-sola sallanıyor mu: hızlı yön değişimlerini say
            if self.yon and (dx > 0) != (self.yon > 0):
                self.donus = [d for d in self.donus if t - d < 1.0] + [t]
            self.yon = dx
        if (fx, fy) != self.fare:
            if t - self.fare_zaman > 90:
                self.yuz("kizgin" if random.random() < 0.4 else "saskin", 0.9)  # uyuklarken uyandırıldı
            self.fare, self.fare_zaman = (fx, fy), t
        if len(self.donus) >= 6 and t > self.sarsinti_zaman and self.durum == "bos":  # fare deli gibi sallandı
            self.sarsinti_zaman = t + 20
            self.yuz("kizgin", 2.2)
            self.soyle(random.choice(("Dur be, başım döndü!", "Sakin kanka, sakin.", "Ne bu acele?")))
        if self.hedef:  # öğretirken gösterdiği yere bakar
            dx, dy = self.hedef[0] - (self.x + g.kw() / 2), self.hedef[1] - (self.y + 4 + g.kw() / 2)
            k = 3 * min(1.0, math.hypot(dx, dy) / 80) / max(1.0, math.hypot(dx, dy))
            hedef = (dx * k, dy * k)
        elif self.durum in ("dusunuyor", "cozuyor"):
            hedef = (2.6 * math.sin(t * 1.7), -2.2 + 0.6 * math.sin(t * 2.9))
        else:
            if t > self.etraf_zaman:
                self.etraf = (random.uniform(-3, 3), random.uniform(-2.5, 2.5)) if random.random() < 0.7 else None
                self.etraf_zaman = t + random.uniform(1.2, 3.5)
                if random.random() < 0.15:  # arada kafasına göre bir surat: göz devirir, süzer, sırıtır
                    ifade = random.choice(("bikkin", "bikkin", "suphe", "sirit", "sirit", "mutlu"))
                    self.yuz(ifade, random.uniform(1.0, 2.2))
                    if ifade == "bikkin":
                        self.etraf = (random.choice((-2.0, 2.0)), -3.0)  # göz devirme: yukarı yana
            hedef = self.etraf or (0.0, 0.0)  # ya bir yere ya da düz karşıya
        self.goz = [a + (b - a) * 0.35 for a, b in zip(self.goz, hedef)]
        return tuple(round(v * 2) / 2 for v in self.goz)  # yarım piksel adım: önbellek küçük kalsın

    def soyle(self, metin):
        metin = metin.strip() or "(boş cevap)"
        if re.search(r"\bHata|hata oldu|çalışmadı|limiti doldu|veremedim", metin):
            self.yuz(random.choice(("kizgin", "uzgun")), 2.5)
        elif re.search(r"durdum|Duyamadım", metin):
            self.yuz("suphe" if "Duyamadım" in metin else "kizgin", 2.0)
        elif "bitmedi" in metin:
            self.yuz("bikkin", 2.0)
        if self.cevap_bekleniyor:  # sorulan şeyin cevabı (ya da hatası) sohbet geçmişine
            self.sohbete_yaz("kanzi", metin)
        self.sayfalar = sayfala(metin)  # uzun cevap kesilmesin: sayfa sayfa, okuma süresince sırayla
        self.sayfaya_git(0)
        self.akan_goster = ""

    # ---------- komut kutusu ----------
    def komut_kutusu(self):
        if self.kutu:
            self.kutu.destroy()
        fx, fy = self.kok.winfo_pointerxy()
        k = self.kutu = tk.Toplevel(self.kok, bg=g.CIZGI)
        k.overrideredirect(True)
        k.attributes("-topmost", True, "-alpha", 0.96)
        ic = tk.Frame(k, bg=g.KART, padx=12, pady=8)
        ic.pack(fill="both", expand=True, padx=1, pady=1)
        on = tk.Label(ic, text="Kanzi ›", bg=g.KART, fg=g.VURGU, font=("Segoe UI Semibold", 12))
        on.pack(side="left")
        g_ = tk.Entry(ic, font=("Segoe UI", 12), bg=g.KART, fg=g.YAZI, insertbackground=g.VURGU, relief="flat",
                      bd=0, width=34, highlightthickness=0)
        g_.pack(side="left", fill="x", expand=True, padx=(8, 8))
        tk.Label(ic, text="Enter gönder · Esc kapat", bg=g.KART, fg=g.SOLUK, font=("Segoe UI", 9)).pack(side="right")
        k.update_idletasks()
        k.geometry(f"+{fx + 20}+{max(0, fy - k.winfo_height() - 24)}")
        g.koyu_pencere(user32.GetParent(k.winfo_id()) or k.winfo_id())
        k.after(50, lambda: (k.focus_force(), g_.focus_set()))

        def kapat(_=None):
            k.destroy()
            self.kutu = None

        def gonder(_=None):
            metin = g_.get().strip()
            kapat()
            self.yazilan(metin)

        g_.bind("<Return>", gonder)
        g_.bind("<Escape>", kapat)

    # ---------- dikte ----------
    def kendi_penceresi(self, hwnd):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == os.getpid()

    def yazma_hedefi_al(self):
        on = user32.GetForegroundWindow()
        if on and not self.kendi_penceresi(on):
            self.yazma_hedefi = on

    def dikte_yaz(self, metin):
        """Söyleneni aynen, odaktaki kutuya yazar (Sesli Komut gibi; Claude'a gitmez)."""
        on = user32.GetForegroundWindow()
        hedef = self.yazma_hedefi if self.kendi_penceresi(on) else on  # kutu/sohbet öndeyse önceki pencere

        def yaz():
            time.sleep(0.3)  # komut kutusu kapansın, odak geri dönsün
            if hedef and user32.GetForegroundWindow() != hedef and not isler.one_getir(hedef):
                return self.q.put(("baloncuk", "Yazacağım pencereyi öne alamadım, kutuya tıklayıp tekrar söyle."))
            isler.klavyeye_yaz(metin)
            self.q.put(("baloncuk", random.choice(("Yazdım.", "Tamam, yazdım.", "Yazdım, Enter'a sen bas."))))

        threading.Thread(target=yaz, daemon=True).start()

    def logo_tazele(self):
        """Logo seçili tasarımı izlesin. Değişmediyse dokunma (masaüstü simge önbelleği boşuna yenilenmesin)."""
        tasarim = f"{self.ayar['renk']}|{self.ayar['sekil']}|{self.ayar['kravat']}"
        if getattr(self, "_logo", None) == tasarim:
            return
        self._logo = tasarim
        try:
            ico = os.path.join(KLASOR, "kanzi_v2_mavi.ico")
            g.logo_kaydet(os.path.join(KLASOR, "kanzi_v2.png"), ico)
            # Windows simgeyi dosya yoluna göre önbellekte tutuyor: kısayol için her tasarıma ayrı adlı kopya
            kisa = os.path.join(KLASOR, f"logo_{zlib.crc32(tasarim.encode()):08x}.ico")
            if not os.path.exists(kisa):
                shutil.copyfile(ico, kisa)
                for eski in os.listdir(KLASOR):
                    if eski.startswith("logo_") and eski.endswith(".ico") and eski != os.path.basename(kisa):
                        os.remove(os.path.join(KLASOR, eski))
                threading.Thread(target=kisayol_simgesi, args=(kisa,), daemon=True).start()
        except OSError as e:  # logo yazılamadı diye Kanzi durmasın
            print("logo:", e, flush=True)

    def yazilan(self, metin):
        """Komut kutusundan ya da sohbet penceresinden yazılan."""
        if metin.lower() == "yeni konu":
            self.sifirla()
        elif metin:
            self.istek(metin, sesli=False)

    # ---------- sohbet ----------
    def sohbete_yaz(self, kim, metin):
        self.cevap_bekleniyor = kim == "sen"
        self.sohbet = (self.sohbet + [[kim, metin.strip(), time.strftime("%d.%m %H:%M")]])[-300:]
        sohbet_yaz(self.sohbet)
        if self.sohbet_pen and self.sohbet_pen.winfo_exists():
            self.sohbet_pen.ekle(*self.sohbet[-1])

    def sohbet_penceresi(self):
        if self.sohbet_pen and self.sohbet_pen.winfo_exists():
            self.sohbet_pen.lift()
            self.sohbet_pen.giris.focus_force()
            return
        p = self.sohbet_pen = tk.Toplevel(self.kok, bg=g.ZEMIN, padx=16, pady=14)
        p.title("Kanzi v2 — Sohbet")
        p.update_idletasks()
        if self.gorunmez:  # ekran okuyunca (OCR / Claude) sohbet penceresi "ekrandaki şey" sanılmasın
            user32.SetWindowDisplayAffinity(ctypes.c_void_p(user32.GetParent(p.winfo_id())), 0x11)
        p.attributes("-topmost", True, "-alpha", 0.97)
        p.minsize(420, 360)
        ikon = os.path.join(KLASOR, "kanzi_v2_mavi.ico")
        if os.path.exists(ikon):
            p.iconbitmap(ikon)
        ust = tk.Frame(p, bg=g.ZEMIN)
        ust.pack(fill="x", pady=(0, 10))
        p.resim = ImageTk.PhotoImage(g.karakter("bos", False, 0, 0, 0))
        tk.Label(ust, image=p.resim, bg=g.ZEMIN).pack(side="left")
        bas = tk.Frame(ust, bg=g.ZEMIN)
        bas.pack(side="left", padx=8)
        tk.Label(bas, text="Sohbet", bg=g.ZEMIN, fg=g.YAZI, font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(bas, text="Geçmiş kalıcı · “yeni konu” yazınca Claude sıfırlanır", bg=g.ZEMIN,
                 fg=g.SOLUK, font=("Segoe UI", 9)).pack(anchor="w")

        alt = tk.Frame(p, bg=g.CIZGI)  # yazma kutusu: komut kutusuyla aynı görünüm
        alt.pack(side="bottom", fill="x", pady=(10, 0))
        ic = tk.Frame(alt, bg=g.KART, padx=12, pady=8)
        ic.pack(fill="x", padx=1, pady=1)
        tk.Label(ic, text="›", bg=g.KART, fg=g.VURGU, font=("Segoe UI Semibold", 13)).pack(side="left")
        giris = p.giris = tk.Entry(ic, font=("Segoe UI", 11), bg=g.KART, fg=g.YAZI, insertbackground=g.VURGU,
                                   relief="flat", bd=0, highlightthickness=0)
        giris.pack(side="left", fill="x", expand=True, padx=8)

        def gonder(_=None):
            metin = giris.get().strip()
            giris.delete(0, "end")
            self.yazilan(metin)

        dugme(ic, "Gönder", gonder, ana=True).pack(side="right")
        giris.bind("<Return>", gonder)

        cerceve = tk.Frame(p, bg=g.CIZGI)
        cerceve.pack(fill="both", expand=True)
        kutu = tk.Frame(cerceve, bg=g.ZEMIN)
        kutu.pack(fill="both", expand=True, padx=1, pady=1)
        kaydirma = tk.Scrollbar(kutu, bg=g.KART, troughcolor=g.ZEMIN, bd=0, width=10)
        kaydirma.pack(side="right", fill="y")
        t = tk.Text(kutu, bg=g.ZEMIN, fg=g.YAZI, font=("Segoe UI", 11), wrap="word", relief="flat", bd=0, padx=10,
                    pady=8, width=58, height=20, highlightthickness=0, yscrollcommand=kaydirma.set, cursor="arrow")
        t.pack(side="left", fill="both", expand=True)
        kaydirma.configure(command=t.yview)
        # mesajlar baloncuk gibi: seninkiler sağda açık kartta, Kanzi'ninkiler solda koyu kartta
        t.tag_configure("sen_ad", foreground=g.VURGU, justify="right", font=("Segoe UI Semibold", 9),
                        spacing1=10, rmargin=4)
        t.tag_configure("sen", background=g.KART2, justify="right", lmargin1=90, lmargin2=90, rmargin=4,
                        lmargincolor=g.ZEMIN, rmargincolor=g.ZEMIN, spacing1=3, spacing3=3)
        t.tag_configure("kanzi_ad", foreground=g.SOLUK, font=("Segoe UI Semibold", 9), spacing1=10, lmargin1=4)
        t.tag_configure("kanzi", background=g.KART, lmargin1=4, lmargin2=4, rmargin=90, lmargincolor=g.ZEMIN,
                        rmargincolor=g.ZEMIN, spacing1=3, spacing3=3)

        def ekle(kim, metin, zaman):
            t.configure(state="normal")
            t.insert("end", ("Sen" if kim == "sen" else "Kanzi") + f" · {zaman}\n", kim + "_ad")
            t.insert("end", f" {metin} \n", kim)
            t.configure(state="disabled")
            t.see("end")

        p.ekle = ekle
        if not self.sohbet:
            t.insert("end", "Henüz konuşma yok. Aşağıya yaz ya da Ctrl+Alt+S ile konuş.\n", "kanzi_ad")
        for m in self.sohbet:
            ekle(*m)
        t.configure(state="disabled")
        p.bind("<Escape>", lambda _: p.destroy())
        p.update_idletasks()
        g.koyu_pencere(user32.GetParent(p.winfo_id()))
        fx, fy = self.kok.winfo_pointerxy()
        alan = monitor_alani(fx, fy)
        w, h = p.winfo_reqwidth() + 16, p.winfo_reqheight() + 40  # pencere henüz açılmadı: istenen boyut + çerçeve
        x = min(max(alan[0], fx - w // 2), alan[2] - w)  # tek monitörde, görev çubuğunun üstünde kalsın
        y = min(max(alan[1], fy - h // 2), alan[3] - h - 48)
        p.geometry(f"+{x}+{max(alan[1], y)}")
        p.after(50, lambda: (p.focus_force(), giris.focus_set()))

    # ---------- ayarlar ----------
    def yetki(self):
        return EYLEM if self.ayar["yetki"] == "is" else ONAY_YOK

    def ayarla(self, **degisen):
        self.ayar.update(degisen)
        ayar_yaz(self.ayar)
        if not self.ayar["sesli"]:
            self.konusmaci.durdur()

    def sifirla(self):
        if os.path.exists(OTURUM):
            os.remove(OTURUM)
        self.soyle("Tamam, sayfayı çevirdik. Yeni konu.")

    def ayarlar_penceresi(self):
        if self.pencere and self.pencere.winfo_exists():
            self.pencere.lift()
            self.pencere.focus_force()
            return
        p = self.pencere = tk.Toplevel(self.kok, bg=g.ZEMIN, padx=16, pady=14)
        p.title("Kanzi v2 — Ayarlar")
        p.attributes("-topmost", True, "-alpha", 0.97)
        p.resizable(False, False)
        ikon = os.path.join(KLASOR, "kanzi_v2_mavi.ico")
        if os.path.exists(ikon):
            p.iconbitmap(ikon)
        yazi = {"bg": g.KART, "fg": g.YAZI, "font": ("Segoe UI", 10)}
        secim = dict(yazi, activebackground=g.KART, activeforeground=g.YAZI, selectcolor=g.KART2,
                     highlightthickness=0, bd=0, cursor="hand2", anchor="w")

        ust = tk.Frame(p, bg=g.ZEMIN)
        ust.pack(fill="x", pady=(0, 10))
        govde = tk.Frame(p, bg=g.ZEMIN)  # iki sütun: pencere ince uzun değil geniş olsun
        govde.pack(fill="x")
        sol, sag = tk.Frame(govde, bg=g.ZEMIN), tk.Frame(govde, bg=g.ZEMIN)
        sol.pack(side="left", fill="y", anchor="n")
        sag.pack(side="left", fill="y", anchor="n", padx=(14, 0))
        p.resim = ImageTk.PhotoImage(g.karakter("bos", False, 0, 0, 0))  # pencere kapanana dek silinmesin
        bas_resim = tk.Label(ust, image=p.resim, bg=g.ZEMIN)
        bas_resim.pack(side="left")
        bas = tk.Frame(ust, bg=g.ZEMIN)
        bas.pack(side="left", padx=8)
        tk.Label(bas, text="Kanzi v2", bg=g.ZEMIN, fg=g.YAZI, font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(bas, text="İmlecinin yanındaki yardımcın", bg=g.ZEMIN, fg=g.SOLUK,
                 font=("Segoe UI", 9)).pack(anchor="w")

        def kart(baslik, p):
            tk.Label(p, text=baslik.upper(), bg=g.ZEMIN, fg=g.SOLUK, font=("Segoe UI Semibold", 8)
                     ).pack(anchor="w", pady=(8, 3), padx=2)
            dis = tk.Frame(p, bg=g.CIZGI)  # 1 px kenar çizgisi
            dis.pack(fill="x")
            ic = tk.Frame(dis, bg=g.KART, padx=14, pady=10)
            ic.pack(fill="x", padx=1, pady=1)
            return ic

        sesli = tk.BooleanVar(value=self.ayar["sesli"])
        ses = tk.StringVar(value=self.ayar["ses"])
        yetki = tk.StringVar(value=self.ayar["yetki"])

        def kaydet():
            self.ayarla(sesli=sesli.get(), ses=ses.get(), yetki=yetki.get())

        def dinle():
            self.konusmaci.durdur()
            self.konusmaci.ekle("Merhaba, ben Kanzi.", SESLER[ses.get()])

        k = kart("Ses", sol)
        tk.Checkbutton(k, text="Sesle sorduğumda cevabı sesli oku", variable=sesli, command=kaydet,
                       **secim).pack(fill="x")
        satir = tk.Frame(k, bg=g.KART)
        satir.pack(fill="x", pady=(6, 0))
        tk.Label(satir, text="Ses:", **dict(yazi, fg=g.SOLUK)).pack(side="left")
        for ad in SESLER:
            tk.Radiobutton(satir, text=ad, value=ad, variable=ses, command=kaydet, **secim
                           ).pack(side="left", padx=(8, 0))
        dugme(satir, "▶ Dinle", dinle).pack(side="right")

        k = kart("Görünüm", sol)
        onizleme = {}  # (tür, ad) -> etiket; seçili olan açık mavi çerçeveli
        secili = tk.Label(k, anchor="w", **dict(yazi, fg=g.SOLUK))

        def resim(renk, sekil):
            g.tema(renk, sekil, self.ayar["kravat"])
            im = g.karakter("bos", False, 0, 0, 0)
            return ImageTk.PhotoImage(im.resize((im.width * 3 // 5, im.height * 3 // 5)))

        def tazele():
            a = self.ayar
            for (tur, ad), et in onizleme.items():
                et.resim = resim(ad if tur == "renk" else a["renk"], ad if tur == "sekil" else a["sekil"])
                et.configure(image=et.resim, highlightbackground=g.VURGU if a[tur] == ad else g.KART)
            g.tema(a["renk"], a["sekil"], a["kravat"])
            p.resim = ImageTk.PhotoImage(g.karakter("bos", False, 0, 0, 0))
            bas_resim.configure(image=p.resim)
            secili.configure(text=f"{a['renk']} · {a['sekil']}")
            self.son_kare = None  # Kanzi yeni haliyle yeniden çizilsin
            self.logo_tazele()

        for tur, secenekler, baslik in (("renk", g.RENKLER, "Renk"), ("sekil", g.SEKILLER, "Şekil")):
            satir = tk.Frame(k, bg=g.KART)
            satir.pack(fill="x", pady=(0, 4))
            tk.Label(satir, text=baslik, width=6, anchor="w", **dict(yazi, fg=g.SOLUK)).pack(side="left")
            for ad in secenekler:
                et = tk.Label(satir, bg=g.KART, cursor="hand2", highlightthickness=2, highlightbackground=g.KART)
                et.pack(side="left", padx=1)
                et.bind("<Button-1>", lambda _e, t=tur, a=ad: (self.ayarla(**{t: a}), tazele()))
                onizleme[(tur, ad)] = et
        kravat = tk.BooleanVar(value=self.ayar["kravat"])
        tk.Checkbutton(k, text="Kravat taksın", variable=kravat, **secim,
                       command=lambda: (self.ayarla(kravat=kravat.get()), tazele())).pack(fill="x")
        secili.pack(fill="x")
        tazele()

        k = kart("Yetki", sag)
        tk.Radiobutton(k, text="İş yapabilir: e-posta taslağı, Word, dosya (PowerShell)", value="is",
                       variable=yetki, command=kaydet, **secim).pack(fill="x")
        tk.Radiobutton(k, text="Sadece göstersin ve öğretsin: hiçbir şeye dokunmaz", value="ogret",
                       variable=yetki, command=kaydet, **secim).pack(fill="x", pady=(4, 0))

        k = kart("Konuşma", sol)
        satir = tk.Frame(k, bg=g.KART)
        satir.pack(fill="x")
        tk.Label(satir, text="Kapatıp açınca da kaldığı yerden sürer.", **dict(yazi, fg=g.SOLUK)).pack(side="left")
        dugme(satir, "Sıfırla", self.sifirla).pack(side="right")

        k = kart("Yerel beyin (OpenJarvis)", sag)
        yerel_ac = tk.BooleanVar(value=self.ayar["yerel"])
        tk.Checkbutton(k, text="Basit soruları yerelde, anında ve limitsiz cevapla", variable=yerel_ac,
                       command=lambda: self.ayarla(yerel=yerel_ac.get()), **secim).pack(fill="x")
        durum = {"hazir": f"Hazır · {yerel.MODEL} · ekran ve iş yaptırma yine Claude'da",
                 "basliyor": "Açılıyor…", "kapali": "Kapalı",
                 "yok": "Çalışmıyor: OpenJarvis ya da Ollama kurulu değil (openjarvis.log)"}[self.yerel.durum]
        tk.Label(k, text=durum, anchor="w", **dict(yazi, fg=g.SOLUK)).pack(fill="x", pady=(4, 0))

        k = kart("Kısayollar", sag)
        for tus, ne in KISAYOLLAR:
            satir = tk.Frame(k, bg=g.KART)
            satir.pack(fill="x", pady=1)
            tk.Label(satir, text=tus, width=15, anchor="w", bg=g.KART, fg=g.VURGU, font=("Consolas", 10)
                     ).pack(side="left")
            tk.Label(satir, text=ne, anchor="w", **yazi).pack(side="left")

        alt = tk.Frame(p, bg=g.ZEMIN)
        alt.pack(fill="x", pady=(14, 0))
        dugme(alt, "Kanzi'yi kapat", lambda: self.q.put(("cik", None))).pack(side="left")
        dugme(alt, "Tamam", p.destroy, ana=True).pack(side="right")
        p.bind("<Escape>", lambda _: p.destroy())
        p.update_idletasks()
        g.koyu_pencere(user32.GetParent(p.winfo_id()))
        fx, fy = self.kok.winfo_pointerxy()
        p.geometry(f"+{max(0, fx - p.winfo_width() // 2)}+{max(0, fy - p.winfo_height() // 2)}")
        p.after(50, p.focus_force)

    # ---------- ses girişi ----------
    def ses_ac_kapa(self):
        if self.kayit is not None:  # ikinci basış: kaydı bitir, Whisper'a ver
            ham, self.kayit = b"".join(self.kayit), None
            self.durum = "cozuyor"
            threading.Thread(target=lambda: self.q.put(("duyuldu", self.kulak.coz(ham))), daemon=True).start()
            return
        if self.durum == "dusunuyor":
            self.soyle("Bi dur ya, önceki iş bitmedi (iptal: Ctrl+Alt+X).")
            return
        self.konusmaci.durdur()  # Kanzi konuşurken söze girilebilsin
        self.kayit, self.durum, self.iptal_edildi = [], "dinliyor", False
        threading.Thread(target=self._kaydet, daemon=True).start()

    def _kaydet(self):
        try:
            with sr.Microphone(sample_rate=HIZ, chunk_size=PARCA) as mik:
                while self.kayit is not None and len(self.kayit) < 60 * HIZ // PARCA:  # en fazla 1 dakika
                    veri = mik.stream.read(PARCA)
                    self.seviye = seviye(veri)
                    if self.kayit is not None:
                        self.kayit.append(veri)
        except Exception as e:  # mikrofon yoksa Kanzi "dinliyorum" diye takılı kalmasın
            self.kayit = None
            self.q.put(("baloncuk", f"Mikrofon açılamadı: {e}"))

    # ---------- açıklama ----------
    def pano(self):
        try:
            return self.kok.clipboard_get()
        except tk.TclError:
            return ""

    def acikla_basla(self, cevir=False):
        # Panoyu boşaltıp Ctrl+C gönder: bir şey seçili değilse eski pano "seçili metin" sanılmasın.
        eski = self.pano()
        self.kok.clipboard_clear()
        threading.Thread(target=kopyala_tusla, daemon=True).start()
        self.kok.after(500, lambda: self.acikla(eski, cevir))

    def acikla(self, eski, cevir=False):
        secili = self.pano()
        if not secili and eski:
            self.kok.clipboard_append(eski)  # seçim yoktu, kullanıcının panosunu geri koy
        self.sohbete_yaz("sen", ("Çevir: " if cevir else "Açıkla: ") + (secili[:300] or "imlecin olduğu yer"))
        if cevir:
            if not secili:
                return self.soyle("Önce çevireceğim yazıyı seç kanka.")
            if isler.turkce_mi(secili):  # Türkçe -> İngilizce yerelde iyi; tersinde 4B model Türkçeyi bozuyor: Claude
                if self.ayar["yerel"] and self.yerel.durum == "hazir":
                    return self.sor_yerel("Translate the following Turkish text into English. Output only the English "
                                          f"translation.\n\n{secili[:3000]}", sesli=False, baglam=False)
                return self.sor(f"Şu metni İngilizceye çevir, yalnızca çeviriyi yaz:\n{secili[:3000]}", ONAY_YOK, False)
            return self.sor(f"Şu metni Türkçeye çevir, yalnızca çeviriyi yaz:\n{secili[:3000]}", ONAY_YOK, False)
        if self.ayar["yerel"] and self.yerel.durum == "hazir":  # Mert istedi: açıklama yerelde (anında, limitsiz)
            self.son_soru = (f"Şu metni kısaca açıkla:\n{secili[:3000]}" if secili
                             else "İmlecin olduğu yerde ne var? Yalnızca 'İMLECİN HEMEN ÇEVRESİ' bölümündekini kısaca açıkla, "
                                "ekranın geri kalanını ve pencereyi anlatma.")
            return self.sor_yerel(self.son_soru, sesli=False, ekran=not secili, baglam=False, yakin=True)
        istek = ("İmlecin olduğu yerde ne görüyorsan kısaca açıkla ve bir sonraki adımı öğret (HEDEF ile göster)."
                 + (f"\nKullanıcının seçtiği metin (pano):\n{secili[:4000]}" if secili else ""))
        self.sor(istek, ONAY_YOK, sesli=False)

    # ---------- Claude ----------
    def iptal(self):
        self.iptal_edildi = True
        self.istek_no += 1  # yoldaki parçalar ve cevap yok sayılır
        self._oldur()
        self.konusmaci.durdur()
        self.kayit, self.hedef, self.durum, self.akan = None, None, "bos", ""
        self.soyle("Tamam be, durdum.")

    def _oldur(self):
        surec = self.surec
        if surec:  # claude ve başlattığı PowerShell komutları birlikte
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(surec.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def istek(self, metin, sesli):
        """Kullanıcının yazdığı/söylediği isteği yönlendirir: basit olan yerele, gerisi Claude'a."""
        self.sohbete_yaz("sen", metin)
        dikte = isler.dikte_komutu(metin)
        if dikte:
            return self.dikte_yaz(dikte)
        h = isler.hatirlatma(metin)
        if h:
            return self.hatirlat_kur(*h)
        medya = isler.medya_komutu(metin)
        if medya:
            isler.tusa_bas(*medya[1:])
            return self.soyle(isler.CEVAP[medya[0]])
        yer = yer_komutu(metin)
        if yer:
            return self.otur() if yer == "otur" else self.kalk()
        self.son_soru = metin
        yon = yerel.yonlendir(metin)
        if self.ayar["yerel"] and self.yerel.durum == "hazir" and yon != "claude":
            self.sor_yerel(metin, sesli, ekran=yon == "ekran")  # yerel model hiçbir şeye dokunamaz
        else:
            self.sor(metin, self.yetki(), sesli)

    # ---------- koltuk ----------
    def koltugu_bas(self):
        if user32.GetLayeredWindowAttributes(ctypes.c_void_p(self.koltuk_hwnd), None, None, None):
            # Tk SetLayeredWindowAttributes çağırmış: UpdateLayeredWindow hata 87 verir. LAYERED'ı kapatıp açmak sıfırlar
            ex = user32.GetWindowLongW(self.koltuk_hwnd, -20)
            user32.SetWindowLongW(self.koltuk_hwnd, -20, ex & ~0x80000)
            user32.SetWindowLongW(self.koltuk_hwnd, -20, ex | 0x80000)
        g.katmana_bas(self.koltuk_hwnd, g.koltuk(g.OLCEK), *self.koltuk)

    def otur(self, soz=True):
        kg, kb = g.koltuk_boyutu()
        if not self.koltuk:
            alan = calisma_alani()
            self.koltuk = [alan[0] + 24, alan[3] - kb - 12]
        alan = monitor_alani(*self.koltuk)  # monitör çıkarıldıysa koltuk görünür yere gelsin
        self.koltuk = [max(alan[0], min(self.koltuk[0], alan[2] - kg)), max(alan[1], min(self.koltuk[1], alan[3] - kb))]
        self.oturuyor = True
        self.ayarla(oturuyor=True, koltuk=[int(v) for v in self.koltuk])
        # Tk'nin withdraw/deiconify'ı SetLayeredWindowAttributes çağırıyor, UpdateLayeredWindow sonra hata 87 veriyor
        user32.ShowWindow(ctypes.c_void_p(self.koltuk_hwnd), 4)  # SW_SHOWNOACTIVATE
        self.koltugu_bas()
        if not soz:
            return
        self.yuz("sirit", 1.5)
        self.soyle(random.choice(("Tamam, köşemdeyim. Lazım olursa seslen.", "Oh be, nihayet oturdum.",
                                  "Koltuğumdayım kanka. 'Gel' dersen gelirim.")))

    def kalk(self, soz=True):
        self.oturuyor = False
        self.ayarla(oturuyor=False)
        user32.ShowWindow(ctypes.c_void_p(self.koltuk_hwnd), 0)
        if soz:
            self.soyle(random.choice(("Geldim, söyle.", "Tamam tamam, kalktım.", "Buradayım.")))

    def koltuk_tut(self, e):
        self.surukle = (e.x_root - self.koltuk[0], e.y_root - self.koltuk[1])

    def koltuk_tasi(self, e):
        if self.surukle:
            self.koltuk = [e.x_root - self.surukle[0], e.y_root - self.surukle[1]]
            self.koltugu_bas()

    def ekran_al(self):
        """Kanzi'siz tüm ekranların görüntüsü. (dosya, imleç x, imleç y) — görüntü pikseliyle."""
        fx, fy = self.kok.winfo_pointerxy()
        self.koken = (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77))  # sanal ekranın sol-üstü
        ekran = os.path.join(tempfile.gettempdir(), "kanzi_v2_ekran.png")
        if self.gorunmez:  # Kanzi zaten görüntüye girmiyor, gizlemeye gerek yok
            ImageGrab.grab(all_screens=True).save(ekran)
            return ekran, fx - self.koken[0], fy - self.koken[1]
        self.kok.withdraw()  # Kanzi ekran görüntüsünde görünmesin
        try:
            self.kok.update()
            time.sleep(0.05)  # pencere ekrandan gerçekten silinsin
            ImageGrab.grab(all_screens=True).save(ekran)
        finally:
            self.kok.deiconify()  # ne olursa olsun Kanzi gizli kalmasın
        self.son_kare = None  # yeniden basılsın
        return ekran, fx - self.koken[0], fy - self.koken[1]

    def sor_yerel(self, metin, sesli, onek="", ekran=False, baglam=None, yakin=False):
        """baglam: eski konuşma da gitsin mi; ekran sorusunda ve açıkla/çevir'de gitmez, yoksa eski konuyu anlatıyor."""
        baglam = not ekran if baglam is None else baglam
        if self.durum in ("dusunuyor", "dinliyor", "cozuyor"):
            self.soyle("Bi dur ya, önceki iş bitmedi (iptal: Ctrl+Alt+X).")
            return
        goruntu = self.ekran_al() if ekran else None
        self.konusmaci.durdur()
        self.istek_no += 1
        no = self.istek_no
        self.durum, self.sesli, self.iptal_edildi, self.yerelde = "dusunuyor", sesli, False, True
        self.akan, self.akan_goster, self.bolucu = "", "", CumleBolucu()
        if onek:
            self.q.put(("parca", (no, onek)))

        def calis():
            soru = metin
            if goruntu:
                try:
                    soru = yerel.ekran_metni(*goruntu, yalniz_yakin=yakin) + "\n\nSoru: " + metin
                except (OSError, subprocess.SubprocessError):  # OCR olmadı: Claude'a geç
                    return self.q.put(("claudea", (no, metin, sesli)))
            try:
                cevap = self.yerel.sor(soru, lambda p: self.q.put(("parca", (no, p))), gecmis=baglam,
                                       iptal=lambda: no != self.istek_no)
            except OSError:  # sunucu düştü ya da cevap vermedi: Claude'a geç
                if not self.yerel.hazir_mi():
                    self.yerel.durum = "kapali"
                return self.q.put(("claudea", (no, metin, sesli)))
            if no == self.istek_no:
                self.q.put(("baloncuk", (no, onek + cevap if cevap else "Cevap veremedim, Claude'a sorayım mı?")))

        threading.Thread(target=calis, daemon=True).start()

    def sor(self, istek, araclar, sesli):
        if self.durum in ("dusunuyor", "dinliyor", "cozuyor"):
            self.soyle("Bi dur ya, önceki iş bitmedi (iptal: Ctrl+Alt+X).")
            return
        if self.ayar["yetki"] == "ogret":
            istek = "(Sadece göster ve öğret modu: hiçbir şeyi kendin yapma, adımı HEDEF ile göster.)\n" + istek
        self.konusmaci.durdur()
        self.istek_no += 1
        self.durum, self.sesli, self.iptal_edildi, self.yerelde = "dusunuyor", sesli, False, False
        self.akan, self.akan_goster, self.bolucu = "", "", CumleBolucu()
        try:
            ekran, fx, fy = self.ekran_al()  # Claude ekran görüntüsü pikseliyle konuşur
        except Exception:
            self.durum = "bos"
            raise
        sistem = SISTEM.format(ekran=ekran, x=fx, y=fy, klasor=KLASOR,
                               py=os.path.join(os.path.dirname(sys.executable), "python.exe"))
        threading.Thread(target=self._claude, args=(istek, araclar, sistem, self.istek_no), daemon=True).start()

    def _claude(self, istek, araclar, sistem, no):
        oturum = open(OTURUM).read().strip() if os.path.exists(OTURUM) else None
        try:
            sonuc, cikti = self._calistir(istek, araclar, sistem, oturum, no)
            if no != self.istek_no:
                return
            if sonuc is None and oturum and "conversation found" in cikti.lower():  # eski oturum yoksa yenisi
                sonuc, cikti = self._calistir(istek, araclar, sistem, None, no)
            if sonuc is not None:
                if sonuc.get("session_id"):
                    with open(OTURUM, "w") as f:
                        f.write(sonuc["session_id"])
                cevap = sonuc.get("result") or ""
                if sonuc.get("is_error"):
                    cevap = f"Hata: {cevap[-300:]}"
            elif self.zaman_asti:
                cevap = "4 dakikada bitmedi, vazgeçtim."
            else:
                cevap = f"Hata: {cikti[-300:] or 'Claude Code cevap vermedi.'}"
        except OSError as e:
            cevap = f"Claude Code çalışmadı: {e}"
        if cevap.startswith("Hata") and yerel.limit_hatasi(cevap):
            return self.q.put(("limit", (no, self.son_soru or istek, self.sesli)))
        self.q.put(("baloncuk", (no, cevap)))

    def _calistir(self, istek, araclar, sistem, oturum, no):
        """Claude'u akışlı çalıştırır; yazı parçalarını kuyruğa atar. (sonuç sözlüğü ya da None, JSON olmayan çıktı)."""
        arg = claude_argumanlari(araclar, sistem) + (["--resume", oturum] if oturum else [])
        self.zaman_asti = False
        self.surec = subprocess.Popen(arg, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", cwd=KLASOR,
                                      env=dict(os.environ, KANZI_ONAY="1" if onay_mi(istek) else "0"),
                                      creationflags=subprocess.CREATE_NO_WINDOW)

        def zaman_doldu():
            self.zaman_asti = True
            self._oldur()  # süreç ağacı arkada çalışmaya devam etmesin

        saat = threading.Timer(240, zaman_doldu)
        saat.start()
        sonuc, diger, yazdi = None, [], False
        try:
            self.surec.stdin.write(istek)
            self.surec.stdin.close()
            for satir in self.surec.stdout:
                try:
                    olay = akis_olayi(json.loads(satir))
                except ValueError:
                    diger.append(satir)
                    continue
                if olay is None:
                    continue
                tur, veri = olay
                if tur == "yazi" and veri:
                    self.q.put(("parca", (no, veri)))
                    yazdi = True
                elif tur == "mesaj" and yazdi:  # araç kullanımı arasındaki ayrı mesajlar birbirine yapışmasın
                    self.q.put(("parca", (no, "\n")))
                elif tur == "sonuc":
                    sonuc = veri
            self.surec.wait()
        finally:
            saat.cancel()
            self.surec = None
        return sonuc, "".join(diger)


if __name__ == "__main__":
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kilit = k32.CreateMutexW(None, False, "KanziV2TekKopya")
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS: zaten açık, ikinci kopya açılmasın
        Kanzi().kok.mainloop()
