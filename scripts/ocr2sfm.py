#!/usr/bin/env python3
r"""
ocr2sfm - convert a raw TXT file from OCR source to a loose (MA) SFM/USFM file.

    ocr2sfm JER22F-hsb.ocr.txt

Candidate tasks for this script:
    1. Double-check for common OCR errors in the file.
      - 1/l/I
      - O/0
      - random capitalization
      - other confused characters
    1. Do MA substitutions.  (can be done manually or using Easy-KeyEdit4)
      - Create new, properly-named TXT/SFM file.
      - Paste text from OCR file.
      - Make substitutions required by MissionAssist.
        - e.g. "/a" instead of "á"
        - e.g. "?-?" instead of "-" for line-break hyphens
        - "-.-" for mid-line hyphens
    1. Add MA-SFM.
      - Add 2x linebreaks for paragraph breaks.
      - Insert \id, \id2, \c markers manually.
      - Insert section header SFM markers (manually).
      - Insert paragraph SFM markers. [/\n\n/\n\\p\n/]
      - Insert verse SFM markers. [/(?<!\\[cv]) ([0-9]+)[ \n]/ \n\\v \1 /]
      - Insert any other SFM markers.
      - Remove mid-paragraph linebreaks. [/(?<!\\[a-z]])\n(?=[^\n\\])/ /]
    1. Final cleanup.
      - Remove repeated spaces. [/ {2,}/ /]
      - Remove verse-end spaces. [/ \n/\n/]
"""

import argparse
import re
from pathlib import Path

EOL_HYPHEN_RE = re.compile(r"\b- *\n")
MULTI_SPACE_RE = re.compile(r" {2,}")
MID_PARA_NEWLINE_RE = re.compile(r"(?<!\\[a-z]])\n(?=[^\n\\])")
EOL_SPACE_RE = re.compile(r" +\n")


def ma_char_subs(text):
    """Common substitutions; e.g. line-break hyphens -> "?-?" """
    # Add line-break uncertain hyphens.
    text = EOL_HYPHEN_RE.sub("?-?", text)
    # Ensure NFC?
    return text


def add_p_markers(text):
    text = re.sub(r"\n\n", r"\n\\p\n", text, flags=re.MULTILINE)
    return text


def add_v_markers(text, v_re):
    """Verse numbering can take different forms; use a regex `pat` to define it for this text."""
    text = v_re.sub(r"\\v \1 ", text)
    return text


def final_cleanup(text):
    # Remove repeated spaces.
    text = MULTI_SPACE_RE.sub(" ", text)
    # Remove mid-paragraph line breaks.
    text = MID_PARA_NEWLINE_RE.sub(" ", text)
    # Remove line-end spaces.
    text = EOL_SPACE_RE.sub(r"\n", text)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("FILE", type=Path, help="text file to be converted to SFM")
    ap.add_argument("-v", "--verse-pattern", type=str, default=" ([0-9]+) ",
        help="regex pattern to match verse numbers",
    )
    args = ap.parse_args()
    infile = args.FILE
    outfile = infile.with_suffix(".SFM")
    text = args.FILE.read_text()
    text = ma_char_subs(text)
    text = add_p_markers(text)
    text = add_v_markers(text, re.compile(args.verse_pattern, flags=re.MULTILINE))
    text = final_cleanup(text)
    outfile.write_text(text)


if __name__ == "__main__":
    main()