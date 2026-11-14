# Progress (whole-ship viewer milestone)

One line per step: step · status · commit · gaps.

- Step 1 · done · 1348a2f · Fragments picking not scored (harness alignment); fps on this VM is software GL only.
- Step 2 · done · 34756c7 · glTF/GLB upload not converted (IFC only); overview by size-per-triangle, not exterior visibility; 1/12 RCRV pick samples returns no hit (never a wrong id).
- Step 3 · done · b518185 · independent scan covers 1 rule on deck5 (R-FLS-01) and all 5 running rules on RCRV; pipe material found by pattern (attribute names lost in the export); first RCRV banner takes ~20 s (scan), cached after.
- Step 4 · done · ec76e73 · matrix rows are part names as the CAD export gives them (many 'Inline…' blocks on RCRV); no server-side paging of passes (4 MB run JSON).
