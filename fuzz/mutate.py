"""
Format-agnostic byte mutators for seed-based fuzzing.

Deterministic given a seed (reproducible crashes). Strategies deliberately span
the bug classes that hit document parsers: bit/byte corruption (state confusion),
truncation (unexpected EOF), chunk duplication + repeat insertion (allocation /
loop blowups), and 0xFF int fields (integer-overflow-driven allocation).

Optionally shells out to `radamsa` if it's on PATH (a far stronger mutator);
otherwise uses the pure-Python strategies below — no dependency required.
"""
from __future__ import annotations
import os
import random
import shutil
import subprocess

STRATEGIES = ("bitflip", "byteset", "truncate", "chunkdup", "repeat", "intfield")


def mutate(data: bytes, rng: random.Random, keep_header: int = 8) -> tuple[bytes, str]:
    """Return (mutated_bytes, strategy_name). `keep_header` bytes are preserved
    so the parser gets past magic-byte sniffing and into real parsing code."""
    if len(data) <= keep_header + 4:
        return data, "noop"
    strat = rng.choice(STRATEGIES)
    head, body = data[:keep_header], bytearray(data[keep_header:])
    n = len(body)

    if strat == "bitflip":
        for _ in range(rng.randint(1, 16)):
            i = rng.randrange(n)
            body[i] ^= 1 << rng.randrange(8)
    elif strat == "byteset":
        for _ in range(rng.randint(1, 32)):
            body[rng.randrange(n)] = rng.choice((0x00, 0xFF, rng.randrange(256)))
    elif strat == "truncate":
        body = body[: rng.randrange(1, n)]
    elif strat == "chunkdup":
        a = rng.randrange(n)
        b = min(n, a + rng.randrange(1, max(2, n // 4)))
        chunk = body[a:b]
        body[a:a] = chunk * rng.randint(1, 8)
    elif strat == "repeat":
        i = rng.randrange(n)
        body[i:i] = bytes([rng.randrange(256)]) * rng.choice((1024, 65536, 1 << 20))
    elif strat == "intfield":
        for _ in range(rng.randint(1, 8)):
            i = rng.randrange(max(1, n - 4))
            body[i:i + 4] = b"\xff\xff\xff\xff"

    return head + bytes(body), strat


def radamsa_available() -> bool:
    return shutil.which("radamsa") is not None


def radamsa_mutate(path: str, out: str, rng: random.Random) -> str:
    subprocess.run(["radamsa", "-s", str(rng.randrange(1 << 30)), "-o", out, path],
                   check=True, timeout=30)
    return "radamsa"
