# Evidence record: amp type and IR cab names (spec 007 US4, FR-011)

Status: **manual, not yet matched on fw 96** (2026-11-25). Sources are found and transcribed. At
the owner's request (2026-11-25) openvave shows the manual's names (S1) as `hypothesis` next to the
raw position, in the draft PR for spec 007 Milestone 4. The names do not ship in a release until
the matching below is recorded (FR-011).

The manual's images and the vendor PDF are **not** committed (copyright). This file cites and
transcribes only. Local copies used for the transcription stay outside the repository.

## Sources

| # | Source | URL | Publisher | Document date | Accessed |
|---|---|---|---|---|---|
| S1 | "M-VAVE TANK-G Multi Guitar Pedal User Manual" (web page with the manual's figures), archived snapshot | `https://web.archive.org/web/20250920035229/https://manuals.plus/m-vave/tank-g-multi-guitar-pedal-manual` (figures: `…/wp-content/uploads/2024/02/M-VAVE-TANK-G-Multi-Guitar-Pedal-FIG-5.png` amp list, `…-FIG-6.png` IR cab list, `…-PRODCUT.png` front panel) | Manuals+ (third-party copy of M-VAVE's manual) | posted 2024-02-13 | 2026-11-24 |
| S2 | "M Vave Tank G Multi Guitar Pedal manual" (12 page images of S1) | `https://askmanual.pages.dev/m-vave/tank-g-multi-guitar-pedal` (page 5 = amp list; the IR cab list image is missing from its page 7, only the caption `FIG-6` is printed) | askmanual (third party) | — | 2026-11-24 |
| S3 | "TANK-G NEW PRESET" preset card (PDF title `(PD34)TANK-G 预设介绍卡片_英文_电子详细版_120x75mm_V04_20260208`) | `https://community.m-vave.com/bbs/api/software?file=TANK-G_en.pdf`, linked as "Preset EN" from `https://www.m-vave.com/download.html` | M-VAVE (vendor) | V04 2026-02-08 (PDF created 2026-02-24) | 2026-11-24 |
| S4 | TANK-G firmware release notes | `https://yms-file-store.oss-cn-hongkong.aliyuncs.com/software/releaseNote/firmware/Tank-G.txt`, linked from the same download page | M-VAVE (vendor) | v96 2024-12-31 … v99 2026-11-16 | 2026-11-24 |

Also searched, nothing usable: manuals.plus direct pages and PDFs (HTTP 403 to scripts),
Scribd copies "Tank-G User Manual and Presets Guide" and "M-Vave Tank-G 2" (no text without a
login), Equipboard's PDF (a print of S1 without the figures), M-VAVE's product page (no manual),
retailer listings (counts only: 9 preamps, 8 IR slots). The vendor's `TANK-G.zip` from the same
download page is only the Windows firmware updater (no model names in its file list). The phone app (M-effects 3.9.2314) has no
names (`specs/protocol/command-layer.md`, open questions): amp type 1–9, IR cab `OFF` then 1–8.

## Transcription

### S1 (2024 manual), AMP module, figure 5

"TYPE knob: Select the types of AMP, there are 9 different types, please look at the list."

| SLOT | NAME | TYPE |
|---|---|---|
| 1 | Based on VOX AC30HW Normal | Clean |
| 2 | Based on Fender 65 Twin Reverb | Clean |
| 3 | Based on Bogner Shiva | Overdrive |
| 4 | Based on Marshall JTM45 OD | Overdrive |
| 5 | Based on Plexi 100 | Overdrive |
| 6 | Based on Marshall JCM800 | Dist |
| 7 | Based on EVH 5150 LEAD | Dist |
| 8 | Based on ENGL Powerball E645/2 | Dist |
| 9 | Based on Mesa Boogie Dual Rectifier | Dist |

S2 page 5 shows the same table, word for word.

### S1 (2024 manual), IR CAB module, figure 6

"IR CAB knob: Select the types of IR CAB. A total of 9 slots, the first slot means the IR has been
turned off, and the other 8 slots are 8 types of IR CAB, please look at the list. You can import
the IR files to TANK-G on computer software or APP, the previous IR will overwritten with the
current IR."

| SLOT | NAME | CAB TYPES |
|---|---|---|
| 0 | The IR CAB turn off | None |
| 1 | Based on VHT Deliverance | 4x12 |
| 2 | Based on Sperimental | 4x12 |
| 3 | Based on Electrovoice | 2x10 |
| 4 | Based on Mesa Boogie | 4x12 |
| 5 | Based on Fender Champ | 1x8 |
| 6 | Based on Fender Pr Junior | 1x10 |
| 7 | Based on Marshall 1960V30 | 4x12 |
| 8 | Based on Diezel V30 | 4x12 |

Spelling as printed ("Sperimental", "Electrovoice", "Pr Junior").

Disclaimer printed under both lists: "The brand and model names mentioned above are Trademarks of
their respective owners, which are in no way associated with TANK-G. It was only used to identify
the sound character. We will constantly update the timbre without notice, may be different from
the real thing, but the actual object prevails."

### S3 (vendor preset card, 2026), AMP and CAB tables, page 1

| Effect Name | Type | Effect Description (first words) |
|---|---|---|
| 1J120_CL | Clean | Based on Roland JC-120 Jazz Chorus |
| 2J900_CL | Clean | Based on Marshall JCM900 |
| 3VAVE_TS | Overdrive | Based on M-VAVE ODRIVE-TS |
| 4RAT_OD | Overdrive | Based on Pro Co RAT |
| 5VAVE_HTS | Distortion | Based on M-VAVE ODRIVE-TS (high gain) |
| 6VAVE_DS | Distortion | Based on M-VAVE MT1 |
| 7MS_GV2 | Distortion | Based on Marshall GV-2 Guv'nor Plus |
| 8J900_HV | Distortion | Based on Marshall JCM900 |
| 9MS_HIGAIN | Distortion | Based on Marshall BB-2 Blues breaker |

| Effect Name | Type | Effect Description |
|---|---|---|
| 1AC-SeVin | 2x10 | Sampling AC-SE210 with U87 |
| 2JVM_1960_57 | 4x12 | Sampling JVM410]with SM57 |
| 3MESA_412 | 4x12 | Sampling MESA boogie with SM57 |
| 4WANGS112 | 1x12 | Sampling WANGS112 G12 with U87 |
| 5VOX_AC30 | 2x12 | Sampling VOX AC30 with U87 |
| 6HIFI_YAMAHA | 2x10 | Sampling YAMAHA HIFI with U87 |
| 7EGNL_412 | 4x12 | Sampling ENGEL 412 with MD421 |
| 8V30_MD421 | 1x12 | Sampling V30 with MD421 |

Page 2 lists the 36 presets with their AMP and CAB (e.g. 1A = `1J120_CL`, no cab; 1B = `3VAVE_TS`,
`1AC-SeVin`; 9D = `9MS_HIGAIN`, `6HIFI_YAMAHA`) and a trademark statement in the same spirit as
S1's.

### S4 (release notes), what bears on names

- v96 (2024-12-31): "Supports AM3 Psychoacoustic AI Model" (with ANN software and EFCS updates).
- v97 (2026-01-31): "Supports AM4 format files for AMP modules".
- v98 (2026-10-27): NAM / NAN models imported through the companion software.

So on newer firmware the AMP positions also take user files, like the IR slots; whether fw 96's
amp positions can be replaced is not known.

## The two lists disagree

S1 and S3 are both M-VAVE's own content (S1 through a third-party copy) and name **different**
models for every amp position and every cab position. S3 is titled "NEW PRESET", dated 2026-02,
and sits next to firmware V099 on the download page. Hypothesis: S3 describes new factory content
shipped with a later firmware or preset pack, and a fw 96 pedal still has S1's set. Not verified.

The owner's pedal does **not** hold S3's factory presets. Comparing S3 page 2 (position − 1 = raw)
with the stored presets read on 2026-11-16 ("Preset comparison (fw 96)" in
`specs/protocol/command-layer.md`), none of the ten compared presets matches on `amp_type` and
`ir_cab`:

| Preset | S3 amp, cab → raw | Pedal raw (byte 5, 17) |
|---|---|---|
| 1A | 1J120_CL, none → 0, 0 | 5, 7 |
| 1B | 3VAVE_TS, 1AC-SeVin → 2, 1 | 4, 7 |
| 1C | 5VAVE_HTS, 1AC-SeVin → 4, 1 | 4, 7 |
| 1D | 7MS_GV2, 1AC-SeVin → 6, 1 | 5, 4 |
| 2A | 2J900_CL, 2JVM_1960_57 → 1, 2 | 5, 7 |
| 2B | 4RAT_OD, 2JVM_1960_57 → 3, 2 | 0, 0 |
| 9A | 6VAVE_DS, 1AC-SeVin → 5, 1 | 0, 0 |
| 9B | 7MS_GV2, 3MESA_412 → 6, 3 | 3, 1 |
| 9C | 8J900_HV, 4WANGS112 → 7, 4 | 8, 1 |
| 9D | 9MS_HIGAIN, 6HIFI_YAMAHA → 8, 5 | 8, 8 |

That fits the hypothesis (a different, older preset bank) but does not prove which amp and cab
sounds the pedal has: the presets may also have been edited. No source lists S1's factory presets.

## Position mapping (derived, not yet matched on the pedal)

- **Amp type**: S1 numbers its slots 1–9; the phone app shows the amp type as raw + 1 (`ir_cab` row Notes in
  `specs/protocol/command-layer.md`); the knob has 9 positions, raw 0–8, counted click by click (session 19:17).
  So printed slot *k* = raw *k* − 1, **if** the manual's slot numbers are the app's numbers and
  the knob order. S3 uses the same 1–9 numbering in its names.
- **IR cab**: S1 numbers its slots 0–8 and slot 0 is "The IR CAB turn off"; raw 0 is cab off (the
  app shows `OFF`, heard in gate session C, 2026-11-19). So printed slot *k* = raw *k*. Raw 0 is
  confirmed; 1–8 are inferred. S3 numbers its 8 cabs 1–8, which gives the same raw *k*.
- **Faceplate**: the front panel (S1's product photo) prints only the knob names (TYPE, IR CAB,
  …), no position labels, so the owner cannot check a position by eye. The pedal has no screen
  for it either (the display shows the bank number).
- **User-replaceable slots**: S1 says an imported IR overwrites the slot's IR, so IR names can only
  describe the factory IRs. The same may hold for amp positions on firmware that imports amp
  models (S4).

## Confidence

| Claim | Confidence |
|---|---|
| S1 and S3 transcriptions (the printed text) | exact, read from the images / PDF on 2026-11-24 |
| IR cab raw 0 = off | confirmed (spec 007 gate session C) |
| IR cab raw 1–8 = S1 slots 1–8, amp type raw 0–8 = S1 slots 1–9 | hypothesis (numbering inferred) |
| The owner's fw 96 pedal has S1's set, not S3's | hypothesis (S3 presets absent; sound not compared) |

## Position matching on the pedal (pending)

Nothing is written from the computer and nothing is saved: the owner turns the pedal's own knobs
in LIVE mode (edit buffer only) while `openvave watch` (read-only) shows the raw position, then
leaves LIVE mode without saving (observed to restore the preset). The lists differ most at these
positions, so the owner listens there first:

| Raw | S1 (2024 manual) | S3 (2026 card) | What tells them apart |
|---|---|---|---|
| amp 0 | VOX AC30HW Normal, clean | Roland JC-120, clean | both clean; JC-120 is the brighter, glassier one |
| amp 4 | Plexi 100, overdrive | VAVE_HTS, high-gain distortion | crunch vs heavy distortion |
| amp 8 | Mesa Boogie Dual Rectifier, distortion | Marshall Bluesbreaker, light bluesy distortion | the heaviest position vs a light one |
| cab 3 | Electrovoice 2x10 | Mesa 4x12 | small vs big |
| cab 5 | Fender Champ 1x8 | VOX AC30 2x12 | the smallest, thinnest cab vs a full one |
| cab 6 | Fender Pro Junior 1x10 | Yamaha hi-fi 2x10 | small guitar cab vs hi-fi speaker |

Procedure:

1. Phone app closed. `uv run openvave watch` in the owner's terminal (reads only; `q` stops it).
2. Tap B+C to enter LIVE mode. Only the AMP module on (footswitch D flashing; A, B, C off). GAIN,
   TREBLE, MIDDLE, BASS at noon, IR CAB on raw 7 (a 4x12 in both lists).
3. Turn TYPE fully left (`amp_type` reads 0), then one click at a time to 8; play the same chord at
   each and note clean, crunch, overdrive or heavy distortion.
4. TYPE back to 0, GAIN low. Turn IR CAB fully left (`ir_cab` 0, cab off), then one click at a time
   to 8; note small, medium or big cabinet at each.
5. Tap B+C to leave LIVE mode. **Do not hold A/B/C/D** (holding saves the preset). `watch` should
   show the buffer back to the stored preset. Stop `watch` with `q`.
6. Also record: whether an IR or amp model was ever imported, or a preset pack loaded with the
   vendor software, on this pedal.

**Passing rule, position by position.** A name is promoted to `observed` only where the two
lists describe that position differently **and** the owner's note fits one description and not
the other. Where both lists describe the same character, a match by ear cannot tell which model
it is: that name stays a `hypothesis` (or is removed, if the owner prefers numbers only), even when
the discriminating positions point to one list. A position whose sound fits neither list loses
its name.

| Raw | S1 | S3 | Distinguishable by ear? |
|---|---|---|---|
| amp 0 | AC30, clean | JC-120 (stereo chorus in the description), clean | only if a chorus-like shimmer is heard (JC-120) or not (AC30) |
| amp 1 | Twin Reverb, clean | JCM900, clean | no |
| amp 2 | Bogner Shiva, overdrive | M-VAVE TS, overdrive | no |
| amp 3 | JTM45, overdrive | RAT, overdrive | no |
| amp 4 | Plexi 100, overdrive | high-gain TS, distortion | yes: crunch vs heavy |
| amp 5 | JCM800, distortion | MT1, distortion | no |
| amp 6 | 5150 lead, distortion | Guv'nor Plus, distortion | no |
| amp 7 | ENGL Powerball, distortion | JCM900, distortion | no |
| amp 8 | Dual Rectifier, distortion | Bluesbreaker, light distortion | yes: the heaviest vs light |
| cab 1 | 4x12 | 2x10 | yes: big vs small |
| cab 2 | 4x12 | 4x12 | no |
| cab 3 | 2x10 | 4x12 | yes |
| cab 4 | 4x12 | 1x12 | yes |
| cab 5 | 1x8 | 2x12 | yes: the smallest vs full |
| cab 6 | 1x10 | 2x10 (hi-fi) | weak: small guitar cab vs hi-fi speaker |
| cab 7 | 4x12 | 4x12 | no |
| cab 8 | 4x12 | 1x12 | yes |

The procedure above therefore records a note at **every** position (steps 3 and 4), and the record
lists, per position: the note, the list it fits (S1, S3, neither, or both), and the resulting
confidence. The IR cab names stay labelled factory names.

## What changes for each outcome

The names live in one table, `src/openvave/protocol/names.py`; the tests, the command-layer.md
table and the docs' tables are built from or checked against it.

| Outcome of the match | Change |
|---|---|
| S1 (manual) at every distinguishable position | `NAME_CHOICE`: `observed` for the distinguishable positions that fit S1, the others stay `hypothesis` (or `None` if the owner prefers); `NAME_STATUS` → "manual, matched by ear on fw 96 (date)"; regenerate the command-layer.md table; docs drop "not yet matched"; this record gets the session; T031 and T036 ticked |
| S3 (card) at every distinguishable position | `NAME_CHOICE`: source `manual-2024` → `preset-card-2026` everywhere; `observed` where distinguishable, `hypothesis` elsewhere; the same doc steps; the docs' tables list the card's names |
| Mixed (some positions fit each list, or neither) | `NAME_CHOICE` per position: the matching source with `observed` where distinguishable, `None` (no name, shown `#n`) where neither fits or the evidence is split, and for the undistinguishable positions `None` (no list can be preferred); the same doc steps; the docs say the lists are mixed |
| Inconclusive | nothing changes: the names stay a `hypothesis` and the PR stays a draft, or US4 is deferred again with the names removed (`NAME_CHOICE` all `None`) |
