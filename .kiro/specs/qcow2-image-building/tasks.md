# Implementation Plan: qcow2-image-building

## Overview

This plan restructures the single static file `skillhub/en/qcow2-image-building.html` **in place** into two parallel top-level approaches. The existing OpenStack SDK content becomes Approach A (headings demoted), a "Two approaches" intro is inserted after the lesson meta, and a new condensed Approach B (manual KVM/QEMU bare-metal build, Proxmox VE 9.2) is authored from `docs/Preparing_Proxmox_QCOW2_Image_OPCP_BareMetal_EN.md`. All scaffolding, script includes, `lang="en"`, and the single `mark-complete-btn` / `prev-next-nav` are preserved. There is no build tooling or test runner; verification is structural inspection of the resulting document. No test framework is introduced.

Because Approach B is one contiguous `h2` block whose `h3` subsections (B1–B14) share the same file region, the authoring sub-tasks are sequenced rather than parallelized to avoid conflicting edits to the same file.

## Tasks

- [x] 1. Read the source files and lock in current structure
  - Read `skillhub/en/qcow2-image-building.html` fully to capture existing Approach A prose, code blocks, table, and `language-*` classes verbatim
  - Read `docs/Preparing_Proxmox_QCOW2_Image_OPCP_BareMetal_EN.md` to source Approach B content (version 9.2 strings, commands, diagrams)
  - Confirm existing head, header, sidebar, footer, five script includes order, `lang="en"`, single `mark-complete-btn`, single `prev-next-nav`
  - _Requirements: 2.1, 4.1, 4.2, 4.3, 4.6_

- [x] 2. Add the "Two approaches" intro and establish Approach A as a top-level section
  - [x] 2.1 Insert the Two_Approaches_Intro block
    - Add an intro `<p>` (block) immediately after `h1` + `p.lesson-meta` and before the first approach section
    - Describe Approach A as the OpenStack SDK Python pipeline (version 8.2)
    - Describe Approach B as the manual KVM/QEMU bare-metal build (version 9.2)
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 Wrap existing SDK content under `h2` "Approach A — OpenStack SDK pipeline" and demote headings
    - Add the `h2` "Approach A — OpenStack SDK pipeline" above the existing SDK content
    - Demote former Approach A `h2` sections (Overview, Prerequisites, Step-by-step Workflow, Configuration Reference, CLI Usage) to `h3`
    - Demote Step 1–5 `h3` headings to `h4`
    - Preserve all prose, code blocks, the table, and `language-python`/`language-yaml`/`language-bash`/`language-text` classes verbatim; keep version strings 8.2 unchanged
    - _Requirements: 2.1, 2.2, 2.3, 4.4, 4.5_

- [x] 3. Checkpoint - verify intro and Approach A structure
  - Confirm intro placement, single `h2` for Approach A, demoted `h3`/`h4` levels, and unchanged Approach A content/version. Ask the user if questions arise.

- [x] 4. Author Approach B top-level section and foundational subsections (B1–B5)
  - [x] 4.1 Add `h2` "Approach B — Manual KVM/QEMU bare-metal build" and B1 Overview & architecture
    - Add the Approach B `h2` after Approach A content
    - B1 `h3`: objective (generic whole-disk Proxmox VE image for Glance → Ironic bare metal), GPT/UEFI, system disk separate from data disks; include pipeline/architecture diagram in `language-text`; note `x86_64 / amd64` + `proxmox-ve_9.2-1.iso` (version 9.2)
    - _Requirements: 3.1, 3.2, 4.4, 4.5_

  - [x] 4.2 Add B2 Prerequisites
    - B2 `h3`: build-host needs (Debian/Ubuntu, QEMU, libvirt, virt-install, qemu-img, OVMF, KVM accel); `apt install qemu-utils qemu-system-x86 libvirt-daemon-system libvirt-clients virtinst ovmf` + version checks in `language-bash`
    - _Requirements: 3.3, 4.4_

  - [x] 4.3 Add B3 Prepare the Proxmox ISO and B4 Create the 64G qcow2 disk
    - B3 `h3`: `cp` ISO into `/var/lib/libvirt/images/`, `chmod 644`, verify with `ls -lh` in `language-bash`
    - B4 `h3`: `qemu-img create -f qcow2 … 64G`, `qemu-img info` in `language-bash`; expected-output snippet in `language-text`; note data/ZFS/Ceph disks excluded
    - _Requirements: 3.4, 3.5, 4.4_

  - [x] 4.4 Add B5 Create the build VM
    - B5 `h3`: `virt-install` with 8 vCPU, 16 GB RAM, UEFI (`--boot uefi`), VirtIO disk + NIC, CD-ROM ISO; bridge alternative note in `language-bash`
    - _Requirements: 3.6, 4.4_

- [x] 5. Author Approach B install, config, and cleanup subsections (B6–B9)
  - [x] 5.1 Add B6 Install Proxmox VE
    - B6 `h3`: UEFI boot, GPT, ext4/LVM, VirtIO disk; recommended simple layout (EFI + LVM root/swap/data); avoid ZFS for template disk; layout in `language-text`
    - _Requirements: 3.7, 4.4_

  - [x] 5.2 Add B7 Generic config (network, hostname, no cluster)
    - B7 `h3`: minimal `/etc/network/interfaces` (`auto lo` / `iface lo inet loopback`); `hostnamectl set-hostname pve-template`; must NOT join a Proxmox cluster (no Corosync/Ceph/shared storage); cluster created only after deployment; commands in `language-bash`, interfaces snippet in `language-text`
    - _Requirements: 3.8, 4.4_

  - [x] 5.3 Add B8 Clean the image
    - B8 `h3`: SSH host keys (`rm -f /etc/ssh/ssh_host_*`), machine-id (`truncate -s 0 /etc/machine-id` + dbus symlink), DHCP leases (`rm -f /var/lib/dhcp/*`), journal (`journalctl --rotate` / `--vacuum-time=1s`, remove `*.gz`), `apt clean` in `language-bash`
    - _Requirements: 3.9, 4.4_

  - [x] 5.4 Add B9 Shutdown & remove the temp VM
    - B9 `h3`: `shutdown -h now`; identify `proxmox-opcp.qcow2` as the system image; `virsh undefine proxmox-image-builder --nvram` (never delete storage volumes) in `language-bash`
    - _Requirements: 3.10, 3.11, 4.4_

- [x] 6. Checkpoint - verify Approach B B1–B9
  - Confirm Approach B `h2`, B1–B9 `h3` subsections present with correct `language-*` classes and 9.2 strings. Ask the user if questions arise.

- [x] 7. Author Approach B verification, deployment, and evolution subsections (B10–B14)
  - [x] 7.1 Add B10 Verify & compress and B11 Test boot
    - B10 `h3`: `qemu-img check`, `qemu-img info`; compressed copy via `qemu-img convert -O qcow2 -c … proxmox-opcp-final.qcow2`; re-check in `language-bash`
    - B11 `h3`: `virt-install --import --boot uefi` with final qcow2, no ISO in `language-bash`; boot chain UEFI → GRUB → kernel → Proxmox in `language-text`
    - _Requirements: 3.12, 3.13, 4.4_

  - [x] 7.2 Add B12 Import to Glance
    - B12 `h3`: `openstack image create … --disk-format qcow2 --container-format bare --file …`, `openstack image show` in `language-bash`; whole-disk image, no `kernel_id`/`ramdisk_id`; properties in `language-text`
    - _Requirements: 3.14, 4.4_

  - [x] 7.3 Add B13 Bare-metal UEFI & deploy
    - B13 `h3`: Ironic node `boot_mode:uefi`, `openstack baremetal node show`; `openstack server create --image Proxmox-VE-9-Baremetal …` in `language-bash`; Ironic write-to-disk workflow diagram in `language-text`
    - _Requirements: 3.15, 3.16, 4.4_

  - [x] 7.4 Add B14 Post-deployment, recommendations & evolution
    - B14 `h3`: node-specific config applied on first boot (hostname, IP, DNS, NTP, vmbr0, bonds, VLANs, storage, cluster); keep golden image generic (include/exclude lists); recommended evolution via cloud-init / first-boot systemd / Ansible / Terraform; lists/diagrams in `language-text`
    - _Requirements: 3.17, 4.4_

- [x] 8. Finalize placement and verify structural integrity
  - [x] 8.1 Ensure completion button and nav are last in `main`
    - Confirm the single `button.mark-complete-btn` and single `div.prev-next-nav` sit after all Approach B content and before `</main>`
    - _Requirements: 4.6_

  - [x] 8.2 Structural inspection of the whole document
    - Verify `lang="en"` on `<html>`; all HTML_Conventions scaffolding intact; five script includes (`lessons.js`, `i18n.js`, `navigation.js`, `code-highlight.js`, `main.js`) present once, in order
    - Verify exactly two `h2` (the approaches) with `h3` subsections and demoted `h4` steps; balanced tags; every code example in `pre > code.language-*`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 9. Final checkpoint - full-page review
  - Review the rendered page structure end to end. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP. (This feature has no optional sub-tasks: it is static HTML with no test framework, and no automated tests are introduced per the design.)
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation by structural inspection.
- No property-based tests are generated: the design classifies all acceptance criteria as example/structural checks on a single fixed artifact, so PBT adds no value.
- Approach B subsections (B1–B14) edit the same file region and are therefore sequenced across waves rather than run in parallel.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2"] },
    { "id": 5, "tasks": ["4.3"] },
    { "id": 6, "tasks": ["4.4"] },
    { "id": 7, "tasks": ["5.1"] },
    { "id": 8, "tasks": ["5.2"] },
    { "id": 9, "tasks": ["5.3"] },
    { "id": 10, "tasks": ["5.4"] },
    { "id": 11, "tasks": ["7.1"] },
    { "id": 12, "tasks": ["7.2"] },
    { "id": 13, "tasks": ["7.3"] },
    { "id": 14, "tasks": ["7.4"] },
    { "id": 15, "tasks": ["8.1"] },
    { "id": 16, "tasks": ["8.2"] }
  ]
}
```
