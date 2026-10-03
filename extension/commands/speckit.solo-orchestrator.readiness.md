---
description: Require current human Implementation Readiness approval.
---

# Solo Implementation Readiness

Run only at the mandatory native `before_implement` boundary, after the current
installed Feature Governance Guard and MVP Complexity Preflight both PASS.
An earlier approval never substitutes for either fresh guard. If either is
missing, uncertain or blocking, stop without writing implementation code.

Run `python3 scripts/solo.py readiness` from the project root. A successful
result is `IMPLEMENTATION READINESS: PASS`. Any error blocks Core implementation.
This check requires current Spec approval before checking Readiness. For missing
or stale Spec approval, derive the route again with `solo.py next` and follow its
existing governed Spec boundary; preserve all downstream artifacts and progress.
For missing, rejected or stale Readiness approval, present the current Feature's spec,
plan, tasks and applicable UX authorities for explicit Implementation Readiness
approval. Do not choose for the human. Stop at this boundary; the Solo caller
records the decision using `solo.py approve implementation-readiness --human --verification PASS`
only after the actual explicit human decision. A fresh invocation reruns the
native guards and this check. Do not implement, persist guard results, or
rerun/copy either guard from this hook.

Readiness binds foundation authorities, Spec, Plan, Tasks scope and applicable
UX/design authorities. Normal source, test, build or implementation/browser
evidence changes do not require renewed Readiness approval. Native task
completion marks do not change approved scope. Changed governing inputs still
require renewed approval; an approval never substitutes for fresh Analyze,
Feature Governance Guard or MVP Complexity Preflight requirements.
