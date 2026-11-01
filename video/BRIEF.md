# Video brief: FCI assessment demo

A 3-minute demo of the supplier catalogue automation for FCI London's round-2 technical
assessment. The audience is Ria Chatterjee and the back-office team. Every number, image
and line of text on screen comes from the real supplier files and the real run.

This video has its own look, music and sound. Nothing is reused from earlier project videos
apart from the narrator voice and the creator's photo and QR code.

## Build
```
uv run fci run jobs/ | tee video/assets/run.txt   # the real run shown on screen
uv run python video/prepare.py                    # assets/ + assets/data.json from the outputs
python3 video/voice.py                            # build/voice.wav, build/timing.json, fci-demo.srt
FCI_DEV_LINKS=1 uv run fci serve > server.log &   # the real web app, for the app scenes
uv run --with playwright python video/capture_app.py server.log   # app screenshots + Drive/Sheet data
python3 video/render.py --stills 8.8 50.3         # preview frames in build/stills/
python3 video/render.py --thumbnail               # fci-demo-thumbnail.png only
python3 video/render.py                           # fci-demo.mp4 (thumbnail embedded as cover)
```
`render.py` runs `audio.py`, which writes the music, the sound effects and the mix.
Rendering uses the installed Google Chrome through Playwright.

## Format
1920×1080, 30 fps, H.264 with AAC at −16 LUFS, about 183 s, opening on the thumbnail for 1.3 s. It ships with a thumbnail,
`fci-demo.srt` captions and `DESCRIPTION.md`.

## Look
- **Concept:** a furniture spec sheet. Warm stone paper (`#ECE6DC`) with a faint architectural grid.
- **Colour:** ink type, terracotta (`#A8482A`) for what matters, brass for totals.
- **Type:**
  - Fraunces for headlines and big numbers;
  - JetBrains Mono for data, file names and labels;
  - Inter Tight for body text and captions.
- **Measurements** are drawn as dimension lines, e.g. "W 305 cm" over the Burt plan.
- **Chapter changes:** a terracotta sheet wipes across with the chapter title (01 The run … 06 Result).
- **Captions** are burned in at the bottom. Each word lights up as it's spoken.
- **Numbers count up** and land on the word that says them.

## Sound
- **Voice:** `en-US-AndrewNeural` (male, English only) at +4%. The multilingual version read the Burt
  sum in French, so the English-only voice is used; every sentence was re-checked with speech
  recognition (all English).
- **Music:** composed in `audio.py`, with no samples.
  - A felt-piano arpeggio over a soft pad in D major at 76 BPM: Dmaj9, Bm9, Gmaj9, A add9.
  - Bass and a light shaker join when the run starts and drop out for the closing card.
  - A synthetic room reverb.
  - The music sits 12 dB under the voice and drops further while he speaks.
- **Effects:** synthesised in `audio.py` and placed from the page's own cue list (`build/sfx.json`):
  - a soft sheet sound on chapter wipes;
  - wooden ticks on checks and rows;
  - a low knock and a bell when a number lands;
  - a stamp thud;
  - a rising shimmer when the 70 PDF cells light up.

## Scenes
| # | id | On screen | Source |
|---|---|---|---|
| 0 | hook | Title; the three products with base prices; the six CSV names; the run command | `output/*/images`, `report.json` |
| 1 | pain | p.358 with the page counter running to 358 of 373; rows of the real prices CSV; a counter to 2,340; "by hand" stamp | PDF render, `prices.csv` |
| 2 | run | The three supplier files; the Richard job file typed in; the real terminal output of the run | `jobs/`, `assets/run.txt` |
| 3 | richard | All 70 price cells boxed on p.358; 5 sizes / 10 columns / storage; 18 ECP swatches; 356 colours; 70 → 2,340 | PDF word positions, swatches, `report.json` |
| 4 | burt | Photo; plan of the corner-with-terminal from the module sizes; the 4 module rows summed to £2,313; 4 layouts / 192 covers / 768 rows | `.xlsm` row 519 |
| 5 | images | The original 3543 × 2362 photo with the square crop marked; a 400% zoom of the original and the FCI file; the dB scale with all 14 measured photos | `originals/`, `images/`, `report.json` |
| 6 | swatches | 45 of Richard's 356 swatches; 30 of Burt's 162 reused swatches and 34 empty "needed" slots | swatch files, FCI's server, flags |
| 7 | copy | Nemotron's real meta description typed out, with the three checks it passed | `product-upload.csv`, `content.py` |
| 8 | thomas | FCI's hand-built sizes beside ours, each ticked; €4,002 base price; 41 withdrawn colours | `templates/`, golden test |
| 9 | drive | The live Drive tree (price lists, Outputs/2026-11-01/<sku>), the Products sheet rows, the Layouts tab, and the file-name pattern that picks up a new catalogue | Drive and Sheets via the app's connection (`capture_app.py`) |
| 10 | changes | previous run vs new run → changed rows only; Thomas's real result: "no price changes (560 unchanged)" | `price-changes.md` |
| 11 | assistant | The React app: the question, the live Nemotron answer (3 glove-leather prices), the "Checked against the data" mark | Screenshots of the running app |
| 12 | confirm | The proposed run, Confirm, running, done with "560 unchanged" and the Drive link | Screenshots of a real confirmed run |
| 13 | verify | The report warning; `fci grid` output; 192 tests; the CI steps | `report.md`, `fci grid`, pytest + vitest, CI |
| 14 | close | 85–90%; new product = a row in a sheet, new supplier = a new reader; results table; repo link | README, `report.json` |
| 15 | creator | The standard outro content: "Designed & built by", Prateek Sahni, MEng, AI Software Builder, "Asking why. Building what's useful.", QR code (https://prateeksahni.pages.dev) and 6 contact cards | Creator assets, contacts from the standard outro |

## Fact ledger
Every number spoken or shown, with its source. All were re-checked on 2026-11-01 after the final run.

| Claim | Value | Source |
|---|---|---|
| Price list length | 373 pages | PDF page count |
| Richard page | p.358 of the PDF (the printed page number is 345) | `report.json` sources; page footer |
| Richard price cells | 70 = 5 sizes × (4 + 6 columns) + 5 × 4 storage columns | PDF words matching `d.ddd`: 70; parsed tables match in order |
| Richard colours | 356 | `report.json` swatches; attributes.csv |
| Richard rows | 2,340 = 5 × 356 + 5 × 112; €4,121–€8,769 | prices.csv; `report.json` |
| Burt Corner with Terminal (Cat.70) | 698 + 320 + 564 + 731 = £2,313 | `.xlsm` BERTE' FF, row 519 |
| Burt layouts / covers / rows | 4 / 192 / 768 | prices.csv; `report.json` |
| Image fidelity | 56.0–64.7 dB over 14 photos (drawings aren't measured) | `report.json` `fidelity_db` |
| Swatches | Richard 356 downloaded; Burt 162 reused, 34 needed (31 missing + 3 recoloured); Thomas 114 | `report.json` |
| Meta description | 116 characters; checks: no prices, 100–160 characters, fallback | `product-upload.csv`; `src/fci/content.py` |
| Thomas | sizes match FCI's sample; 41 withdrawn colours; €4,002 = FCI live page | golden test; fcilondon.co.uk `"price":4002` |
| Tests | 192 = 185 Python + 7 React | `pytest --co`, `vitest list` |
| CI | lint, type check, unit, integration, dependency audit, security scan, on every push | `.github/workflows/ci.yml` |
| Automated share | 85–90% | README "How much is automated" |
| Drive workspace | 3 price-list files, 3 product rows, 4 Burt layouts, Outputs/2026-11-01 with 3 products | live listing in `assets/app/drive.json` |
| Re-pricing | Thomas re-run: no price changes (560 unchanged) | `output/cattelan-italia-806/price-changes.md` |
| Assistant answer | €7,192 / €7,249 / €8,162 for Richard D in glove leather | live answer; matches `prices.csv` |
| Contacts | hksahni0@gmail.com · in/prateek-sahni-meng · @hksahni0-ux · @prateek_lee (Instagram, X) · calendly/prateeksahni | standard outro (B2B_CRM demo video) |

Not claimed: run time (it was measured only without the AI step), and which layout the
Burt photo shows.
