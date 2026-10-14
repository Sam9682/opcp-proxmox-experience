# Design Document

## Overview

This design updates the existing English SkillHub lesson `skillhub/en/qcow2-image-building.html` **in place**. The page currently documents only the OpenStack SDK Python pipeline. The update restructures the lesson body into two parallel top-level approaches:

- **Approach A — OpenStack SDK pipeline** (Proxmox VE 8.2): the existing content, wrapped in a top-level section.
- **Approach B — Manual KVM/QEMU bare-metal build** (Proxmox VE 9.2): a condensed version of the 23-section source doc `docs/Preparing_Proxmox_QCOW2_Image_OPCP_BareMetal_EN.md`.

This is a static HTML documentation task. There is no build tooling, no bundler, and no test runner. The work is confined to editing one HTML file. The page slug `qcow2-image-building` is already registered in `skillhub/assets/js/lessons.js`, so no catalog, sidebar, or navigation changes are required.

## Architecture

### Scope of change

Only `main.main-content` is restructured. The following scaffolding is left **untouched**:

- `head` (charset, viewport, title, stylesheet link)
- `header.site-header` (logo, `lang-toggle`, `progress-bar-container` + `progress-bar-fill`, `progress-text`, `hamburger-btn`)
- `sidebar-overlay`
- `site-wrapper > aside.sidebar > nav#sidebar-nav`
- `breadcrumbs`, `h1`, `p.lesson-meta` (kept as-is at the top of the body)
- `footer.site-footer`
- the five ordered `Script_Includes`: `lessons.js`, `i18n.js`, `navigation.js`, `code-highlight.js`, `main.js`
- the `lang="en"` attribute on `<html>`

### Lesson body structure (target)

```text
main.main-content
├── breadcrumbs            (existing, untouched)
├── h1                     (existing, untouched)
├── p.lesson-meta          (existing, untouched)
├── Two approaches intro   (NEW block: intro <p> describing A and B)
├── h2  Approach A — OpenStack SDK pipeline
│   └── existing content moved under this h2, demoted:
│       ├── h3 Overview            (was h2)
│       ├── h3 Prerequisites       (was h2)
│       ├── h3 Step-by-step Workflow (was h2)
│       │   ├── h4 Step 1 … Step 5 (were h3)   OR keep h3 — see "Heading demotion"
│       ├── h3 Configuration Reference (was h2)
│       └── h3 CLI Usage           (was h2)
├── h2  Approach B — Manual KVM/QEMU bare-metal build
│   └── h3 subsections (condensed, see mapping)
├── button.mark-complete-btn   (existing, single, moved to end)
└── div.prev-next-nav          (existing, single, moved to end)
```

### Heading demotion for Approach A

The existing Approach A content uses `h2` for its sections (Overview, Prerequisites, Step-by-step Workflow, Configuration Reference, CLI Usage) and `h3` for Steps 1–5. To satisfy Requirement 4.5 (two top-level approaches at `h2`, subsections at `h3`), the two approaches become the only `h2` elements. Approach A's former `h2` sections are demoted to `h3`, and the Step 1–5 `h3` headings are demoted to `h4`. All prose, code blocks, the table, and `language-*` classes within Approach A are preserved verbatim; only the heading levels change.

## Components and Interfaces

This is a single static HTML file. There are no runtime components or interfaces beyond the DOM structure consumed by the existing scripts. The relevant "interfaces" are the structural contracts the shared scripts depend on:

| Element | Consumed by | Contract |
|---------|-------------|----------|
| `nav#sidebar-nav` (empty) | `navigation.js` | populated at runtime from `lessons.js`; left empty in markup |
| `.breadcrumbs` (empty) | `navigation.js` | populated at runtime |
| `.prev-next-nav` (empty, single) | `navigation.js` | populated at runtime; exactly one instance |
| `.mark-complete-btn` (single) | `main.js` | exactly one instance; completion toggle |
| `.progress-bar-fill`, `.progress-text` | `main.js` | progress rendering |
| `pre > code.language-*` | `code-highlight.js` | each code block carries a `language-*` class |
| `lang-toggle` | `i18n.js` | language switch |

No script references section headings by id or text, so re-leveling headings and adding sections is safe.

## Data Models

Not applicable. No data structures, state, or persistence are introduced. Content is static HTML.

## Approach B — Section mapping (condensed)

Approach B is authored as an `h2` followed by `h3` subsections. The 23 markdown sections are condensed into the following `h3` blocks. Each code block uses the `language-*` class noted.

| # | `h3` subsection | Source §§ | Content summary | Code block language |
|---|-----------------|-----------|-----------------|----------------------|
| B1 | Overview & architecture | 1, 2, 3 | Objective: generic whole-disk Proxmox VE image for Glance → Ironic bare metal; GPT, UEFI, system disk separate from data disks; server-specific settings applied post-deploy. Include the pipeline/architecture diagram and `x86_64 / amd64` + `proxmox-ve_9.2-1.iso` note. | `language-text` (diagram) |
| B2 | Prerequisites | 4 | Build host needs Debian/Ubuntu, QEMU, libvirt, virt-install, qemu-img, OVMF, KVM accel. `apt install` of `qemu-utils qemu-system-x86 libvirt-daemon-system libvirt-clients virtinst ovmf`; version checks. | `language-bash` |
| B3 | Prepare the Proxmox ISO | 5 | `cp` ISO into `/var/lib/libvirt/images/`, `chmod 644`, verify with `ls -lh`. | `language-bash` |
| B4 | Create the 64G qcow2 disk | 6 | `qemu-img create -f qcow2 … 64G`; `qemu-img info`; note that data/ZFS/Ceph disks are excluded. Expected-output snippet. | `language-bash` (cmds), `language-text` (expected output) |
| B5 | Create the build VM | 7 | `virt-install` with 8 vCPU, 16 GB RAM, UEFI (`--boot uefi`), VirtIO disk + NIC, CD-ROM ISO; bridge alternative note. | `language-bash` |
| B6 | Install Proxmox VE | 8 | UEFI boot, GPT, ext4/LVM, VirtIO disk; recommended simple layout (EFI + LVM root/swap/data); avoid ZFS for template disk. | `language-text` (layout) |
| B7 | Generic config (network, hostname, no cluster) | 9, 10, 11 | Minimal `/etc/network/interfaces` (`auto lo` / `iface lo inet loopback`); `hostnamectl set-hostname pve-template`; must NOT join a Proxmox cluster (no Corosync/Ceph/shared storage); cluster created only after deployment. | `language-bash` (cmds), `language-text` (interfaces snippet) |
| B8 | Clean the image | 12 | SSH host keys (`rm -f /etc/ssh/ssh_host_*`), machine-id (`truncate -s 0 /etc/machine-id` + dbus symlink), DHCP leases (`rm -f /var/lib/dhcp/*`), journal (`journalctl --rotate` / `--vacuum-time=1s`, remove `*.gz`), `apt clean`. | `language-bash` |
| B9 | Shutdown & remove the temp VM | 13, 14 | `shutdown -h now`; identify `proxmox-opcp.qcow2` as the system image; `virsh undefine proxmox-image-builder --nvram` (never delete storage volumes). | `language-bash` |
| B10 | Verify & compress | 15, 16 | `qemu-img check`, `qemu-img info`; compressed copy via `qemu-img convert -O qcow2 -c … proxmox-opcp-final.qcow2`; re-check. | `language-bash` |
| B11 | Test boot | 17 | `virt-install --import --boot uefi` with the final qcow2, no ISO; boot chain UEFI → GRUB → kernel → Proxmox. | `language-bash` (cmd), `language-text` (boot chain) |
| B12 | Import to Glance | 18 | `openstack image create … --disk-format qcow2 --container-format bare --file …`; `openstack image show`; whole-disk image, **no** `kernel_id` / `ramdisk_id`. | `language-bash` (cmds), `language-text` (properties) |
| B13 | Bare-metal UEFI & deploy | 19, 20 | Ironic node `boot_mode:uefi`, `openstack baremetal node show`; `openstack server create --image Proxmox-VE-9-Baremetal …`; Ironic write-to-disk workflow diagram. | `language-bash` (cmds), `language-text` (workflow) |
| B14 | Post-deployment, recommendations & evolution | 21, 22, 23 | Brief: node-specific config applied on first boot (hostname, IP, DNS, NTP, vmbr0, bonds, VLANs, storage, cluster); keep golden image generic (include/exclude lists); recommended evolution via cloud-init / first-boot systemd / Ansible / Terraform. | `language-text` (lists/diagrams) |

Version strings in Approach B remain **9.2** as written in the source doc. Approach A version strings remain **8.2** unchanged.

### Code block language convention

- `language-bash` — shell commands: `apt`, `qemu-img`, `virt-install`, `virsh`, `hostnamectl`, `openstack`, `rm`, `cp`, `chmod`, `ls`, `truncate`, `journalctl`, `shutdown`.
- `language-text` — non-executable content: architecture/pipeline diagrams, disk layouts, expected command output, property listings, boot chains, include/exclude lists.
- Approach A keeps its existing `language-python`, `language-yaml`, `language-bash`, and `language-text` classes unchanged.

## Error Handling

Not applicable at runtime. The relevant correctness concern is structural integrity of the edited HTML:

- Preserve well-formed markup: every opened tag within the restructured body is closed; `pre`/`code` pairs balanced.
- Exactly one `button.mark-complete-btn` and one `div.prev-next-nav`, both placed after the last Approach B content and before `</main>`.
- The five script includes remain in the required order and are not duplicated.
- `lang="en"` remains on `<html>`.

Verification is a manual review of the rendered file in a browser plus a structural check (heading hierarchy, single completion button / nav, script order, balanced tags). No automated test framework exists for this static site and none is introduced.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

This feature is a single static HTML documentation edit. Per the Fast Task PBT guidance, UI rendering and static markup are **not** appropriate for property-based testing (no pure function with varying input/output; verification is structural and example-based). The prework below classifies each acceptance criterion and records why no property-based tests are generated. Verification is by structural inspection of the single resulting document.

### Prework classification summary

All acceptance criteria describe the structure and content of one static HTML document.

- **1.1–1.3** (Two approaches intro present and describes A/B): EXAMPLE — single-document presence/content check.
- **2.1–2.3** (Approach A content retained, version 8.2, top-level section): EXAMPLE — presence check against the one page.
- **3.1–3.17** (Approach B present, version 9.2, each required subsection documented): EXAMPLE / EDGE_CASE — each is a one-time presence check of specific content in the single document; behavior does not vary with input, so PBT adds no value.
- **4.1–4.6** (lang attribute, HTML conventions, script order, `language-*` classes, heading levels, single mark-complete/nav): EXAMPLE / SMOKE — structural checks on the one document.

No criterion can be expressed as a meaningful "for all inputs X, property P(X) holds" statement, because there is a single fixed artifact and no input variation. Therefore there are **no property-based tests** for this feature. Correctness is validated by example-based structural inspection.

**No testable properties** (static HTML; verified by structural inspection).

## Requirements Traceability

| Requirement | Design coverage |
|-------------|-----------------|
| 1.1 Intro after `h1`+`lesson-meta`, before first approach | Lesson body structure: "Two approaches intro" block positioned between `p.lesson-meta` and the first `h2`. |
| 1.2 Intro describes Approach A as SDK pipeline | Two approaches intro block content. |
| 1.3 Intro describes Approach B as manual KVM/QEMU | Two approaches intro block content. |
| 2.1 Approach A content retained | Heading demotion section: all Approach A prose/code/table preserved verbatim under new `h2`. |
| 2.2 Approach A version 8.2 | "Approach B — Section mapping" version note; Approach A strings unchanged. |
| 2.3 Approach A top-level section | `h2 Approach A — OpenStack SDK pipeline`. |
| 3.1 Approach B top-level section | `h2 Approach B — Manual KVM/QEMU bare-metal build`. |
| 3.2 Approach B version 9.2 | Version note; B subsections keep `9.2` strings. |
| 3.3 Prerequisites (qemu, libvirt, virt-install, ovmf) | B2. |
| 3.4 ISO preparation | B3. |
| 3.5 64G qcow2 via `qemu-img create` | B4. |
| 3.6 `virt-install` UEFI, 8 vCPU, 16 GB | B5. |
| 3.7 Install: UEFI, GPT, LVM | B6. |
| 3.8 Generic network, `pve-template`, no cluster | B7. |
| 3.9 Clean: SSH keys, machine-id, DHCP, logs, apt | B8. |
| 3.10 Clean shutdown | B9. |
| 3.11 `virsh undefine --nvram` | B9. |
| 3.12 qcow2 check & compress | B10. |
| 3.13 Boot test without ISO | B11. |
| 3.14 Glance whole-disk import, no kernel_id/ramdisk_id | B12. |
| 3.15 Ironic `boot_mode:uefi` | B13. |
| 3.16 Bare-metal deploy | B13. |
| 3.17 Post-deploy / recommendations / evolution summaries | B14. |
| 4.1 `lang="en"` retained | Architecture: scaffolding untouched. |
| 4.2 HTML conventions retained | Architecture: scaffolding untouched; Components table. |
| 4.3 Script includes order | Architecture + Error Handling: five includes unchanged. |
| 4.4 `pre > code` with `language-*` classes | Code block language convention; mapping table language column. |
| 4.5 `h2` for approaches, `h3` for subsections | Lesson body structure + Heading demotion. |
| 4.6 Single mark-complete + single prev-next-nav before `</main>` | Lesson body structure + Error Handling. |
