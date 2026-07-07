/**
 * SkillHub — Lesson Catalog Data Module
 *
 * Defines the lesson catalog for opcp-proxmox-install.
 * Shared via the window.SkillHub namespace (no build tools).
 */
(function () {
  'use strict';

  window.SkillHub = window.SkillHub || {};

  var LESSONS = [
    {
      id: 'prerequisites',
      slug: 'prerequisites',
      titleEN: 'Prerequisites',
      titleFR: 'Prérequis',
      difficulty: 'beginner',
      estimatedMinutes: 15,
      prerequisites: []
    },
    {
      id: 'intro',
      slug: 'index',
      titleEN: 'Introduction',
      titleFR: 'Introduction',
      difficulty: 'beginner',
      estimatedMinutes: 5,
      prerequisites: ['prerequisites']
    },
    {
      id: 'core-concepts',
      slug: 'core-concepts',
      titleEN: 'Core Concepts',
      titleFR: 'Concepts Fondamentaux',
      difficulty: 'beginner',
      estimatedMinutes: 15,
      prerequisites: ['intro']
    },
    {
      id: 'provisioning',
      slug: 'provisioning',
      titleEN: 'Baremetal Provisioning',
      titleFR: 'Provisionnement Baremetal',
      difficulty: 'intermediate',
      estimatedMinutes: 25,
      prerequisites: ['core-concepts']
    },
    {
      id: 'proxmox-install',
      slug: 'proxmox-install',
      titleEN: 'Proxmox VE Installation',
      titleFR: 'Installation Proxmox VE',
      difficulty: 'intermediate',
      estimatedMinutes: 30,
      prerequisites: ['provisioning']
    },
    {
      id: 'gpu-passthrough',
      slug: 'gpu-passthrough',
      titleEN: 'GPU Passthrough (IOMMU & VFIO)',
      titleFR: 'GPU Passthrough (IOMMU & VFIO)',
      difficulty: 'advanced',
      estimatedMinutes: 35,
      prerequisites: ['proxmox-install']
    },
    {
      id: 'vm-creation',
      slug: 'vm-creation',
      titleEN: 'VM Creation with GPU',
      titleFR: 'Création de VM avec GPU',
      difficulty: 'advanced',
      estimatedMinutes: 25,
      prerequisites: ['gpu-passthrough']
    },
    {
      id: 'validation',
      slug: 'validation',
      titleEN: 'Validation & Testing',
      titleFR: 'Validation & Tests',
      difficulty: 'intermediate',
      estimatedMinutes: 20,
      prerequisites: ['vm-creation']
    },
    {
      id: 'cleanup',
      slug: 'cleanup',
      titleEN: 'Cleanup Resources',
      titleFR: 'Nettoyage des ressources',
      difficulty: 'beginner',
      estimatedMinutes: 10,
      prerequisites: ['validation']
    },
    {
      id: 'cheat-sheet',
      slug: 'cheat-sheet',
      titleEN: 'CLI & Config Cheat Sheet',
      titleFR: 'Aide-mémoire CLI & Config',
      difficulty: 'beginner',
      estimatedMinutes: 10,
      prerequisites: ['cleanup']
    }
  ];

  window.SkillHub.lessons = LESSONS;
})();
