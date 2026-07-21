# Grimoire source PDF — Deutsch

The PDF that belongs in this folder is **not in the repository**, and must never be committed:
it is Fantasy Flight Games' copyrighted book, and this project is not affiliated with FFG
(see the footer of the site). `.gitignore` keeps `*.pdf` out of here on purpose.

**What goes here**

| version | file to put in this folder |
|---|---|
| v1.0 (2026-03-25) | `arkham-horror-lcg-841333136918-arkham-grimoire_v1.pdf` |

Take the file from the official download, name it exactly as the table says, and drop it here.
The expected name is not a convention — it is read from `langs/de/lang.json`, under
`book.versions[]` → `pdf`. If you use a different filename, change it there instead of renaming the
book.

**Do I need it?**

Only to RE-BUILD this language. The site itself does not read the PDFs: it serves
`data/grimoire_de.json`, which is committed. You need the PDF when you run:

    python tools/ingest.py de

Without it that command stops with a message naming the exact file it wanted, and the other
languages still build.
