# Implementation Plan: Fix SkillHub CLI Command Docs

## Overview

This is a documentation-consistency bugfix. Every runnable example showing the invalid
`proxmox-install --config config.yaml [...]` form is rewritten to the correct install form
`proxmox-install install --config config.yaml [...]`, preserving all trailing options and
option values verbatim. The valid `proxmox-install --help` form is never changed. A
light-touch `build-image` mention is added to both cheat sheets. English and French pages
receive identical command forms; only surrounding comment/prose language differs.

**Transformation rule (applies to every edit below):**
```
proxmox-install --config config.yaml [options]   →   proxmox-install install --config config.yaml [options]
```
- Trailing options (`--dry-run`, `--skip-gpu`, `--skip-vm`, `--debug`, `--cleanup-only`, `--log-file build.log`) are preserved verbatim.
- The config file name (`config.yaml`) and all option values are unchanged.
- `proxmox-install --help` is left untouched (never prefixed with `install`).
- Match on exact existing line content per occurrence; leave comment lines (`#`) as-is.

No Python source is modified. Verification is grep-based (no unit or property tests apply to static docs).

## Tasks

- [x] 1. Correct command examples in the index lab pages
  - [x] 1.1 Correct `skillhub/en/index.html`
    - Rewrite both invalid occurrences: `--config --dry-run` and `--config` forms
    - Apply `proxmox-install --config ...` → `proxmox-install install --config ...`, preserving `--dry-run` and the `config.yaml` name/values
    - Leave any `proxmox-install --help` line unchanged
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 5.3_

  - [x] 1.2 Correct `skillhub/fr/index.html`
    - Rewrite both invalid occurrences in parallel with the EN page (identical command forms)
    - Apply the transformation rule; only the surrounding French comment/prose differs
    - Leave any `proxmox-install --help` line unchanged
    - _Requirements: 1.1, 1.2, 1.3, 4.2, 5.1, 5.3_

- [x] 2. Correct command examples and add build-image mention in the cheat-sheet pages
  - [x] 2.1 Correct the seven command lines in `skillhub/en/cheat-sheet.html`
    - Rewrite all seven affected lines to the correct install form:
      `--config`; `--config --dry-run`; `--config --skip-gpu`; `--config --skip-vm`; `--config --debug`; `--config --cleanup-only`; `--config --log-file build.log`
    - Preserve every trailing option and the `config.yaml` name/values verbatim
    - Leave any `proxmox-install --help` line unchanged (unprefixed)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.4, 5.3_

  - [x] 2.2 Add the build-image mention to `skillhub/en/cheat-sheet.html`
    - Inside the existing "Automation CLI" `<pre><code>` block, append one comment line plus one command line:
      ```
      # Build the qcow2 image (build-image subcommand)
      proxmox-install build-image --config config.yaml
      ```
    - Use the correct `build-image --config` form only
    - _Requirements: 3.1, 3.2_

  - [x] 2.3 Correct the seven command lines in `skillhub/fr/cheat-sheet.html`
    - Rewrite the same seven affected lines to the correct install form, parallel to EN (identical command forms)
    - Preserve every trailing option and the `config.yaml` name/values verbatim
    - Leave any `proxmox-install --help` line unchanged (unprefixed)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.3, 2.4, 5.1, 5.3_

  - [x] 2.4 Add the parallel build-image mention to `skillhub/fr/cheat-sheet.html`
    - Inside the existing "CLI de l'automatisation" `<pre><code>` block, append one comment line plus one command line:
      ```
      # Construire l'image qcow2 (sous-commande build-image)
      proxmox-install build-image --config config.yaml
      ```
    - Keep the command form identical to EN; only the French comment wording differs
    - _Requirements: 3.1, 3.2, 5.2_

- [x] 3. Correct command examples in the prerequisites lab pages
  - [x] 3.1 Correct `skillhub/en/prerequisites.html`
    - Rewrite the single `--config --dry-run` occurrence to the correct install form
    - Preserve `--dry-run` and the `config.yaml` name/values; leave any help line unchanged
    - _Requirements: 1.1, 1.2, 4.3, 5.3_

  - [x] 3.2 Correct `skillhub/fr/prerequisites.html`
    - Rewrite the single `--config --dry-run` occurrence in parallel with the EN page (identical command form)
    - Preserve `--dry-run` and the `config.yaml` name/values; leave any help line unchanged
    - _Requirements: 1.1, 1.2, 4.4, 5.1, 5.3_

- [x] 4. Correct command examples in the cleanup lab pages
  - [x] 4.1 Correct `skillhub/en/cleanup.html`
    - Rewrite the single `--config --cleanup-only` occurrence to the correct install form
    - Preserve `--cleanup-only` and the `config.yaml` name/values; leave any help line unchanged
    - _Requirements: 1.1, 1.3, 4.5, 5.3_

  - [x] 4.2 Correct `skillhub/fr/cleanup.html`
    - Rewrite the single `--config --cleanup-only` occurrence in parallel with the EN page (identical command form)
    - Preserve `--cleanup-only` and the `config.yaml` name/values; leave any help line unchanged
    - _Requirements: 1.1, 1.3, 4.6, 5.1, 5.3_

- [x] 5. Correct the command example in `README.md`
  - [x] 5.1 Correct the affected command in the README fenced code block
    - Rewrite the single `--config` occurrence to `proxmox-install install --config config.yaml`
    - Preserve the `config.yaml` name/values; leave any `proxmox-install --help` line unchanged
    - _Requirements: 1.1, 1.3, 4.7, 5.3_

- [x] 6. Final verification checkpoint
  - [x] 6.1 Run the grep-based verification checks from the design
    - Invalid pattern absent: `grep -rn 'proxmox-install --config' skillhub README.md` → expect zero matches
    - Help form preserved (unprefixed): `grep -rn 'proxmox-install --help' skillhub README.md` → still present, never prefixed with `install`
    - Correct install form counts: `grep -rc 'proxmox-install install --config' skillhub README.md` → index EN/FR = 2 each, cheat-sheet EN/FR = 7 each, prerequisites EN/FR = 1 each, cleanup EN/FR = 1 each, README = 1
    - Build-image mention present: `grep -rn 'proxmox-install build-image --config' skillhub/en/cheat-sheet.html skillhub/fr/cheat-sheet.html` → one match per file
    - EN/FR parallel: corrected command-line sets match across each language pair, with unchanged file name and option values
    - Ensure all checks pass; ask the user if questions arise.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2, 5.3_

## Notes

- No Python source is modified; this feature edits documentation text only.
- Each task references specific requirements for traceability.
- No property or unit tests are appropriate for static documentation; verification is grep-based per the design.
- EN and FR pages receive identical command forms; only surrounding comment/prose language differs.
- The transformation is idempotent: after a correct edit `proxmox-install --config` no longer exists, so re-running cannot double-prefix.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "2.3", "3.1", "3.2", "4.1", "4.2", "5.1"] },
    { "id": 1, "tasks": ["2.2", "2.4"] },
    { "id": 2, "tasks": ["6.1"] }
  ]
}
```
