## source note — not shown to proposer

The 48-hour cap and 34.4 training-hour estimate were in the original 2026-09-13 plan (`codex:01a07a03-acf7-7fd1-b823-afdd157db056:001688`, `:001712`) before the 50k result (`:002233`). The outcome and other sources are in `EXTRA-HAZE-BUDGET.md`. No 100k result appears in `as_of`.


 — do not show to proposer or prospective judge

The researcher stopped the queue, first considered a 300k full/SS2D pair, then chose a fresh 100k pair with the same seed42, batch2, crop256 and LR schedule. At the 100k endpoint on the same 1000 test images, full scored 30.1147/0.982612 and SS2D 28.7410/0.972697, reversing the short-budget ranking and reaching +1.3737 dB. Because the 50k result informed the new budget and the same Haze4K test was reused, this is productive exploration and a real cross-dataset score, not an untouched precommitted confirmation. NSI also used a numerically/gradient-checked faster implementation in the 100k pair.

Sources: original official-recipe audit `codex:01a07a03-acf7-7fd1-b823-afdd157db056:002139` (2026-09-13 12:26 UTC); initial 50k result `:002233` (2026-09-14 00:05); human stop/reallocation `:002240` (00:08), 100k decision `:002313` (00:19), fresh-pair protocol `:002316` and `:002344`; endpoint `:002957` (11:02), checkpoint verification `:003028`, accelerated-implementation checks `:002579` and `:002630`. Evidence level: original-session training/evaluation report and checks, single seed and adaptive test reuse.
