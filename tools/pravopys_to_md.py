#!/usr/bin/env python3
"""Convert the official Український правопис PDF into markdown for use as LLM context.

Usage:
    python tools/pravopys_to_md.py [PDF] [-o OUT] [--keep-stress] [--with-preface] [--with-index]

Requires the `pdftotext` binary (poppler-utils).

By default only the normative body (the standard itself, from
«Стандарт державної мови «Український правопис»» up to «ПОКАЖЧИК») is kept,
stress marks are removed, and the result is written to pravopys/pravopys.md.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = ROOT / "pravopys" / "sdm-ukrayinskii-pravopis-vidannia.pdf"
DEFAULT_OUT = ROOT / "pravopys" / "pravopys.md"

BODY_START = "Стандарт державної мови «Український правопис»"
PREFACE_START = "ПЕРЕДМОВА"
INDEX_START = "ПОКАЖЧИК"

COMBINING_ACUTE = "́"
# The PDF font renders stressed Cyrillic vowels as Latin look-alikes.
LATIN_STRESSED = {
    "á": "а", "ó": "о", "é": "е", "ý": "у",
    "Á": "А", "Ó": "О", "É": "Е", "Ý": "У",
}

# Lines that begin a new block (never joined to the previous line).
BLOCK_START_RE = re.compile(
    r"""^(
        §\s*\d+                       # § 12. ...
      | \d+(\.\d+)+\.?\s              # 4.2.1. Heading
      | \d+\.\s                       # 1. numbered part
      | \d+\)\s                       # 1) item
      | [а-яґєії]\)\s                 # а) sub-item
      | Примітк[аи]                   # Примітка / Примітки
      | [–—-]\s                       # dash list item
      | ЗАТВЕРДЖЕНО
    )""",
    re.VERBOSE,
)
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(.*)$")
PARAGRAPH_SIGN_RE = re.compile(r"^(§\s*\d+\.)\s*(.*)$")
PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")


def pdf_to_pages(pdf: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError:
        sys.exit("error: pdftotext not found (install poppler-utils)")
    return out.split("\f")


def drop_page_number(page: str) -> list[str]:
    lines = page.split("\n")
    # pdftotext puts the page number on the first non-empty line.
    for i, line in enumerate(lines):
        if line.strip():
            if PAGE_NUMBER_RE.match(line.strip()):
                del lines[i]
            break
    return lines


def is_cyrillic(ch: str) -> bool:
    return "Ѐ" <= ch <= "ӿ"


def fix_stress(text: str, keep: bool) -> str:
    """Map Latin stressed look-alikes back to Cyrillic; optionally drop stress."""
    out: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch in LATIN_STRESSED:
            j = i - 1
            while j >= 0 and text[j] == "-":  # paradigm endings: душ-á
                j -= 1
            prev = text[j] if j >= 0 else ""
            nxt = text[i + 1] if i + 1 < n else ""
            if is_cyrillic(prev) or is_cyrillic(nxt):
                out.append(LATIN_STRESSED[ch])
                if keep:
                    out.append(COMBINING_ACUTE)
                continue
        if ch == COMBINING_ACUTE and not keep:
            continue
        out.append(ch)
    return "".join(out)


ALPHABET_HEADERS = ["Порядковий номер", "Велика буква", "Мала буква", "Назва букви"]


def fix_alphabet_table(lines: list[str]) -> list[str]:
    """The alphabet table comes out as four vertical columns; rebuild it."""
    try:
        start = lines.index(ALPHABET_HEADERS[0])
    except ValueError:
        return lines
    cols: list[list[str]] = []
    i = start
    for header in ALPHABET_HEADERS:
        while i < len(lines) and lines[i].strip() != header:
            i += 1
        i += 1
        col: list[str] = []
        while i < len(lines) and not lines[i].strip():
            i += 1
        while i < len(lines) and lines[i].strip():
            col.append(lines[i].strip())
            i += 1
        cols.append(col)
    if len({len(c) for c in cols}) != 1:
        return lines  # unexpected shape; leave as-is
    table = [
        "",
        "| " + " | ".join(ALPHABET_HEADERS) + " |",
        "|" + "---|" * len(ALPHABET_HEADERS),
    ]
    for row in zip(*cols):
        table.append("| " + " | ".join(row) + " |")
    table.append("")
    return lines[:start] + table + lines[i:]


def to_markdown(lines: list[str]) -> str:
    blocks: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            blocks.append(join_lines(cur))
            cur.clear()

    in_heading = False
    for raw in split_merged_headings(lines):
        line = raw.strip()
        if raw.startswith("|"):  # pre-built table row
            flush()
            blocks.append(raw)
            in_heading = False
            continue
        if not line:
            # pdftotext emits blank lines at page breaks mid-paragraph too,
            # so a blank line alone does not end a block.
            continue
        if line.startswith("____"):
            continue
        if in_heading and not line[0].islower():
            # A heading only continues onto a wrapped lowercase line;
            # anything else (rule text, table cells) starts a new block.
            flush()
        elif BLOCK_START_RE.match(line) or is_heading_line(line):
            flush()
        if not cur:
            in_heading = bool(PARAGRAPH_SIGN_RE.match(line) or SECTION_RE.match(line))
        cur.append(line)
    flush()

    out: list[str] = []
    for block in blocks:
        if block.startswith("|"):
            # keep table rows contiguous
            if out and out[-1].startswith("|"):
                out[-1] += "\n" + block
            else:
                out.append(block)
            continue
        out.append(format_block(block))
    return "\n\n".join(out).strip() + "\n"


MERGED_HEADING_RE = re.compile(r"^(§\s*\d+\..*?[-–А-ЯҐЄІЇ])(1\.\s.*)$")


def split_merged_headings(lines: list[str]) -> list[str]:
    """pdftotext sometimes glues `§ 21. ... -Н` and `1. Rule text` into one line."""
    out: list[str] = []
    for line in lines:
        m = MERGED_HEADING_RE.match(line.strip())
        if m:
            out.extend([m.group(1), m.group(2)])
        else:
            out.append(line)
    return out


def is_heading_line(line: str) -> bool:
    return line in (BODY_START, PREFACE_START, INDEX_START) or line.isupper() and len(line) > 3


def join_lines(lines: list[str]) -> str:
    text = lines[0]
    for line in lines[1:]:
        if text.endswith("-") and not text.endswith(" -"):
            text += line  # keep the hyphen: compounds like член-кореспондент
        else:
            text += " " + line
    return re.sub(r"[ \t]+", " ", text)


def format_block(block: str) -> str:
    m = PARAGRAPH_SIGN_RE.match(block)
    if m and len(block) < 200:
        return f"#### {m.group(1)} {m.group(2)}".rstrip()
    m = SECTION_RE.match(block)
    if m and len(block) < 160 and not block.rstrip().endswith((",", ";")):
        depth = m.group(1).count(".")  # 4.2 -> 1, 4.2.1 -> 2
        level = "##" if depth <= 1 else "###"
        return f"{level} {m.group(1)}. {m.group(2)}"
    if block in (BODY_START, PREFACE_START, INDEX_START):
        return f"# {block}"
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    ap.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--keep-stress", action="store_true", help="keep stress marks (more tokens)")
    ap.add_argument("--with-preface", action="store_true", help="include the preface and approval decision")
    ap.add_argument("--with-index", action="store_true", help="include the word index (ПОКАЖЧИК)")
    args = ap.parse_args()

    pages = [drop_page_number(p) for p in pdf_to_pages(args.pdf)]
    lines = [line for page in pages for line in page]
    stripped = [line.strip() for line in lines]

    start_marker = PREFACE_START if args.with_preface else BODY_START
    start = stripped.index(start_marker)
    if args.with_index:
        end = len(lines)
    else:
        end = stripped.index(INDEX_START, start)
    lines = fix_alphabet_table(lines[start:end])

    md = to_markdown(lines)
    md = fix_stress(md, keep=args.keep_stress)
    header = (
        "<!-- Generated from the official PDF by tools/pravopys_to_md.py. Do not edit by hand. -->\n\n"
    )
    args.out.write_text(header + md)
    print(f"wrote {args.out} ({len(md):,} chars)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
