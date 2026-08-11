"""
Single-shot extraction worker (run as a subprocess, one file, one parser).

Calls the parser library DIRECTLY — not through extractors/adapters.py, which
deliberately swallows every exception. Here we want failures to surface so the
orchestrator can classify them:
  - normal return           -> {"status": "ok"}          (or "handled" empty)
  - Python exception        -> {"status": "exception", "exc": "<Type>: ..."}
  - MemoryError/Recursion   -> flagged by the orchestrator as DoS-class
  - native crash (segfault) -> process dies by signal; parent sees returncode<0
  - hang                    -> parent kills on timeout

Resource limits are best-effort: RLIMIT_AS/DATA are unreliable on macOS, so the
orchestrator's wall-clock timeout is the primary DoS guard; RLIMIT_CPU is a
backstop for pure-CPU loops.

    python -m fuzz.worker <parser> <path> <mem_mb> <cpu_sec>
"""
from __future__ import annotations
import json
import os
import resource
import sys


def _limit(mem_mb: int, cpu_sec: int) -> None:
    for res in (getattr(resource, "RLIMIT_AS", None),
                getattr(resource, "RLIMIT_DATA", None)):
        if res is not None:
            try:
                resource.setrlimit(res, (mem_mb * 1024 * 1024,) * 2)
            except (ValueError, OSError):
                pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_sec, cpu_sec))
    except (ValueError, OSError):
        pass


def run_pypdf(path: str) -> int:
    from pypdf import PdfReader
    r = PdfReader(path)
    return sum(len(p.extract_text() or "") for p in r.pages)


def run_pdfminer(path: str) -> int:
    from pdfminer.high_level import extract_text
    return len(extract_text(path) or "")


def run_pymupdf(path: str) -> int:
    import fitz
    doc = fitz.open(path)
    total = sum(len(page.get_text()) for page in doc)
    doc.close()
    return total


def run_oletools(path: str) -> int:
    import olefile
    total = 0
    if olefile.isOleFile(path):
        ole = olefile.OleFileIO(path)
        for s in ole.listdir():
            total += len(ole.openstream(s).read())
        ole.close()
    from oletools.olevba import VBA_Parser
    vp = VBA_Parser(path)
    if vp.detect_vba_macros():
        for _f, _s, _n, code in vp.extract_macros():
            total += len(code or "")
    vp.close()
    return total


PARSERS = {
    "pypdf": run_pypdf,
    "pdfminer": run_pdfminer,
    "pymupdf": run_pymupdf,
    "oletools": run_oletools,
}


def main() -> int:
    parser, path, mem_mb, cpu_sec = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    _limit(mem_mb, cpu_sec)
    fn = PARSERS[parser]
    try:
        n = fn(path)
        print(json.dumps({"status": "ok", "text_len": n}))
    except RecursionError as e:
        print(json.dumps({"status": "recursion", "exc": repr(e)[:200]}))
    except MemoryError as e:
        print(json.dumps({"status": "memory", "exc": repr(e)[:200]}))
    except Exception as e:
        print(json.dumps({"status": "exception", "exc": f"{type(e).__name__}: {e}"[:200]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
