#!/usr/bin/env python3
"""
Concatenate all SFM files & sanitize them so that PTXprint can lay them out.
"""

import argparse
import re
from pathlib import Path


MISSION_ASSIST_FILE_PAT = re.compile(
    r"[1-3A-Z]{3}"  # book name
    r"[0-9]{2,3}"  # chapter number
    r"[a-zA-Z]{1,3}"  # keyboarder reference letters
    r"-[a-z]{3}\.txt"  # "-" plus language iso code + ".txt"
)
EXTRA_SFMS = (r"\id2", r"\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("DIR", type=Path, help="MissionAssist project folder path")
    args = parser.parse_args()
    if not args.DIR.is_dir():
        raise ValueError(f"Not a folder: {args.DIR}")
     
    sfm_files = sorted([f for f in args.DIR.iterdir() if MISSION_ASSIST_FILE_PAT.match(f.name)])
    if not sfm_files:
        raise ValueError(f"No valid files found in {args.DIR}")
    
    first_file = sfm_files[0] 
    book = first_file.name[:3]
    parent = first_file.parent
    out_file = parent / f"{book}.SFM"
    out_lines = []
    first = True
    for sfm_file in sfm_files:
        for line in sfm_file.read_text().splitlines():
            if not line or line.startswith(EXTRA_SFMS):
                continue
            if line.startswith(r"\id"):
                if first:
                    out_lines.append(line)
                    first = False
                continue
            out_lines.append(line)
    if out_lines:
        out_file.write_text("\n".join(out_lines))
        print(f"Saved to {out_file}")


if __name__ == "__main__":
    main()

