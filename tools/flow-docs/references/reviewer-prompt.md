# Independent agent review

Use a fresh subagent with no inherited conversation when the runtime supports it. Supply the raw artifacts below; omit the author's proposed verdict and justifications. A human reviewer is the fallback when available. Repository-required human approval remains separate.

## Dispatch template

```text
Review flow-documentation consistency for the supplied candidate.
Read-only: do not modify files, execute target application code, publish,
approve a repository review, or spawn additional reviewers.

Inputs:
- Comparison base, candidate identity, scope/impact policy and feature ID.
- The checker-generated fingerprint for that feature.
- The manifest's exact flow path, relevant document paths and recorded layout overrides.
- Raw diff plus base/candidate source, module context and dependencies.
- Base/candidate flow sources, mappings and relevant contracts.
- Behavioral test code and execution evidence, with unverified items marked.

Verify the feature's actual branches, interactions, errors, cancellation,
recovery and side effects against its flow. Check hidden impact from removed
mappings, changed globals/imports and new entrypoints. Read additional relevant
source when the supplied artifacts are insufficient; request missing access.
A hash or passing checker is not semantic proof. State any unchanged-flow
reason precisely, supported by the artifacts, rather than accepting an
assertion from the author.

Return JSON only:
{"feature":"<ID>","fingerprint":"<provided fingerprint>",
 "reviewer":"<actual agent/task identity>","verdict":"pass|fail|incomplete",
 "findings":[],"evidence":["<source/test references>"],
 "limitations":["<unverified matters>"]}

Use fail for demonstrated inconsistencies, incomplete for missing evidence,
and pass only when the reviewed scope has no unresolved consistency findings.
Each finding names location, consequence and smallest correction.
```

The coordinator preserves the returned JSON at the review-evidence path in the [project-file layout](../SKILL.md#project-files-and-responsibilities), verifies it names the intended feature/fingerprint, and records that exact path in the manifest. Review outputs are excluded from their own fingerprints. Subsequent input changes invalidate the affected result.

This file format is an auditable agent declaration. It neither authenticates a remote reviewer nor supplies a cryptographic signature. A CI integration must use its own trusted review/control path when reviewer authenticity is required. The checker validates record consistency and rejection conditions; it cannot determine whether an author impersonated a reviewer.

Fix findings and repeat with a fresh reviewer for at most two rounds per request. Report remaining findings or unavailable review service; do not silently downgrade them to a successful semantic gate.
