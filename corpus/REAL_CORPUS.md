# Real-corpus normalization (Week 5-6)

Result of running `corpus/loader.py` over a real public corpus, to complement
the synthetic `baseline/` + `mutated/` fixtures with genuine attachments.

## Source
Apache **SpamAssassin public corpus** (spam sets), a stable, license-clean,
widely-cited public collection:
- `20021010_spam`, `20030228_spam`, `20030228_spam_2`, `20050311_spam_2`
- fetched from `https://spamassassin.apache.org/old/publiccorpus/`

## Normalization
`python corpus/loader.py <spam-dir> corpus/real/ --all` walked **2,400** raw
email messages and extracted every attachment (safe hash-named; bodies skipped;
nothing executed). Recovered **31 attachments**.

## Attachment inventory (the finding)
| type | count |
|---|---|
| jpg/gif/png (images) | 25 |
| html/htm | 4 |
| **doc (Office)** | **1** |
| other (text) | 1 |

**Old public spam is overwhelmingly image/HTML-based; document attachments are
rare.** This is itself relevant to the study: attachment-borne *content* evasion
via document parsers is a real but narrow slice of the threat surface in these
corpora. A document-rich sample needs a newer phishing collection, the Enron
attachment set, or a sandboxed malware set (the latter out of scope per the
README guardrail — kept out of git).

## Divergence measured on the one document attachment
`Yinxiang_Motorcycles.*.doc` (real Word 97 spam, code page 936):

| pair | similarity | note |
|---|---|---|
| oletools vs tika | **0.13** | oletools emits raw OLE-stream strings (`bjbj` records, `HYPERLINK` field codes); tika does proper Word parsing → clean body text + resolved URL |

A genuine **extractor-vs-extractor divergence on real-world spam** — the core
claim, on non-synthetic data. No detector-evasion measured: `.doc` has no OCR
ground-truth channel (the oracle renders PDF/OOXML only), so there is no
human-visible reference to flip against for this format.

## Reproduce (SpamAssassin)
```bash
# download a few spam sets into $DIR, then:
source env.sh
python corpus/loader.py $DIR corpus/real/ --all
python matrix.py corpus/real
python detector_impact.py corpus/real
```
`corpus/real/` is gitignored — regenerate from the public source above.

---

# Document-rich corpus: Digital Corpora GovDocs1

SpamAssassin is body/image-heavy, so for a real *document-parser* matrix we use
**GovDocs1** — ~1M redistributable real U.S. government documents in exactly the
formats the extractors handle. (The public Enron release is text-only —
attachments stripped — so it yields nothing for this study.)

Source: `https://digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/000.zip`
One thread zip = 981 files: 200 pdf, 111 doc, 88 ppt, 62 xls (+ html/txt/images).
Sampled **42** small (<1.5 MB) documents: 20 pdf, 10 doc, 6 xls, 6 ppt.

## Divergence matrix (42 real documents, OCR disabled)
```
overall divergence rate: 46.5%   (66/142 extractor-pair comparisons)
files with divergence:   69%
  pdfminer vs tika     70%      pdfbox  vs pdfminer  50%
  oletools vs tika     68%      pypdf   vs tika      35%
  pdfminer vs pypdf    55%      pdfbox  vs tika      30%
                               pdfbox  vs pypdf     15%
```
Contrast with the synthetic baseline, where pypdf vs pdfminer = **0%**. On real
PDFs they diverge **55%** of the time — the cross-extractor claim, on genuine data.

## Worked example — `000816.pdf` (US Census, NAICS Subsector 324)
The same special dash glyph, read four incompatible ways on identical bytes
(pypdf vs pdfminer similarity = **0.25**):

| extractor | emitted for the glyph | chars |
|---|---|---|
| pypdf | `/thrqtrEMdash` (internal glyph name leaked) | 31,614 |
| pdfminer | `(cid:1)` (unmapped CID marker) | 25,270 |
| tika | `�` (U+FFFD replacement char) | 24,619 |
| pdfbox | `\x01` (raw control byte) — and only ~40% of the text | 12,519 |

A naturally-occurring **font/encoding** divergence — the same class the Week 7
font-remap vector weaponizes deliberately. `run OCR_DISABLE=1` for bulk runs;
the extractor-vs-render axis is measured on the controlled synthetic set.

## Reproduce (GovDocs1)
```bash
curl -sSL -o 000.zip <govdocs1 zipfiles/000.zip URL> && unzip -q 000.zip
# copy a size-bounded sample of pdf/doc/xls/ppt into corpus/real/govdocs/, then:
source env.sh && OCR_DISABLE=1 python matrix.py corpus/real/govdocs
```
