# Workfloor walkthrough

[Watch in the portfolio](https://connor-oshea-outlands.thatrobotguy.chatgpt.site/#workfloor-walkthrough) · [Download the MP4](media/workfloor-walkthrough.mp4) · [WebVTT captions](media/workfloor-walkthrough.vtt)

An approximately **80-second**, captioned step walkthrough made from actual Workfloor browser captures on Windows, 26 October 2026. All manufacturing records are invented. The presentation uses edited still-frame timing and has no audio; it is not a continuous screen recording. Captions sit outside the application capture and do not replace interface content.

| Time | Workflow and explanation |
| --- | --- |
| 00:00 | Choose UTC due dates. The exclusive end boundary is 8 October 2026. All records are invented. |
| 00:10 | Filter to **Delayed**: four of nine orders, with one completed late and three still open at cutoff. Two review cases stay separate. |
| 00:20 | Inspect **WO-1002**. Completion was after its due time. Two identical EV-02 records remain visible; the replay is collapsed for classification. |
| 00:30 | Compare **26 joined rows with 9 actual orders**. Validation catches 17 extra rows and 1,195 units instead of 365. |
| 00:40 | Read the deliberately incorrect SQL. Joining both raw one-to-many relationships multiplies rows before `COUNT(*)`. |
| 00:50 | Read the corrected aggregation: group evidence and steps before joining one row per work order. Dates are bound separately, and a separate procedural reference checks the result. |
| 01:00 | Save a snapshot to SQLite, preserving results, evidence, parameters, dataset fingerprint and SQL. Saving checks the fingerprint again in a transaction. |
| 01:10 | After interrupting and restarting the app using the same data directory, open the saved snapshot. The interface marks the result **SAVED SNAPSHOT**. A snapshot is not a database backup. |

## Capture and verification boundary

The demonstrated source was commit `f645e9a0200020ff356f3f891be931aa933ef7d8`; that commit adds CI without changing the v0.1.0 application. Python 3.12.7 and SQLite 3.45.3 ran the application locally. The dataset SHA-256 was `aaa7e4677f215de750cff24cfa315ccaa9d2b15d2c5cce7fc96c4c3bef6126d5`. Snapshot `a6e66719…` was saved at `2026-10-26T21:48:27Z`, remained listed after the owned server was interrupted and restarted, and was opened through the browser UI. The interruption returned exit code 1; this is not a claim of graceful shutdown or power-loss recovery.

The video is H.264, 1280 × 900, 25 fps, approximately 80 seconds, with burned-in captions and an optional WebVTT track for the portfolio player. See [capture hashes and video checksum](media/video-receipt.json). Screenshots, captions and the walkthrough use only this original synthetic demonstration. The [CI run](https://github.com/TheOutlandsDev/workfloor/actions/runs/40407181415) is separate evidence of automated backend checks, not automated video or browser testing.
