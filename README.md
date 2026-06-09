# Thin Wrap

A terminal chat for any LLM API endpoint -- bridging pure coding and vibe-coding.

## Installation

**Linux/macOS** (curl/wget + unzip required):
```bash
curl -fsSL https://raw.githubusercontent.com/thunderbyte-labs/thin-wrap/main/install.sh | sh
```
Installs to `~/.local/bin` / `~/.local/lib/thin-wrap/`, config at `~/.config/thin-wrap/`, updates PATH.

**Windows:** Download `.zip` from [Releases](https://github.com/thunderbyte-labs/thin-wrap/releases), extract, add to PATH manually.

**Uninstall:**
```bash
curl -fsSL https://raw.githubusercontent.com/thunderbyte-labs/thin-wrap/main/uninstall.sh | sh
```

## Features

- **Multi-LLM:** Switch providers via `/model` (DeepSeek, Gemini, OpenRouter, custom endpoints).
- **File Context:** `Ctrl+B` opens a 3-column browser (editable / readable / navigator). `r`/`e`/`d` moves files; `Ctrl+D` clears all.
- **Proxy:** Use any SOCKS5/HTTP proxy (`--proxy` or `/proxy`). Per-model proxy hints via `"proxy": true` in config.
- **Intelligent Editing:** LLM-recommended edits get timestamped backups (`file.thin-wrap.20250130.py`) with Python-native diff stats. Backup can be disabled entirely via `backup.enabled` (see Configuration).
- **Session Logging:** Conversations auto-saved as `.toml.zip` with metadata (message count, preview). Reload with `/reload`.
- **Free Chat:** Choose "No root directory" at startup to chat without file context.
- **History:** `PageUp`/`PageDown` navigates sent messages and temporary drafts.

## Configuration

`config.json` is resolved in order: `--config` arg → `$THIN_WRAP_CONFIG_DIR` → `~/.config/thin-wrap/` → executable directory.

### Models

Each entry requires `model`, `api_key` (env var name), `api_base_url`.  
Optional fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `proxy` | bool | `false` | Prompt for proxy when selecting this model |
| `endpoint` | string | `/chat/completions` | Custom API endpoint path |
| `input_key` | string | `"messages"` | Payload key for input (e.g., `"input"` for DashScope) |
| `extra_arguments` | object | `{}` | Additional JSON fields sent in request body |
| `plugins` | list or dict | `[]` | Define API plugins/tools (see Plugins section) |

Example:
```json
{
  "gemini-2.5-flash": {
    "model": "gemini-2.5-flash",
    "api_key": "GOOGLE_API_KEY",
    "api_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "proxy": true
  }
}
```

### Plugins

The `plugins` field lets you attach API-level plugins (e.g., web search, code execution) to a model. Plugins are merged into the request payload and are provider-dependent.

- **List form:** Simple list of plugin names or type objects. Currently only tested on OpenRouter.  
  ```json
  "plugins": ["web_search", "web_extractor"]
  ```
- **Dict form:** Full plugin definitions with options. Currently only tested on Qwen-Plus 3.6.  
  ```json
  "plugins": {
    "tools": [
      { "type": "web_search", "search_strategy": "agent" },
      { "type": "web_extractor" }
    ]
  }
  ```

**Note:** Plugins functionality depends on the API provider. For OpenAI-compatible endpoints, equivalent behaviour can be achieved via `extra_arguments` with a `tools` key. The `plugins` field provides a more abstract, model-centric way to declare them.

### Backup

Controls file backup behaviour during intelligent editing.

When `"enabled": true`, the three fields `timestamp_format`, `extra_string` and `overwrite_original` **are mandatory**.

```json
"backup": {
  "enabled": true,
  "timestamp_format": "%Y%m%d%H%M%S",
  "extra_string": "thin-wrap",
  "overwrite_original": true
}
```

| Field              | Type   | Description |
|--------------------|--------|-------------|
| `enabled`          | bool   | Master switch. `false` disables all backups (direct overwrite). |
| `overwrite_original` | bool | If `true`: rename original to timestamped backup, then write new content to original path.<br>If `false`: write new content to a separate timestamped file, leave original untouched. |
| `timestamp_format` | string | strftime format used in backup filenames. |
| `extra_string`     | string | String inserted before the timestamp in backup filename. |

## Usage

1. Run `thin-wrap` (or `python thin_wrap.py` from source).
2. Select a project root (or free chat mode).
3. Choose a model (proxy prompt appears if needed).
4. Type message, press **Alt+Enter** to send.
5. Use **Ctrl+B** to manage files, **PageUp/Down** for history.

### CLI Arguments

```
--root-dir <path>      Project root
--read <files>         Readable files (space-separated)
--edit <files>         Editable files
--message <text>       First message to send
--proxy <url>          Proxy URL
--config <path>        Config file path
--help                 Show help with data locations
```

### Commands

| Command | Description |
|---------|-------------|
| `/help` `/?` | Show command help |
| `/clear` | Clear conversation |
| `/bye` | Exit (saves session) |
| `/model` | Switch model (interactive or `name`) |
| `/reload` | Load a previous session |
| `/rootdir` | Change root directory (option 0 = free chat) |
| `/files` | Open file context menu |
| `/proxy` | Configure proxy (`off` to disable) |

## Architecture

| Module | Role |
|--------|------|
| `thin_wrap.py` | Entry point, chat loop |
| `config.py` | Config loading and validation |
| `llm_client.py` | Raw `httpx`-based API calls |
| `file_processor.py` | Query generation, XML parsing, file editing |
| `input_handler.py` | Multi-line input, history, command completion |
| `command_handler.py` | Slash command dispatch |
| `menu.py` | Textual-based file browser |
| `proxy_wrapper.py` | Proxy validation, SOCKS/HTTP |
| `session_logger.py` | TOML+ZIP session persistence |
| `tags.py` | XML tag utilities |
| `text_utils.py` | Text cleaning, token estimation |
| `ui.py` | Banners, colors, interactive selectors |

## Security

- Refuses root execution.
- API keys via environment variables (strongly recommended).
- XDG-compliant config storage.

## Contributing

Maintain cross-platform compat, PEP 8, add tests for new features. PRs to `main`. Read TESTING.md.

## License

AGPL-3.0