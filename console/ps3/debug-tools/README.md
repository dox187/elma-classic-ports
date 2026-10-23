# PPU debugger status

The host's `/usr/bin/gdb.minimal` (Fedora GDB 17.2) supports
`powerpc:common64`, starts successfully, and reads the unstripped ELF. The SDK's
`ppu-gdb` crashes on this host and is not needed for ELF inspection.

**Do not use the remote snapshot script with the current RPCS3 server.**
A live test on 2026-10-23 read PC/LR/SP and stack memory, but RPCS3 rejected
GDB's detach packet and subsequently timed out its debugger server, freezing
emulation. No guest memory/register writes or breakpoints were issued. This
server is unsuitable for routine sampling until its disconnect/resume behavior
is fixed and verified in a disposable test instance. Use in-process timing
counters for performance work instead.

The `snapshot.sh` script is retained as a disabled diagnostic record. It refuses
to connect by default. Only a separately verified compatible remote server may
be used with an explicit `ELMA_ALLOW_DEBUGGER_ATTACH=1` override; this override
is not approval to attach to any existing emulator session.

Read-only offline ELF inspection remains available:

```sh
/usr/bin/gdb.minimal --nx --batch console/ps3/build/elma.elf \
  -ex 'set architecture powerpc:common64' -ex 'set endian big' -ex 'info files'
```
