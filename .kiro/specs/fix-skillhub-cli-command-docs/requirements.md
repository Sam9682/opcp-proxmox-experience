# Requirements Document

## Introduction

The `proxmox-install` command-line interface exposes its operations through Click subcommands. The primary operation, installation, lives under the `install` subcommand, and image building lives under the `build-image` subcommand. The top-level command group accepts no options of its own; a bare invocation only prints help.

Several documentation surfaces (the SkillHub lab pages in English and French, and the project README) currently show an invalid command pattern: `proxmox-install --config config.yaml`. Because the top-level group rejects the `--config` option, every documented example following this pattern fails when a reader copies and runs it.

This feature corrects the documentation so that every runnable command example reflects the actual CLI contract. Command examples that pass options such as `--config` and `--dry-run` are rewritten to place those options under the `install` subcommand, and a light mention of the `build-image` subcommand is added where relevant. The bare `proxmox-install --help` form remains unchanged because it is valid as documented. English and French wording is kept parallel.

## Glossary

- **CLI**: The `proxmox-install` command-line interface defined in `proxmox_install_automation/cli.py`, whose entry point maps `proxmox-install` to `cli:main`.
- **Command_Group**: The top-level Click group `main`, configured with `invoke_without_command=True`, that accepts no options and prints help when invoked bare.
- **Install_Subcommand**: The `install` subcommand of the CLI, which owns the options `--config`/`-c` (required), `--debug`/`-d`, `--dry-run`, `--skip-gpu`, `--skip-vm`, `--cleanup-only`, and `--log-file`.
- **Build_Image_Subcommand**: The `build-image` subcommand of the CLI, which owns the options `--config`/`-c` (required) and `--dry-run`.
- **Invalid_Pattern**: The documented command form `proxmox-install --config config.yaml`, which fails because the Command_Group rejects the `--config` option.
- **Correct_Install_Form**: A command form that places installation options under the Install_Subcommand, for example `proxmox-install install --config config.yaml` or `proxmox-install install --config config.yaml --dry-run`.
- **Help_Form**: The command `proxmox-install --help`, which is valid against the Command_Group and requires no subcommand prefix.
- **Cheat_Sheet_Page**: A SkillHub documentation page presenting copy-paste command examples, specifically `skillhub/en/cheat-sheet.html` and `skillhub/fr/cheat-sheet.html`.
- **Lab_Page**: Any SkillHub documentation page in the `skillhub/en/` or `skillhub/fr/` directory, including index, prerequisites, cleanup, and cheat-sheet pages.
- **README**: The project file `README.md`.
- **EN_Page**: A SkillHub documentation page under `skillhub/en/`.
- **FR_Page**: A SkillHub documentation page under `skillhub/fr/`.

## Requirements

### Requirement 1

**User Story:** As a reader following the documentation, I want every `proxmox-install` command example that passes installation options to run successfully when copied, so that I do not encounter option-rejection errors.

#### Acceptance Criteria

1. THE Documentation SHALL replace every occurrence of the Invalid_Pattern with a Correct_Install_Form that places the `--config` option under the Install_Subcommand.
2. WHERE a documented example passes the `--dry-run` option alongside `--config`, THE Documentation SHALL render the example as `proxmox-install install --config config.yaml --dry-run`.
3. WHERE a documented example passes only the `--config` option, THE Documentation SHALL render the example as `proxmox-install install --config config.yaml`.
4. THE Documentation SHALL leave every Help_Form example unchanged, without inserting the Install_Subcommand prefix.

### Requirement 2

**User Story:** As a reader using the cheat sheet, I want each command line to be independently copy-paste runnable, so that I can execute any single line without adding a missing subcommand.

#### Acceptance Criteria

1. THE Cheat_Sheet_Page SHALL prefix every command example line that passes installation options with the Install_Subcommand.
2. THE `skillhub/en/cheat-sheet.html` file SHALL present all seven affected command example lines in a Correct_Install_Form.
3. THE `skillhub/fr/cheat-sheet.html` file SHALL present all seven affected command example lines in a Correct_Install_Form.
4. WHERE a Cheat_Sheet_Page presents a Help_Form line, THE Cheat_Sheet_Page SHALL leave that line without the Install_Subcommand prefix.

### Requirement 3

**User Story:** As a reader exploring the CLI, I want to know that image building is available under a dedicated subcommand, so that I understand the CLI offers more than installation.

#### Acceptance Criteria

1. WHERE a Cheat_Sheet_Page documents CLI commands, THE Cheat_Sheet_Page SHALL include a mention of the Build_Image_Subcommand.
2. WHERE the Build_Image_Subcommand is mentioned, THE Documentation SHALL present its correct form using the `build-image` subcommand with the `--config` option.

### Requirement 4

**User Story:** As a maintainer, I want all affected documentation files corrected, so that no documentation surface retains the invalid pattern.

#### Acceptance Criteria

1. THE `skillhub/en/index.html` file SHALL present both affected command examples in a Correct_Install_Form.
2. THE `skillhub/fr/index.html` file SHALL present both affected command examples in a Correct_Install_Form.
3. THE `skillhub/en/prerequisites.html` file SHALL present the affected command example in a Correct_Install_Form.
4. THE `skillhub/fr/prerequisites.html` file SHALL present the affected command example in a Correct_Install_Form.
5. THE `skillhub/en/cleanup.html` file SHALL present the affected command example in a Correct_Install_Form.
6. THE `skillhub/fr/cleanup.html` file SHALL present the affected command example in a Correct_Install_Form.
7. THE README SHALL present the affected command example in a Correct_Install_Form.

### Requirement 5

**User Story:** As a bilingual reader, I want the English and French documentation to convey the same corrected instructions, so that both audiences receive equivalent guidance.

#### Acceptance Criteria

1. THE Documentation SHALL keep the corrected command examples on each EN_Page parallel to the corresponding FR_Page.
2. WHERE a mention of the Build_Image_Subcommand is added to an EN_Page, THE Documentation SHALL add a parallel mention to the corresponding FR_Page.
3. THE Documentation SHALL preserve the original command semantics of each example, changing only the command form and not the referenced configuration file name or option values.
