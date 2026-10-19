#!/usr/bin/env python3
"""Headless PCSX-Redux harness for the Elasto Mania PSX port.

Usage as a library:

    from pcsx import run
    r = run(exe="build/hello.exe", lua="test/hello_test.lua",
            map_file="build/hello.map", timeout=60,
            args={"frames": "120"})
    assert r.returncode == 0, r.output

Usage on the command line:

    python3 test/pcsx.py --exe build/hello.exe --map build/hello.map \
        --lua test/hello_test.lua [--iso X.cue] [--pcdrv DIR] [--8mb] \
        [--timeout 60] [--arg key=value ...] [--redux PATH]

The emulator is started as `-cli -no-ui -testmode -noupdate -stdout -run`
(plus `-exe`/`-iso`, `-8mb`, `-pcdrv`/`-pcdrvbase`, `-fastboot`) and the Lua
script is run with `-dofile`. What it prints (stdout of the emulator and of
Lua `print`) is captured in `Result.output`: the first 1 MB and the last 8 MB,
the whole of it up to 64 MB in output.log of the work directory. The process
exit code is the one passed to `PCSX.quit(code)` in Lua; a timeout kills the
emulator and returns 124, more than 256 MB of output (a run stuck in a loop)
kills it and returns 125.

Resources: the emulator runs in a systemd scope of its own with MemoryMax 3G
and no swap (PCSX_MEMORY_MAX overrides it, 0 turns it off), so that a runaway
run is killed alone and never takes the user's session with it.

BIOS: no Sony BIOS is needed. PCSX-Redux logs `Could not open BIOS ... Retrying
with the OpenBIOS` and boots its bundled OpenBIOS, which runs PS-EXEs and
discs with SYSTEM.CNF. The harness sets HOME and XDG_CONFIG_HOME to a private
directory so the user's emulator settings and memory cards are untouched.

Silent and invisible by default: the emulator runs under `xvfb-run` (private
X server, WAYLAND_DISPLAY removed, Mesa software GL) and with the SDL dummy
audio driver; PULSE_SERVER/PIPEWIRE_REMOTE point nowhere. Pass --visible
(visible=True) / --sound (sound=True) only when the user asks to see or hear
it. Run long tests with the Bash tool's run_in_background option.

Lua helpers
-----------
The harness does not pass your script to `-dofile` directly. It generates a
prelude that defines the global table `elma` and then runs your script:

  elma.args            table of the --arg key=value pairs (strings)
  elma.sym(name)       address of a symbol read from the .map file (or nil)
  elma.u8/u16/u32(a)   read guest RAM (KSEG0/KSEG1/physical addresses all
                       work: the address is masked to the RAM size)
  elma.write_u32(a,v)  write guest RAM
  elma.on_frame(fn)    fn(n) is called once per emulated frame (GPU vsync),
                       n counts from 1
  elma.press(port, name) / elma.release(port, name)
                       pad input, see below
  elma.screenshot(path) write the current display as a PPM image
  elma.vram(path)       write the whole 1024x512 VRAM as a PPM image
  PCSX.quit(code)       end the run with this exit code

(a) Pad input from Lua: VERIFIED. PCSX-Redux exposes
    PCSX.SIO0.slots[1].pads[1].setOverride(PCSX.CONSTS.PAD.BUTTON.CROSS) and
    clearOverride(button). Button names: CROSS CIRCLE SQUARE TRIANGLE UP DOWN
    LEFT RIGHT L1 L2 R1 R2 SELECT START. elma.press(port, "CROSS") wraps it
    (port 1 or 2). The game sees the press through the normal BIOS pad
    driver, so the real pad code path is exercised.
(b) RAM reads from Lua: VERIFIED. PCSX.getMemPtr() returns a LuaJIT cdata
    pointer to guest RAM (2 MB, or 8 MB with --8mb); elma.u32 etc. wrap it.
(c) Screenshot / VRAM: VERIFIED. PCSX.GPU.takeScreenShot() returns
    {width, height, bpp, data}; PCSX.GPU.getVRAM() returns the 1024x512 VRAM
    (RGB555 or 24 bit depending on the build). elma.screenshot() and
    elma.vram() write PPM files.

Other useful facts: PCSX.getCPUCycles() returns the emulated cycle counter
(for profiling), PCSX.pauseEmulator()/resumeEmulator() pause and resume,
PCSX.getRegisters() gives the CPU registers.
"""

import argparse
import collections
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

DEFAULT_HOME = os.path.expanduser("~/.local/share/elma-psx")
DEFAULT_REDUX = os.path.join(
    DEFAULT_HOME, "pcsx-redux", "PCSX-Redux-HEAD-x86_64.AppImage")

LUA_LIB = r'''
local ffi = require("ffi")
local mem = PCSX.getMemPtr()
local mask = 0x1fffff
elma.ram8 = elma.args.ram8 == "1"
if elma.ram8 then mask = 0x7fffff end

function elma.sym(name) return elma.symbols[name] end
function elma.u8(a) return mem[bit.band(a, mask)] end
function elma.u16(a) return ffi.cast("uint16_t*", mem + bit.band(a, mask))[0] end
function elma.u32(a) return ffi.cast("uint32_t*", mem + bit.band(a, mask))[0] end
function elma.write_u32(a, v) ffi.cast("uint32_t*", mem + bit.band(a, mask))[0] = v end

local frame = 0
local listeners = {}
function elma.on_frame(fn) listeners[#listeners + 1] = fn end
elma._vsync = PCSX.Events.createEventListener("GPU::Vsync", function()
    frame = frame + 1
    for _, fn in ipairs(listeners) do fn(frame) end
end)

local function pad_of(port) return PCSX.SIO0.slots[port].pads[1] end
function elma.press(port, name)
    pad_of(port).setOverride(PCSX.CONSTS.PAD.BUTTON[name])
end
function elma.release(port, name)
    pad_of(port).clearOverride(PCSX.CONSTS.PAD.BUTTON[name])
end

local function write_ppm(path, w, h, rgb)
    local f = assert(io.open(path, "wb"))
    f:write(string.format("P6\n%d %d\n255\n", w, h))
    f:write(rgb)
    f:close()
end

-- Convert a raw bitmap (a binary string: 24-bit RGB or 16-bit RGB555 LE) to
-- RGB bytes for a PPM file.
local function to_rgb(w, h, str)
    local out = {}
    local p = ffi.cast("const uint8_t*", str)
    if #str >= w * h * 3 then
        for i = 0, w * h - 1 do
            out[#out + 1] = string.char(p[i * 3], p[i * 3 + 1], p[i * 3 + 2])
        end
    else
        for i = 0, w * h - 1 do
            local v = p[i * 2] + p[i * 2 + 1] * 256
            local r = bit.band(v, 31) * 255 / 31
            local g = bit.band(bit.rshift(v, 5), 31) * 255 / 31
            local b = bit.band(bit.rshift(v, 10), 31) * 255 / 31
            out[#out + 1] = string.char(r, g, b)
        end
    end
    return table.concat(out)
end

-- Only valid once the emulator has run a few frames (the first frames
-- return an empty 0x0 image).
function elma.screenshot(path)
    local ss = PCSX.GPU.takeScreenShot()
    write_ppm(path, ss.width, ss.height, to_rgb(ss.width, ss.height, tostring(ss.data)))
end

function elma.vram(path)
    local v = PCSX.GPU.getVRAM()
    write_ppm(path, 1024, 512, to_rgb(1024, 512, tostring(v)))
end
'''


@dataclass
class Result:
    returncode: int
    output: str
    timed_out: bool


def read_symbols(map_file):
    """Parse an `nm -f posix -l -n` map: 'name type addr [size] [file:line]'."""
    syms = {}
    if not map_file:
        return syms
    with open(map_file) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3 and re.fullmatch(r"[0-9a-fA-F]+", parts[2]):
                syms[parts[0]] = int(parts[2], 16) & 0xFFFFFFFF
    return syms


def lua_quote(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def run(exe=None, iso=None, lua=None, map_file=None, timeout=60, pcdrv=None,
        ram8=False, fastboot=False, args=None, redux=None, workdir=None,
        extra_flags=(), visible=False, sound=False):
    """Run PCSX-Redux headless and silent and return a Result.

    By default the emulator runs inside a private Xvfb server (nothing
    appears on the user's desktop) with audio forced to SDL's dummy driver.
    visible=True runs on the user's display, sound=True allows real audio.
    """
    redux = redux or os.environ.get("PCSX_REDUX") or DEFAULT_REDUX
    args = dict(args or {})
    if ram8:
        args["ram8"] = "1"
    workdir = os.path.abspath(workdir or tempfile.mkdtemp(prefix="pcsx-"))
    os.makedirs(workdir, exist_ok=True)

    prelude = os.path.join(workdir, "prelude.lua")
    with open(prelude, "w") as f:
        f.write("elma = {args = {%s}, symbols = {%s}}\n" % (
            ", ".join("[%s] = %s" % (lua_quote(k), lua_quote(str(v)))
                      for k, v in args.items()),
            ", ".join("[%s] = %d" % (lua_quote(k), v)
                      for k, v in read_symbols(map_file).items())))
        f.write(LUA_LIB)
        if lua:
            # An error in the script would otherwise leave the emulator
            # running until the timeout.
            f.write("local ok, err = pcall(dofile, %s)\n"
                    "if not ok then print('LUA ERROR: ' .. tostring(err)); "
                    "PCSX.quit(99) end\n" % lua_quote(os.path.abspath(lua)))

    cmd = [redux, "-cli", "-no-ui", "-testmode", "-noupdate", "-stdout", "-run"]
    if exe:
        cmd += ["-exe", os.path.abspath(exe)]
    if iso:
        cmd += ["-iso", os.path.abspath(iso)]
    if ram8:
        cmd += ["-8mb"]
    if fastboot:
        cmd += ["-fastboot"]
    if pcdrv:
        cmd += ["-pcdrv", "-pcdrvbase", os.path.abspath(pcdrv)]
    cmd += list(extra_flags)
    cmd += ["-dofile", prelude]

    env = dict(os.environ)
    # PCSX-Redux keeps its settings and memory cards under $HOME/.config.
    home = os.path.join(workdir, "home")
    os.makedirs(home, exist_ok=True)
    env["HOME"] = home
    env["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
    if not visible:
        # Private X server; WAYLAND_DISPLAY must go or SDL would prefer the
        # user's compositor. Mesa llvmpipe provides the OpenGL context.
        env.pop("WAYLAND_DISPLAY", None)
        env["SDL_VIDEODRIVER"] = "x11"
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24"] + cmd
    if not sound:
        env["SDL_AUDIODRIVER"] = "dummy"
        env["PULSE_SERVER"] = "unix:/nonexistent/pulse"
        env["PIPEWIRE_REMOTE"] = "/nonexistent/pipewire"
        env["ALSA_CONFIG_PATH"] = "/dev/null"

    # A memory limit of its own: a runaway emulator is killed alone instead
    # of the kernel's OOM killer taking down the whole terminal session.
    memory_max = os.environ.get("PCSX_MEMORY_MAX", "3G")
    if memory_max != "0" and shutil.which("systemd-run"):
        cmd = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
               "-p", "MemoryMax=" + memory_max, "-p", "MemorySwapMax=0", "--"] + cmd

    # The emulator runs in its own process group: on a timeout or an
    # interrupt the whole group (xvfb-run, Xvfb, the AppImage and its child)
    # is killed, otherwise the emulator outlives xvfb-run.
    p = subprocess.Popen(cmd, env=env, cwd=workdir, start_new_session=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = _BoundedOutput(os.path.join(workdir, "output.log"))
    reader = threading.Thread(target=output.drain, args=(p.stdout,), daemon=True)
    reader.start()
    timed_out = False
    try:
        deadline = time.monotonic() + timeout
        while p.poll() is None:
            if output.total > OUTPUT_KILL_BYTES:
                break
            if time.monotonic() > deadline:
                timed_out = True
                break
            time.sleep(0.1)
    finally:
        _kill_group(p)
        p.wait()
        reader.join(5)
        output.close()
    text = output.text()
    if output.total > OUTPUT_KILL_BYTES:
        return Result(125, text + "\n[pcsx.py] killed: more than %d MB of output\n"
                      % (OUTPUT_KILL_BYTES >> 20), False)
    if timed_out:
        return Result(124, text + "\n[pcsx.py] timeout\n", True)
    return Result(p.returncode, text, False)


# Output of one run: the start and the end are kept in memory, the whole of
# it (up to a limit) in output.log of the work directory. A run that prints
# more than OUTPUT_KILL_BYTES is stopped: it is stuck in a loop.
OUTPUT_HEAD_BYTES = 1 << 20
OUTPUT_TAIL_BYTES = 8 << 20
OUTPUT_LOG_BYTES = 64 << 20
OUTPUT_KILL_BYTES = 256 << 20


class _BoundedOutput:
    def __init__(self, log_path):
        self.head = bytearray()
        self.tail = collections.deque()
        self.tail_bytes = 0
        self.total = 0
        self.log = open(log_path, "wb")
        self.logged = 0

    def drain(self, stream):
        for chunk in iter(lambda: stream.read1(65536), b""):
            self.total += len(chunk)
            if self.logged < OUTPUT_LOG_BYTES:
                self.log.write(chunk[:OUTPUT_LOG_BYTES - self.logged])
                self.logged += len(chunk)
            if len(self.head) < OUTPUT_HEAD_BYTES:
                take = OUTPUT_HEAD_BYTES - len(self.head)
                self.head += chunk[:take]
                chunk = chunk[take:]
            if chunk:
                self.tail.append(chunk)
                self.tail_bytes += len(chunk)
                while self.tail_bytes - len(self.tail[0]) >= OUTPUT_TAIL_BYTES:
                    self.tail_bytes -= len(self.tail.popleft())

    def close(self):
        self.log.close()

    def text(self):
        skipped = self.total - len(self.head) - self.tail_bytes
        middle = b"\n[pcsx.py] %d bytes of output left out\n" % skipped if skipped > 0 else b""
        return (bytes(self.head) + middle + b"".join(self.tail)).decode(errors="replace")


def _kill_group(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exe")
    ap.add_argument("--iso")
    ap.add_argument("--lua")
    ap.add_argument("--map")
    ap.add_argument("--pcdrv")
    ap.add_argument("--8mb", dest="ram8", action="store_true")
    ap.add_argument("--fastboot", action="store_true")
    ap.add_argument("--visible", action="store_true",
                    help="show the emulator window on the user's display")
    ap.add_argument("--sound", action="store_true",
                    help="allow real audio output")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--redux")
    ap.add_argument("--workdir")
    ap.add_argument("--grep", metavar="REGEX",
                    help="print only the output lines matching REGEX")
    ap.add_argument("--arg", action="append", default=[], metavar="KEY=VALUE")
    o = ap.parse_args()
    args = dict(a.split("=", 1) for a in o.arg)
    r = run(o.exe, o.iso, o.lua, o.map, o.timeout, o.pcdrv, o.ram8,
            o.fastboot, args, o.redux, o.workdir,
            visible=o.visible, sound=o.sound)
    if o.grep:
        rx = re.compile(o.grep)
        sys.stdout.write("".join(l + "\n" for l in r.output.splitlines()
                                 if rx.search(l)))
    else:
        sys.stdout.write(r.output)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
