#!/usr/bin/env python3
"""
sfm2pdf - typeset a loose SFM/USFM file with PTXprint and open the PDF.

    sfm2pdf JER22F-hsb.txt
    sfm2pdf JER22F-hsb.txt --sty my.sty --changes mychanges.txt
    sfm2pdf --gui            # open PTXprint on the preview project to adjust layout

PTXprint only works on Paratext projects, so this script keeps a small,
persistent "fake" project (SFMPREV) in your user data folder. Each run drops
your file into it with the right Paratext file name and runs PTXprint headless.
Because the project persists, any layout/font settings you change in the
PTXprint GUI (sfm2pdf --gui) are reused for every later preview.
"""

import argparse
import configparser
import itertools
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = "SFMPREV"
POSTPART = f"{PROJECT}.SFM"

# Paratext book codes -> file-name numbers.
CANON = {
    "FRT": "A0", "BAK": "A1", "OTH": "A2",
    "INT": "A7", "CNC": "A8", "GLO": "A9",
    "TDX": "B0", "NDX": "B1",
    "GEN": "01", "EXO": "02", "LEV": "03", "NUM": "04", "DEU": "05",
    "JOS": "06", "JDG": "07", "RUT": "08", "1SA": "09", "2SA": "10",
    "1KI": "11", "2KI": "12", "1CH": "13", "2CH": "14", "EZR": "15",
    "NEH": "16", "EST": "17", "JOB": "18", "PSA": "19", "PRO": "20",
    "ECC": "21", "SNG": "22", "ISA": "23", "JER": "24", "LAM": "25",
    "EZK": "26", "DAN": "27", "HOS": "28", "JOL": "29", "AMO": "30",
    "OBA": "31", "JON": "32", "MIC": "33", "NAM": "34", "HAB": "35",
    "ZEP": "36", "HAG": "37", "ZEC": "38", "MAL": "39",
    "MAT": "41", "MRK": "42", "LUK": "43", "JHN": "44", "ACT": "45",
    "ROM": "46", "1CO": "47", "2CO": "48", "GAL": "49", "EPH": "50",
    "PHP": "51", "COL": "52", "1TH": "53", "2TH": "54", "1TI": "55",
    "2TI": "56", "TIT": "57", "PHM": "58", "HEB": "59", "JAS": "60",
    "1PE": "61", "2PE": "62", "1JN": "63", "2JN": "64", "3JN": "65",
    "JUD": "66", "REV": "67",
    "XXA": "94", "XXB": "95", "XXC": "96", "XXD": "97", "XXE": "98",
    "XXF": "99",
}

DEFAULT_FONT = "Charis SIL"
# PTXprint stores each face as "Family|Style|...". Style names follow the
# pattern PTXprint wrote for Charis SIL; other fonts may name them differently.
FONT_FACES = {
    "fontregular": "",
    "fontbold": " Bold",
    "fontitalic": " Italic",
    "fontbolditalic": " Italic Bold",
}


class CaseConfigParser(configparser.ConfigParser):
    """ConfigParser that keeps key case as PTXprint wrote it."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def book_number(code):
    if code not in CANON:
        sys.exit(f"sfm2pdf: unknown book code '{code}'. Use --book to set one.")
    return CANON[code]


def data_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "sfm2pdf"


def find_ptxprint(explicit=None):
    candidates = [explicit, os.environ.get("PTXPRINT_BIN"), shutil.which("ptxprint")]
    if os.name == "nt":
        candidates.append(r"C:\Program Files\PTXprint\ptxprint.exe")
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    sys.exit("sfm2pdf: can't find PTXprint. Put it on PATH, set PTXPRINT_BIN, "
             "or use --ptxprint PATH.")


def read_text(path, fallback_encoding):
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        print(f"sfm2pdf: {path} is not UTF-8; reading as {fallback_encoding}.")
        return raw.decode(fallback_encoding)


def write_settings(projdir, lang):
    (projdir / "Settings.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<ScriptureText>
  <Name>{PROJECT}</Name>
  <FullName>SFM preview</FullName>
  <Language>Preview</Language>
  <LanguageIsoCode>{lang}:::</LanguageIsoCode>
  <Encoding>65001</Encoding>
  <Versification>4</Versification>
  <StyleSheet>usfm.sty</StyleSheet>
  <FileNamePrePart></FileNamePrePart>
  <FileNamePostPart>{POSTPART}</FileNamePostPart>
  <FileNameBookNameForm>41MAT</FileNameBookNameForm>
  <BooksPresent>{'1' * 123}</BooksPresent>
</ScriptureText>
""", encoding="utf-8")


def find_config(projdir, config):
    """Return the ptxprint.cfg for this configuration (existing or to be created)."""
    for cfg in projdir.rglob("ptxprint.cfg"):
        if cfg.parent.name == config:
            return cfg
    return projdir / "shared" / "ptxprint" / config / "ptxprint.cfg"


def set_font(projdir, config, family, only_if_missing):
    """Write the body font into ptxprint.cfg.

    With only_if_missing=True (no --font given), an existing font choice, e.g.
    one made in the PTXprint GUI, is left alone.
    """
    cfgpath = find_config(projdir, config)
    cp = CaseConfigParser(interpolation=None)
    if cfgpath.exists():
        cp.read(cfgpath, encoding="utf-8")
    section = next((s for s in cp.sections() if cp.has_option(s, "fontregular")),
                   "document")
    if only_if_missing and cp.has_option(section, "fontregular") \
            and cp.get(section, "fontregular").split("|")[0].strip():
        return
    if not cp.has_section(section):
        cp.add_section(section)
    wanted = {k: f"{family}|{style}|false|false|" for k, style in FONT_FACES.items()}
    if all(cp.get(section, k, fallback=None) == v for k, v in wanted.items()):
        return
    for k, v in wanted.items():
        cp.set(section, k, v)
    cfgpath.parent.mkdir(parents=True, exist_ok=True)
    with open(cfgpath, "w", encoding="utf-8") as f:
        cp.write(f)
    print(f"Font set to {family} in {cfgpath}")


MARKER_RE = re.compile(r"^\\Marker\s+(\S+)", re.MULTILINE)


def merge_styles(target, source):
    """Add the marker definitions in `source` to the stylesheet `target`.

    PTXprint always reads the configuration's ptxprint.sty (it ignores a
    project custom.sty here). Definitions for the same markers are replaced,
    so repeated runs don't pile up duplicates; other styles, including ones
    changed in the PTXprint GUI, are kept.
    """
    new = Path(source).read_text(encoding="utf-8-sig").strip()
    names = set(MARKER_RE.findall(new))
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    starts = [m.start() for m in MARKER_RE.finditer(old)] + [len(old)]
    kept = [old[:starts[0]].rstrip()]
    for a, b in itertools.pairwise(starts):
        block = old[a:b].strip()
        m = MARKER_RE.match(block)
        if m and m.group(1) not in names:
            kept.append(block)
    merged = "\n\n".join(x for x in kept + [new] if x) + "\n"
    if merged != old:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(merged, encoding="utf-8")


def open_file(path):
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def main():
    ap = argparse.ArgumentParser(description="Preview a loose SFM/USFM file with PTXprint.")
    ap.add_argument("infile", nargs="?", help="SFM/USFM file to typeset")
    ap.add_argument("-o", "--output", help="PDF path (default: next to the input file)")
    ap.add_argument("--book", help="3-letter book code (default: from the \\id line)")
    ap.add_argument("--sty", help="stylesheet defining your own markers (merged into "
                                  "the configuration's ptxprint.sty)")
    ap.add_argument("--changes", help="regex changes file applied before typesetting "
                                      "(becomes PrintDraftChanges.txt)")
    ap.add_argument("--font", help=f"body font family (default: keep the configured "
                                   f"font, or {DEFAULT_FONT} if none is set)")
    ap.add_argument("--config", default="Default", help="PTXprint configuration name")
    ap.add_argument("--lang", default="en", help="language ISO code for Settings.xml")
    ap.add_argument("--encoding", default="cp1252",
                    help="encoding to assume if the file isn't UTF-8 (default cp1252)")
    ap.add_argument("--ptxprint", help="path to the PTXprint executable")
    ap.add_argument("--gui", action="store_true",
                    help="open the PTXprint GUI on the preview project instead")
    ap.add_argument("--no-open", action="store_true", help="don't open the PDF")
    argv = sys.argv[1:]
    if "--" in argv:  # everything after -- goes straight to PTXprint
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    else:
        extra = []
    args = ap.parse_args(argv)

    ptx = find_ptxprint(args.ptxprint)
    projects = data_dir() / "projects"
    projdir = projects / PROJECT
    projdir.mkdir(parents=True, exist_ok=True)
    if not (projdir / "Settings.xml").exists():
        write_settings(projdir, args.lang)

    set_font(projdir, args.config, args.font or DEFAULT_FONT,
             only_if_missing=args.font is None)

    if args.gui:
        subprocess.run([ptx, "-p", str(projects), PROJECT], check=False)
        return
    if not args.infile:
        ap.error("an input file is required (or use --gui)")

    text = read_text(args.infile, args.encoding)
    book = args.book
    if not book:
        m = re.search(r"^\s*\\id\s+(\S{3})", text, re.MULTILINE)
        if not m:
            sys.exit("sfm2pdf: no \\id line found; use --book JER (etc.).")
        book = m.group(1)
    book = book.upper()
    if not re.search(r"^\s*\\id\s", text, re.MULTILINE):
        text = f"\\id {book}\n" + text

    # Replace any book files left from earlier runs with this one.
    for old in projdir.glob(f"*{POSTPART}"):
        old.unlink()
    (projdir / f"{book_number(book)}{book}{POSTPART}").write_text(text, encoding="utf-8")

    # Custom markers: stylesheet and/or pre-typesetting regex changes.
    if args.sty:
        merge_styles(find_config(projdir, args.config).parent / "ptxprint.sty", args.sty)
    changes = projdir / "PrintDraftChanges.txt"
    if args.changes:
        shutil.copyfile(args.changes, changes)
    elif changes.exists():
        changes.unlink()

    cmd = [ptx, "-P", "-q", "-p", str(projects), "-c", args.config,
           "-b", book, *extra, PROJECT]
    print("Running:", " ".join(cmd))
    start = time.time()
    result = subprocess.run(cmd, check=False)

    # PTXprint's output name/location varies by version, so take the newest PDF.
    pdfs = [p for p in projdir.rglob("*.pdf") if p.stat().st_mtime >= start - 1]
    if not pdfs:
        logs = [p for p in projdir.rglob("*.log") if p.stat().st_mtime >= start - 1]
        where = (f"Check {max(logs, key=lambda p: p.stat().st_mtime)}" if logs
                 else "PTXprint stopped before typesetting; see its messages above")
        sys.exit(f"sfm2pdf: PTXprint produced no PDF (exit code {result.returncode}). {where}.")
    pdf = max(pdfs, key=lambda p: p.stat().st_mtime)
    out = Path(args.output) if args.output else Path(args.infile).with_suffix(".pdf")
    shutil.copyfile(pdf, out)
    print(f"Wrote {out}")
    if not args.no_open:
        open_file(str(out))


if __name__ == "__main__":
    main()