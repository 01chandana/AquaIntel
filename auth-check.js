const API = window.location.origin;

function getToken() {
  return localStorage.getItem("token");
}

function getRole() {
  return localStorage.getItem("role") || "viewer";
}

function isAdmin() {
  return getRole() === "admin";
}

function requireLogin() {
  if (!getToken()) {
    window.location.href = "/login-page";
  }
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("email");
  localStorage.removeItem("role");
  window.location.href = "/login-page";
}

function goTo(page) {
  window.location.href = page;
}

// ---- Theme ----
function getTheme() {
  return localStorage.getItem("theme") || "dark";
}

function applyTheme() {
  const theme = getTheme();
  document.documentElement.setAttribute("data-theme", theme);
}

function toggleTheme() {
  const newTheme = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem("theme", newTheme);
  applyTheme();
}

// ---- Browser Notifications ----
function requestNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}

function getSeenAlertIds() {
  const stored = localStorage.getItem("seenAlertIds");
  return stored ? JSON.parse(stored) : [];
}

function saveSeenAlertIds(ids) {
  localStorage.setItem("seenAlertIds", JSON.stringify(ids));
}

let hasCheckedOnce = false;

async function checkForNewAlerts() {
  try {
    const res = await fetch(API + "/alerts");
    const alerts = await res.json();
    const seenIds = getSeenAlertIds();

    const newAlerts = alerts.filter(a => !seenIds.includes(a.id));

    if (newAlerts.length > 0 && hasCheckedOnce) {
      newAlerts.forEach(a => {
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("⚠️ AquaIntel Alert", {
            body: a.message,
            icon: "https://em-content.zobj.net/source/apple/391/droplet_1f4a7.png"
          });
        }
      });
    }

    saveSeenAlertIds(alerts.map(a => a.id));
    hasCheckedOnce = true;
  } catch (e) {
    console.error("Notification check failed:", e);
  }
}

function startAlertWatcher() {
  requestNotificationPermission();
  checkForNewAlerts();
  setInterval(checkForNewAlerts, 5000);
}