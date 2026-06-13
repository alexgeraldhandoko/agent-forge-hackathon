export function getWorkspaceCodeFromUrl() {
  const url = new URL(window.location.href);
  const workspaceId = url.searchParams.get("w") || "";
  return /^\d{6}$/.test(workspaceId) ? workspaceId : "";
}

export function createWorkspaceCode() {
  const bytes = new Uint32Array(1);
  window.crypto.getRandomValues(bytes);
  return String((bytes[0] % 900000) + 100000);
}

export function setWorkspaceCode(workspaceId) {
  const cleanCode = workspaceId.replace(/\D/g, "").slice(0, 6);
  if (!/^\d{6}$/.test(cleanCode)) {
    return "";
  }
  const url = new URL(window.location.href);
  url.searchParams.set("w", cleanCode);
  window.history.replaceState({}, "", url.toString());
  return cleanCode;
}

export function setUsername(username) {
  const cleanName = username.trim() || "Member A";
  const url = new URL(window.location.href);
  url.searchParams.set("name", cleanName);
  window.history.replaceState({}, "", url.toString());
  window.localStorage.setItem("ai-workspace-name", cleanName);
  return cleanName;
}

export function createWorkspaceSocket({ workspaceId, username, onMessage, onStatus }) {
  let socket;
  let closedByClient = false;
  let reconnectTimer;

  const connect = () => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const apiBase = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
    const wsBase = apiBase.replace(/^http/, protocol);
    socket = new WebSocket(`${wsBase}/ws/${encodeURIComponent(workspaceId)}/${encodeURIComponent(username)}`);

    socket.onopen = () => {
      onStatus("connected");
      socket.send(JSON.stringify({ type: "ping" }));
    };

    socket.onmessage = (event) => {
      onMessage(JSON.parse(event.data));
    };

    socket.onclose = () => {
      onStatus("reconnecting");
      if (!closedByClient) {
        reconnectTimer = window.setTimeout(connect, 900);
      }
    };

    socket.onerror = () => {
      onStatus("offline");
    };
  };

  connect();

  return {
    send(payload) {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(payload));
      }
    },
    close() {
      closedByClient = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}
