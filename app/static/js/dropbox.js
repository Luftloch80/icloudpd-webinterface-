(function () {
  const badge = document.getElementById("dropbox-status-badge");
  const logBox = document.getElementById("dropbox-log");
  if (!badge) return;

  async function poll() {
    try {
      const res = await fetch("/dropbox/status");
      if (!res.ok) throw new Error("status " + res.status);
      const data = await res.json();

      if (data.running) {
        badge.textContent = "läuft";
        badge.className = "badge bg-primary";
      } else if (data.error) {
        badge.textContent = "Fehler";
        badge.className = "badge bg-danger";
      } else if (data.started_at) {
        badge.textContent = `fertig (${data.uploaded} hochgeladen, ${data.skipped} unverändert, ${data.failed} fehlgeschlagen)`;
        badge.className = "badge bg-success";
      } else {
        badge.textContent = "kein Upload gestartet";
        badge.className = "badge bg-secondary";
      }

      if (logBox && data.log) {
        const wasAtBottom = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 20;
        logBox.textContent = data.log;
        if (wasAtBottom) logBox.scrollTop = logBox.scrollHeight;
      }

      document.querySelectorAll('form[action$="/dropbox/upload-now"] button')
        .forEach((btn) => {
          if (btn.dataset.connected === "true") btn.disabled = data.running;
        });
    } catch (err) {
      badge.textContent = "Fehler beim Laden";
      badge.className = "badge bg-danger";
    }
  }

  poll();
  setInterval(poll, 3000);
})();
