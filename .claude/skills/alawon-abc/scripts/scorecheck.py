"""Compare the repeat signs on each tune's score image with its ABC.

    uv run --no-project --with pillow --with numpy python scorecheck.py tunes [slug ...]

For every tune with a score.gif, counts the end-repeat signs (:| and :|:) on the score
(a thick bar line with two dots to its left) and in the ABC (:| and ::), and lists the
tunes where they differ. A difference usually means the MIDI played a part a different
number of times than the score shows (so the ABC, made from the MIDI, lost or gained a
repeat), or that the ABC writes out a repeat the score folds (or the other way round).
Check each listed tune against its score image and fix the ABC to follow the score.

Known false alarms: scores with two or more staves per line (harmony, bass) count each
staff's repeat signs; very occasionally a note or dot is taken for a repeat sign.
"""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def staves(ink):
    rows = ink.sum(axis=1)
    width = ink.shape[1]
    long_rows = np.where(rows > 0.5 * width)[0]
    # group adjacent rows into lines
    lines = []
    for r in long_rows:
        if lines and r - lines[-1][-1] <= 1:
            lines[-1].append(r)
        else:
            lines.append([r])
    centres = [(l[0] + l[-1]) / 2 for l in lines]
    out, i = [], 0
    while i + 4 < len(centres):
        five = centres[i:i + 5]
        gaps = np.diff(five)
        if gaps.max() - gaps.min() <= 2 and 5 <= gaps.mean() <= 20:
            out.append((int(lines[i][0]), int(lines[i + 4][-1]), gaps.mean()))
            i += 5
        else:
            i += 1
    return out


def repeat_ends(path):
    """How many end-repeat signs (:| or :|:) the score has: a thick vertical line, from
    the staff's top line to its bottom one, with two dots just to its left (in the
    second and third spaces)."""
    img = np.array(Image.open(path).convert("L"))
    ink = img < 128
    total = 0
    for top, bottom, space in staves(ink):
        full = ink[top:bottom + 1].all(axis=0)
        cols = np.where(full)[0]
        runs = []
        for c in cols:
            if runs and c == runs[-1][-1] + 1:
                runs[-1].append(c)
            else:
                runs.append([c])
        thick = [r for r in runs if len(r) >= max(3, space * 0.3)]
        for r in thick:
            # the dots sit left of the thin line that comes before the thick one, if any
            x1 = r[0] - 1
            x0 = max(0, int(r[0] - space * 1.6))
            dots = 0
            for y in (top + 1.5 * space, top + 2.5 * space):
                y0, y1 = int(y - space * 0.3), int(y + space * 0.3) + 1
                window = ink[y0:y1, x0:x1]
                # a dot: some ink in the window apart from full-height vertical lines
                cols_ink = window.any(axis=0) & ~full[x0:x1]
                if cols_ink.sum() >= max(2, space * 0.2):
                    dots += 1
            if dots == 2:
                total += 1
    return total


def abc_repeat_ends(abc):
    body = abc.split("\nK:", 1)[1].split("\n", 1)[1]
    body = re.sub(r'"[^"]*"|^%.*$', "", body, flags=re.M)
    return len(re.findall(r":\||::", body))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "tunes")
    only = set(sys.argv[2:])
    differ = 0
    for score in sorted(root.glob("*/score.gif")):
        slug = score.parent.name
        abc_path = score.parent / "tune.abc"
        if (only and slug not in only) or not abc_path.exists():
            continue
        abc = abc_path.read_text(encoding="utf-8")
        in_abc, in_score = abc_repeat_ends(abc), repeat_ends(score)
        if in_abc != in_score:
            differ += 1
            reviewed = " (reviewed)" if "%%alawon-reviewed" in abc else ""
            print(f"{slug}{reviewed}: ABC has {in_abc} end repeat(s), the score {in_score}")
    print(f"{differ} tune(s) to check")


if __name__ == "__main__":
    main()
