# FCI London: supplier-to-website product pipeline

A Python pipeline that takes a supplier's price list, swatch documents and website and
produces FCI's six import CSVs, web-ready product images and swatch images, plus a report
listing everything a person should check. It was built for the two assessment products, and
a third product (Thomas) was added with a job file only, to show reuse:

| Product | Supplier source | FCI code | Base price | Combinations | Images |
|---|---|---|---|---|---|
| Richard Double Bed | Cattelan Italia, PDF price list (EUR) | `cattelan-italia-889` | 4121 | 2,340 | 6 |
| Burt Corner Sofa | Naustro Fiera / Franco Ferri "BERTE' FF", Excel price list (GBP) | `fiera-collection-043` | 1650 | 768 | 3 |
| Thomas Double Bed | Cattelan Italia, same PDF (EUR) | `cattelan-italia-806` | 4002 | 560 | 7 |

The Richard and Thomas base prices match the 4121 and 4002 FCI already holds for them. Prices are the
supplier's prices as written, as agreed; FCI's platform applies its own uplift.

## Running it

```bash
uv sync                                    # Python 3.12, installs everything
uv run fci run jobs/richard-double-bed.yaml
uv run fci run jobs/                       # every job in the folder
```

Supplier files go in `supplier_inputs/`. Output goes to `output/<code>/`:

```
output/cattelan-italia-889/
  csv/        cattelan-italia-889-product-upload.csv, -categories, -images, -attributes, -prices, -details
  images/     cattelan-italia/richard-double-bed-by-cattelan-italia-1.jpg ... -6.jpg
  originals/  the supplier's untouched image files, same names
  swatches/   cattelan-italia/swatches/<material>/<code-colour>.jpg   (356 files)
  report.md   what was produced, from which sources, and every flag
  report.json the same, for other tools
```

Options: `--offline` (use only cached web responses), `--no-images`, `--no-ai`.
Product descriptions are written by NVIDIA Nemotron 3.5 Super when `NVIDIA_API_KEY` is in
`.env` (see `.env.example`). Without a key, the supplier's own text is used and flagged for
review.

## What a person supplies

One short job file per product (`jobs/*.yaml`): FCI name, product type, category code,
SKU and the supplier product URL. These are the same three judgement calls as today's
master sheet (name, category, code). For modular sofas, the job also lists the standard
layouts as module codes, copied once from the supplier's technical sheet. Everything else is
extracted, derived or flagged.

## How each step works

**1. Extraction.**
- *Cattelan price list (373-page PDF).* The parser finds the product by its title and
  reads each price table from word positions. It handles European number formats
  ("4.121" = 4,121), variant tables ("Pull-up slats with container"), decimal sizes and
  pages that hold two products. With no product-specific code, it fully reads 426 of the
  list's 543 products.
- *Franco Ferri price list (.xlsm).* The parser reads each model block with its own
  header row and returns every module's price in each of the 8 fabric categories,
  plus dimensions.
- *Supplier websites.* The parser reads the description, the full-size originals of each
  gallery image (not thumbnails) and the technical-sheet link.

**2. Pricing and CSVs.**
- *Cattelan.* Every column of the price table maps to material groups through
  `config/brands/*.yaml`. Each (size, material) pair becomes one price combination.
- *Franco Ferri.* A layout's price is the sum of its modules in that material's category.
  Mirrored layouts are checked to cost the same.
- *Base price.* The cheapest combination becomes the base price.
- *Gaps.* Combinations the supplier doesn't price are left out and listed, never estimated.
- *Derived columns.* Names, URLs, titles, keywords, image names and alt text follow FCI's
  rules, worked out from the sample CSVs and the walkthrough video.
- *CSV structure.* Column order is read from FCI's template files at run time, so the
  structure cannot drift.

**3. Swatches and finishes.**
- *Cattelan.* Upholstery comes from Cattelan's public finishes catalogue, the data behind
  its own swatch pages. That gives 356 covers for Richard across 13 material groups,
  including the sofa fabrics: the first letter of each code (A/B/D/F) is its price group.
- *Franco Ferri.* The swatch card is text only, so it supplies colours by price category
  and the pipeline checks each article's colour count against the card's own total. The
  pipeline then reuses swatch images already on FCI's server, matched by colour code and
  article, and flags any it can't find.

**4. Images.** The goal is the supplier's full quality, so zooming shows the same detail as
the original.
- *Selection.* Full-size originals are downloaded, never thumbnails, and anything under
  500 px is dropped. Duplicates (the same photo at another size) are removed by perceptual
  hash, keeping the larger copy.
- *Ordering.* Studio cut-outs go first, so the listing image is clean.
- *No resampling.* Every output pixel is a source pixel at its original resolution (Richard
  2362×2362, Burt up to 1920×1920). Room shots are cropped square; cut-outs are trimmed and
  padded with white, and the product is never scaled.
- *Same quality as the supplier.* JPEGs are re-saved with the supplier file's own quality
  settings (quantisation tables), full colour detail (4:4:4) and its colour profile.
  Crops are aligned to JPEG's 8-pixel block grid, so this re-save is almost lossless.
- *Measured.* Each image's fidelity against its source is recorded in the report. All are
  56.0–64.7 dB, where 40 dB and above is visually lossless. Anything below 40 dB is flagged.
- *Originals kept.* The untouched supplier files are saved in `originals/`.
- *Technical drawing.* This is rendered at 300 dpi from the PDF price list, with the room
  photo masked out. A supplier technical sheet can be used too, but not when it carries the
  supplier's branding: Franco Ferri's sheet shows its logo and address, while FCI sells the
  range as Naustro Fiera, so it is switched off for that brand.
- *Swatches.* These are square at native resolution (591×591 for Cattelan), with the same
  quality rules.
- *Names.* All file names are SEO-friendly, e.g. `richard-double-bed-by-cattelan-italia-1.jpg`.
- *Fixed size.* FCI's site resizes images on the fly through its CDN, so high-resolution
  masters are safe to upload. A fixed size (e.g. the previous 1000 px) is one setting
  (`ImageSpec(size=1000)`).

**5. Copy.** NVIDIA Nemotron 3.5 Super (`nvidia/nemotron-3.5-super-vl-120b-a12b`, reasoning
off) rewrites the supplier text into a meta description of up to 160 characters and a long
description, returned as JSON. This is the only step that uses AI.
Output that isn't valid JSON, is too long, mentions a price or is declined is rejected, and
the supplier text is used instead. The report records which model wrote the copy. Prices
never come from the model.

**6. Report.** Each run writes `report.md`, which lists the sources (file, page or row, URL),
each image's source and status, and every flag at error, warning or info level.

## Adding a supplier or product

- **New product from an existing supplier:** a new job file, typically 7 lines.
- **New supplier with a familiar format** (grid PDF or module spreadsheet): a brand YAML
  that maps price columns to material groups and names the files.
- **New format:** one adapter in `src/fci/adapters/`, plus a `collect_*` function in
  `src/fci/suppliers.py`. The model, pricing rules, image processing, exporters and report
  are shared, so they don't change.

## How much is automated

Roughly 85–90% of the per-product work is automated. A run takes 8 seconds (Burt) to 43
seconds (Richard, including 356 swatch downloads); repeat runs use the cache.

| Step | Automated | Human review |
|---|---|---|
| Find product in price list, read sizes and prices | Yes | No |
| Build every price combination and base price | Yes | No |
| Materials and swatches (Cattelan) | Yes, with images | No |
| Materials and swatches (Franco Ferri) | Yes, colours from card; 162 images reused from FCI's server | Images for 34 options: 31 never stocked by FCI, 3 whose colour changed |
| Product images | Yes | Optional: choose a different main image |
| Six CSVs in FCI's format | Yes | No |
| Descriptions | Yes, with an API key | Spot-check tone |
| Category code | No: chosen in the job file, as today | Burt's `FUR-SEA-SOF` is inferred; confirm |
| Modular layouts | Module codes typed once per product from the technical sheet | Check the layout choice (see the audit below: this is where the one price error came from) |
| Sizes that look identical | Flagged automatically | Richard A and B differ only by mattress size (153 or 160 × 200), which is drawn, not printed; add it by hand |

## Findings from the data

- **FCI's live Thomas bed offers 41 covers Cattelan no longer makes.** These are mostly old
  B2xx/B4xx fabrics; Cattelan now offers B240 to B932. The golden test that rebuilds
  FCI's own Thomas sample found this, and the same check could audit the whole catalogue.
- **The same golden test confirms the price mapping.** Every Thomas cover that still exists
  sits in exactly the price column FCI used. FCI's prices are a constant 0.9615 of the
  current list, consistent with one list update of about 4%.
- **Hand-made paths in the sample contain spaces and capitals** (`mn006-Dusty rose.jpg`), and
  one is missing its leading slash. The pipeline produces clean, consistent paths.
- **Franco Ferri has re-coloured some Boston codes.** For example, FCI's "16 sky" swatch is
  now "16 Light Teal" on the card. The pipeline doesn't reuse those three images and flags
  them for new ones.
- **Richard's live page has no "Fabric B" sofa fabrics**, which the price list offers at the
  same price as Cattelan's own fabrics. The pipeline includes them.

## Limitations and open points

- **Category codes.** Only `FUR-BED-DB` and `ACC-MIR` are known for certain. The sofa
  code is inferred and flagged, and a list of FCI's category codes would remove this step.
- **Pull-up storage version.** The price list doesn't price sofa upholstery with the
  pull-up storage version, so those combinations are omitted and reported.
- **Franco Ferri Aquaclean fabric.** It's listed as "All colours, see book", with no
  individual colours, and is flagged. Three price categories (Cat.80/25/35) have prices
  but no materials on the card.
- **Franco Ferri images.** The site has only three photos for Berte, all showing one
  layout in one leather. The other layouts are shown only on the technical sheet.
- **Cattelan parser coverage.** The parser reads 78% of the Cattelan list unchanged. The
  rest (extendable tables, some modular sofas) would need small additions when those
  products are needed.

## Independent audit

After the build, every output was re-checked by a separate pass that re-extracted every
value straight from the PDF, the workbook and the swatch card with its own code, not the
pipeline's parsers.
- **Prices:** all 2,340 Richard and 560 Thomas prices match the PDF cell by cell, and
  every cover sits in the right price column.
- **Materials:** covers match the supplier catalogue and swatch card, with nothing missing
  or extra.
- **Descriptions:** every factual claim in the AI-written copy matched a supplier source. The
  only exception was one adjective ("sculptural") in an earlier Thomas run. The copy is
  regenerated on each run, so it stays marked for a quick human read.

It found one real error. In the Burt job file, the "Corner with Terminal" layout was copied
from the technical sheet without its corner module (0401), so its 192 prices were too low,
e.g. £1,749 instead of £2,313 in Cat.70. The job file is fixed, and a test now pins all four
layouts to the drawing. It also found smaller issues, now fixed:
- double slashes in some swatch paths;
- Windows line endings in the CSVs;
- a reused swatch image whose colour no longer matched the card;
- Richard sizes A and B, which are indistinguishable without the mattress size and weren't
  flagged;
- the Franco Ferri sheet's branding.

Two points were left as they are. Room shots are centre-cropped, which cuts the ends of a
wide bed in two Thomas photos; FCI's own live Thomas images are cropped the same way.
Several Cattelan swatches carry the supplier's "NEW" ribbon.

## Quality checks

`uv run pytest` runs 125 tests at 94% coverage, all offline:
- unit tests for every adapter and rule;
- a golden test against FCI's Thomas sample;
- end-to-end runs of the Richard and Burt jobs from saved fixtures;
- real-file tests that run when `supplier_inputs/` is present.

Also: `ruff` (lint and format), `mypy`, `bandit` and `pip-audit`. CI is in
`.github/workflows/ci.yml`. Test fixtures can be rebuilt from the supplier files with
`tests/fixtures/build_fixtures.py`.
