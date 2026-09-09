(function () {
  const modalEl = document.getElementById("folderBrowserModal");
  const directoryInput = document.getElementById("directory");
  const currentPathEl = document.getElementById("fb-current-path");
  const listEl = document.getElementById("fb-list");
  const errorEl = document.getElementById("fb-error");
  const newFolderInput = document.getElementById("fb-new-folder-name");
  const createFolderBtn = document.getElementById("fb-create-folder");
  const selectCurrentBtn = document.getElementById("fb-select-current");

  if (!modalEl || !directoryInput) return;

  let currentRelPath = "";
  let currentAbsPath = "/data";

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove("d-none");
  }

  function clearError() {
    errorEl.classList.add("d-none");
    errorEl.textContent = "";
  }

  async function load(relPath) {
    clearError();
    try {
      const res = await fetch("/settings/browse?path=" + encodeURIComponent(relPath || ""));
      const data = await res.json();
      if (!res.ok || data.error) {
        showError(data.error || "Fehler beim Laden des Verzeichnisses.");
        return;
      }

      currentRelPath = data.path;
      currentAbsPath = data.absolute_path;
      currentPathEl.textContent = currentAbsPath;

      listEl.innerHTML = "";

      if (data.parent !== null && data.parent !== undefined) {
        const upItem = document.createElement("li");
        upItem.className = "list-group-item list-group-item-action";
        upItem.style.cursor = "pointer";
        upItem.textContent = "⬆ .. (nach oben)";
        upItem.addEventListener("click", () => load(data.parent));
        listEl.appendChild(upItem);
      }

      if (data.folders.length === 0) {
        const empty = document.createElement("li");
        empty.className = "list-group-item text-muted";
        empty.textContent = "(keine Unterordner)";
        listEl.appendChild(empty);
      }

      data.folders.forEach((name) => {
        const item = document.createElement("li");
        item.className = "list-group-item list-group-item-action";
        item.style.cursor = "pointer";
        item.textContent = "📁 " + name;
        const childRel = currentRelPath ? currentRelPath + "/" + name : name;
        item.addEventListener("click", () => load(childRel));
        listEl.appendChild(item);
      });
    } catch (err) {
      showError("Netzwerkfehler beim Laden des Verzeichnisses.");
    }
  }

  modalEl.addEventListener("show.bs.modal", () => {
    load("");
  });

  selectCurrentBtn.addEventListener("click", () => {
    directoryInput.value = currentAbsPath;
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.hide();
  });

  createFolderBtn.addEventListener("click", async () => {
    const name = newFolderInput.value.trim();
    if (!name) return;
    clearError();
    try {
      const res = await fetch("/settings/browse/mkdir", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: currentRelPath, name: name }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        showError(data.error || "Ordner konnte nicht angelegt werden.");
        return;
      }
      newFolderInput.value = "";
      load(currentRelPath);
    } catch (err) {
      showError("Netzwerkfehler beim Anlegen des Ordners.");
    }
  });
})();
