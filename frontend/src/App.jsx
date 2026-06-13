import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  clearStoredUser,
  getStoredUser,
  hasGoogleOAuth,
  renderGoogleButton,
  sessionName,
} from "./auth";
import { createWorkspaceCode, createWorkspaceSocket, getWorkspaceCodeFromUrl, setUsername, setWorkspaceCode } from "./ws";
import "./styles.css";

const pageMotion = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
  transition: { duration: 0.42, ease: [0.22, 1, 0.36, 1] },
};

const panelMotion = {
  initial: { opacity: 0, scale: 0.98 },
  animate: { opacity: 1, scale: 1 },
  transition: { duration: 0.38, ease: [0.22, 1, 0.36, 1] },
};

const pressMotion = {
  whileHover: { y: -1 },
  whileTap: { scale: 0.97 },
  transition: { duration: 0.16 },
};

function App() {
  const [user, setUser] = useState(getStoredUser());
  const [authError, setAuthError] = useState("");
  const [workspaceId, setWorkspaceId] = useState(getWorkspaceCodeFromUrl());

  const currentName = useMemo(() => sessionName(user), [user]);

  function signInWithGoogle(nextUser) {
    setAuthError("");
    setUser(nextUser);
  }

  function signOut() {
    clearStoredUser();
    setUser(null);
    setWorkspaceId("");
  }

  function enterWorkspace(nextWorkspaceId) {
    const cleanCode = setWorkspaceCode(nextWorkspaceId);
    if (cleanCode) {
      setWorkspaceId(cleanCode);
    }
  }

  if (!user) {
    return (
      <SignInScreen
        authError={authError}
        canUseGoogle={hasGoogleOAuth}
        onGoogleSignIn={signInWithGoogle}
        onAuthError={setAuthError}
      />
    );
  }

  if (!workspaceId) {
    return (
      <WorkspaceLobby
        currentName={currentName}
        user={user}
        onCreate={() => enterWorkspace(createWorkspaceCode())}
        onJoin={enterWorkspace}
        onSignOut={signOut}
      />
    );
  }

  return (
    <Workspace
      currentName={currentName}
      user={user}
      workspaceId={workspaceId}
      onSignOut={signOut}
    />
  );
}

function SignInScreen({ authError, canUseGoogle, onAuthError, onGoogleSignIn }) {
  const googleButtonRef = useRef(null);

  useEffect(() => {
    if (!canUseGoogle || !googleButtonRef.current) return;
    const timer = window.setTimeout(() => {
      renderGoogleButton(googleButtonRef.current, onGoogleSignIn, onAuthError);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [canUseGoogle, onAuthError, onGoogleSignIn]);

  return (
    <motion.main className="signin-screen" {...pageMotion}>
      <motion.section className="signin-panel" {...panelMotion}>
        <motion.h1 initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.5 }}>
          Shared AI
        </motion.h1>
        <motion.p className="signin-lede" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18, duration: 0.42 }}>
          A shared AI workspace for teams to build, research, generate, and run work together in one live room.
        </motion.p>

        <motion.div className="signin-actions" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.28, duration: 0.36 }}>
          <div className="google-button-slot" ref={googleButtonRef} />
          {!canUseGoogle && <p className="inline-note">Google OAuth client ID is not configured. Local sign-in is active.</p>}
          {authError && <p className="error-note">{authError}</p>}
        </motion.div>
      </motion.section>
    </motion.main>
  );
}

function WorkspaceLobby({ currentName, user, onCreate, onJoin, onSignOut }) {
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState("");

  function submitJoin(event) {
    event.preventDefault();
    const cleanCode = joinCode.replace(/\D/g, "");
    if (!/^\d{6}$/.test(cleanCode)) {
      setError("Enter a valid 6-digit workspace code.");
      return;
    }
    onJoin(cleanCode);
  }

  return (
    <motion.main className="lobby-screen" {...pageMotion}>
      <motion.section className="lobby-panel" {...panelMotion}>
        <div className="signin-brand">
          <span>AI</span>
          <div>
            <p>Signed in as {user.email || currentName}</p>
            <h1>Start a shared workspace</h1>
          </div>
        </div>

        <div className="lobby-actions">
          <motion.button type="button" className="primary-action" onClick={onCreate} {...pressMotion}>
            Create workspace
          </motion.button>

          <form onSubmit={submitJoin}>
            <label htmlFor="joinCode">Join with teammate code</label>
            <div className="join-row">
              <input
                id="joinCode"
                inputMode="numeric"
                maxLength={6}
                placeholder="6-digit code"
                value={joinCode}
                onChange={(event) => {
                  setError("");
                  setJoinCode(event.target.value.replace(/\D/g, "").slice(0, 6));
                }}
              />
              <motion.button type="submit" {...pressMotion}>Join</motion.button>
            </div>
          </form>
          {error && <p className="error-note">{error}</p>}
        </div>

        <footer className="lobby-footer">
          <span>Create generates a random 6-digit code. Teammates sign in with Google and enter it here.</span>
          <motion.button type="button" onClick={onSignOut} {...pressMotion}>Switch account</motion.button>
        </footer>
      </motion.section>
    </motion.main>
  );
}

function Workspace({ currentName, user, workspaceId, onSignOut }) {
  const [status, setStatus] = useState("connecting");
  const [activePanel, setActivePanel] = useState("");
  const [showContext, setShowContext] = useState(true);
  const [members, setMembers] = useState([]);
  const [files, setFiles] = useState({});
  const [lockMap, setLockMap] = useState({});
  const [actions, setActions] = useState([]);
  const [events, setEvents] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState("");
  const [inviteStatus, setInviteStatus] = useState("");
  const [pendingConflict, setPendingConflict] = useState(null);
  const socketRef = useRef(null);
  const feedRef = useRef(null);

  useEffect(() => {
    const cleanName = setUsername(currentName);
    socketRef.current?.close();
    socketRef.current = createWorkspaceSocket({
      workspaceId,
      username: cleanName,
      onStatus: setStatus,
      onMessage: handleSocketMessage,
    });
    return () => socketRef.current?.close();
  }, [currentName]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [events]);

  const fileNames = useMemo(() => Object.keys(files).sort(), [files]);
  const activeFile = selectedFile && files[selectedFile] !== undefined ? selectedFile : fileNames[0] || "";
  const latestActions = actions.slice(-4).reverse();

  const inviteLink = useMemo(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("w", workspaceId);
    return url.toString();
  }, [workspaceId]);

  function handleSocketMessage(message) {
    if (message.type === "sync") {
      setFiles(message.files || {});
      setLockMap(message.lock_map || {});
      setActions(message.action_log || []);
      setMembers(message.members || []);
    }

    if (message.type === "user_joined" || message.type === "user_left") {
      setMembers(message.members || []);
    }

    if (message.type === "agent_thinking") {
      pushEvent("assistant thinking", "Generating with shared context...", message);
    }

    if (message.type === "conflict") {
      setPendingConflict(message);
      pushEvent("conflict", message.message, message);
    }

    if (message.type === "file_update") {
      const snapshot = message.snapshot || {};
      setFiles(snapshot.files || {});
      setLockMap(snapshot.lock_map || {});
      setActions(snapshot.action_log || []);
      setPendingConflict(null);
      pushEvent("assistant update", message.assistant_message || message.explanation, message);
    }

    if (message.type === "lock_update") {
      setLockMap(message.lock_map || {});
    }

    if (message.type === "workspace_reset") {
      const snapshot = message.snapshot || {};
      setFiles(snapshot.files || {});
      setLockMap(snapshot.lock_map || {});
      setActions(snapshot.action_log || []);
      setMembers(snapshot.members || []);
      setSelectedFile("");
      setPendingConflict(null);
      setEvents([]);
    }

    if (message.type === "error") {
      pushEvent("error", message.message, message);
    }
  }

  function pushEvent(kind, text, payload = {}) {
    setEvents((current) => [
      ...current.slice(-100),
      { id: crypto.randomUUID(), kind, text, payload, time: new Date().toLocaleTimeString() },
    ]);
  }

  function sendPrompt(override = false) {
    const cleanPrompt = override ? pendingConflict?.prompt : prompt;
    if (!cleanPrompt?.trim()) return;
    pushEvent("you", cleanPrompt.trim(), { user: currentName });
    socketRef.current?.send({ type: "prompt", prompt: cleanPrompt.trim(), override });
    if (!override) setPrompt("");
  }

  async function copyWorkspaceCode() {
    await navigator.clipboard.writeText(workspaceId);
    setInviteStatus("Workspace code copied.");
  }

  async function copyWorkspaceLink() {
    await navigator.clipboard.writeText(inviteLink);
    setInviteStatus("Workspace link copied.");
  }

  function handlePromptKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendPrompt(false);
    }
  }

  return (
    <motion.main className={`product-shell ${showContext ? "" : "context-collapsed"}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.28 }}>
      <motion.aside className="team-sidebar" initial={{ x: -18, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}>
        <header className="mini-brand">
          <span>AI</span>
        </header>

        <nav className="panel-nav" aria-label="Workspace sections">
          {[
            ["files", "Files", "Generated workspace files"],
            ["team", "People", "Participants and join code"],
          ].map(([key, label, title]) => (
            <motion.button
              type="button"
              className={activePanel === key ? "active" : ""}
              key={key}
              title={title}
              onClick={() => setActivePanel(key)}
              {...pressMotion}
            >
              {label}
            </motion.button>
          ))}
        </nav>

        <motion.section layout className={`sidebar-section ${activePanel === "team" ? "" : "compact-section"}`}>
          <div className="section-heading">
            <span>Participants</span>
            <strong>{members.length}</strong>
          </div>
          <div className="member-list">
            {members.map((member) => (
              <motion.div className="member-row" key={member} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}>
                <span className="presence" />
                <span>{member}</span>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section layout className={`invite-panel ${activePanel === "team" ? "" : "compact-section hidden-when-compact"}`}>
          <div className="section-heading">
            <span>Random join code</span>
          </div>
          <p className="join-code-help">Share this 6-digit code. Teammates sign in with Google, choose join, and enter it.</p>
          <motion.button type="button" className="workspace-code" onClick={copyWorkspaceCode} title="Copy workspace code" aria-label={`Copy workspace code ${workspaceId}`} {...pressMotion}>
            {workspaceId}
          </motion.button>
          <div className="share-actions">
            <motion.button type="button" onClick={copyWorkspaceCode} {...pressMotion}>
              Copy code
            </motion.button>
            <motion.button type="button" onClick={copyWorkspaceLink} {...pressMotion}>
              Copy link
            </motion.button>
          </div>
          {inviteStatus && <p className="copy-status">{inviteStatus}</p>}
        </motion.section>

        <motion.section layout className={`sidebar-section ${activePanel === "files" ? "" : "compact-section"}`}>
          <div className="section-heading">
            <span>Files</span>
            <strong>{fileNames.length}</strong>
          </div>
          <FileExplorer
            files={files}
            selectedFile={activeFile}
            onSelectFile={setSelectedFile}
            compact
          />
        </motion.section>

        <footer className="account-card">
          <div>
            <strong>{currentName}</strong>
            <p>{user?.email || "Workspace member"}</p>
          </div>
          <motion.button type="button" onClick={onSignOut} {...pressMotion}>
            Sign out
          </motion.button>
        </footer>
      </motion.aside>

      <motion.section className={`chat-workspace ${events.length === 0 ? "empty-mode" : ""}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.32 }}>
        <motion.header className="chat-header" layout>
          <div>
            <h1>Shared AI</h1>
            <p>
              <span className={`status-light ${status}`} />
              {status}
            </p>
          </div>
          <div className="chat-actions">
            <motion.button type="button" onClick={() => setShowContext((value) => !value)} {...pressMotion}>
              {showContext ? "Context on" : "Context off"}
            </motion.button>
          </div>
        </motion.header>

        <AnimatePresence>
          {pendingConflict && (
          <motion.div className="conflict-callout" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
            <div>
              <strong>Conflict warning</strong>
              <p>{pendingConflict.message}</p>
            </div>
            <motion.button type="button" onClick={() => sendPrompt(true)} {...pressMotion}>Override</motion.button>
          </motion.div>
          )}
        </AnimatePresence>

        <div className="chat-thread" ref={feedRef}>
          <AnimatePresence mode="popLayout">
          {events.length === 0 && (
            <motion.div className="empty-chat" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <span className="launch-pill">Shared context · teammate aware</span>
              <h2>What should your team build?</h2>
              <p>Ask for code, scraping, training, or integration work. The agent reads shared files, conflicts, and teammate activity before it acts.</p>
            </motion.div>
          )}

          {events.map((event) => (
            <Message key={event.id} event={event} onSelectFile={setSelectedFile} />
          ))}
          </AnimatePresence>
        </div>

        <motion.form
          className="chat-composer"
          layout
          onSubmit={(event) => {
            event.preventDefault();
            sendPrompt(false);
          }}
        >
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handlePromptKeyDown}
            placeholder="Describe what you want to build, research, generate, train, or run..."
            rows={1}
          />
          <motion.button type="submit" disabled={status !== "connected"} {...pressMotion}>Send</motion.button>
        </motion.form>
      </motion.section>

      <motion.aside className="context-drawer" initial={{ x: 18, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.12, duration: 0.34, ease: [0.22, 1, 0.36, 1] }}>
        <section>
          <div className="section-heading">
            <span>Shared context</span>
            <strong>{actions.length}</strong>
          </div>
          <div className="stat-grid">
            <span>{fileNames.length} files</span>
            <span>{Object.keys(lockMap).length} conflicts</span>
            <span>{members.length} participants</span>
          </div>
        </section>

        <section>
          <div className="section-heading">
            <span>Conflicts</span>
          </div>
          <div className="conflicts-list">
            {Object.keys(lockMap).length === 0 && <p className="soft-text">No active conflicts.</p>}
            {Object.entries(lockMap).map(([name, owner]) => (
              <div className="conflict-pill" key={name}>
                <strong>{name}</strong>
                <span>{owner}</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <div className="section-heading">
            <span>Recent work</span>
          </div>
          <div className="recent-work">
            {latestActions.length === 0 && <p className="soft-text">No generated changes yet.</p>}
            {latestActions.map((action) => (
              <motion.article key={`${action.timestamp}-${action.user}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                <strong>{action.user}</strong>
                <p>{action.explanation}</p>
              </motion.article>
            ))}
          </div>
        </section>

        <section className="code-preview">
          <div className="section-heading">
            <span>Workspace tree</span>
            <strong>{fileNames.length}</strong>
          </div>
          <FileExplorer
            files={files}
            selectedFile={activeFile}
            onSelectFile={setSelectedFile}
          />
        </section>
      </motion.aside>
    </motion.main>
  );
}

function FileExplorer({ files, selectedFile, onSelectFile, compact = false }) {
  const fileNames = useMemo(() => Object.keys(files).sort(), [files]);
  const tree = useMemo(() => buildFileTree(fileNames), [fileNames]);

  if (fileNames.length === 0) {
    return (
      <div className={`file-explorer empty ${compact ? "compact" : ""}`}>
        <p>No generated files yet.</p>
      </div>
    );
  }

  return (
    <div className={`file-explorer ${compact ? "compact" : ""}`} role="tree" aria-label="Generated files">
      {tree.children.map((node) => (
        <FileTreeNode
          key={node.path}
          node={node}
          level={0}
          selectedFile={selectedFile}
          onSelectFile={onSelectFile}
        />
      ))}
    </div>
  );
}

function FileTreeNode({ node, level, selectedFile, onSelectFile }) {
  const [isOpen, setIsOpen] = useState(true);
  const isFolder = node.type === "folder";

  if (isFolder) {
    return (
      <div className="tree-node" role="treeitem" aria-expanded={isOpen}>
        <motion.button
          type="button"
          className="tree-row folder"
          style={{ "--tree-level": level }}
          onClick={() => setIsOpen((value) => !value)}
          {...pressMotion}
        >
          <span className="tree-caret">{isOpen ? "v" : ">"}</span>
          <span className="folder-icon">DIR</span>
          <span className="tree-name">{node.name}</span>
        </motion.button>
        <AnimatePresence initial={false}>
          {isOpen && (
            <motion.div
              className="tree-children"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              {node.children.map((child) => (
                <FileTreeNode
                  key={child.path}
                  node={child}
                  level={level + 1}
                  selectedFile={selectedFile}
                  onSelectFile={onSelectFile}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  return (
    <motion.button
      type="button"
      role="treeitem"
      className={`tree-row file ${selectedFile === node.path ? "active" : ""}`}
      style={{ "--tree-level": level }}
      onClick={() => onSelectFile(node.path)}
      title={node.path}
      {...pressMotion}
    >
      <span className="tree-caret" />
      <span className="file-kind">{fileKind(node.name)}</span>
      <span className="tree-name">{node.name}</span>
    </motion.button>
  );
}

function buildFileTree(fileNames) {
  const root = { name: "root", path: "", type: "folder", children: [] };

  for (const fileName of fileNames) {
    const parts = fileName.split("/").filter(Boolean);
    let current = root;
    let currentPath = "";

    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      let next = current.children.find((child) => child.name === part && child.type === (isFile ? "file" : "folder"));

      if (!next) {
        next = {
          name: part,
          path: currentPath,
          type: isFile ? "file" : "folder",
          children: [],
        };
        current.children.push(next);
        current.children.sort((a, b) => {
          if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
          return a.name.localeCompare(b.name);
        });
      }

      current = next;
    });
  }

  return root;
}

function fileKind(fileName) {
  const extension = fileName.split(".").pop()?.toLowerCase();
  const labels = {
    py: "PY",
    js: "JS",
    jsx: "JSX",
    ts: "TS",
    tsx: "TSX",
    css: "CSS",
    html: "HTML",
    json: "JSON",
    md: "MD",
    txt: "TXT",
    yml: "YML",
    yaml: "YAML",
  };
  return labels[extension] || "FILE";
}

function Message({ event, onSelectFile }) {
  const isUser = event.kind === "you";
  const isAssistant = event.kind.startsWith("assistant");
  const name = isUser ? event.payload.user : event.payload.user || (isAssistant ? "Agent" : "Workspace");
  const files = event.payload.files ? Object.keys(event.payload.files) : [];

  return (
    <motion.article
      layout
      className={`chat-message ${isUser ? "from-user" : ""} ${event.kind.replaceAll(" ", "-")}`}
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.98 }}
      transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="message-content">
        <header>
          <strong>{name}</strong>
          <time>{event.time}</time>
        </header>
        <p>{event.text}</p>
        {event.payload.prompt && !isUser && <blockquote>{event.payload.prompt}</blockquote>}
        {files.length > 0 && (
          <div className="file-chips">
            {files.map((fileName) => (
              <motion.button type="button" key={fileName} onClick={() => onSelectFile(fileName)} {...pressMotion}>
                {fileName}
              </motion.button>
            ))}
          </div>
        )}
        {files.length > 0 && (
          <div className="generated-files">
            {files.map((fileName) => (
              <details className="generated-file-card" key={fileName} open={files.length === 1}>
                <summary>
                  <span className="file-kind">{fileKind(fileName)}</span>
                  <span>{fileName}</span>
                </summary>
                <pre>{event.payload.files[fileName]}</pre>
              </details>
            ))}
          </div>
        )}
        {event.payload.run_output && <pre>{event.payload.run_output}</pre>}
      </div>
    </motion.article>
  );
}

createRoot(document.getElementById("root")).render(<App />);
