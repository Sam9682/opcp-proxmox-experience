/**
 * SkillHub — Navigation System
 *
 * Renders sidebar navigation from the lesson catalog, tracks learning
 * progress via localStorage, and handles the mobile hamburger menu.
 * Shared via the window.SkillHub namespace (no build tools).
 */
(function () {
  'use strict';

  window.SkillHub = window.SkillHub || {};

  var COMPLETED_KEY = 'skillhub-completed';

  function getCompletedLessons() {
    try {
      var raw = localStorage.getItem(COMPLETED_KEY);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) { return parsed; }
      }
    } catch (e) { /* graceful degradation */ }
    return [];
  }

  function saveCompletedLessons(arr) {
    try { localStorage.setItem(COMPLETED_KEY, JSON.stringify(arr)); } catch (e) { /* noop */ }
  }

  function renderNavigation(locale, currentPath) {
    var lessons = window.SkillHub.lessons;
    if (!lessons || !lessons.length) { return; }
    var sidebarEl = document.getElementById('sidebar-nav');
    if (!sidebarEl) { return; }

    var completed = getCompletedLessons();
    var html = '<ul class="nav-list" role="list">';

    for (var i = 0; i < lessons.length; i++) {
      var lesson = lessons[i];
      var isActive = currentPath.indexOf('/' + lesson.slug + '.html') !== -1;
      if (lesson.slug === 'index') {
        var localeDir = '/' + locale + '/';
        isActive = currentPath.indexOf(localeDir + 'index.html') !== -1 ||
                   currentPath.replace(/\/$/, '').endsWith('/' + locale);
      }
      var isCompleted = completed.indexOf(lesson.id) !== -1;
      var classes = 'nav-item';
      if (isActive) { classes += ' active'; }
      if (isCompleted) { classes += ' completed'; }
      var title = locale === 'fr' ? lesson.titleFR : lesson.titleEN;
      var badgeClass = 'badge badge-' + lesson.difficulty;
      var badge = '<span class="' + badgeClass + '">' + lesson.difficulty + '</span>';
      var href = lesson.slug + '.html';
      html += '<li class="' + classes + '" data-lesson-id="' + lesson.id + '">';
      html += '<a href="' + href + '" aria-label="' + title + ' — ' + lesson.difficulty + '">';
      html += '<span class="nav-title">' + title + '</span> ' + badge;
      html += '</a></li>';
    }

    html += '</ul>';
    sidebarEl.innerHTML = html;
    var progress = getProgress();
    updateProgressBar(progress.percentage);
  }

  function markLessonComplete(lessonId) {
    var completed = getCompletedLessons();
    if (completed.indexOf(lessonId) === -1) {
      completed.push(lessonId);
      saveCompletedLessons(completed);
    }
    var navItem = document.querySelector('.nav-item[data-lesson-id="' + lessonId + '"]');
    if (navItem) { navItem.classList.add('completed'); }
    var progress = getProgress();
    updateProgressBar(progress.percentage);
  }

  function getProgress() {
    var lessons = window.SkillHub.lessons || [];
    var totalCount = lessons.length;
    var completed = getCompletedLessons();
    var completedCount = 0;
    for (var i = 0; i < lessons.length; i++) {
      if (completed.indexOf(lessons[i].id) !== -1) { completedCount++; }
    }
    var percentage = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
    return { completedCount: completedCount, totalCount: totalCount, percentage: percentage };
  }

  function updateProgressBar(percentage) {
    var fill = document.querySelector('.progress-bar-fill');
    if (fill) { fill.style.width = percentage + '%'; }
    var text = document.querySelector('.progress-text');
    if (text) { text.textContent = Math.round(percentage) + '% complete'; }
  }

  function initHamburgerMenu() {
    var hamburgerBtn = document.querySelector('.hamburger-btn');
    var sidebar = document.querySelector('.sidebar');
    var overlay = document.querySelector('.sidebar-overlay');
    if (!hamburgerBtn || !sidebar) { return; }
    hamburgerBtn.addEventListener('click', function () {
      sidebar.classList.toggle('open');
      var isOpen = sidebar.classList.contains('open');
      hamburgerBtn.setAttribute('aria-expanded', String(isOpen));
      if (overlay) { overlay.classList.toggle('visible'); }
    });
    if (overlay) {
      overlay.addEventListener('click', function () {
        sidebar.classList.remove('open');
        overlay.classList.remove('visible');
        hamburgerBtn.setAttribute('aria-expanded', 'false');
      });
    }
  }

  window.SkillHub.navigation = {
    renderNavigation: renderNavigation,
    markLessonComplete: markLessonComplete,
    getProgress: getProgress,
    updateProgressBar: updateProgressBar,
    initHamburgerMenu: initHamburgerMenu
  };
})();
