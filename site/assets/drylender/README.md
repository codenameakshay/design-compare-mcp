# DryLender case-study media

Prepared on 2026-10-23 for the user-authorized public case study. These are publication derivatives, not the private source recordings or audit screenshots. The user authorized these videos and the display of their own calendar history for this website. This authorization is not a general redistribution license.

## Source roles and credit

The reference source is a user-supplied screen recording of **Drylendar**, the original app attributed to App Craft Consulting. It is not established publisher-provided promotional footage, and the recording's physical creator is not independently established. The supplied file already contains FFmpeg encoder tags, so it is not described as an untouched recording.

Reference UI: Drylendar by App Craft Consulting, <https://drylendar.com/>. User-supplied screen recording. Independent DryLender recreation; no affiliation or endorsement implied.

The clone source is the supplied, already-edited **DryLender** simulator walkthrough. It has a title, burned-in captions, cuts between recordings, and held Party/export frames. It replays user-provided calendar history, not synthetic history. It is neither an uninterrupted session nor a timing benchmark.

## Files and editing disclosure

- `original.mp4`: 13.377031 seconds, 1,996,537 bytes, 590 x 1278, 789 frames. H.264 High, yuv420p, silent. This filename means the reference app, not an unedited camera original.
- `clone.mp4`: 53.766667 seconds, 6,920,593 bytes, 720 x 1680, 1,613 frames at 30 fps, silent. The complete supplied edit, including its title, captions, cuts, held frames, permission prompt, and export share sheet, remains in order. No new footage or claims were added.
- `original-poster.jpg`: 51,324 bytes, 590 x 1278. Actual green zero-drink editor frame extracted at an output seek of 4.500 seconds.
- `clone-poster.jpg`: 78,609 bytes, 720 x 1680. Actual orange five-drink editor frame extracted at an output seek of 26.000 seconds, with the existing caption intact.
- `media.json`: short alternatives and longer visual descriptions for both videos and posters. Use video descriptions as visible adjacent text or an accessible description, not as an unsupported HTML video `alt` attribute.

Both videos use FFmpeg/libx264, CRF 19, the slow preset, a 4 Mbit/s maximum rate with an 8 Mbit buffer, square pixels, and MP4 faststart. Neither video is cropped or stretched. The full source-frame aspect ratios are preserved. The reference is resized by exactly one half; the clone is resized by exactly two thirds. No grading, generative imagery, interpolation, overlays other than the disclosed privacy mask, or speed changes were added. JPEG posters are deterministic frame extractions, not reconstructed screens.

### Reference cut list

All times below refer to the supplied reference source. Start times are inclusive and end times exclusive. The only new joins are hard cuts.

1. Settings, 11.700 to 13.500 seconds. 106 source frames, first at 11.708333 and last at 13.493333 seconds.
2. Calendar settings, 19.000 to 21.500 seconds. 149 source frames, first at 19.015000 and last at 21.483333 seconds. An opaque neutral rectangle covers the timezone value throughout this segment. Its source-resolution coordinates are x=600, y=1700, width=550, height=160 in the 1180 x 2556 source. The mask is applied before resizing, giving x=300, y=850, width=275, height=80 in the public video.
3. Drink editor, 38.700 to 47.800 seconds. 534 source frames, first at 38.713333 and last at 47.786667 seconds. The source's brief returns to the calendar during this passage remain; they show the authorized user's history. The green, yellow, orange, red, and dark blackout card states, arrows, Submit/Cancel controls, and empty note placeholder remain.

The public joins begin at approximately 1.801979 and 4.287031 seconds. The 13.377031-second output reflects available source frames and variable-frame-rate boundaries, rather than adding holds to reach the nominal 13.4-second interval sum. Within each excerpt, frame timing is preserved to the source timebase. All 789 eligible source frames are retained.

The reference audio track is removed entirely. Profile and Friends passages, unrelated third-party names/avatars/messages, optional calendar still, optional rewards passage, and all additional original recordings are excluded. The separate original Party recording is not used. The clone's supplied Party-mode section is retained.

## Text alternatives

Reference video: "Edited Drylendar reference showing Settings, calendar appearance controls with the timezone hidden, and the drink-count editor changing from green through yellow, orange and red to a dark blackout state."

Reference visual description: A portrait phone recording opens in Settings, with Purchases, Notifications, Calendar, Social accounts, Privacy, About and Assistance controls. A hard cut shows Intermediate shades, System/Light/Dark appearance choices, and a timezone row whose value is covered. Another hard cut shows a green zero-drink card. It briefly closes to the user's calendar and reopens. The drink count rises through ten as the card changes color. Down/up arrows, Submit and Cancel remain visible. A Blackout toggle changes the card between red and dark gray. There is no spoken content or audio. The excerpt does not establish persistence or all gesture behavior.

Clone video: "Edited DryLender simulator walkthrough with captions, showing the calendar and SobriScore, multi-day fill, a past-day editor, Party-mode Live Activity with a permission prompt, reward cards, and CSV export controls."

Clone visual description: A title introduces DryLender. Captioned segments show a colored monthly calendar, a SobriScore sheet and yearly grids, then long-press range selection and a multi-day drink card. Balloon animations cross the calendar. A past-day editor changes a drink count and returns to the calendar. Party mode opens a drink card and then a Lock Screen Live Activity with the iOS permission prompt still open. Reward cards open and animate. The final section opens Settings and a CSV export share sheet. Cuts omit waiting time and some frames are held. There is no spoken content or audio.

Reference poster: "Drylendar's green zero-drink editor with down/up arrows, Submit and Cancel."

Clone poster: "DryLender's orange five-drink editor beneath the caption Edit any past day, with down/up arrows, Submit and Cancel."

## Known clone limitations

- Around 31 to 38 seconds, the Live Activity permission prompt remains open. This does not demonstrate successful Lock Screen arrow interactions or removal of the activity on close.
- This pre-build-4 walkthrough predates the single-tap gesture fix. The earlier calendar long-press recognizer swallowed quick real touches; a later build-4 fix addressed that issue. Accessibility-triggered taps in this recording do not establish real-touch reliability or demonstrate the later fix.
- Balloons are visible, but no balloon pop or haptic response is recorded.
- Around 48 seconds to the end, import/export controls and an export share sheet are visible. No completed import or export/import round trip is demonstrated.
- Existing captions are retained as supplied. They are section labels, not independent verification of every behavior they name. Cuts and held frames cannot establish interaction latency.
- This later edited walkthrough is not a fresh visual benchmark and must not be presented as proof that historical comparison scores cover every feature shown. No production-readiness, device-equivalence, speedup, or pixel-perfect claim is made here.

## Verification

- Both videos fully decode without reported FFmpeg errors. Each has exactly one video stream, H.264 with yuv420p; neither has audio, subtitles, data tracks, or chapters.
- MP4 atom inspection confirms `moov` precedes `mdat` in both outputs, so faststart is present.
- Source fingerprints were recomputed and match the audited originals. Source files were not changed or included here.
- Chronological contact-sheet review covered the complete 789-frame reference sequence, including both joins. Full-size Settings, masked calendar settings, editor, blackout, and poster frames were checked for readable controls and identifying content. The final timestamp-preserving encode was checked again throughout at four frames per second and at full size for representative controls.
- No third-party identities, messages, profile view, Friends view, or financial notifications were found in the retained reference frames. The timezone mask was checked visually and its interior checked across all 149 calendar-settings frames. Authorized personal calendar history remains visible during the editor's brief calendar views.
- The clone was reviewed at one-second intervals across its full duration, with full-size editor/poster, permission-prompt and final share-sheet checks. No unrelated identities or messages were found in these checks. All 1,613 frame timestamps exactly match the supplied walkthrough, preserving its full sequence and timing.
- Reference frame counts match all three requested source windows. Within-segment timestamp deltas match the source to within two microseconds as reported by FFprobe. No playback-speed multiplier is used.
- Only technical container/encoder tags remain. No source paths, personal author tags, creation dates, location tags, or JPEG EXIF payloads were retained. Public text files contain no private source paths or personal names.
- File-size gates passed: reference below 5 MiB and clone below 12 MiB. This is file/frame verification, not a deployed-site or browser-playback claim.

## SHA-256 provenance

Supplied reference source, 27,943,846 bytes:

```text
7cc179f8b7589e1a8424c6fa28d851d052ca5fb91af1347d58f1bc734080fadf
```

Supplied edited clone walkthrough source, 11,791,132 bytes:

```text
479eabf73a798289743f3bdd9a41ba37c57a674e59f76b1b47893df7a8458f6b
```

Public media outputs:

```text
40b2e21f2efdf93db02a2a9435c8f486a6ede5661f327d8e2defc78413328fbc  original.mp4
d803e74a2ca0dab226786bbafc0ac3a3d92f107f2cd8ac340f0f7f023faa7e9a  clone.mp4
dd97021310aed4d2f54b2be46201222fde98a4bdce0457b0e18db981687bb807  original-poster.jpg
37a86f0547632691407b612addde9da96ea88d69d44291bb73a36d79fd94ded3  clone-poster.jpg
```
