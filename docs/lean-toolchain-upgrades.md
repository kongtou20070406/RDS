# Following stable Lean and Mathlib releases

RDS follows the newest matching stable Lean/Mathlib release that passes its native
checks. Lean 4.33.1 is not a compatibility ceiling. As checked on 2026-10-03,
[Lean v4.34.1](https://github.com/leanprover/lean4/releases/tag/v4.34.1) and
[Mathlib v4.34.1](https://github.com/leanprover-community/mathlib4/releases/tag/v4.34.1)
are the latest stable pair. Mathlib master uses a release candidate and is not the
stable upgrade target.

Each accepted revision still records an exact `formal/lean-toolchain`, Mathlib tag
in `formal/lakefile.lean`, all dependency SHAs in `formal/lake-manifest.json`, and
the matching `MATHLIB_REV` guard in `scripts/rds_statistical_verify.py`. These locks
make older commits and proof certificates reproducible. The
[official Elan guidance](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Managing-Toolchains-with-Elan/)
also recommends an exact project toolchain. Do not substitute floating `stable`,
`latest`, `master`, or a nightly for the accepted toolchain.

## Update the pair

Work in a clean branch or isolated worktree. From the repository root:

```text
python -B scripts/update_lean_toolchain.py --check
python -B scripts/update_lean_toolchain.py --apply
python -B scripts/update_lean_toolchain.py --check-lock
```

`--check` reads the official Mathlib release API without changing files. `--apply`
uses that release's declared Lean toolchain, updates the exact tag, runs
`lake update mathlib`, and synchronizes the checker revision with the regenerated
manifest. `--version v4.34.1` selects an explicit stable pair for a controlled
upgrade or rollback. The updater restores the four configuration files if an
update fails; downloaded toolchains/packages may remain installed. It does not
build, commit, push or merge. `--check-lock` is offline; the existing CI unit suite
checks the actual checkout's paired locks. The updater accepts the bundled Formal Lakefile layout and rejects
comments or additional declarations for manual review instead of guessing how to
rewrite a customized project. No automatic upgrade schedule or automatic merge
is enabled.

Build new artifacts using the selected toolchain; do not copy old `.olean` files:

```text
cd formal
lake exe cache get
lake build
cd ..
python -B -m unittest discover -s tests -p test_update_lean_toolchain.py -v
python -B -m unittest discover -s tests -p 'test_rds_lean*.py' -v
python -B -m unittest discover -s tests -p test_rds_statistical_obligations.py -v
```

If Windows Git reports Schannel `SEC_E_NO_CREDENTIALS`, use OpenSSL for that
invocation (`GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=http.sslBackend`,
`GIT_CONFIG_VALUE_0=openssl`), retaining the existing credential helper.
Install the declared toolchain explicitly if Elan needs access outside the
workspace; runtime verification never installs or downloads dependencies.

The existing Lean CI job must build the entire Formal library, audit its axioms,
require native artifacts, and run native certificate replay. Locally, perform
the same preflight (`rds_lean_verify._executable()` and
`rds_statistical_verify._library(module)` for all selected theorem modules) so
missing artifacts cannot turn required native coverage into skipped tests.
Exercise the actual CLI `formal verify --no-cache` followed by `formal check`
for a closed rational obligation and each of Hoeffding, Ville and DPI; require
`LEAN_KERNEL_CHECKED`, preserving `application_status: UNKNOWN` for statistical
application premises. See [native replay commands](lean-native.md#build-and-replay).

Review changed APIs and transitive dependency SHAs, run `git diff --check`, and
submit the complete pair for review. The existing CI and review decide adoption;
a newer release alone does not establish compatibility. Keep the previous
accepted revision available for rollback. Version/library changes invalidate
old certificate bindings and require a fresh proof and independent replay.

## External Lean packages

Evaluate TorchLean and equality-saturation libraries against the new accepted
pair in a separate Lake workspace. A package pinned to an older version can be
ported or tested against the current stable pair; its pin does not freeze RDS.
Only integrate it after its proofs, shape premises, runtime/FFI boundary and
license have been checked. Matching version numbers alone establish no such
result. The [tensor roadmap](tensor-operator-formalization.md) remains a design
and dependency evaluation, not a delivered general tensor backend.
