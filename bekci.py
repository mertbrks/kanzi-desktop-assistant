"""Kanzi v2 bekçisi: Claude'un PowerShell/Bash komutlarını çalışmadan önce denetleyen PreToolUse hook'u.

Gönderme gibi geri alınamaz adımlar yalnızca kullanıcı o mesajda onay verdiyse (KANZI_ONAY=1) geçer;
silme, kurulum, kapatma, kayıt defteri hiç geçmez. Engellenince çıkış kodu 2: Claude sebebi görür.
shortcut: metin kalıbıyla yakalar, kasıtlı gizlenmiş komutu kaçırabilir; Claude'a karşı değil kazaya karşı.
"""
import json
import os
import re
import sys

ONAYLI = re.compile(r"\.Send\s*\(|Send-MailMessage|SendKeys.*(%s|\{ENTER\}|~)", re.I)
YASAK = re.compile(r"Remove-Item|\b(rm|del|erase|rmdir|rd)\b\s|Clear-RecycleBin|Format-Volume|"
                   r"Stop-Computer|Restart-Computer|\bshutdown\b|\breg(\.exe)?\s+(add|delete)|"
                   r"Set-ItemProperty\s+.*HK(LM|CU)|winget|choco\s|msiexec|Install-(Module|Package)|\.Delete\s*\(", re.I)


def karar(komut, onay):
    """Engel sebebi (str) ya da None (geçebilir)."""
    if YASAK.search(komut):
        return "Kanzi bekçisi: silme, kurulum, kapatma ve sistem ayarı yasak. Kullanıcıya bunu kendisinin yapmasını söyle."
    if ONAYLI.search(komut) and not onay:
        return "Kanzi bekçisi: göndermek geri alınamaz. Taslağı göster ve 'Göndereyim mi?' diye sor; onaylarsa gönder."
    return None


if __name__ == "__main__":
    girdi = json.load(sys.stdin)
    sebep = karar((girdi.get("tool_input") or {}).get("command", ""), os.environ.get("KANZI_ONAY") == "1")
    if sebep:
        sys.stderr.reconfigure(encoding="utf-8")  # Windows'ta varsayılan cp1254, Türkçe harfler bozuluyordu
        print(sebep, file=sys.stderr)
        sys.exit(2)
