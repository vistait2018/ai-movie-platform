"use strict";
(() => {
  const BROWSER = "/api/v1/auth/browser";
  const PUBLIC = "/api/v1/auth";
  const notice = document.getElementById("notice");
  let busy = false;
  const show = message => { notice.textContent = message; };
  const clearSecrets = () => {
    for (const id of ["enrollment", "recovery"]) {
      const element = document.getElementById(id);
      element.textContent = "";
      element.hidden = true;
    }
  };
  async function request(path, data, method = "POST", browser = true) {
    const headers = {};
    if (method !== "GET") {
      headers["Content-Type"] = "application/json";
      if (browser) {
        const challenge = await fetch(BROWSER + "/csrf", {credentials: "same-origin", cache: "no-store"});
        if (!challenge.ok) throw new Error("Security challenge unavailable. Please try again.");
        headers["X-CSRF-Token"] = (await challenge.json()).csrf_token;
      }
    }
    const response = await fetch(path, {
      method, headers, credentials: "same-origin", cache: "no-store",
      ...(method === "GET" ? {} : {body: JSON.stringify(data || {})})
    });
    const result = response.status === 204 ? {} : await response.json();
    if (!response.ok) {
      if (response.status === 401) { clearSecrets(); throw new Error("Sign in or renew your session, then retry the action."); }
      if (response.status === 429) throw new Error("Too many attempts. Please wait before trying again.");
      throw new Error(typeof result.detail === "string" ? result.detail : "Check the form values and try again.");
    }
    return result;
  }
  async function profile() {
    const session = await request(BROWSER + "/session", null, "GET");
    const result = await request(BROWSER + "/users/" + encodeURIComponent(session.user_id), null, "GET");
    document.getElementById("profile").textContent = JSON.stringify(result, null, 2);
  }
  async function act(action, data) {
    if (action === "clear-secrets") { clearSecrets(); show("Sensitive details hidden."); return; }
    if (action === "profile") { await profile(); show("Profile loaded."); return; }
    if (action === "login") { clearSecrets(); await request(BROWSER + "/login", data); show("Signed in."); return; }
    if (["register", "request-verification", "verify-email", "forgot-password", "reset-password"].includes(action)) {
      const result = await request(PUBLIC + "/" + action, data, "POST", false);
      if (action === "reset-password") { clearSecrets(); document.getElementById("profile").textContent = "Sign in with your new password."; }
      show(result.message); return;
    }
    if (["refresh", "logout", "logout-all"].includes(action)) {
      await request(BROWSER + "/" + action, {});
      clearSecrets();
      if (action !== "refresh") document.getElementById("profile").textContent = "Signed out.";
      show(action === "refresh" ? "Session renewed. MFA expiry is unchanged." : "Signed out."); return;
    }
    if (action === "profile-update") {
      const session = await request(BROWSER + "/session", null, "GET");
      await request(BROWSER + "/users/" + encodeURIComponent(session.user_id), data, "PATCH");
      await profile(); show("Profile updated."); return;
    }
    if (action === "status") {
      await request(BROWSER + "/users/" + encodeURIComponent(data.user_id) + "/status", {status: data.status}, "PATCH");
      show("Account status updated."); return;
    }
    if (action.startsWith("mfa-")) {
      clearSecrets();
      const result = await request(BROWSER + "/mfa/" + action.slice(4), data);
      if (action === "mfa-enroll") {
        const element = document.getElementById("enrollment");
        element.textContent = "Add this secret to your authenticator, then confirm below:\n" + result.secret + "\n\n" + result.provisioning_uri;
        element.hidden = false;
      }
      if (action === "mfa-confirm") {
        const element = document.getElementById("recovery");
        element.textContent = "Save these recovery codes somewhere safe. They are shown once:\n" + result.recovery_codes.join("\n");
        element.hidden = false;
      }
      if (action === "mfa-disable") document.getElementById("profile").textContent = "Signed out.";
      show("Authenticator operation completed.");
    }
  }
  async function run(action, data, form) {
    if (busy) return;
    busy = true;
    for (const button of document.querySelectorAll("button")) button.disabled = true;
    try { await act(action, data); }
    catch (error) { show(error instanceof Error ? error.message : "The request could not be completed."); }
    finally {
      if (form) for (const input of form.querySelectorAll('input[type="password"]')) input.value = "";
      for (const button of document.querySelectorAll("button")) button.disabled = false;
      busy = false;
    }
  }
  for (const form of document.querySelectorAll("form[data-action]")) {
    form.addEventListener("submit", event => {
      event.preventDefault();
      run(form.dataset.action, Object.fromEntries(new FormData(form)), form);
    });
  }
  for (const button of document.querySelectorAll("button[data-action]")) {
    button.addEventListener("click", () => run(button.dataset.action, {}));
  }
  window.addEventListener("pagehide", clearSecrets);
})();
