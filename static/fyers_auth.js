const elements = {
  clientId: document.getElementById("fyersClientId"),
  secretKey: document.getElementById("fyersSecretKey"),
  redirectUri: document.getElementById("fyersRedirectUri"),
  saveBtn: document.getElementById("saveFyersConfigBtn"),
  clearBtn: document.getElementById("clearFyersConfigBtn"),
  status: document.getElementById("fyersConfigStatus"),
};

if (elements.clientId || elements.secretKey || elements.redirectUri || elements.saveBtn || elements.clearBtn || elements.status) {
  bootFyersAuthPanel();
}

function bootFyersAuthPanel() {
  if (elements.saveBtn) {
    elements.saveBtn.addEventListener("click", saveConfig);
  }
  if (elements.clearBtn) {
    elements.clearBtn.addEventListener("click", clearConfig);
  }
  loadConfig();
}

async function loadConfig() {
  try {
    const response = await fetch("/api/fyers-config", { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to load FYERS credentials.");

    if (elements.clientId) elements.clientId.value = data.client_id || "";
    if (elements.redirectUri) elements.redirectUri.value = data.redirect_uri || "";
    if (elements.secretKey) elements.secretKey.value = "";
    setStatus(data.configured ? sourceLabel(data.source) : "Not configured", data.configured);
  } catch (error) {
    setStatus(error.message || "Unable to load FYERS credentials.", false);
  }
}

async function saveConfig() {
  const payload = {
    client_id: elements.clientId ? elements.clientId.value.trim() : "",
    secret_key: elements.secretKey ? elements.secretKey.value.trim() : "",
    redirect_uri: elements.redirectUri ? elements.redirectUri.value.trim() : "",
  };

  try {
    setBusy(true);
    const response = await fetch("/api/fyers-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to save FYERS credentials.");

    setStatus(`Saved via ${sourceLabel(data.source)}`, true);
    if (elements.secretKey) elements.secretKey.value = "";
    setTimeout(() => window.location.reload(), 250);
  } catch (error) {
    setStatus(error.message || "Unable to save FYERS credentials.", false);
  } finally {
    setBusy(false);
  }
}

async function clearConfig() {
  try {
    setBusy(true);
    const response = await fetch("/api/fyers-config", { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Unable to clear FYERS credentials.");

    if (elements.clientId) elements.clientId.value = "";
    if (elements.secretKey) elements.secretKey.value = "";
    if (elements.redirectUri) elements.redirectUri.value = "";
    setStatus("Not configured", false);
    setTimeout(() => window.location.reload(), 250);
  } catch (error) {
    setStatus(error.message || "Unable to clear FYERS credentials.", false);
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  if (elements.saveBtn) elements.saveBtn.disabled = isBusy;
  if (elements.clearBtn) elements.clearBtn.disabled = isBusy;
}

function setStatus(text, isConfigured) {
  if (!elements.status) return;
  elements.status.textContent = text;
  elements.status.classList.toggle("ok", Boolean(isConfigured));
}

function sourceLabel(source) {
  const value = String(source || "").trim().toLowerCase();
  if (value === "runtime") return "Runtime";
  if (value === "env") return "Environment";
  if (!value) return "missing";
  return value;
}
