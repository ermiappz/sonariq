# Progress (whole-ship viewer milestone)

One line per step: step · status · commit · gaps.

- Step 1 · done · 1348a2f · Fragments picking not scored (harness alignment); fps on this VM is software GL only.
- Step 2 · done · 34756c7 · glTF/GLB upload not converted (IFC only); overview by size-per-triangle, not exterior visibility; 1/12 RCRV pick samples returns no hit (never a wrong id).
- Step 3 · done · b518185 · independent scan covers 1 rule on deck5 (R-FLS-01) and all 5 running rules on RCRV; pipe material found by pattern (attribute names lost in the export); first RCRV banner takes ~20 s (scan), cached after.
- Step 4 · done · ec76e73 · matrix rows are part names as the CAD export gives them (many 'Inline…' blocks on RCRV); no server-side paging of passes (4 MB run JSON).
- Step 5 · done · b3ae89e · Realistic has no shadows (cut first per plan); edges are element outlines only (no creases inside one element).
- Step 6 · done · 3c72499 · caps on structure and architecture only (pipes, ducts, cables, equipment get outlines: open meshes); RCRV cut + caps + edges settle in ~60 s on software GL; RCRV frames are metres from the aft end (no frame grid in the model).
- Step 7 · done · d81c019 · fallback match (rule + element name) is flagged "please confirm", never auto-merged; past revisions open read-only in the list, the 3D shows the file of that run; revision store is runtime data (gitignored).
- Step 8 · done · (this commit) · pins only for findings with an evidence box; anchor height is 2 m above the footprint (engine sends 2D boxes); tinted volumes cut (plan cut-list); unlocatable card not exercised in e2e (no such finding on deck5).
- Step 9 · done · (this commit) · demo runs on the Deck 5 demo model (not RCRV) and saves a Rev A once if missing; fps measured on software GL only (RCRV 0.1 fps orbiting), no GPU number; largest open IFC sample is 2.3 MB; lint still reports pre-existing `any` in ShipView.

## Studio reliability milestone (branch fix/studio-reliability, 14 Nov)

- Step 0 · done · (this commit) · diagnosis in docs/INCIDENT-2026-11-14.md: Node not on the systemd unit's PATH; Inbox/Tasks follow the newest run in the whole store; demo step 2 polls 10 min with Next disabled.
- Step 1 · done · (this commit) · engine resolves Node at startup (SONARIQ_NODE_BIN, else PATH), /health reports converter ok|missing with a readable message; deploy pins the Node binary in the systemd units and pre-converts deck5 A/B/Fix 2 + RCRV (cached by content hash; RCRV by its fixed id); viewer error card with Retry; prepare takes convert:false (demo never converts).
- Step 2 · done · (this commit) · projects → models → revisions with per-revision marks, tasks, views; migration archives step 7 demo revisions and seeds Demo ship (Deck 5 Rev A/B/Fix 2, RCRV Rev 1); header Project + Revision menus; Studio model list per project; upload asks new model / new revision. Not scoped: Revisions screen (run history) and Thread (DECISIONS M15).
- Step 3 · done · (same commit as step 2) · Clear all dialog (Save and clear / Clear without saving / Cancel); Reset all data moved to Settings → Danger zone behind typed RESET.
- Step 4 · done · (this commit) · demo in its own throwaway project (deleted at Stop/Finish or after 1 h), per-step precondition + timeout (20 s / 60 s) + error card with Retry / Skip step, Next/Pause/Stop always respond, Stop restores project/revision/tab/mode/cuts, no conversion during the demo; e2e checks a non-blank canvas at step 2 (DECISIONS M16).
- Step 5 · done · (this commit) · / redirects to /studio (Home moved to /welcome); five-step first-run guide placed by viewer/callout.ts placeCallout with rings + leader on the real controls; Skip/Done remember it (localStorage + project flag; the shared Demo ship flag does not hide it from new browsers, M17); ? Help menu reopens the guide or plays the demo.
