# Studio reference fixtures

`studio_capture.html` is an interactive synthetic application used to exercise capture decoding and localization. It is not an existing commercial product or evidence of a real-user pilot. Serve it over loopback HTTP. The default route is English; `?locale=zh-Hans` renders Chinese. Capture phone at 390×844 and desktop at 1440×900. Browser screenshots are JPEG; preserve them as JPEG without editing.

`studio_matrix.config.json` declares six cards, English and Chinese, and iPhone/Mac targets. Copy this configuration into a fresh isolated consuming project as `creative.config.json`, and put authorized captures in:

- `captures/phone-en.jpg`
- `captures/phone-zh.jpg`
- `captures/mac-en.jpg`
- `captures/mac-zh.jpg`

Each language and device uses its own capture assignment. Six cards intentionally reuse a source per assignment to exercise the 24-output matrix, ordering, and independent copy. This does not prove six distinct product scenes. Run the existing canonical export and validation CLI against that project. Missing captures must fail; do not manufacture render-evidence records or treat fixture dimensions as a successful production render.

For visual acceptance, compare actual exported pixels with reviewed target-specific previews and confirm readable complete copy, the correct capture/language, background continuity, and no unintended cropping/collision. Record failed cases and repair/retry. A real product fixture and consented participant study remain separate requirements.
