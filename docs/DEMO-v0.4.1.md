# Workfloor v0.4.1 - import history walkthrough

An 84-second captioned tour assembled from actual Windows Chromium captures of
the published v0.4.1 application. Timing is edited; this is not a continuous
screen recording. There is no audio. The video has burned-in chapter text and a
separate WebVTT track. Every manufacturing record is invented.

## Chapters and transcript

- **00:00 - Begin with a known result.** The default report contains nine orders,
  365 units and four delayed orders. No CSV has been imported.
- **00:14 - Preview before writing.** Load the included synthetic sample. All
  three rows pass validation while the original report remains unchanged.
- **00:28 - Commit the orders and receipt together.** Three orders and two events
  are inserted. The report becomes 12 orders / six delayed. One receipt is stored
  in the same SQLite transaction. Failure to store it rolls back the import.
- **00:42 - Inspect the stored explanation.** View the persisted receipt and
  download its exact JSON bytes: file hash, order IDs, counts and source fingerprints.
  Raw CSV contents and filenames are not stored.
- **00:56 - Restart the app.** Stop the first process and start a separate Python
  process using the same database. Download the receipt and compare its bytes.
- **01:10 - Restore into a fresh directory.** Stop, back up, verify and restore
  with the CLI. A third app process opens the new copy. The browser download must
  match the first receipt exactly. Receipts are local history, not signed audit evidence.

[Watch the walkthrough](https://connor-oshea-outlands.thatrobotguy.chatgpt.site/#workfloor-v04-walkthrough) · [MP4](media/workfloor-v041-walkthrough.mp4) · [WebVTT](media/workfloor-v041-walkthrough.vtt)

## Capture method and fixture disclosure

The capture script downloads the public v0.4.1 ZIP and verifies its outer SHA-256,
manifest, every member and source revision before opening it. No runtime file,
DOM text or CSS is changed for capture. Only the first server substitutes an
explicitly fictional receipt ID and time, so screenshots are repeatable and do
not publish random session identifiers or a runner's current timestamp. API
secrets remain random and private. The later processes use the receipt stored
by the first process. No token, database, backup or raw download is published.

Full images and their hashes are in [the capture record](media/v0.4.1-captures/capture.json).
The video renderer letterboxes actual captures, crops the first report to its
header/metrics and crops the preview to the validated rows. Exact crop coordinates
and chapter text are recorded in [the video receipt](media/video-v041-receipt.json).
The full original JPEGs remain available beside that record. The video is an
explanation of checked steps; CLI backup/verify/restore operations occur between
browser captures and are not represented as terminal footage.

The first v0.4.0 capture review found pale receipt text inherited from SQL styling.
Patch v0.4.1 fixes the real application, rather than recoloring its screenshot.
Both the browser regression and capture verify the rendered text contrast.
The original v0.4.0 and older public assets remain historical and unchanged.

## Reproduce

Use a Windows Python 3.12 development environment. Install the hash-locked
requirements-browser-windows.txt, then the associated Playwright Chromium build.
These are capture dependencies only; the app itself still needs no pip packages.

```text
python -m pip install --require-hashes --only-binary=:all: -r requirements-browser-windows.txt
python -m playwright install chromium
python scripts/capture_v040.py --output ABSOLUTE_NEW_CAPTURE_DIRECTORY
```

The capture script name refers to the 0.4 feature series; its constants pin 0.4.1.
It starts/stops only its three isolated app processes and removes private state.
It writes exactly six JPEGs and capture.json. The fixed time/ID substitution is
confined to the first capture process; ordinary application use is unaffected.
Use the app itself to inspect the receipt; keep real user receipts private.

To rebuild the video, install Pillow and obtain FFmpeg separately. Supply your
local font files and FFmpeg path explicitly; no binaries or fonts are redistributed.

```text
python scripts/build_v040_walkthrough.py --captures ABSOLUTE_CAPTURE_DIRECTORY --output ABSOLUTE_NEW_VIDEO_DIRECTORY --ffmpeg ABSOLUTE_FFMPEG --regular-font ABSOLUTE_REGULAR_TTF --bold-font ABSOLUTE_BOLD_TTF
```

Source image hashes are checked before rendering. Caption bounds, all six chapter
intervals and a complete decode of the resulting H.264 MP4 are checked. The images
and final chapter frames are visually reviewed separately. Different fonts,
encoders or browser builds may produce different media bytes; compare against
the receipts for the particular published output. This is not an accessibility,
physical-device, power-loss or production-readiness certification.

Capture run: [Windows release capture](https://github.com/TheOutlandsDev/workfloor/actions/runs/40722383756). Runtime release source: `6a7a02ade5b01e1a6fc76f6e87a40ac7d2c24af6`. Package checks: [Windows/Ubuntu, Python 3.12/3.13](https://github.com/TheOutlandsDev/workfloor/actions/runs/40721865589).
