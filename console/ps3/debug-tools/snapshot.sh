#!/usr/bin/env bash
# Read-only RPCS3 PPU snapshot. Only connect to the user's designated instance.
set -euo pipefail
if [[ ${ELMA_ALLOW_DEBUGGER_ATTACH:-0} != 1 ]]; then
    echo "Remote attach disabled: current RPCS3 debugger rejects detach and freezes." >&2
    echo "Use offline ELF inspection or in-process timing counters." >&2
    exit 2
fi
if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "Usage: $0 /path/to/matching/elma.elf localhost-port [output.txt]" >&2
    exit 2
fi
elf=$1
port=$2
output=${3:-ps3-stack-snapshot.txt}
if [[ ! -f $elf || ! $port =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
    echo "A matching ELF file and a numeric localhost port (1..65535) are required." >&2
    exit 2
fi
port=$((10#$port))
gdb_bin=${ELMA_GDB:-/usr/bin/gdb.minimal}
if [[ ! -x $gdb_bin ]]; then
    echo "Set ELMA_GDB to a working GDB supporting powerpc:common64." >&2
    exit 2
fi
# Remote attachment briefly stops the designated emulator. Detach resumes it.
# timeout is a last resort; normal GDB packet waits expire after ten seconds.
# This script sends no memory/register writes and changes no breakpoints.
status=0
timeout --signal=INT --kill-after=5s 45s "$gdb_bin" --nx --batch "$elf" \
    -ex 'set pagination off' \
    -ex 'set confirm off' \
    -ex 'set remotetimeout 10' \
    -ex 'set architecture powerpc:common64' \
    -ex 'set endian big' \
    -ex "target remote 127.0.0.1:$port" \
    -ex 'info threads' \
    -ex 'info registers pc lr r1 r2' \
    -ex 'x/24gx $r1' \
    -ex 'thread apply all bt 24' \
    -ex 'detach' >"$output" 2>&1 || status=$?
cat "$output"
exit "$status"
