import ctypes
from ctypes import wintypes

wininet = ctypes.WinDLL("wininet", use_last_error=True)
wininet.InternetQueryOptionW.restype = wintypes.BOOL
wininet.InternetQueryOptionW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
wininet.InternetSetOptionW.restype = wintypes.BOOL
wininet.InternetSetOptionW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

OPT = 75  # INTERNET_OPTION_PER_CONNECTION_OPTION

class VAL(ctypes.Union):
    _fields_ = [("dwValue", wintypes.DWORD), ("pszValue", wintypes.LPWSTR), ("ftValue", wintypes.FILETIME)]

class OPTION(ctypes.Structure):
    _fields_ = [("dwOption", wintypes.DWORD), ("Value", VAL)]

class LIST(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("pszConnection", wintypes.LPWSTR),
                ("dwOptionCount", wintypes.DWORD), ("dwOptionError", wintypes.DWORD),
                ("pOptions", ctypes.POINTER(OPTION))]

count = 4
opts = (OPTION * count)()
for i, o in enumerate([1, 2, 3, 4]):
    opts[i].dwOption = o
lst = LIST(ctypes.sizeof(LIST), None, count, 0, opts)
size = wintypes.DWORD(ctypes.sizeof(LIST))
ok = wininet.InternetQueryOptionW(None, OPT, ctypes.byref(lst), ctypes.byref(size))
print("query ok:", bool(ok), "err:", ctypes.get_last_error(), "size:", size.value)
if ok:
    for o in opts:
        v = o.Value.pszValue if o.dwOption in (2, 3, 4) and o.Value.pszValue else o.Value.dwValue
        print("  ", o.dwOption, repr(v))
    lst.dwSize = ctypes.sizeof(LIST)
    ok2 = wininet.InternetSetOptionW(None, OPT, ctypes.byref(lst), lst.dwSize)
    print("set noop ok:", bool(ok2), "err:", ctypes.get_last_error())
