(function () {
  const badge = document.getElementById("job-status-badge");
  const logBox = document.getElementById("job-log");
  if (!badge || !logBox) return;

  const statusColors = {
    running: "bg-primary",
    success: "bg-success",
    failed: "bg-danger",
    stopped: "bg-secondary",
  };

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
