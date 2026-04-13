# TODOS

## Add philosophy/workflow guidance to MCP tool descriptions
**What:** Enhance MCP tool descriptions in `routes/mcp.py` to include behavioral guidance (when to create pages, visibility recommendations, titling conventions) alongside the current functional descriptions.
**Why:** Claude Code (the primary agent path) reads MCP tool descriptions, not `/api/v1/agent-setup`. This is where philosophy guidance has the highest impact on actual agent behavior. Codex review flagged this as higher leverage than the agent-setup endpoint changes.
**Context:** Currently MCP tool descriptions are functional only (e.g., "Create a new page. Content should be markdown starting with `# Title`."). Philosophy guidance lives in `agent-setup` (for the copy-paste prompt path) but not in MCP (for the native Claude Code path). The `list_pages` MCP tool already returns conventions with AGENTS content, but the tool descriptions themselves don't prime the agent's behavior.
**Depends on:** Nothing. Can be done independently of the agent-setup philosophy changes.
