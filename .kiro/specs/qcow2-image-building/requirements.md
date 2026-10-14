# Requirements Document

## Introduction

This feature updates the existing English SkillHub lesson page at `skillhub/en/qcow2-image-building.html` to present two parallel approaches for building a Proxmox VE qcow2 image. The page currently documents only the OpenStack SDK Python pipeline (Approach A). This update adds a condensed version of the manual KVM/QEMU bare-metal build workflow (Approach B), sourced from `docs/Preparing_Proxmox_QCOW2_Image_OPCP_BareMetal_EN.md`, while preserving the existing SDK content.

The existing SDK content is retained unchanged in substance. A short "Two approaches" introduction is added near the top of the lesson body, followed by two parallel top-level sections. All existing SkillHub HTML conventions, the `lang="en"` attribute, and the five ordered script includes are preserved. The page is already registered in `skillhub/assets/js/lessons.js` with slug `qcow2-image-building`, so no navigation or sidebar registration changes are required.

## Glossary

- **SkillHub_Page**: The English HTML lesson file at `skillhub/en/qcow2-image-building.html`.
- **Approach_A**: The existing OpenStack SDK Python pipeline for building a Proxmox qcow2 image, using Proxmox VE version 8.2.
- **Approach_B**: The manual KVM/QEMU bare-metal build workflow sourced from `docs/Preparing_Proxmox_QCOW2_Image_OPCP_BareMetal_EN.md`, using Proxmox VE version 9.2.
- **Two_Approaches_Intro**: A short introductory block near the top of the lesson body that explains that two build approaches are presented and how they differ.
- **Lesson_Body**: The content inside the `main.main-content` element of the SkillHub_Page.
- **HTML_Conventions**: The established SkillHub page structure: `head` with charset, viewport, title, and stylesheet link; `header.site-header` containing the logo, `lang-toggle`, `progress-bar-container` with `progress-bar-fill`, `progress-text`, and `hamburger-btn`; `sidebar-overlay`; `site-wrapper` containing `aside.sidebar > nav#sidebar-nav` and `main.main-content`; `breadcrumbs`; `h1` with following `p.lesson-meta`; `h2` and `h3` section headings; `pre > code` blocks with `language-*` classes; `button.mark-complete-btn`; `div.prev-next-nav`; and `footer.site-footer`.
- **Script_Includes**: The five script tags at the end of `body`, in this order: `lessons.js`, `i18n.js`, `navigation.js`, `code-highlight.js`, `main.js`.

## Requirements

### Requirement 1

**User Story:** As a SkillHub learner, I want the lesson to introduce two distinct build approaches, so that I understand there is a choice before reading the detailed steps.

#### Acceptance Criteria

1. THE SkillHub_Page SHALL include a Two_Approaches_Intro block positioned after the `h1` heading and its following `p.lesson-meta` element and before the first approach section.
2. THE Two_Approaches_Intro SHALL describe Approach_A as the OpenStack SDK Python pipeline.
3. THE Two_Approaches_Intro SHALL describe Approach_B as the manual KVM/QEMU bare-metal build.

### Requirement 2

**User Story:** As a SkillHub learner, I want the existing SDK pipeline content preserved, so that the automated workflow I already rely on remains documented.

#### Acceptance Criteria

1. THE SkillHub_Page SHALL retain the Approach_A content covering build instance creation, ISO download, qcow2 conversion, snapshot creation, Glance upload, configuration reference, and CLI usage.
2. THE SkillHub_Page SHALL present Approach_A Proxmox VE version as 8.2.
3. THE SkillHub_Page SHALL present Approach_A as a top-level section parallel to Approach_B.

### Requirement 3

**User Story:** As a SkillHub learner, I want a condensed manual KVM/QEMU workflow, so that I can build a Proxmox bare-metal image without the OpenStack SDK.

#### Acceptance Criteria

1. THE SkillHub_Page SHALL present Approach_B as a top-level section parallel to Approach_A.
2. THE SkillHub_Page SHALL present Approach_B Proxmox VE version as 9.2.
3. THE Approach_B section SHALL document the prerequisites covering qemu, libvirt, virt-install, and ovmf.
4. THE Approach_B section SHALL document Proxmox ISO preparation.
5. THE Approach_B section SHALL document creation of a 64G qcow2 disk using `qemu-img create`.
6. THE Approach_B section SHALL document building the VM with `virt-install` using UEFI, 8 vCPU, and 16 GB RAM.
7. THE Approach_B section SHALL document the Proxmox installation using UEFI boot, GPT partitioning, and LVM.
8. THE Approach_B section SHALL document generic network configuration, the `pve-template` hostname, and the note that the image must not join a Proxmox cluster.
9. THE Approach_B section SHALL document image cleaning covering SSH host keys, machine-id, DHCP leases, logs, and apt cache cleanup.
10. THE Approach_B section SHALL document the clean VM shutdown step.
11. THE Approach_B section SHALL document removing the temporary VM with `virsh undefine --nvram`.
12. THE Approach_B section SHALL document qcow2 integrity check and compression using `qemu-img`.
13. THE Approach_B section SHALL document the boot test of the finalized image without the ISO.
14. THE Approach_B section SHALL document the Glance import using `openstack image create` as a whole-disk image without `kernel_id` or `ramdisk_id`.
15. THE Approach_B section SHALL document the Ironic `boot_mode:uefi` configuration.
16. THE Approach_B section SHALL document the bare-metal deployment step.
17. THE Approach_B section SHALL include brief summaries of post-deployment configuration, recommendations, and recommended evolution.

### Requirement 4

**User Story:** As a SkillHub maintainer, I want the page to keep all established HTML conventions, so that it renders and behaves consistently with the rest of the site.

#### Acceptance Criteria

1. THE SkillHub_Page SHALL retain the `lang="en"` attribute on the `html` element.
2. THE SkillHub_Page SHALL retain all HTML_Conventions structural elements.
3. THE SkillHub_Page SHALL retain the Script_Includes in the defined order.
4. WHERE a code example is presented, THE SkillHub_Page SHALL wrap the example in a `pre > code` block using a `language-*` class consistent with the example content.
5. THE SkillHub_Page SHALL use `h2` elements for the two top-level approach sections and `h3` elements for subsections within each approach.
6. THE SkillHub_Page SHALL retain a single `button.mark-complete-btn` element and a single `div.prev-next-nav` element positioned after the final lesson content and before the closing of `main.main-content`.
