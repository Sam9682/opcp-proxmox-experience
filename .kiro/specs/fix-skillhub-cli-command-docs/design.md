# Design Document

## Overview

This is a documentation-consistency bugfix. The `proxmox-install` CLI is a Click group (`main`, `invoke_without_command=True`) that accepts no options of its own; installation options live under the `install` subcommand and image building under the `build-image` subcommand. Several documentation surfaces show the invalid form `proxmox-install --config ...`, which fails at runtime because the top-level group rejects `--config`.

The change edits only documentation: SkillHub HTML lab pages (EN/FR) and `README.md`. No Python source is modified. Every runnable example that passes installation options is rewritten to place them under the `install` subcommand, a light mention of `build-image` is added to the cheat sheets, and the valid `proxmox-install --help` form is left untouched.

## CLI Contract (source of truth)

Confirmed by inspecting `proxmox_install_automation/cli.py`:

- `main` — `@click.group(invoke_without_command=True)`, no options. A bare invocation prints help.
- `install` — `@main.command()`, owns `--config`/`-c` (required), `--debug`/`-d`, `--dry-run`, `--skip-gpu`, `--skip-vm`, `--cleanup-only`, `--log-file`.
- `build-image` — `@main.command("build-image")`, owns `--config`/`-c` (required), `--dry-run`.

Implications for the docs:

- `proxmox-install --config config.yaml [...]` is invalid → must become `proxmox-install install --config config.yaml [...]`.
- `proxmox-install --help` is valid → unchanged.
- `proxmox-install build-image --config config.yaml` is the correct image-build form.

## Transformation Strategy

A single, mechanical find/replace applied inside `<pre><code>` blocks (and the README fenced code block):

```
proxmox-install --config   →   proxmox-install install --config
```

Rules:

1. Apply only to lines beginning the command with `proxmox-install --config`. All trailing options (`--dry-run`, `--skip-gpu`, `--skip-vm`, `--debug`, `--cleanup-only`, `--log-file`) are preserved verbatim after the config argument.
2. Do not alter the config file name (`config.yaml`) or any option values (Req 5.3).
3. Never touch `proxmox-install --help` (Req 1.4, 2.4).
4. Do not prefix an already-correct `install`/`build-image` invocation a second time (idempotence guard for re-runs).
5. Comment lines (starting with `#`) inside the code blocks are left as-is.

The edit is deterministic and enumerable; it is safest to apply per occurrence using an exact-match string replace rather than a broad regex, so surrounding markup and comments are untouched.

## Per-File Breakdown of Occurrences

Line numbers reflect the current files and are approximate; edits are matched by content.

| File | Occurrences | Forms |
|------|-------------|-------|
| `skillhub/en/index.html` | 2 | `--config --dry-run`; `--config` |
| `skillhub/fr/index.html` | 2 | `--config --dry-run`; `--config` |
| `skillhub/en/cheat-sheet.html` | 7 | `--config`; `--config --dry-run`; `--config --skip-gpu`; `--config --skip-vm`; `--config --debug`; `--config --cleanup-only`; `--config --log-file build.log` |
| `skillhub/fr/cheat-sheet.html` | 7 | same seven as EN |
| `skillhub/en/prerequisites.html` | 1 | `--config --dry-run` |
| `skillhub/fr/prerequisites.html` | 1 | `--config --dry-run` |
| `skillhub/en/cleanup.html` | 1 | `--config --cleanup-only` |
| `skillhub/fr/cleanup.html` | 1 | `--config --cleanup-only` |
| `README.md` | 1 | `--config` |

Total: 23 occurrences of the invalid pattern become the correct install form (2+2+7+7+1+1+1+1+1).

### Corrected forms

- `proxmox-install install --config config.yaml`
- `proxmox-install install --config config.yaml --dry-run`
- `proxmox-install install --config config.yaml --skip-gpu`
- `proxmox-install install --config config.yaml --skip-vm`
- `proxmox-install install --config config.yaml --debug`
- `proxmox-install install --config config.yaml --cleanup-only`
- `proxmox-install install --config config.yaml --log-file build.log`

## `build-image` Subcommand Mention

The cheat-sheet pages are the natural fit because they enumerate CLI commands as copy-paste lines (Req 3.1, 3.2, 5.2). Add a single line inside the existing "Automation CLI" / "CLI de l'automatisation" `<pre><code>` block, kept parallel EN/FR.

- EN (`skillhub/en/cheat-sheet.html`), appended within the automation CLI block:
  ```
  # Build the qcow2 image (build-image subcommand)
  proxmox-install build-image --config config.yaml
  ```
- FR (`skillhub/fr/cheat-sheet.html`), parallel wording:
  ```
  # Construire l'image qcow2 (sous-commande build-image)
  proxmox-install build-image --config config.yaml
  ```

The mention is light-touch: one comment line plus one command line per cheat sheet, using the correct `build-image --config` form. No other page gains a build-image mention, keeping EN and FR symmetric.

## EN/FR Parallelism

Each EN page and its FR counterpart receive identical command forms; only the surrounding comment/prose language differs (Req 5.1, 5.2). The config file name and option values are identical across both languages (Req 5.3). After editing, the set of corrected command lines in `en/cheat-sheet.html` must equal the set in `fr/cheat-sheet.html`, and likewise for index, prerequisites, and cleanup.

## Verification Approach

This is documentation editing, so verification is grep-based (no unit or property tests are appropriate for static docs):

1. Absence of the invalid pattern — the primary gate:
   ```bash
   grep -rn 'proxmox-install --config' skillhub README.md
   ```
   Expected: zero matches. Any match indicates a missed occurrence.

2. Confirm the valid help form is untouched (should still appear, never prefixed with `install`):
   ```bash
   grep -rn 'proxmox-install --help' skillhub README.md
   ```

3. Confirm the correct install form is present with the expected counts per file:
   ```bash
   grep -rc 'proxmox-install install --config' skillhub README.md
   ```
   Expected: index EN/FR = 2 each, cheat-sheet EN/FR = 7 each, prerequisites EN/FR = 1 each, cleanup EN/FR = 1 each, README = 1.

4. Confirm the build-image mention exists in both cheat sheets:
   ```bash
   grep -rn 'proxmox-install build-image --config' skillhub/en/cheat-sheet.html skillhub/fr/cheat-sheet.html
   ```
   Expected: one match per file.

5. Optional CLI-contract confirmation — re-inspect `proxmox_install_automation/cli.py` to confirm `install` and `build-image` own `--config` and that the group takes no options, ensuring the documented forms match the code.

Note: step 1 must exclude the intentional `build-image` and `--help` forms; because those forms are `proxmox-install build-image --config` and `proxmox-install --help`, the literal string `proxmox-install --config` will not match them, so a plain grep for `proxmox-install --config` cleanly isolates only the invalid pattern.

## Error Handling / Risks

- Risk: a code block wraps the command across lines or includes trailing whitespace. Mitigation: match on the exact existing line content per occurrence (already confirmed single-line in every file).
- Risk: re-running the edit double-prefixes (`install install`). Mitigation: the transformation targets `proxmox-install --config` specifically, which no longer exists after a correct edit, so the operation is idempotent.
- No runtime, data, or infrastructure impact — changes are confined to documentation text.

## Correctness Properties

Per the prework analysis, every acceptance criterion describes a fixed, enumerable documentation edit or an EN/FR consistency check rather than code logic whose behavior varies across a large input space. Following the workflow guidance (documentation and configuration edits are not suitable for property-based testing), no universally-quantified correctness properties are defined for this feature. Verification is example/integration-style via the grep checks in the Verification Approach section:

- Invalid-pattern-absent check (Req 1.1, 2.1, 4.1–4.7) — repository grep returns zero matches.
- Exact-form checks (Req 1.2, 1.3, 2.2, 2.3) — grep for the literal corrected lines.
- Help-form-preserved check (Req 1.4, 2.4) — grep confirms `proxmox-install --help` remains, unprefixed.
- Build-image mention checks (Req 3.1, 3.2) — grep for `proxmox-install build-image --config` in both cheat sheets.
- EN/FR parallelism checks (Req 5.1, 5.2, 5.3) — corrected command-line sets match across language pairs with unchanged file name and option values.
