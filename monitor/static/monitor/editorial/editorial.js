(() => {
  document.querySelectorAll('.chatter').forEach(section => {
    const history = section.querySelector('.chatter-history');
    const button = section.querySelector('.history-toggle');
    if (!history || !button) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let paused = reduced.matches;
    let hovering = false;
    let last = 0;
    const update = () => {
      button.textContent = paused ? button.dataset.resume : button.dataset.pause;
      button.setAttribute('aria-pressed', String(paused));
    };
    button.addEventListener('click', () => { paused = !paused; update(); });
    reduced.addEventListener('change', () => { paused = reduced.matches; update(); });
    history.addEventListener('mouseenter', () => { hovering = true; });
    history.addEventListener('mouseleave', () => { hovering = false; });
    const tick = now => {
      if (!section.isConnected) return;
      if (now - last > 80) {
        if (!paused && !hovering && !history.contains(document.activeElement) && !document.hidden && history.scrollHeight > history.clientHeight) {
          history.scrollTop = history.scrollTop + 1 >= history.scrollHeight - history.clientHeight ? 0 : history.scrollTop + 1;
        }
        last = now;
      }
      requestAnimationFrame(tick);
    };
    update();
    requestAnimationFrame(tick);
  });
})();
