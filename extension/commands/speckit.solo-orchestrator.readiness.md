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
For missing, rejected or stale approval, present the current Feature's spec,
plan, tasks and applicable UX authorities for explicit Implementation Readiness
approval. Do not choose for the human. Stop at this boundary; the Solo caller
records the decision using `solo.py approve implementation-readiness --human --verification PASS`
only after the actual explicit human decision. A fresh invocation reruns the
native guards and this check. Do not implement, persist guard results, or
rerun/copy either guard from this hook.
