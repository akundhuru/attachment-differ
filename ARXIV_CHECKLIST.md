# arXiv submission checklist (cs.CR)

Paper: *One File, Many Readings: Cross-Extractor Content Divergence as an Evasion
Primitive in Email Attachment Pipelines* (`PAPER.md`).

Ordered so the slow/blocking items (endorsement, LaTeX conversion) start first.

---

## 0. Blockers to start NOW (can take days)

- [ ] **arXiv account** at https://arxiv.org (use an institutional email if you
      have one — helps auto-endorsement).
- [ ] **Endorsement for cs.CR.** First-time cs.CR submitters usually need an
      endorsement from an existing arXiv author. Institutional email or prior
      arXiv history can auto-satisfy it. If not: line up an endorser early — this
      is the single most common multi-day delay. (arXiv will show an endorsement
      code/link when you start the submission.)

## 1. Content readiness (fill every placeholder)

- [ ] **Authors + affiliation** on the paper, `LICENSE` (full legal name),
      `CITATION.cff` (`family-names`, repo URL).
- [ ] **References complete + exact:** PDF Mirage (Markwood et al., USENIX Sec
      2017), Extract Me If You Can (Carmony et al., NDSS 2016), Body Obfuscation
      (Dalmiere '25 — fill exact venue/URL), Ange Albertini file-format tricks,
      GovDocs1 / Digital Corpora (Garfinkel et al.), SpamAssassin public corpus.
      For §9: olefile issue #103, CWE-674, sqlparse CVE-2024-4340, eml_parser
      CVE-2026-44844.
- [ ] **Numbers reproducible:** run `bash reproduce.sh` clean-room; confirm the
      figures in `RESULTS.md` / `PAPER.md` §6–§8 match regenerated `results/`.
- [ ] *(Recommended)* scale the real-corpus matrix (larger GovDocs1 sample) and
      update the `n=42` §6/D3 numbers + drop the "preliminary" tag where firm.
- [ ] **Ethics/disclosure clean:** §9 makes **no CVE claim** (olefile = confirmed
      residual of #103). Decide whether to file the incomplete-fix PR before or
      after posting; either is fine since it's low-severity and #103 is public.
- [ ] **No pre-disclosure leak:** `DISCLOSURE.md`, `results/`, `.env.local`,
      `jars/` are gitignored and NOT in the artifact repo.

## 2. Manuscript format (the main mechanical task)

arXiv strongly prefers **LaTeX source** (it recompiles it); PDF-only is allowed
but second-class. `PAPER.md` is Markdown, so:

- [ ] Convert to LaTeX. First pass: `pandoc PAPER.md -o paper.tex`. Then drop into
      a standard template — **`article`** is fine for a preprint; `usenix`,
      `IEEEtran`, or `acmart` if you want venue-shaped for the later reviewed
      submission.
- [ ] Move references into a **`.bib`** file; use `\cite{}`. (natbib/biblatex.)
- [ ] Fix tables (the Markdown pipe tables → `tabular`/`booktabs`), the four-way
      `000816.pdf` example, and the defense-gap catch/miss table.
- [ ] If any figures/plots are added, embed as vector PDF; ensure `\pdfoutput=1`
      is in the first few lines so arXiv builds pdfLaTeX.
- [ ] Compile locally end-to-end (`pdflatex`→`bibtex`→`pdflatex`×2) with **no
      errors** and no missing refs/citations. arXiv fails the build on errors.
- [ ] Abstract ≤ ~1920 chars for the arXiv abstract field (the paper abstract is
      fine; you paste a plain-text version separately).

## 3. Submission metadata

- [ ] **Primary category:** `cs.CR`. Consider cross-list `cs.SE` (parsers/tooling)
      — optional.
- [ ] **License:** choose **CC BY 4.0** for maximum reuse/citation (best for an
      adoption-evidence artifact) unless you have a reason to pick the default
      arXiv non-exclusive license.
- [ ] **Comments field:** e.g. "N pages, M figures. Code and reproduction:
      <repo URL>." (Links here are how readers find the artifact.)
- [ ] **ACM-class / MSC** (optional): ACM class e.g. `K.6.5; D.4.6`.
- [ ] Title + author list exactly match the manuscript.

## 4. Artifact repo (do BEFORE posting — the paper links to it)

- [ ] `git init`; verify `.gitignore` excludes `DISCLOSURE.md`, `results/`,
      `.env.local`, `jars/`, `.venv/`, `corpus/` generated sets.
- [ ] Push to a public GitHub repo; put the URL in the paper + `CITATION.cff`.
- [ ] **Zenodo DOI:** enable the GitHub–Zenodo integration and cut a tagged
      release (e.g. `v0.1.0`) → mints a DOI. Cite the DOI in the paper's Artifact
      Availability section. (A DOI + release + stars/forks is exactly the
      third-party-recognition evidence the project is meant to generate.)
- [ ] Add a repo README badge to the arXiv paper once you have the id.

## 5. Submit

- [ ] Upload the LaTeX source (or PDF) at https://arxiv.org/submit.
- [ ] Review arXiv's auto-generated PDF carefully (fonts, tables, page breaks).
- [ ] Set category, license, comments, metadata (§3); submit.
- [ ] Submissions before 14:00 US Eastern on a weekday announce ~20:00 ET the
      same business day; otherwise the next cycle. Plan the announce date.

## 6. After it's live

- [ ] Update `CITATION.cff` (`preferred-citation` + arXiv id), repo README, and
      the paper's own Artifact section with the arXiv id.
- [ ] Re-tag the release so the DOI snapshot includes the arXiv id.
- [ ] (Later, per plan) submit the same work to a reviewed venue: LangSec / WOOT
      first, then CCS / USENIX. Keep the arXiv v1 as the citable anchor.
- [ ] If you file the olefile incomplete-fix PR, link it from §9 once it has an
      issue/PR number.

---

### Quick "day-of" sequence
`bash reproduce.sh` → confirm numbers → fill placeholders → compile `paper.tex`
clean → push repo + Zenodo release → upload to arXiv → set cs.CR + CC BY 4.0 +
comments(repo URL) → review PDF → submit.
