"""
Normalize public email corpora into loose attachment files the differ consumes.

Public phishing/spam corpora (Nazario, SpamAssassin, CEAS, Enron) ship as .eml
or mbox files. This loader walks those, pulls every attachment out, and writes
it into an output directory under a safe, de-duplicated name, preserving the
original extension so the differ can format-detect it.

    python corpus/loader.py <src.eml|src.mbox|dir> corpus/real/

Guardrails (see README scope note):
  - text/plain and text/html body parts are skipped (this study is attachments,
    not bodies) unless --bodies is passed.
  - nothing is executed; bytes are only written to disk. Keep any corpus that
    may contain live malware in a sandboxed, gitignored path.
"""
from __future__ import annotations
import email
import hashlib
import mailbox
import os
import sys
from email.message import Message

KEEP_EXTS = (".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
             ".rtf", ".ole", ".zip", ".htm", ".html")


def _safe_name(filename: str, payload: bytes) -> str:
    base = os.path.basename(filename or "attachment")
    base = "".join(c if c.isalnum() or c in "._-" else "_" for c in base) or "attachment"
    digest = hashlib.sha1(payload).hexdigest()[:10]
    stem, ext = os.path.splitext(base)
    return f"{stem}.{digest}{ext}"


def _attachments(msg: Message):
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        is_attachment = "attachment" in disp or filename is not None
        is_body = ctype in ("text/plain", "text/html")
        if is_body and not is_attachment:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        yield filename, payload


def _messages(src: str):
    if os.path.isdir(src):
        for dirpath, _dirs, files in os.walk(src):
            for f in files:
                p = os.path.join(dirpath, f)
                if f.lower().endswith(".mbox"):
                    yield from (m for m in mailbox.mbox(p))
                else:
                    with open(p, "rb") as fh:
                        yield email.message_from_binary_file(fh)
    elif src.lower().endswith(".mbox"):
        yield from (m for m in mailbox.mbox(src))
    else:
        with open(src, "rb") as fh:
            yield email.message_from_binary_file(fh)


def extract_attachments(src: str, out_dir: str, keep_only: bool = True) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    for msg in _messages(src):
        for filename, payload in _attachments(msg):
            name = _safe_name(filename or "attachment", payload)
            if keep_only and not name.lower().endswith(KEEP_EXTS):
                continue
            out = os.path.join(out_dir, name)
            if not os.path.exists(out):
                with open(out, "wb") as fh:
                    fh.write(payload)
                written.append(out)
    return written


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python corpus/loader.py <src.eml|.mbox|dir> <out-dir> [--all]")
        return 1
    src, out_dir = argv[0], argv[1]
    keep_only = "--all" not in argv
    written = extract_attachments(src, out_dir, keep_only=keep_only)
    print(f"extracted {len(written)} attachment(s) -> {out_dir}")
    for w in written:
        print(f"  {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
