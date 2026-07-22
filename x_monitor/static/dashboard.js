// {{AGENT_ATTRIBUTION}}
// v1.6 staleness indicator: refresh the "last updated" text every 30s
// without a full re-render. The htmx poll on <main> does not touch the
// outer <header>, so this client-side update runs in the background and
// marks the stamp .stale (amber) when data is more than 1h old.
(function() {
  function updateLastRun() {
    var el = document.getElementById('last-run-stamp');
    if (!el) return;
    var iso = el.getAttribute('data-finished-at');
    if (!iso) {
      el.textContent = 'last updated: never';
      el.classList.add('stale');
      return;
    }
    var finishedAt = new Date(iso);
    if (isNaN(finishedAt.getTime())) return;
    var now = new Date();
    var ageSec = Math.max(0, Math.floor((now - finishedAt) / 1000));
    var label;
    if (ageSec < 60) label = ageSec + 's ago';
    else if (ageSec < 3600) label = Math.floor(ageSec / 60) + 'm ago';
    else if (ageSec < 86400) label = Math.floor(ageSec / 3600) + 'h ago';
    else label = Math.floor(ageSec / 86400) + 'd ago';
    el.textContent = 'last updated: ' + label;
    el.classList.toggle('stale', ageSec > 3600);
  }
  setInterval(updateLastRun, 30000);
  updateLastRun();
})();
