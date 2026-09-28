const API = window.location.origin;

function getToken() { return localStorage.getItem("token"); }
function getRole() { return localStorage.getItem("role") || "viewer"; }
function isAdmin() { return getRole() === "admin"; }

async function validateSession() {
  const token = getToken();
  if (!token) {
    window.location.href = "/login-page";
    return false;
  }
  try {
    const res = await fetch(API + "/me", { headers: { Authorization: "Bearer " + token } });
    if (!res.ok) throw new Error("Session expired");
    const user = await res.json();
    localStorage.setItem("email", user.email);
    localStorage.setItem("role", user.role);
    return true;
  } catch (e) {
    logout();
    return false;
  }
}

function requireLogin() {
  if (!getToken()) window.location.href = "/login-page";
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("email");
  localStorage.removeItem("role");
  window.location.href = "/login-page";
}

function goTo(page) { window.location.href = page; }

function getTheme() { return localStorage.getItem("theme") || "dark"; }
function applyTheme() { document.documentElement.setAttribute("data-theme", getTheme()); }
function toggleTheme() {
  const newTheme = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem("theme", newTheme);
  applyTheme();
}

function requestNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }
}

function getSeenAlertIds() {
  try { return JSON.parse(localStorage.getItem("seenAlertIds") || "[]"); }
  catch { return []; }
}
function saveSeenAlertIds(ids) { localStorage.setItem("seenAlertIds", JSON.stringify(ids)); }
let hasCheckedOnce = false;

async function checkForNewAlerts() {
  try {
    const res = await fetch(API + "/alerts?limit=100", { headers: { Authorization: "Bearer " + getToken() } });
    if (res.status === 401) return logout();
    if (!res.ok) return;
    const alerts = await res.json();
    const seenIds = getSeenAlertIds();
    const newAlerts = alerts.filter(a => !seenIds.includes(a.id));
    if (newAlerts.length > 0 && hasCheckedOnce && "Notification" in window && Notification.permission === "granted") {
      newAlerts.forEach(a => new Notification("AquaIntel Alert", { body: a.message }));
    }
    saveSeenAlertIds(alerts.map(a => a.id));
    hasCheckedOnce = true;
  } catch (e) { console.error("Notification check failed:", e); }
}

function startAlertWatcher() {
  requestNotificationPermission();
  checkForNewAlerts();
  setInterval(checkForNewAlerts, 10000);
}
