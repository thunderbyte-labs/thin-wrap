
# Thin Wrap - LLM Terminal Chat
A thin cross-platform terminal-based chat application for wrapping your Large Language Model APIs, featuring file context management, code editing capabilities, and session logging.

## Features

- **Multi-LLM Support**: Seamlessly switch between different LLM providers (Claude, DeepSeek, Grok, etc.)
- **File Context Management**: Interactive three-column file browser (**Ctrl+Space**) for managing editable and readable files
- **Intelligent Code Editing**: 
  - Automatic file versioning with timestamped backups
  - Git-style diff reporting for changes
  - Preserves file permissions and formatting
- **Project Root Selection**: Interactive project root selection with history and Tab autocompletion
- **Multi-line Input**: Natural multi-line message composition (**Alt+Enter** to send)
- **Session Logging**: Automatic session log saving with timestamps
- **Proxy Support**: SOCKS5 and HTTP proxy support for restricted networks
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd thin-wrap

# Install dependencies
pip install -r requirements.txt
```

### Dependencies

- `openai` - Unified API client for LLM interactions
- `prompt_toolkit` - Advanced terminal input handling
- `textual` - Terminal UI framework for file browser
- `rich` - Rich text and logging support
- `platformdirs` - Cross-platform directory handling
- `requests` - HTTP client
- `pysocks` - SOCKS proxy support (optional)
- `questionary` - Interactive prompts

## Quick Start

```bash
# Basic usage
python chat.py

# With project root specified
python chat.py --root-dir /path/to/project

# With initial file context
python chat.py --root-dir . --read main.py --edit config.py

# With proxy support
python chat.py --proxy socks5://127.0.0.1:1080
```

## Configuration

### API Keys

Set environment variables for your chosen LLM providers:

```bash
export ANTHROPIC_API_KEY="your-key-here"
export DEEPSEEK_API_KEY="your-key-here"
export OPENROUTER_API_KEY="your-key-here"
export HERA_API_KEY="your-key-here"
```

### Supported Models

Configure models in `config.py`:
- `claude-sonnet-4-20250514` (Anthropic)
- `deepseek-reasoner` (DeepSeek)
- `x-ai/grok-4.1-fast` (OpenRouter)
- `anthropic/claude-sonnet-4.5` (OpenRouter)
- `hera/qwen` (Hera)
- `baidu/ernie-4.5-300b-a47b` (OpenRouter)

## Usage

### Interactive Commands

- `/help` or `/?` - Show available commands
- `/model [name]` - Switch LLM model or show current model
- `/clear` - Clear conversation history
- `/save` - Manually save session log
- `/files` - Open file context menu (or press Ctrl+Space)
- `/rootdir [path]` - Show or set project root directory
- `/bye` - Exit and save session (then Alt+Enter)

### File Context Management

Press **Ctrl+Space** to open the three-column file browser:

- **Left Column**: Editable files (LLM can modify these)
- **Middle Column**: Readable files (LLM can read but not modify)
- **Right Column**: Project navigator (browse all files)

**Keyboard Shortcuts**:
- `Tab` / `Shift+Tab` - Switch between columns
- `e` - Mark file as editable
- `r` - Mark file as readable
- `d` - Remove file from context
- `Ctrl+Space` or `Escape` - Close menu

### Message Input

- `Enter` - New line
- `Alt+Enter` - Send message
- `Ctrl+Space` - Open file context menu

## Architecture

### Core Components

- **chat.py**: Main application entry point and chat loop
- **llm_client.py**: Unified LLM API client with multi-provider support
- **file_processor.py**: File context management and code editing
- **input_handler.py**: Advanced terminal input handling
- **command_handler.py**: Command processing and routing
- **menu.py**: Three-column file browser UI (Textual-based)
- **session_logger.py**: Session logging and persistence
- **proxy_wrapper.py**: SOCKS5/HTTP proxy support
- **config.py**: Centralized configuration
- **ui.py**: Terminal UI utilities and banner display
- **text_utils.py**: Text processing and token estimation

### XML-Based Protocol

The application uses a custom XML protocol for precise file context management:

**Request Format**:
```xml
<prompt_engineering_query_source_code_files>
  <prompt_engineering_query_root_directory_of_project>...</prompt_engineering_query_root_directory_of_project>
  <prompt_engineering_query_read_only_files>
    <prompt_engineering_query_read_only_file path="...">...</prompt_engineering_query_read_only_file>
  </prompt_engineering_query_read_only_files>
  <prompt_engineering_query_editable_files>
    <prompt_engineering_query_editable_file path="...">...</prompt_engineering_query_editable_file>
  </prompt_engineering_query_editable_files>
</prompt_engineering_query_source_code_files>
<prompt_engineering_query_user_request>...</prompt_engineering_query_user_request>
```

**Response Format**:
```xml
<prompt_engineering_answer_edited_files>
  <prompt_engineering_answer_edited_file path="...">...</prompt_engineering_answer_edited_file>
</prompt_engineering_answer_edited_files>
<prompt_engineering_answer_new_files>
  <prompt_engineering_answer_new_file path="...">...</prompt_engineering_answer_new_file>
</prompt_engineering_answer_new_files>
<prompt_engineering_answer_comments>...</prompt_engineering_answer_comments>
```

## Session Logs

Session logs are automatically saved to `llm_session_YYYYMMDD_HHMMSS.txt` in the script directory. Each log includes:
- Session start/end timestamps
- All user inputs and LLM responses
- Interaction count

## Advanced Features

### Proxy Configuration

Supports both SOCKS5 and HTTP proxies:

```bash
# SOCKS5 with authentication
python chat.py --proxy socks5://user:pass@127.0.0.1:1080

# HTTP proxy
python chat.py --proxy http://proxy.example.com:8080
```

### File Versioning

All edited files are automatically backed up with timestamps:
```
original_file.py -> original_file.20250131123045.py
```

### Git Integration

The application uses `git diff` for change reporting, showing:
- Number of insertions/deletions
- File-specific change summaries

## Cross-Platform Compatibility

- **Windows**: Uses `notepad` as default editor
- **Linux/macOS**: Uses `vim`/`nano` as default editors
- Automatic terminal width detection with fallback
- Cross-platform path handling via `pathlib`
- Platform-specific proxy configuration

## Logging

Configurable logging via `config.py`:
- Uses `rich.logging.RichHandler` for enhanced terminal output
- Supports file logging and custom handlers
- Adjustable log levels (DEBUG, INFO, WARNING, ERROR)

## Troubleshooting

### Common Issues

1. **API Key Not Found**: Ensure environment variables are set correctly
2. **Proxy Connection Failed**: Verify proxy URL format and credentials
3. **File Permission Errors**: Check file permissions in project directory
4. **Unicode Errors**: Application handles UTF-8 with automatic fallback

### Debug Mode

Enable debug logging in `config.py`:
```python
LOG_LEVEL = logging.DEBUG
```

## Contributing

Contributions are welcome! Please ensure:
- Code follows existing style conventions
- All features work cross-platform
- Documentation is updated
- Error handling is robust

## License

[Add your license information here]

## Acknowledgments

Built with:
- OpenAI API client library
- Prompt Toolkit for advanced terminal input
- Textual for terminal UI
- Rich for beautiful terminal output
