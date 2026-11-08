from kanzi_v2 import GEN, YUK, claude_argumanlari, hedef_konum

# normalde imlecin sağ-altı
assert hedef_konum(100, 100, (0, 0, 1920, 1080)) == (118, 118)
# sağ alt köşede pencere imlecin sol-üstüne geçer, ekrandan taşmaz
x, y = hedef_konum(1900, 1070, (0, 0, 1920, 1080))
assert x + GEN <= 1900 and y + YUK <= 1070
# açıklama modunda yalnızca okuma aracı izinli
a = claude_argumanlari("Read", "s")
assert a[a.index("--allowedTools") + 1:a.index("--append-system-prompt")] == ["Read"]
print("tamam")
from kanzi_v2 import hedef_ayikla
assert hedef_ayikla("Ekle menüsüne tıkla.\nHEDEF: 412, 88") == ("Ekle menüsüne tıkla.", (412, 88))
assert hedef_ayikla("Bitti.") == ("Bitti.", None)
print("tamam 2")
from kanzi_v2 import ekrana_cevir
assert ekrana_cevir((100, 50), (-1920, 0)) == (-1820, 50)  # solda ikinci monitör varsa
print("tamam 3")
import os, tempfile
from kanzi_v2 import VARSAYILAN, ayar_oku, ayar_yaz
yol = os.path.join(tempfile.gettempdir(), "kanzi_v2_ayar_test.json")
open(yol, "w").write("bozuk{")
assert ayar_oku(yol) == VARSAYILAN  # bozuk dosya varsayılana döner
open(yol, "w").write('{"sesli": "evet", "ses": "Kemal", "yetki": "ogret", "fazla": 1}')
assert ayar_oku(yol) == dict(VARSAYILAN, yetki="ogret")  # yanlış türler/değerler atılır
ayar_yaz(dict(VARSAYILAN, sesli=False, ses="Emel"), yol)
assert ayar_oku(yol) == dict(VARSAYILAN, sesli=False, ses="Emel")
ayar_yaz(dict(VARSAYILAN, renk="Gökkuşağı", sekil="Elmas"), yol)
assert ayar_oku(yol) == dict(VARSAYILAN, sekil="Elmas")  # bilinmeyen renk varsayılana döner
os.remove(yol)
print("tamam 4")
from kanzi_v2 import akis_olayi
assert akis_olayi({"type": "stream_event", "event": {"type": "content_block_delta",
                   "delta": {"type": "text_delta", "text": "Mer"}}}) == ("yazi", "Mer")
assert akis_olayi({"type": "stream_event", "event": {"type": "content_block_delta",
                   "delta": {"type": "thinking_delta", "thinking": ""}}}) is None
assert akis_olayi({"type": "result", "result": "x"})[0] == "sonuc"
assert akis_olayi({"type": "system"}) is None
from ses import CumleBolucu
b = CumleBolucu(); c = []
for p in ["Merhaba", " Mert! Bu", "gün ", "nasılsın? Ekle ", "menüsüne tıkla.\nHEDEF: 12", ",34"]:
    c += b.ekle(p)
assert c + b.bitir() == ["Merhaba Mert!", "Bugün nasılsın?", "Ekle menüsüne tıkla."]
print("tamam 5")
from kanzi_v2 import onay_mi
from bekci import karar
assert onay_mi("Evet gönder") and onay_mi("gönder") and not onay_mi("Prof. Lee'ye e-posta yaz, gönder")
taslak = "$m=$o.CreateItem(0); $m.To='a@b.c'; $m.Display()"
assert karar(taslak, False) is None  # taslak serbest
assert karar("$m.Send()", False) and karar("$m.Send()", True) is None  # gönderme onayla geçer
assert karar("Remove-Item C:\\x.txt", True) and karar("del x.txt", True)  # silme onayla bile yasak
assert karar("Get-ChildItem | Select Name", False) is None
print("tamam 6")
from yerel import DusunceSuzgeci, limit_hatasi, yonlendir
for m in ["Merhaba nasılsın?", "Fotosentez nedir?", "125'in yüzde 18'i kaç?", "İngilizcede 'özlemek' ne demek?",
          "Bana kısa bir fıkra anlat"]:
    assert yonlendir(m) == "yerel", m
for m in ["Prof. Lee'ye e-posta taslağı hazırla", "Word'e tablo ekle", "Not Defteri'ni aç",
          "Bunu nasıl yaparım, göster", "Evet gönder", "Ekranı oku ve bu dosyayı kaydet", ""]:
    assert yonlendir(m) == "claude", m
for m in ["Bu ekranda ne var?", "şu hatayı açıkla", "ekranı anlat", "burada ne yazıyor", "bunu oku"]:
    assert yonlendir(m) == "ekran", m
assert limit_hatasi("Claude AI usage limit reached|1762") and not limit_hatasi("Bitti.")
s = DusunceSuzgeci(); out = ""
for p in ["<thi", "nk>\nhmm düşün", "üyorum</th", "ink>\n\nMerhaba", " Mert! <", "3 değil"]:
    out += s.ekle(p)
out += s.tampon
assert out == "Merhaba Mert! <3 değil", repr(out)
print("tamam 6")
from kanzi_v2 import yer_komutu
for m in ["köşeye geç", "Köşede bekle.", "kanka git otur", "koltuğuna geç", "otur", "kenara çekil"]:
    assert yer_komutu(m) == "otur", m
for m in ["gel", "Buraya gel!", "kalk", "hadi yanıma gel"]:
    assert yer_komutu(m) == "gel", m
for m in ["oturum açma ekranında ne yazıyor bana anlat", "fotosentez nedir", "geliştirici modu nasıl açılır"]:
    assert yer_komutu(m) is None, m
print("tamam koltuk")
import datetime
from isler import hatirlatma, medya_komutu
n = datetime.datetime(2026, 11, 8, 14, 0)
assert hatirlatma("20 dakika sonra çamaşırı asmayı hatırlat", n) == (1200, "çamaşırı asmayı")
assert hatirlatma("bana yarım saat sonra toplantıyı hatırlat.", n) == (1800, "toplantıyı")
assert hatirlatma("saat 15:30'da annemi aramayı hatırlat", n) == (5400, "annemi aramayı")
assert hatirlatma("saat 13:00'te hatırlat", n)[0] == 23 * 3600  # geçmiş saat: yarın
assert hatirlatma("25 dakikalık odak başlat", n)[0] == 1500
assert hatirlatma("hatırlatmaları göster") == ("liste", "") and hatirlatma("hatırlatmaları iptal et") == ("sil", "")
assert hatirlatma("pisagor teoremini hatırlat") is None  # süre yok: normal soru
assert medya_komutu("şarkıyı geç")[0] == "sonraki" and medya_komutu("Sesi kıs.")[0] == "kıs"
assert medya_komutu("sesli cevabı aç") is None and medya_komutu("devam et") is None
yol = os.path.join(tempfile.gettempdir(), "kanzi_v2_ayar_test.json")
ayar_yaz(dict(VARSAYILAN, oturuyor=True, hatirlatmalar=[[1.5, "su"], ["bozuk"], [2, 3]]), yol)
assert ayar_oku(yol) == dict(VARSAYILAN, oturuyor=True, hatirlatmalar=[[1.5, "su"]])
os.remove(yol)
import gorunum as gg
sag, sol = (gg.kare("bos", False, (0, 0), 0, 0, 0, "Merhaba kanka", 420, 16, None, sol=s_) for s_ in (False, True))
assert sag.size == sol.size and sol.getpixel((sol.width - gg.kw() // 2, sol.height // 2))[3] > 200  # küre sağda
print("tamam hatırlatma")
from isler import turkce_mi
assert turkce_mi("Bugün hava güzel") and turkce_mi("bu iyi") and not turkce_mi("Please submit before Friday.")
print("tamam çeviri")
