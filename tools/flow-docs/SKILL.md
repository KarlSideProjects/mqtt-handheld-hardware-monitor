---
name: flow-docs-sync
description: Use when establishing system or feature flowcharts with source-code navigation, requiring agents to read flow documents before code changes, enforcing documentation synchronization in CI, or adding, modifying, refactoring, moving or deleting code in an adopted project.
license: MIT
---

# Flow documentation synchronization

Keep system overview, feature flows and implementation references consistent in the same change. The bundled checker verifies structural/content consistency; source review and behavioral evidence establish semantic confidence.

## Select the operation

- **Adopt:** inventory features/inputs, establish flows and mappings, install the project reading rule and checker/hook.
- **Maintain:** read affected flows before editing, synchronize changes and run checks/review.
- **Audit:** report coverage gaps and bypasses without changing the system.

Read local instructions and terminology first; reuse the project's documentation and discovery tools. Installing this skill does not configure a project or its CI. Whole-project adoption requires all first-party behavior-bearing logic accounted for; excluded logic remains an explicit coverage gap.

## Project files and responsibilities

Use these repository-relative paths for new adoption. `<feature-id>` is the manifest feature ID, such as `download.run`; use filename-safe IDs. `<fingerprint>` is the checker's current feature fingerprint, and `<scenario-id>` is a stable filename-safe runtime scenario name.

| Path / filename | Required when | Purpose |
| --- | --- | --- |
| `AGENTS.md` | Every adoption | Shared pre-edit reading and post-edit synchronization rules; link the actual flow index, manifest and checker command. |
| `docs/flows/README.md` | Every adoption | System overview and flow index: feature IDs, links to checked flows and contracts, source-file/symbol navigation, adopted scope/gaps, and existing document paths/owners. |
| `docs/flows/<feature-id>.mmd` | Each adopted feature | Checked Mermaid flowchart for that feature. Set the manifest's `flow` to this exact path. An explicitly selected PlantUML flow uses the same basename with `.puml`. |
| `docs/flow-manifest.json` | Every adoption | Machine-readable source inventory, fingerprints, feature/node/symbol mappings, `depends_on`, reviews and policy inputs. |
| `docs/flows/contracts.md` | Shared contracts have no existing authoritative document | Shared boundaries, inputs/outputs, errors and invariants. If an existing contract owns them, link its exact path from the flow index instead of copying it. |
| `docs/flow-evidence/adoption.md` | Every adoption | Adoption report: exact artifact paths, reused documents, scope/gaps and separate verification states. It records results; rules remain in `AGENTS.md`. |
| `docs/flow-evidence/reviews/<feature-id>/<fingerprint>.json` | A feature requires independent review | Raw reviewer JSON preserved by the coordinator. The corresponding manifest review entry's `evidence` points to this exact file. |
| `docs/flow-evidence/runtime/<feature-id>/<scenario-id>.md` | Runtime or external-behavior evidence is needed | Filled runtime evidence template. Keep supporting logs/traces/images beside it in `<scenario-id>/`, surviving environment cleanup. |
| `tools/flow-docs/flow_checker.py`, `tools/flow-docs/flow_parsers.py`, `tools/flow-docs/requirements-ast.txt` | Every checker-enabled adoption | Copy the complete bundled `scripts/` directory here: CLI checker, optional language adapters and dependency pins. |
| `.git/hooks/pre-commit` | Installing a hook in a project without an existing hook manager | Staged check entrypoint. Compose with an existing hook manager or configured `core.hooksPath` instead, recording the actual file path. |
| `.github/workflows/flow-docs.yml` | Adding a dedicated GitHub Actions check | Project-specific candidate validation workflow; no workflow template is bundled. Existing CI may run the check in its current file; record that exact path. |
| `README.md` at repository root | Optional navigation | Short introduction and link to `docs/flows/README.md`; it does not own synchronization rules, feature flows, the manifest or adoption evidence. |

Existing requirements/architecture/contracts keep their authoritative locations; the flow index references them. Reusing documents does not relocate these required artifacts. Only explicit project instructions may override the default layout: record every default-to-actual path in `AGENTS.md` and the actual flow index, and update commands, manifest/evidence pointers and links consistently. Root `README.md` cannot substitute for required artifacts.

## Mandatory bootstrap, available in this file

During adoption, keep the shared synchronization rule in root `AGENTS.md` as its single source of truth. Use the project-file layout above; resolve and record any explicitly required path overrides before writing this block. Preserve existing instructions and local-only files. Establish missing document baselines before enabling their pointers.

When the actual Claude Code session discovers `AGENTS.md` directly, do not create `CLAUDE.md`. If root `CLAUDE.md` already exists, preserve its content and add a missing `@AGENTS.md` import; `.claude/CLAUDE.md` uses `@../AGENTS.md`. Imports resolve relative to their containing file; an ordinary Markdown link does not load instructions. For sessions without direct support, use a minimal import entrypoint as a compatibility fallback. Keep the rule itself in `AGENTS.md`.

Preserve `CLAUDE.local.md`: it can switch default discovery away from `AGENTS.md`, as can relevant ancestor instruction files. Verify imports or the session's effective instruction-file setting, including nested scopes and other tools; report discovery unverified when it was not observed. See the [entrypoint matrix](references/enforcement-contract.md#agent-entrypoint-discovery) for version conditions and verification.

```markdown
## [MANDATORY] Flow Documentation Sync Gate
1. Pre-Edit Read: before adding, modifying, refactoring, moving or deleting
   code or behavior-bearing inputs, read docs/flows/README.md,
   docs/flow-manifest.json and all affected feature/shared flows and contracts.
   Before the first edit, report: Affected Feature IDs: <resolved IDs>.
   Missing/stale flows require a source-verified baseline first;
   unreadable required documents block dependent edits.
2. Post-Edit Sync: run flow-docs-sync Maintain, update affected flows,
   mappings and source fingerprints in the same change, then run:
   python3 tools/flow-docs/flow_checker.py check --base HEAD
   Use the project's actual comparison base; HEAD is the local default.
   Obtain independent agent review where required; preserve repository human
   approval requirements. Hash refreshes alone are not semantic review.
3. Delegation/resume: each executing agent reads its own affected documents.
   Recheck the read set after scope/input changes or a handoff.
   Missing required checks or unresolved coverage prevent completion claims.
```

This block is usable without a reference file or installed skill. For new capabilities, read related flows and document intended behavior as proposed before implementation. Record read document identities and affected IDs in existing task evidence. Reading source to discover impact is allowed before editing. A read declaration cannot prove comprehension.

If an optional packaged resource is missing, retain this rule, verify the installed package and recover the matching resource from the skill's managed source. Report tooling incomplete; missing tooling does not authorize bypassing it or require stopping unrelated work.

## Adopt workflow

1. **Assign document responsibility.** Inventory existing requirements, architecture, contracts and flows; record their real paths and owners in `docs/flows/README.md` using the layout above. Requirements/contracts define intended behavior; source review establishes actual behavior. Record conflicts before changing the owning document instead of duplicating it.
2. **Choose a bounded scope.** Start with a core end-to-end feature plus its shared dependencies and behavioral inputs. List excluded and unknown areas as coverage gaps; partial adoption cannot claim whole-project coverage. Follow the [adoption inventory](references/enforcement-contract.md#adoption-inventory-and-staged-rollout).
3. **Establish the baseline.** Select explicit source modes, register sources/symbols and feature dependencies, then create the overview, per-feature flows and manifest at their specified paths. Link existing authoritative documents and reuse source-discovery tools. Refresh registered fingerprints and obtain initial reviews against the real comparison base before claiming a passing baseline.
4. **Install and verify.** Adopt the inline bootstrap and check actual discovery/read-before-edit ordering. Copy the complete checker tools, compose with existing hooks, run candidate-specific checks and verify required CI/merge settings. Preserve project-specific validation; absent execution evidence remains unverified.
5. **Report each gate.** Write `docs/flow-evidence/adoption.md` using the [completion report](references/enforcement-contract.md#completion-report), listing every required/conditional artifact with its exact path and created/reused/missing/not-applicable status. Save runtime evidence at the specified per-feature scenario path using the [template](references/enforcement-contract.md#runtime-evidence-template). Expand the adopted scope with its dependencies through another reviewed change; retain the same gates within the adopted scope.

Before claiming adoption complete, verify each required artifact exists, has its assigned content and is linked correctly. For conditional artifacts, record the actual file or a concrete reason it is not applicable. A README-only change, an empty directory, or a checklist claiming files exist does not establish adoption; missing artifacts/checks leave it incomplete.

## Maintain workflow

1. **Read and pin.** Read root instructions, overview, manifest, affected flows and shared contracts. Identify the comparison base and exact worktree, staged or committed candidate. Re-read after expanding scope.
2. **Compute impact.** Use the union of base/candidate mappings, including removed records, new files and new symbols in existing files. Follow explicit dependent-feature links. Review scope reductions and policy/checker changes separately. Uncertain dependencies use conservative file-level coverage.
3. **Synchronize.** Update flow sources, mappings and evidence. Run `snapshot` to refresh explicitly registered inputs; it does not register unknown code or approve behavior. Native Python and optional multi-language Tree-sitter adapters normalize syntax while retaining semantic tokens/directives. Module context changes affect all features mapped to that file; symbol-body changes affect mapped features and declared dependents. Keep raw MD5 for file-byte integrity. Unsupported syntax or uncertain dynamic dependencies use explicit file-level coverage rather than an invented symbol match.
4. **Review automatically.** When feature fingerprints identify affected synchronization obligations, obtain each affected feature's fingerprint, then dispatch a fresh reviewer with no conversation history using [the reviewer prompt](references/reviewer-prompt.md). Supply raw base/candidate sources, diff, flows, mappings, policy and tests, including relevant dependencies. The reviewer may request more source. Save its structured result as an evidence file and add the matching manifest review entry. This is an independent agent review record, not a cryptographic signature or repository human approval. Use at most two fix/review rounds per review request, then report unresolved findings. When subagents are unavailable, independent review is incomplete; continue safe work and report the missing gate rather than inventing approval.
5. **Check.** Run the bundled checker on the actual candidate, relevant behavioral tests and applicable project integration/deployment checks. For staged hooks use `--staged`; testing worktree bytes does not validate the index. Reject stale reviews when reviewed sources, flows, mappings, dependencies, base or policy change. Keep result records outside their own fingerprints.
6. **Report states.** Use the [completion report](references/enforcement-contract.md#completion-report) to distinguish installation, rule discovery, observed read ordering, coverage, structural checks, semantic review, behavior/visual evidence and human/merge requirements. Missing/skipped checks remain unverified; a structural pass does not establish semantic correctness or reviewer authenticity.

## Change filtering and synchronization gate

Local syntax/hash comparison identifies affected features before requesting semantic review. Ordinary source comments and formatting in supported AST modes only need byte-fingerprint refresh when normalized syntax and other bound inputs are unchanged. Keep their flows unchanged and create no new semantic-review obligation; still read before editing and run candidate checks.

```mermaid
flowchart TD
    A["Read affected flows before editing;<br/>pin the actual base and candidate"]
    B["Edit sources or behavioral inputs;<br/>snapshot registered fingerprints"]
    C{"Inventory, mappings and<br/>diagram syntax valid?"}
    D["Compare normalized syntax, flows,<br/>mappings and policy;<br/>follow declared feature dependencies"]
    E{"Any affected features?"}
    F["REUSE: keep flows;<br/>no new semantic-review obligation"]
    G["Inspect affected features and full context;<br/>sync flows or justify unchanged flows"]
    H["Independent semantic review;<br/>bind evidence to feature fingerprint"]
    I{"Coverage, hashes, affected reviews<br/>and required candidate checks pass?"}
    J["BLOCK: missing or stale inputs/reviews,<br/>unsupported syntax or failed checks"]
    K["Structural gate passed;<br/>report review, tests and merge controls separately"]
    A --> B
    B --> C
    C -->|No| J
    C -->|Yes| D
    D --> E
    E -->|No| F
    E -->|Yes| G
    F --> I
    G --> H
    H --> I
    I -->|No| J
    I -->|Yes| K
    classDef mechanical fill:#dbeafe,stroke:#1d4ed8,color:#172554
    classDef reuse fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef affected fill:#fef3c7,stroke:#a16207,color:#713f12
    classDef review fill:#f3e8ff,stroke:#7e22ce,color:#581c87
    classDef blocked fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    class A,B,C,D,I mechanical
    class F,K reuse
    class E,G affected
    class H review
    class J blocked
```

Blue blocks cover preparation and mechanical comparison/validation; green blocks avoid unnecessary redraws or report structural success. Amber limits work to affected features, purple requires independent review, and red blocks incomplete checks. This colored explanatory diagram uses Mermaid styling; manifest-registered product flows must use the checker's [portable diagram subset](references/enforcement-contract.md#headless-diagram-validation).

Change size is not the trigger: a one-character operator or literal change can affect behavior. AST differences conservatively trigger review; redraw a flow only when its documented behavior changes, otherwise retain it with reviewer-verified reasoning. File-mode inputs remain byte-sensitive; Python docstrings, literal whitespace and supported tool directives can also affect hashes. See the [change/obligation table](references/enforcement-contract.md#change-filtering-and-review-cost) for exact boundaries.

Token savings come from avoiding new semantic-review calls and flow rewrites for unchanged features, while retaining each affected feature's full source/context/dependencies and required pre-edit reading. The checker rejects missing coverage or current review records; required CI and protected merge settings must enforce that result on the actual candidate. It neither writes flows automatically nor proves runtime equivalence, reviewer authenticity or comprehension. Token savings are workload-dependent and unmeasured.

## Bundled tools

Python 3.10+ and Git run the checker; its implementation language does not restrict the project's languages. File-level and native-Python checks need no third-party packages. Install `scripts/requirements-ast.txt` in a dedicated environment for optional Tree-sitter symbol checks across supported languages. Read [the enforcement contract](references/enforcement-contract.md) for the tested grammar/symbol boundaries and first adoption.

```bash
python3 <skill-dir>/scripts/flow_checker.py snapshot --root .
python3 <skill-dir>/scripts/flow_checker.py fingerprint --root . --base HEAD --feature feature.id
python3 <skill-dir>/scripts/flow_checker.py check --root . --base HEAD
```

The checker supports an explicit, bounded Mermaid flowchart/PlantUML named-state subset, not either language's full grammar. Unsupported constructs fail visibly. Its headless checks cover node/symbol mappings, inventory, fingerprints, diff obligations and configurable complexity limits. They do not establish visual readability or semantic correctness. Render and inspect when available; otherwise record `visual verification: pending` without blocking headless structural verification. Regenerate committed derived images through project tooling or report them stale.

Copy the complete `scripts/` directory to a project-owned path when installing CI/hooks. Include the checker, parser adapter and dependency pins in `policy_inputs`. Adapt [the pre-commit template](assets/pre-commit) to the project's hook path; compose with existing hooks rather than overwriting them. A local hook is bypassable. Required CI results and protected review settings provide the merge gate, including a safe manual path for untrusted forks. Verify those settings rather than assuming them.

## Completion boundaries

A semantic review may leave a flow unchanged with a concrete, evidenced explanation. Normalized comment/layout changes need refreshed byte fingerprints but do not invalidate unchanged semantic reviews. A whole-file fallback or module-level context change conservatively affects every mapped feature. Git function-context hunks assist impact investigation but are not a semantic-hash backend.

All first-party logical inputs, public entrypoints and shared dependencies must be accounted for before claiming whole-project coverage. External APIs, remote configuration and floating dependencies require separate runtime evidence. Preserve repository validation requirements and existing authorization for publishing, deployment or remote settings.

A complete install includes this file, the checker, hook and referenced resources. Missing resources mean an incomplete installation, not permission to skip the gate. A project with no checker remains manual-only; unconfirmed remote merge settings mean merge enforcement is unconfirmed.
