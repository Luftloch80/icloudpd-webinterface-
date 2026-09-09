(function () {
  const badge = document.getElementById("job-status-badge");
  const logBox = document.getElementById("job-log");
  if (!badge || !logBox) return;

  const progressWrap = document.getElementById("job-progress-wrap");
  const progressText = document.getElementById("job-progress-text");
  const progressEta = document.getElementById("job-progress-eta");
  const progressBar = document.getElementById("job-progress-bar");

  const statusColors = {
    running: "bg-primary",
    success: "bg-success",
    failed: "bg-danger",
    stopped: "bg-secondary",
  };

  function formatDuration(totalSeconds) {
    if (totalSeconds === null || totalSeconds === undefined) return "–";
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = Math.floor(totalSeconds % 60);
    const pad = (n) => String(n).padStart(2, "0");
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }

  function updateProgress(data) {
    if (!progressWrap) return;
    if (!data.running || data.total === null || data.total === undefined) {
      progressWrap.hidden = true;
      return;
    }
    progressWrap.hidden = false;
    progressText.textContent =
      `${data.processed} von ${data.total} verarbeitet · ${data.remaining} verbleibend`;
    progressEta.textContent = data.eta_seconds !== null && data.eta_seconds !== undefined
      ? `noch ca. ${formatDuration(data.eta_seconds)}`
      : "Restzeit wird berechnet...";
    const pct = data.total > 0 ? Math.min(100, Math.round((data.processed / data.total) * 100)) : 0;
    progressBar.style.width = pct + "%";
  }

  async function poll() {
    try {
      const res = await fetch("/jobs/status", { headers: { "X-Requested-With": "fetch" } });
      if (!res.ok) throw new Error("status " + res.status);
      const data = await res.json();

      const label = data.running ? "läuft" : (data.status || "kein Job");
      badge.textContent = label;
      badge.className = "badge " + (data.running ? statusColors.running : (statusColors[data.status] || "bg-secondary"));

      if (data.log) {
        const wasAtBottom = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 20;
        logBox.textContent = data.log;
        if (wasAtBottom) {
          logBox.scrollTop = logBox.scrollHeight;
        }
      }

      updateProgress(data);

      document.querySelectorAll('form[action$="/start/once"] button, form[action$="/start/continuous"] button')
        .forEach((btn) => { btn.disabled = data.running; });
      document.querySelectorAll('form[action$="/jobs/stop"] button')
        .forEach((btn) => { btn.disabled = !data.running; });
    } catch (err) {
      badge.textContent = "Fehler beim Laden";
      badge.className = "badge bg-danger";
    }
  }

  poll();
  setInterval(poll, 3000);
})();
