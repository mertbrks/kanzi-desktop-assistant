"""Kanzi v2'nin kulağı (Whisper) ve ağzı (edge-tts, cümle cümle akışlı). İlk Kanzi'den (Desktop/claude/kanzi, iptal) alındı."""
import asyncio
import ctypes
import glob
import os
import queue
import re
import site
import tempfile
import threading
import time

import edge_tts
import numpy as np
import speech_recognition as sr

HIZ, PARCA = 16000, 1024
MODEL = "large-v3-turbo"
SESLER = {"Ahmet": "tr-TR-AhmetNeural", "Emel": "tr-TR-EmelNeural"}
UYDURMA_SON = re.compile(r"[\s.,!]*(abone ol(mayı unutmayın)?|izlediğiniz için teşekkür(ler| ederim))[\s.!]*$", re.I)


def cuda_dll_yollari():
    # pip ile gelen nvidia-cublas/cudnn DLL'leri PATH'te değil; Windows'a gösteriyoruz
    for kok in site.getsitepackages():
        for d in glob.glob(os.path.join(kok, "Lib", "site-packages", "nvidia", "*", "bin")) + \
                 glob.glob(os.path.join(kok, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


def seviye(veri):
    x = np.frombuffer(veri, np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x * x)))


def sesli_temizle(metin):
    metin = re.sub(r"```.*?```", " ", metin, flags=re.S)
    metin = re.sub(r"https?://\S+", "bağlantı", metin)
    return re.sub(r"[*_#`>|]", "", metin).strip()


class Kulak:
    """Ekran kartında Whisper; yüklenemezse Google."""

    def __init__(self):
        self.model = None

    def yukle(self):
        try:
            cuda_dll_yollari()
            from faster_whisper import WhisperModel
            self.model = WhisperModel(MODEL, device="cuda", compute_type="float16")
            self.model.transcribe(np.zeros(HIZ, np.float32), language="tr")  # ilk çağrı yavaş, ısıt
            return "internetsiz · ekran kartı"
        except Exception:
            return "Google · internet"

    def bosalt(self):
        """Whisper'ı ekran kartından atar (~1,8 GB); bundan sonra Google ile tanınır."""
        import gc
        self.model = None
        gc.collect()

    def coz(self, ham):
        model = self.model  # tanırken bosalt() çağrılsa da bu çözüm bitsin
        if not model:
            try:
                return sr.Recognizer().recognize_google(sr.AudioData(ham, HIZ, 2), language="tr-TR")
            except sr.UnknownValueError:
                return ""
        ses = np.frombuffer(ham, np.int16).astype(np.float32) / 32768
        parcalar, _ = model.transcribe(ses, language="tr", beam_size=5, condition_on_previous_text=False,
                                            hotwords="Kanzi")
        metin = " ".join(p.text.strip() for p in parcalar if p.no_speech_prob < 0.6).strip()
        return UYDURMA_SON.sub("", metin).strip()  # Whisper sessizlikte altyazı kalıpları uydurur


class CumleBolucu:
    """Claude'dan parça parça gelen yazıyı okunacak cümlelere böler: ilk cümle hemen çıkar, okuma beklemeden başlar."""

    SON = re.compile(r"(?<=[.!?…])\s+|\n+")

    def __init__(self):
        self.tampon = ""

    def ekle(self, parca):
        self.tampon += parca
        *tamam, self.tampon = self.SON.split(self.tampon)
        if len(self.tampon) > 220:  # noktasız uzun cümle: virgülden böl, okuma beklemesin
            k = self.tampon.rfind(", ", 0, 220)
            if k > 40:
                tamam.append(self.tampon[:k + 1])
                self.tampon = self.tampon[k + 2:]
        return [c for c in map(okunacak, tamam) if c]

    def bitir(self):
        kalan, self.tampon = okunacak(self.tampon), ""
        return [kalan] if kalan else []


def okunacak(metin):
    metin = re.sub(r"HEDEF:\s*\d*\s*,?\s*\d*", "", metin)  # tıklama koordinatı okunmaz
    return sesli_temizle(metin)


class Konusmaci:
    """Cümleleri sırayla seslendirir: biri çalarken sıradaki üretilir (Sesli Komut'taki gibi).
    Üretim ve çalma ayrı iş parçacıklarında; MCI açma/çalma/kapama hep çalan iş parçacığında."""

    def __init__(self, hiz="+20%"):
        self.hiz, self.no, self.caliyor = hiz, 0, False
        self.metinler, self.dosyalar = queue.Queue(), queue.Queue()
        self.mci = ctypes.windll.winmm.mciSendStringW
        threading.Thread(target=self._uret, daemon=True).start()
        threading.Thread(target=self._cal, daemon=True).start()

    def ekle(self, cumle, ses="tr-TR-AhmetNeural"):
        self.metinler.put((self.no, cumle, ses))

    def durdur(self):
        self.no += 1  # kuyruktaki eski cümleler atlanır, çalan parça kesilir

    def _uret(self):
        while True:
            no, cumle, ses = self.metinler.get()
            if no != self.no:
                continue
            yol = os.path.join(tempfile.gettempdir(), f"kanzi_v2_{time.time_ns()}.mp3")
            try:
                asyncio.run(edge_tts.Communicate(cumle, ses, rate=self.hiz).save(yol))
            except Exception:  # internet yoksa o cümle atlanır, yazı zaten baloncukta
                continue
            self.dosyalar.put((no, yol))

    def _cal(self):
        durum = ctypes.create_unicode_buffer(32)
        while True:
            no, yol = self.dosyalar.get()
            if no == self.no:
                self.caliyor = True
                self.mci(f'open "{yol}" type mpegvideo alias kanziv2', None, 0, 0)
                self.mci("play kanziv2", None, 0, 0)
                while no == self.no:
                    self.mci("status kanziv2 mode", durum, 32, 0)
                    if durum.value != "playing":
                        break
                    time.sleep(0.04)
                self.mci("close kanziv2", None, 0, 0)
                self.caliyor = not self.dosyalar.empty()
            try:
                os.remove(yol)
            except OSError:
                pass
