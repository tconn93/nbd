/* Hermes Fleet Dashboard Plugin */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { useState, useEffect, useCallback } = React;
  const { fetchJSON } = SDK;
  const {
    Card, CardHeader, CardTitle, CardContent,
    Badge, Button, Separator,
  } = SDK.components;

  const API = "/api/plugins/hermes-fleet";

  // ── Status Dot ─────────────────────────────────────────────────────────
  function StatusDot({ status }) {
    const colors = { online: "bg-green-500", busy: "bg-yellow-500", offline: "bg-red-500" };
    return React.createElement("span", {
      className: `inline-block w-2.5 h-2.5 rounded-full ${colors[status] || "bg-gray-500"} mr-1.5`,
      title: status,
    });
  }

  // ── Message Bubble ─────────────────────────────────────────────────────
  function Message({ msg }) {
    const isUser = msg.role === "user";
    return React.createElement("div", { className: `flex ${isUser ? "justify-end" : "justify-start"} mb-2` },
      React.createElement("div", {
        className: `max-w-[80%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        }`,
      },
        React.createElement("pre", {
          style: { whiteSpace: "pre-wrap", fontFamily: "inherit", margin: 0, fontSize: "0.8125rem" },
        }, msg.content.substring(0, 500)),
        React.createElement("div", { className: `text-[10px] mt-1 ${isUser ? "text-primary-foreground/60" : "text-muted-foreground/60"}` },
          msg.created_at ? msg.created_at.substring(11, 19) : "",
        ),
      ),
    );
  }

  // ── Session Viewer ─────────────────────────────────────────────────────
  function SessionViewer({ session, onBack }) {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
      setLoading(true);
      fetchJSON(`${API}/sessions/${session.id}`)
        .then((data) => { setMessages(data.messages || []); setLoading(false); })
        .catch(() => setLoading(false));
    }, [session.id]);

    return React.createElement("div", null,
      React.createElement("div", { className: "flex items-center gap-2 mb-3" },
        React.createElement(Button, { variant: "ghost", size: "sm", onClick: onBack }, "← Back"),
        React.createElement("h2", { className: "text-sm font-medium truncate flex-1" }, session.title),
        React.createElement(Badge, { variant: "secondary", className: "text-[10px]" },
          `${session.message_count || messages.length} msgs`),
      ),
      React.createElement(Card, null,
        React.createElement(CardContent, { className: "py-3 max-h-[60vh] overflow-y-auto" },
          loading
            ? React.createElement("div", { className: "text-sm text-muted-foreground text-center py-4" }, "Loading...")
            : messages.length === 0
              ? React.createElement("div", { className: "text-sm text-muted-foreground text-center py-4" }, "No messages")
              : messages.map((m) => React.createElement(Message, { key: m.id, msg: m })),
        ),
      ),
    );
  }

  // ── Node Card ──────────────────────────────────────────────────────────
  function NodeCard({ node, sessions, onSelectSession, onRefresh }) {
    const nodeSessions = sessions.filter((s) => s.node_id === node.id);
    const [expanded, setExpanded] = useState(false);

    return React.createElement(Card, { className: "mb-3" },
      React.createElement(CardHeader, { className: "pb-2 cursor-pointer", onClick: () => setExpanded(!expanded) },
        React.createElement("div", { className: "flex items-center justify-between" },
          React.createElement("div", { className: "flex items-center gap-2" },
            React.createElement(StatusDot, { status: node.status }),
            React.createElement(CardTitle, { className: "text-sm font-medium" }, node.name || node.id),
          ),
          React.createElement("div", { className: "flex items-center gap-2" },
            React.createElement(Badge, {
              variant: node.status === "online" ? "default" : "secondary",
              className: "text-[10px] px-1.5",
            }, node.status),
            React.createElement("span", { className: "text-muted-foreground text-xs" },
              expanded ? "▲" : "▼"),
          ),
        ),
      ),
      expanded
        ? React.createElement(CardContent, { className: "pt-0 pb-3 space-y-1 text-xs" },
            React.createElement("div", { className: "text-muted-foreground font-mono truncate" },
              node.api_url),
            node.last_heartbeat
              ? React.createElement("div", { className: "text-muted-foreground" },
                  `Last seen: ${node.last_heartbeat.substring(11, 19)}`)
              : null,
            nodeSessions.length > 0
              ? React.createElement(React.Fragment, null,
                  React.createElement(Separator, { className: "my-2" }),
                  React.createElement("div", { className: "font-medium text-foreground mb-1" },
                    `Sessions (${nodeSessions.length})`),
                  nodeSessions.slice(0, 10).map((s) =>
                    React.createElement("div", {
                      key: s.id,
                      className: "flex items-center gap-2 py-1 cursor-pointer hover:bg-muted/50 rounded px-1 -mx-1",
                      onClick: () => onSelectSession(s),
                    },
                      React.createElement("span", { className: "text-muted-foreground shrink-0" }, "💬"),
                      React.createElement("span", { className: "truncate flex-1" }, s.title),
                      React.createElement("span", { className: "text-muted-foreground shrink-0 text-[10px]" },
                        `${s.message_count || 0}`),
                    ),
                  ),
                )
              : null,
          )
        : null,
    );
  }

  // ── Main Fleet Page ────────────────────────────────────────────────────
  function FleetPage() {
    const [nodes, setNodes] = useState([]);
    const [sessions, setSessions] = useState([]);
    const [selectedSession, setSelectedSession] = useState(null);
    const [error, setError] = useState(null);

    const refresh = useCallback(() => {
      fetchJSON(`${API}/nodes`).then((d) => setNodes(d.nodes || [])).catch(() => {});
      fetchJSON(`${API}/sessions?limit=100`).then((d) => setSessions(d.sessions || [])).catch(() => {});
    }, []);

    useEffect(() => { refresh(); const iv = setInterval(refresh, 15000); return () => clearInterval(iv); }, [refresh]);

    if (selectedSession) {
      return React.createElement(SessionViewer, {
        session: selectedSession,
        onBack: () => setSelectedSession(null),
      });
    }

    const online = nodes.filter((n) => n.status === "online").length;

    return React.createElement("div", { className: "space-y-4" },
      React.createElement("div", null,
        React.createElement("h1", { className: "text-xl font-bold" }, "Fleet"),
        React.createElement("p", { className: "text-xs text-muted-foreground mt-1" },
          `${nodes.length} nodes · ${online} online`),
      ),

      error
        ? React.createElement(Card, { className: "border-red-500/50" },
            React.createElement(CardContent, { className: "py-3 text-sm text-red-400" }, error))
        : null,

      nodes.length === 0
        ? React.createElement(Card, null,
            React.createElement(CardContent, { className: "py-8 text-center text-sm text-muted-foreground" },
              "No connected nodes.",
              React.createElement("div", { className: "mt-2 text-xs" },
                "Nodes register automatically when they run: ",
                React.createElement("code", { className: "bg-muted px-1 py-0.5 rounded" },
                  "hermes proxy"),
              ),
              React.createElement("div", { className: "mt-4 p-3 bg-muted/30 rounded text-left text-xs" },
                React.createElement("div", { className: "font-medium mb-1" }, "Register a node:"),
                React.createElement("code", { className: "block" },
                  `curl -X POST http://<this-host>:9119${API}/nodes/register \\`),
                React.createElement("code", { className: "block" },
                  '  -H "Content-Type: application/json" \\'),
                React.createElement("code", { className: "block" },
                  '  -d \'{"api_url": "http://node:8080", "name": "my-node"}\''),
              ),
            ),
          )
        : nodes.map((n) =>
            React.createElement(NodeCard, {
              key: n.id,
              node: n,
              sessions,
              onSelectSession: setSelectedSession,
            }),
          ),
    );
  }

  // ── Register ───────────────────────────────────────────────────────────
  window.__HERMES_PLUGINS__.register("hermes-fleet", FleetPage);
})();
