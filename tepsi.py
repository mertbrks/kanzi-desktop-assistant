"""Görev çubuğu tepsisinde Kanzi simgesi (ek paket yok: Shell_NotifyIcon, ctypes).
Sol tık: göster/gizle. Sağ tık: menü. Seçimler kuyruğa ("tepsi", ad) olarak düşer; Kanzi ana döngüsü işler."""
import ctypes
import ctypes.wintypes as wt
import threading

u32, s32, k32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.DefWindowProcW.restype = LRESULT
u32.CreateWindowExW.restype = wt.HWND
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
u32.LoadImageW.restype = wt.HANDLE
u32.CreatePopupMenu.restype = wt.HMENU
u32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
u32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID]
k32.GetModuleHandleW.restype = wt.HMODULE

GERI = 0x8000 + 1  # WM_APP+1: simgeye tıklanınca gelen mesaj
MENU = {1: "goster", 2: "sohbet", 3: "ayarlar", 4: "cik"}


class _WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class _NID(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wt.HICON)]


class Tepsi:
    def __init__(self, q, ikon, gizli_mi):
        self.q, self.ikon, self.gizli_mi = q, ikon, gizli_mi  # gizli_mi(): menüde "Göster" mi "Gizle" mi yazsın
        self.hwnd = None
        threading.Thread(target=self._calis, daemon=True).start()

    def _islem(self, hwnd, msg, wp, lp):
        if msg == GERI and lp == 0x0202:  # WM_LBUTTONUP
            self.q.put(("tepsi", "goster"))
        elif msg == GERI and lp == 0x0205:  # WM_RBUTTONUP
            m = u32.CreatePopupMenu()
            u32.AppendMenuW(m, 0, 1, "Göster" if self.gizli_mi() else "Gizle")
            u32.AppendMenuW(m, 0, 2, "Sohbet (Ctrl+Alt+C)")
            u32.AppendMenuW(m, 0, 3, "Ayarlar (Ctrl+Alt+O)")
            u32.AppendMenuW(m, 0x800, 0, None)  # ayraç
            u32.AppendMenuW(m, 0, 4, "Kanzi'yi kapat")
            nokta = wt.POINT()
            u32.GetCursorPos(ctypes.byref(nokta))
            u32.SetForegroundWindow(hwnd)  # yoksa menü dışına tıklayınca kapanmıyor
            secim = u32.TrackPopupMenu(m, 0x0100, nokta.x, nokta.y, 0, hwnd, None)  # TPM_RETURNCMD
            u32.DestroyMenu(m)
            if secim in MENU:
                self.q.put(("tepsi", MENU[secim]))
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    def _calis(self):
        self._proc = WNDPROC(self._islem)  # çöpe gitmesin
        sinif = _WNDCLASS(lpfnWndProc=self._proc, hInstance=k32.GetModuleHandleW(None), lpszClassName="KanziTepsi")
        u32.RegisterClassW(ctypes.byref(sinif))
        self.hwnd = u32.CreateWindowExW(0, "KanziTepsi", "Kanzi", 0, 0, 0, 0, 0, None, None, sinif.hInstance, None)
        simge = u32.LoadImageW(None, self.ikon, 1, 0, 0, 0x10 | 0x40)  # IMAGE_ICON, LR_LOADFROMFILE|LR_DEFAULTSIZE
        self.nid = _NID(cbSize=ctypes.sizeof(_NID), hWnd=self.hwnd, uID=1, uFlags=0x1 | 0x2 | 0x4,
                        uCallbackMessage=GERI, hIcon=simge, szTip="Kanzi v2 · sağ tık: menü")
        s32.Shell_NotifyIconW(0, ctypes.byref(self.nid))  # NIM_ADD
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def kaldir(self):
        """Kanzi kapanırken: simge tepside asılı kalmasın."""
        if self.hwnd:
            s32.Shell_NotifyIconW(2, ctypes.byref(self.nid))  # NIM_DELETE
