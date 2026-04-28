#!/usr/bin/env python3
"""
Apply targeted fixes for 8 malformed markdown links discovered by
pipeline/audits/audit_archive.py. Each fix is an exact-string replacement with
a recorded before/after; the script aborts and reports if any target
string is not found or is ambiguous.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = REPO_ROOT / "site" / "archive"

FIXES: list[tuple[int, str, str, str]] = [
    (
        40,
        "parens-in-URL broke Gilmore/Kapor Wikipedia links",
        "[other EFF founders like John Gilmore](https://en.wikipedia.org/wiki/John_Gilmore_(activist)[) and Mitch Kapor](https://en.wikipedia.org/wiki/Mitch_Kapor)",
        "[other EFF founders like John Gilmore](https://en.wikipedia.org/wiki/John_Gilmore_%28activist%29) and [Mitch Kapor](https://en.wikipedia.org/wiki/Mitch_Kapor)",
    ),
    (
        82,
        "missing `[` before ‘Machine Learning University’ link text",
        "Amazon is now making their ‘Machine Learning University](https://aws.training/machinelearning) available to all.",
        "Amazon is now making their [Machine Learning University](https://aws.training/machinelearning) available to all.",
    ),
    (
        126,
        "parens in Wikipedia URLs (band/musician) cascaded and broke 3 links",
        "Loved [the special highlights of Hüsker Dü](https://en.wikipedia.org/wiki/Hüsker_Dü) [, The Replacements](https://en.wikipedia.org/wiki/The_Replacements_(band)[) , and Soul Asylum](https://www.soulasylum.com) [. Of course Prince](https://en.wikipedia.org/wiki/Prince_(musician)) too.",
        "Loved the special highlights of [Hüsker Dü](https://en.wikipedia.org/wiki/Hüsker_Dü), [The Replacements](https://en.wikipedia.org/wiki/The_Replacements_%28band%29), and [Soul Asylum](https://www.soulasylum.com). Of course [Prince](https://en.wikipedia.org/wiki/Prince_%28musician%29) too.",
    ),
    (
        132,
        "space in Goodreads URL broke the link",
        "[The Rag and Bone Shop of the Heart: A Poetry Anthology](https://www.goodreads.com/book/show/162343. The_Rag_and_Bone_Shop_of_the_Heart)",
        "[The Rag and Bone Shop of the Heart: A Poetry Anthology](https://www.goodreads.com/book/show/162343.The_Rag_and_Bone_Shop_of_the_Heart)",
    ),
    (
        136,
        "stray 'j ' before Matt Wilson URL",
        "[Matt Wilson](j https://www.minneapolismatt.com)",
        "[Matt Wilson](https://www.minneapolismatt.com)",
    ),
    (
        161,
        "space in Apple Maps URL after ?q=",
        "[46.293720,-93.823915](http://maps.apple.com/maps?q= 46.293720,-93.823915)",
        "[46.293720,-93.823915](http://maps.apple.com/maps?q=46.293720,-93.823915)",
    ),
    (
        221,
        "parens in Knuth/TAOCP Wikipedia anchor broke the link",
        "[The Art of Computer Programming](https://en.wikipedia.org/wiki/Donald_Knuth#The_Art_of_Computer_Programming_(TAOCP).",
        "[The Art of Computer Programming](https://en.wikipedia.org/wiki/Donald_Knuth#The_Art_of_Computer_Programming_%28TAOCP%29).",
    ),
    (
        291,
        "space in YouTube URL after ?",
        "[video version on YouTube](https://www.youtube.com/watch? v=RWKaoD-VWeY)",
        "[video version on YouTube](https://www.youtube.com/watch?v=RWKaoD-VWeY)",
    ),
]


def main() -> None:
    errors: list[str] = []
    for num, desc, before, after in FIXES:
        path = ARCHIVE / f"{num}.md"
        text = path.read_text(encoding="utf-8")
        count = text.count(before)
        if count == 0:
            errors.append(f"[#{num}] target string not found ({desc})")
            continue
        if count > 1:
            errors.append(f"[#{num}] target string appears {count}× — ambiguous ({desc})")
            continue
        path.write_text(text.replace(before, after), encoding="utf-8")
        print(f"[#{num}] fixed: {desc}", flush=True)

    if errors:
        print("\nERRORS:", flush=True)
        for e in errors:
            print(f"  {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
