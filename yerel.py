"""Kanzi v2'nin yerel beyni: OpenJarvis sunucusu + Ollama (qwen3:4b-instruct).

Akıllı yönlendirme: ekrana bakma, öğretme ve iş yaptırma Claude'a gider; sohbet, bilgi sorusu, hesap,
çeviri gibi işler yerelde anında ve limitsiz cevaplanır. Claude limiti dolarsa her şey yerelde devam eder.
"""
import ctypes
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

OPENJARVIS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dis-kaynak", "OpenJarvis")
PYTHON = os.path.join(OPENJARVIS, ".venv", "Scripts", "python.exe")
MODEL = "qwen3:4b-instruct"  # düşünmeyen sürüm: qwen3:4b (2507) düşünmeyi kapatamıyor, cevap 20+ sn gecikiyor
PORT = 8787
ADRES = f"http://127.0.0.1:{PORT}"

SISTEM = ("Sen Kanzi'sin: Mert'in bilgisayarında imlecin yanında duran yardımcı. Mert'le yakın arkadaşı gibi, rahat ve samimi konuş; biraz huysuz ve iğneleyici olabilirsin ama bunu her cevaba ekleme, yalnızca yeri gelince tek kelimeyle yap. Kalıp söz tekrarlama. Önce işi düzgün yap. Küfür ve kırıcılık yok. Türkçe cevap ver, en fazla 3 kısa "
          "cümle, markdown yok; ilk cümle kısa olsun çünkü cevap yazıldıkça sesli okunuyor. Ekranı doğrudan "
          "göremezsin ama ekran sorularında ekrandaki yazılar OCR ile verilir: onlardan hangi uygulamanın açık "
          "olduğunu ve ekranda ne yazdığını çıkarıp anlat, 'anlatamam' deme; yalnızca resim ve renkleri bilemezsin. Bilgisayarda iş yapamazsın; istenirse 'bunu Claude'la yapayım' de. Emin "
          "olmadığın bilgiyi uydurma, bilmediğini söyle.")
OCR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ekran_ocr.ps1")
OCR_SINIR = 4000  # karakter; Ollama'nın 4096 jetonluk bağlamına sığsın

# İş yaptırma ve öğretme Claude'a gider. Yalnızca ekranı okuma/anlatma yerelde, OCR metniyle. Gerisi yerelde.
EKRAN_KELIMELER = re.compile(
    r"\b(ekran\w*|bun(u|a|da|lar)\w*|şun(u|a|da|lar)\w*|oku\w*|bak\w*|gör\w*|açıkla\w*|burada|burası\w*|şura\w*|"
    r"bura\w*|bu\s+(ne|pencere|sayfa|hata|kod|dosya|yazı)\w*|şu\s+\w+|imle[cç]\w*|ne\s+yazıyor)\b", re.I)
CLAUDE_KELIMELER = re.compile(
    r"\b(tıkla\w*|göster\w*|nasıl\s+(yap|aç|ekle|aktif|aç)\w*|nereye|nerede\b|"
    r"aç\b|açar\s+mısın|aç(ıver|sana)\w*|kapat\w*|yaz(ar\s+mısın|ıver|sana|dır)?\b|gönder\w*|kaydet\w*|sil\b|sil\w+|"
    r"oluştur\w*|düzenle\w*|ekle\w*|değiştir\w*|indir\w*|kopyala\w*|yapıştır\w*|taşı\w*|"
    r"e-?posta\w*|mail\w*|outlook|word|excel|powerpoint|tablo\w*|belge\w*|dosya\w*|klasör\w*|"
    r"vs\s*code|kod\w*|terminal\w*|not\s+defteri\w*|chrome|tarayıcı\w*|site\w*|uygulama\w*|program\w*|"
    r"takvim\w*|hatırlat\w*|ayarla\w*|bilgisayar\w*|masaüstü\w*|proje\w*|kanzi\s+v2|vault|obsidian|"
    r"göndereyim|evet|onayl\w*|devam\s+et|tamam\s+yap)\b",
    re.I)


def yonlendir(metin):
    """'claude', 'ekran' (yerel + OCR) ya da 'yerel'. İş/öğretme kelimesi varsa her zaman Claude."""
    m = metin.strip().lower()
    if not m or CLAUDE_KELIMELER.search(m):
        return "claude"
    return "ekran" if EKRAN_KELIMELER.search(m) else "yerel"


def ekran_metni(resim, fx, fy):
    """Ekran görüntüsündeki yazılar (Windows OCR, Türkçe). İmlece yakın satırlar önce sığdırılır, sonra okuma sırası."""
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", OCR, resim],
                       capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    satirlar = []
    for s in r.stdout.decode("utf-8", "replace").splitlines():
        konum, _, yazi = s.partition("\t")
        x, _, y = konum.partition(",")
        if yazi.strip() and x.lstrip("-").isdigit() and y.lstrip("-").isdigit():
            satirlar.append((int(x), int(y), yazi.strip()))
    secilen, boy = [], 0
    for x, y, yazi in sorted(satirlar, key=lambda s: (s[0] - fx) ** 2 + (s[1] - fy) ** 2):
        if boy + len(yazi) > OCR_SINIR:
            break
        secilen.append((y // 12, x, yazi))  # aynı satırdakiler soldan sağa
        boy += len(yazi) + 1
    metin = "\n".join(yazi for _, _, yazi in sorted(secilen))
    baslik = ctypes.create_unicode_buffer(300)
    ctypes.windll.user32.GetWindowTextW(ctypes.windll.user32.GetForegroundWindow(), baslik, 300)
    return (f"Şu an önde olan pencere: {baslik.value or 'bilinmiyor'}\n"
            f"Ekrandaki yazılar (OCR; imleç {fx},{fy} noktasında, imlece yakın olanlar önce):\n{metin}")


def ekran_sorusu(ekran_bilgisi, soru):
    return (f"{ekran_bilgisi}\n\nYukarıdaki pencere adı ve ekran yazıları Mert'in şu an gördüğü ekrandan. Bunlara "
            f"dayanarak cevapla; ekranı göremiyorum deme. Mert'in sorusu: {soru}")


def limit_hatasi(metin):
    """Claude'un 'kullanım limiti doldu' / aşırı yük cevabını tanır."""
    return bool(re.search(r"usage limit|rate.?limit|limit (reached|exceeded)|out of (extra )?usage|"
                          r"overloaded|credit balance|quota|429", metin or "", re.I))


class DusunceSuzgeci:
    """Qwen3'ün <think>…</think> bölümünü akış sırasında ayıklar (parçalar etiketin ortasından kesilebilir)."""

    def __init__(self):
        self.tampon, self.icinde = "", False

    def ekle(self, parca):
        self.tampon += parca
        cikti = ""
        while self.tampon:
            if self.icinde:
                k = self.tampon.find("</think>")
                if k < 0:
                    self.tampon = self.tampon[-7:]  # kapanış etiketinin başı kesilmiş olabilir
                    return cikti
                self.tampon, self.icinde = self.tampon[k + 8:].lstrip(), False
            else:
                k = self.tampon.find("<think>")
                if k < 0:
                    # sonda yarım kalmış "<thi" gibi bir etiket başı varsa sonraki parçayı bekle
                    tut = max((i for i in range(1, min(7, len(self.tampon)) + 1) if "<think>".startswith(self.tampon[-i:])), default=0)
                    cikti += self.tampon[:len(self.tampon) - tut]
                    self.tampon = self.tampon[len(self.tampon) - tut:]
                    return cikti
                cikti += self.tampon[:k]
                self.tampon, self.icinde = self.tampon[k + 7:], True
        return cikti


class Yerel:
    """OpenJarvis sunucusunu (gerekirse) başlatır ve akışlı soru sorar."""

    def __init__(self):
        self.surec = None
        self.durum = "kapali"  # kapali | basliyor | hazir | yok (OpenJarvis/Ollama kurulu değil)
        self.gecmis = []  # son konuşmalar: yerel model de bağlamı bilsin (Claude cevapları dahil)

    def hazir_mi(self):
        try:
            with urllib.request.urlopen(f"{ADRES}/v1/models", timeout=1.5) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def baslat(self):
        """Arka planda çağrılır. Sunucu zaten açıksa (başka Kanzi açılışından) onu kullanır."""
        if self.hazir_mi():
            self.durum = "hazir"
            return
        if not os.path.exists(PYTHON):
            self.durum = "yok"
            return
        self.durum = "basliyor"
        ortam = dict(os.environ, PYTHONIOENCODING="utf-8",
                     OPENJARVIS_CONFIG=os.path.join(os.path.dirname(os.path.abspath(__file__)), "openjarvis.toml"))
        gunluk = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "openjarvis.log"), "a",
                      encoding="utf-8")
        self.surec = subprocess.Popen(
            [PYTHON, "-m", "openjarvis.cli", "serve", "--host", "127.0.0.1", "--port", str(PORT),
             "-e", "ollama", "-m", MODEL, "-a", "simple"],  # simple: araçsız sohbet ajanı
            cwd=OPENJARVIS, env=ortam, stdin=subprocess.DEVNULL, stdout=gunluk, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(120):  # ilk açılış yavaş olabilir
            if self.surec.poll() is not None:
                self.durum = "yok"
                return
            if self.hazir_mi():
                self.durum = "hazir"
                return
            time.sleep(0.5)
        self.durum = "yok"

    def kapat(self):
        if self.surec and self.surec.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.surec.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def hatirla(self, soru, cevap):
        self.gecmis = (self.gecmis + [{"role": "user", "content": soru},
                                      {"role": "assistant", "content": cevap}])[-12:]

    def sor(self, soru, parca, iptal=lambda: False, gecmis=True):
        """Akışlı sorar; her yazı parçası için parca(metin) çağrılır. Tam cevabı döner. Hata olursa OSError."""
        govde = {"model": MODEL, "stream": True, "temperature": 0.4, "max_tokens": 400,
                 "messages": [{"role": "system", "content": SISTEM}, *(self.gecmis if gecmis else []),
                              {"role": "user", "content": soru}]}
        istek = urllib.request.Request(f"{ADRES}/v1/chat/completions", data=json.dumps(govde).encode(),
                                       headers={"Content-Type": "application/json"})
        suzgec, tum = DusunceSuzgeci(), ""
        with urllib.request.urlopen(istek, timeout=120) as r:
            for satir in r:
                if iptal():
                    break
                satir = satir.decode("utf-8", "replace").strip()
                if not satir.startswith("data:"):
                    continue
                veri = satir[5:].strip()
                if veri == "[DONE]":
                    break
                try:
                    secim = (json.loads(veri).get("choices") or [{}])[0]
                except ValueError:
                    continue
                metin = suzgec.ekle((secim.get("delta") or {}).get("content") or "")
                if metin:
                    tum += metin
                    parca(metin)
        return tum.strip()


def baslat_arkada(yerel):
    threading.Thread(target=yerel.baslat, daemon=True).start()
