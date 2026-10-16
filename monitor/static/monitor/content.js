(() => {
  'use strict';
  document.querySelectorAll('[data-copy-link]').forEach(button => {
    button.addEventListener('click', async () => {
      const status = document.querySelector('[data-copy-status]');
      try {
        await navigator.clipboard.writeText(button.dataset.copyLink);
        status.textContent = document.documentElement.lang === 'ja' ? 'コピーしました' : document.documentElement.lang.startsWith('zh') ? '已复制' : 'Link copied';
      } catch (_) {
        const link = document.querySelector('.permanent-link');
        link.focus();
        status.textContent = button.dataset.copyLink;
      }
    });
  });
})();
