/**
 * SkillHub — Main Initialization Script
 *
 * Entry point that wires up all modules on DOMContentLoaded.
 * Depends on: lessons.js, i18n.js, navigation.js, code-highlight.js
 */
(function () {
  'use strict';

  function getCurrentLessonId(currentPath) {
    var lessons = window.SkillHub.lessons || [];
    for (var i = 0; i < lessons.length; i++) {
      var lesson = lessons[i];
      if (currentPath.indexOf('/' + lesson.slug + '.html') !== -1) { return lesson; }
      if (lesson.slug === 'index') {
        if (currentPath.indexOf('/index.html') !== -1 ||
            /\/(?:en|fr)\/?$/.test(currentPath)) { return lesson; }
      }
    }
    return null;
  }

  function renderBreadcrumbs(locale, currentPath) {
    var container = document.querySelector('.breadcrumbs');
    if (!container) { return; }
    var homeLabel = locale === 'fr' ? 'Accueil' : 'Home';
    var lesson = getCurrentLessonId(currentPath);
    var lessonTitle = '';
    if (lesson) { lessonTitle = locale === 'fr' ? lesson.titleFR : lesson.titleEN; }
    var html = '<a href="index.html">' + homeLabel + '</a>';
    if (lessonTitle && lesson && lesson.slug !== 'index') {
      html += '<span class="separator">›</span>';
      html += '<span>' + lessonTitle + '</span>';
    }
    container.innerHTML = html;
  }

  function renderPrevNextButtons(locale, currentPath) {
    var container = document.querySelector('.prev-next-nav');
    if (!container) { return; }
    var lessons = window.SkillHub.lessons || [];
    var currentLesson = getCurrentLessonId(currentPath);
    if (!currentLesson) { return; }
    var currentIndex = -1;
    for (var i = 0; i < lessons.length; i++) {
      if (lessons[i].id === currentLesson.id) { currentIndex = i; break; }
    }
    if (currentIndex === -1) { return; }
    var prevLabel = locale === 'fr' ? '← Précédent' : '← Previous';
    var nextLabel = locale === 'fr' ? 'Suivant →' : 'Next →';
    var html = '';
    if (currentIndex > 0) {
      var prev = lessons[currentIndex - 1];
      var prevTitle = locale === 'fr' ? prev.titleFR : prev.titleEN;
      html += '<a href="' + prev.slug + '.html" aria-label="' + prevLabel + ': ' + prevTitle + '">' + prevLabel + '</a>';
    } else { html += '<span></span>'; }
    if (currentIndex < lessons.length - 1) {
      var next = lessons[currentIndex + 1];
      var nextTitle = locale === 'fr' ? next.titleFR : next.titleEN;
      html += '<a href="' + next.slug + '.html" aria-label="' + nextLabel + ': ' + nextTitle + '">' + nextLabel + '</a>';
    } else { html += '<span></span>'; }
    container.innerHTML = html;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var locale = window.SkillHub.i18n.getCurrentLocale();
    var currentPath = window.location.pathname;

    window.SkillHub.navigation.renderNavigation(locale, currentPath);
    window.SkillHub.codeHighlight.initializeCodeBlocks();
    window.SkillHub.i18n.renderLanguageToggle(locale);
    renderBreadcrumbs(locale, currentPath);
    renderPrevNextButtons(locale, currentPath);
    window.SkillHub.navigation.initHamburgerMenu();

    var completeBtn = document.querySelector('.mark-complete-btn');
    if (completeBtn) {
      var lesson = getCurrentLessonId(currentPath);
      if (lesson) {
        var completedLessons = [];
        try {
          var raw = localStorage.getItem('skillhub-completed');
          if (raw) { completedLessons = JSON.parse(raw) || []; }
        } catch (e) { /* noop */ }

        if (completedLessons.indexOf(lesson.id) !== -1) {
          completeBtn.textContent = locale === 'fr' ? '✓ Terminé' : '✓ Completed';
          completeBtn.classList.add('completed');
          completeBtn.setAttribute('disabled', 'true');
        }

        completeBtn.addEventListener('click', function () {
          if (completeBtn.classList.contains('completed')) { return; }
          window.SkillHub.navigation.markLessonComplete(lesson.id);
          completeBtn.textContent = locale === 'fr' ? '✓ Terminé' : '✓ Completed';
          completeBtn.classList.add('completed');
          completeBtn.setAttribute('disabled', 'true');
        });
      }
    }
  });
})();
