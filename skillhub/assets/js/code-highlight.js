/**
 * SkillHub — Code Block Manager
 *
 * Enhances <pre><code> blocks with CSS-based syntax highlighting,
 * copy-to-clipboard buttons, language labels, and line numbers.
 * Shared via the window.SkillHub namespace (no build tools).
 */
(function () {
  'use strict';

  window.SkillHub = window.SkillHub || {};

  var PYTHON_RULES = [
    { pattern: /(#[^\n]*)/g, className: 'token-comment' },
    { pattern: /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g, className: 'token-string' },
    { pattern: /(@\w+)/g, className: 'token-decorator' },
    { pattern: /\b(self)\b/g, className: 'token-self' },
    { pattern: /\b(def|class|import|from|if|elif|else|return|for|while|try|except|finally|with|as|raise|pass|break|continue|and|or|not|in|is|lambda|yield|global|nonlocal|assert|del|async|await)\b/g, className: 'token-keyword' },
    { pattern: /\b(True|False|None)\b/g, className: 'token-boolean' },
    { pattern: /\b(print|len|range|int|str|float|list|dict|set|tuple|type|isinstance|open|super|property|staticmethod|classmethod|enumerate|zip|map|filter|sorted|reversed|any|all|min|max|sum|abs|round|input|format|hasattr|getattr|setattr)\b/g, className: 'token-builtin' },
    { pattern: /\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/g, className: 'token-number' }
  ];

  var BASH_RULES = [
    { pattern: /(#[^\n]*)/g, className: 'token-comment' },
    { pattern: /("(?:\\.|[^"\\])*"|'[^']*')/g, className: 'token-string' },
    { pattern: /(\$\{?\w+\}?)/g, className: 'token-env' },
    { pattern: /(--[\w][\w-]*|-[a-zA-Z])\b/g, className: 'token-flag' },
    { pattern: /([|]|>{1,2}|<)/g, className: 'token-redirect' },
    { pattern: /\b(sudo|cd|ls|cat|echo|grep|awk|sed|curl|wget|pip|python|python3|export|source|chmod|chown|mkdir|rm|cp|mv|ssh|scp|docker|git|npm|apt|yum|dnf|systemctl|qm|pvesh|pvecm|pveversion|lspci|modprobe|update-grub|update-initramfs|dmesg|reboot|hostnamectl)\b/g, className: 'token-command' },
    { pattern: /\b(\d+\.?\d*)\b/g, className: 'token-number' }
  ];

  var JSON_RULES = [
    { pattern: /("(?:\\.|[^"\\])*")(\s*:)/g, className: 'token-key', groupReplace: true },
    { pattern: /:\s*("(?:\\.|[^"\\])*")/g, className: 'token-string', groupIndex: 1 },
    { pattern: /\b(true|false)\b/g, className: 'token-boolean' },
    { pattern: /\b(null)\b/g, className: 'token-boolean' },
    { pattern: /\b(-?\d+\.?\d*(?:e[+-]?\d+)?)\b/g, className: 'token-number' }
  ];

  var YAML_RULES = [
    { pattern: /(#[^\n]*)/g, className: 'token-comment' },
    { pattern: /^(\s*[\w._-]+)(\s*:)/gm, className: 'token-key', groupReplace: true },
    { pattern: /("(?:\\.|[^"\\])*"|'[^']*')/g, className: 'token-string' },
    { pattern: /\b(true|false|yes|no|null)\b/gi, className: 'token-boolean' },
    { pattern: /\b(\d+\.?\d*)\b/g, className: 'token-number' }
  ];

  var LANGUAGE_RULES = {
    python: PYTHON_RULES,
    bash: BASH_RULES,
    sh: BASH_RULES,
    shell: BASH_RULES,
    json: JSON_RULES,
    yaml: YAML_RULES,
    yml: YAML_RULES
  };

  function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function extractLanguage(className) {
    if (!className) { return null; }
    var match = className.match(/(?:language|lang)-(\w+)/);
    return match ? match[1].toLowerCase() : null;
  }

  function countLines(text) {
    if (!text) { return 0; }
    var lines = text.split('\n');
    if (lines.length > 1 && lines[lines.length - 1] === '') { return lines.length - 1; }
    return lines.length;
  }

  function highlightSyntax(element, language) {
    var rules = LANGUAGE_RULES[language];
    if (!rules) { return; }
    var pre = element.parentElement;
    if (pre && pre.tagName === 'PRE') { pre.classList.add('lang-' + language); }
    var code = element.textContent;
    var escaped = escapeHtml(code);
    var tokens = [];
    for (var r = 0; r < rules.length; r++) {
      var rule = rules[r];
      rule.pattern.lastIndex = 0;
      var m;
      while ((m = rule.pattern.exec(escaped)) !== null) {
        var matchText, matchStart;
        if (rule.groupReplace) { matchText = m[1]; matchStart = m.index; }
        else if (rule.groupIndex) { matchText = m[rule.groupIndex]; matchStart = m.index + m[0].indexOf(m[rule.groupIndex]); }
        else { matchText = m[1] || m[0]; matchStart = m.index + m[0].indexOf(matchText); }
        var matchEnd = matchStart + matchText.length;
        var overlaps = false;
        for (var t = 0; t < tokens.length; t++) {
          if (matchStart < tokens[t].end && matchEnd > tokens[t].start) { overlaps = true; break; }
        }
        if (!overlaps) { tokens.push({ start: matchStart, end: matchEnd, text: matchText, className: rule.className }); }
      }
    }
    tokens.sort(function (a, b) { return b.start - a.start; });
    var result = escaped;
    for (var i = 0; i < tokens.length; i++) {
      var tok = tokens[i];
      result = result.substring(0, tok.start) + '<span class="' + tok.className + '">' + tok.text + '</span>' + result.substring(tok.end);
    }
    element.innerHTML = result;
  }

  function copyToClipboard(codeBlockId) {
    var element = document.getElementById(codeBlockId);
    if (!element) { return; }
    var text = element.textContent;
    var wrapper = element.closest('.code-block-wrapper');
    var button = wrapper ? wrapper.querySelector('.copy-btn') : null;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        if (button) {
          var orig = button.textContent;
          button.textContent = '✓ Copied!'; button.classList.add('copied');
          setTimeout(function () { button.textContent = orig; button.classList.remove('copied'); }, 2000);
        }
      }).catch(function () { fallbackSelect(element, button); });
    } else { fallbackSelect(element, button); }
  }

  function fallbackSelect(element, button) {
    var sel = window.getSelection(); var range = document.createRange();
    range.selectNodeContents(element); sel.removeAllRanges(); sel.addRange(range);
    if (button) {
      var orig = button.textContent;
      button.textContent = 'Select + Ctrl+C'; button.classList.add('copied');
      setTimeout(function () { button.textContent = orig; button.classList.remove('copied'); }, 2000);
    }
  }

  var codeBlockCounter = 0;

  function initializeCodeBlocks() {
    var codeBlocks = document.querySelectorAll('pre > code');
    for (var i = 0; i < codeBlocks.length; i++) {
      var codeEl = codeBlocks[i]; var preEl = codeEl.parentElement;
      if (preEl.hasAttribute('data-highlighted')) { continue; }
      preEl.setAttribute('data-highlighted', 'true');
      if (!codeEl.id) { codeEl.id = 'code-block-' + codeBlockCounter++; }
      var language = extractLanguage(codeEl.className);
      if (language) { highlightSyntax(codeEl, language); }
      var wrapper = document.createElement('div'); wrapper.className = 'code-block-wrapper';
      preEl.parentNode.insertBefore(wrapper, preEl); wrapper.appendChild(preEl);
      if (language) {
        var label = document.createElement('span'); label.className = 'code-lang-label';
        label.textContent = language; wrapper.insertBefore(label, preEl);
      }
      var copyBtn = document.createElement('button'); copyBtn.className = 'copy-btn';
      copyBtn.textContent = 'Copy'; copyBtn.setAttribute('aria-label', 'Copy code to clipboard');
      copyBtn.setAttribute('type', 'button');
      var blockId = codeEl.id;
      copyBtn.addEventListener('click', (function (id) { return function () { copyToClipboard(id); }; })(blockId));
      wrapper.appendChild(copyBtn);
      if (countLines(codeEl.textContent) > 5) { addLineNumbers(codeEl); }
    }
  }

  function addLineNumbers(codeEl) {
    codeEl.classList.add('line-numbers');
    var html = codeEl.innerHTML; var lines = html.split('\n');
    if (lines.length > 1 && lines[lines.length - 1] === '') { lines.pop(); }
    var numbered = '';
    for (var i = 0; i < lines.length; i++) { numbered += '<span class="line">' + lines[i] + '</span>\n'; }
    codeEl.innerHTML = numbered;
  }

  window.SkillHub.codeHighlight = {
    initializeCodeBlocks: initializeCodeBlocks,
    copyToClipboard: copyToClipboard,
    highlightSyntax: highlightSyntax
  };
})();
