# Kanzi v2

İmlecin yanında duran koyu mavi cam küre. Ekrana bakar, açıklar, adım adım öğretir ve komutla bilgisayarda iş yapar.
Beyni Claude Code (`claude -p`, akışlı). Kulağı Whisper, sesi edge-tts (`ses.py`). Görünüm `gorunum.py`. İlk Kanzi'nin (`../kanzi`, iptal) yerini alır, ona bağımlı değil.

Aç: masaüstündeki **Kanzi v2** kısayolu (ya da `python kanzi_v2.py`).

| Kısayol | Ne yapar |
|---|---|
| Ctrl+Alt+Space | Yazarak komut ver. `yeni konu` yazarsan konuşma sıfırlanır |
| Ctrl+Alt+S | Konuş: bir kez bas, konuş, tekrar bas. Cevap sesli okunur |
| Ctrl+Alt+A | Seçili metni ya da imlecin üstündekini açıkla. Yerel beyin açıksa yerelde (seçim yoksa OCR), değilse Claude (tıklanacak yeri de gösterir) |
| Ctrl+Alt+T | Seçili metni çevir: Türkçe → İngilizce yerelde, başka dil → Türkçe Claude'da (4B model Türkçeyi bozuyor) |
| Ctrl+Alt+→ / ← | Uzun cevap sayfalara bölünür (1/3…) ve kendiliğinden ilerler; bununla ileri/geri git. Baloncuk kapandıysa son sayfayı geri getirir |
| Ctrl+Alt+C | Sohbet penceresi (ayarlar tasarımında): tüm konuşma geçmişi (`sohbet.json`, son 300 mesaj, kapatıp açınca da durur) + yazma kutusu, yeni mesajlar canlı düşer |
| Ctrl+Alt+M | Sesli cevabı aç/kapa |
| Ctrl+Alt+O | Ayarlar: sesli cevap, ses (Ahmet/Emel), görünüm (6 renk, küre/yumuşak kare/elmas/yıldız, kravat), yetki, yerel beyin, konuşmayı sıfırla |
| Ctrl+Alt+X | Süren işi, sesli okumayı ve gösterilen adımı durdur |
| Ctrl+Alt+Q | Kapat |

- **Öğretme:** "nasıl yapılır" diye sorarsan Kanzi kırmızı okla tıklanacak yere gider. Oraya tıklayınca sıradaki adıma kendisi geçer, iş bitince "Bitti" der.
- **Yetki (Ayarlar):** "İş yapabilir" seçiliyse Word COM, `code`, klavye ve fareyle iş yapar. E-posta: Outlook'ta hesap yok, Gmail bağlayıcısıyla (`create_draft`) yalnızca taslak hazırlar; gönderme izni yok, Gmail'den sen gönderirsin. "Sadece göstersin" seçiliyse hiçbir şeye dokunmaz, yalnızca okuyup gösterir.
- **Yüz ve karakter:** kanka gibi, biraz huysuz. Gözbebekleri kafasına göre etrafa bakar, arada göz devirir, süzer, sırıtır. İş bitince çoğu zaman sırıtır, hata/iptalde kızar ya da üzülür, 15 sn içinde 4 kez çağrılınca kızar, fareyi sağa sola sallarsan "Dur be" der, 90 sn dokunulmazsa uyuklar. İfadeler: normal, mutlu, şaşkın, üzgün, uykulu, düşünceli, kızgın, bıkkın, şüpheli, sırıtan (`gorunum.karakter(..., ifade)`).
- **Akışlı cevap:** Claude yazdıkça baloncuk dolar; ilk cümle biter bitmez okunmaya başlar, biri okunurken sıradaki hazırlanır (Sesli Komut'taki gibi, %20 hızlı).
- **Koltuk:** "köşeye geç", "köşede bekle", "git otur" deyince sol alttaki bordo koltuğuna oturur; "gel" ya da "kalk" deyince imlece döner. Koltuğu fareyle sürükleyebilirsin, yeri `ayarlar.json`da (koltuk) kalır. Kapatıp açınca oturuyorsa koltukta başlar (oturuyor). Koltuk sağ kenardaysa baloncuk sola açılır.
- **Hatırlatıcı (`isler.py`, Claude'suz):** "20 dakika sonra çamaşırı hatırlat", "saat 15:30'da annemi aramayı hatırlat", "25 dakikalık odak başlat", "hatırlatmaları göster / iptal et". Zamanı gelince koltuktan kalkıp gelir, sesli moddaysa okur. `ayarlar.json`da (hatirlatmalar) durur; Kanzi kapalıyken geçen "biraz geç kaldım" diye söylenir.
- **Yazma:** `yaz: …` ya da `aynen yaz …` dersen (sesle ya da yazarak) Claude'a gitmeden, anında, o an seçili kutuya aynen yazar (Sesli Komut gibi); komut kutusu/sohbet penceresi açıkken önceki pencereye yazar. "Arama kutusuna X yaz", "şu mesaja kibar cevap yaz" gibi isteklerde Claude kutuyu ekran görüntüsünde bulur, `tikla_yaz.py` ile tıklar ve yazar (sona ekler; `--degistir` ile eskisinin yerine). Enter'a basmaz, panoya dokunmaz. Yetki "İş yapabilir" olmalı.
- **Müzik:** "şarkıyı geç", "önceki şarkı", "müziği durdur", "sesi kıs/aç/kapat": medya tuşlarına basar (Spotify, YouTube…).
- **Dans:** bilgisayardan ses gelince (Core Audio ses ölçer, ek paket yok) ritimle zıplar, koltuktaysa kafa sallar; kendi konuşması sayılmaz.
- **Mola:** 2 saat ara vermeden kullanınca (5 dk boşta kalmak mola sayılır) "kalk biraz" der; 01:00–06:00 arası 45 dakikada bir "yatsana artık" der.
- **Ekran görüntülerinde görünmez** (`SetWindowDisplayAffinity` WDA_EXCLUDEFROMCAPTURE): soru sorarken gizlenip yanıp sönmez; yan etkisi: senin ekran görüntülerinde ve ekran paylaşımında da çıkmaz.
- Ayarlar `ayarlar.json`, konuşma `oturum.txt`, hatalar ve çökme izleri `kanzi_v2.log` dosyasında.
- Gereken: Claude Code girişi; `pillow`, `numpy`, `faster-whisper`, `SpeechRecognition`, `PyAudio`, `edge-tts`. Mikrofon yalnızca Ctrl+Alt+S'ye basınca açılır.
- Test: `python test_kanzi_v2.py`. Kanzi ekran görüntüsünde görünmez; görerek doğrulamak için `KANZI_GORUNUR=1` ile aç, bitince normal kısayoldan yeniden aç.

## Yerel beyin (yerel.py)
Basit sorular (bilgi, hesap, çeviri, sohbet) Claude'a gitmez: OpenJarvis sunucusu (`../dis-kaynak/OpenJarvis`, port 8787, ayarı `openjarvis.toml`) üzerinden Ollama'daki `qwen3:4b-instruct`'a gider; ilk kelime ~0,4 sn, limitsiz. Ekran, öğretme ve iş yaptırma (`yonlendir()` kelime listesi; şüphede) Claude'da kalır. Claude'un limiti dolarsa soru yerelde cevaplanır. Kanzi açılınca sunucuyu kendisi başlatır, kapanınca kapatır; günlük `openjarvis.log`. Ayarlar'da açılıp kapatılır.
- **Ekranı okuma yerelde:** "ekranı anlat", "burada ne yazıyor", "bu hata ne diyor" gibi yalnızca okuma isteyen sorularda ekranın yazısı Windows OCR (`ekran_ocr.ps1`, Türkçe, ek paket yok, ~0,5 sn) ile çıkarılıp önde olan pencerenin adıyla yerel modele verilir. İş yaptırma ve öğretme kelimesi varsa Claude; Ctrl+Alt+A da yerelde.
- `qwen3:4b` (2507) kullanma: düşünmeyi kapatamıyor, İngilizce düşünüp 15–25 sn gecikiyor.

## Bekçi (bekci.py)
Claude'un her PowerShell/Bash komutu çalışmadan önce `bekci.py`'den geçer (`.claude/settings.json` hook'u).
E-posta gönderme (`.Send()`, SendKeys ile gönder) yalnızca o mesaj "evet / gönder / onaylıyorum" ile başlıyorsa geçer;
silme, kurulum, kapatma, kayıt defteri hiç geçmez. Kalıp tabanlıdır: kazaya karşı korur, kasıtlı gizlemeye karşı değil.
