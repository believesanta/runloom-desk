"""Mist: restrained cool tones inspired by a forest in fog."""
BG = '#141e23'
SIDEBAR = '#10181c'
PANEL = '#1a272d'
TEXT = '#dce5e7'
MUTED = '#9bafb6'
ACCENT = '#b4c9cf'
BORDER = '#304148'
BUTTON = '#25363e'
HOVER = '#344b55'
PRIMARY = '#405f6b'
SELECTED = '#304952'
ERROR = '#ddb1a4'


def dark_titlebar(window):
    """Opt into Windows' dark caption; other systems keep their native caption."""
    import sys
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    window.update_idletasks()
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    hwnd = user32.GetParent(window.winfo_id())
    value = ctypes.c_int(1)
    try:
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except OSError:
        pass
