# Thin Wrap - LLM Terminal Chat

A thin cross-platform terminal-based chat application for wrapping any Large Language Model (LLM) API endpoint, featuring file context management, intelligent code editing, proxy support, and session logging.

## Installation

Pre-built zipped executables are available for Windows, macOS, and Linux platforms.

1. Visit the [Releases page](https://github.com/thunderbyte-labs/thin-wrap/releases).
2. Download the appropriate zip file for your platform:
   - Windows: `thin-wrap-windows.zip`
   - macOS: `thin-wrap-macos.zip`
   - Linux: `thin-wrap-linux.zip`
3. Extract the zip file to a directory of your choice.

A sample `config.json` file is included in the extracted directory.

4. Run the executable:
   - On Windows: Double-click `thin-wrap.exe` (or run from Command Prompt).
   - On macOS or Linux: Open a terminal, navigate to the extracted directory, and execute `./thin-wrap`.

Note: On macOS or Linux, you may need to grant execution permissions with `chmod +x thin-wrap` if required.

## Configuration

The application uses a `config.json` file located in the same directory as the executable.

A sample `config.json` is provided with the release. It contains two main sections:

### models
A dictionary defining available LLM models. Each entry uses a unique model identifier as the key, with:
- **api_key**: The name of the environment variable that holds the actual API key (recommended for security). Direct API key strings may also be used, though this is discouraged.
- **api_base_url**: The base URL for the model's API endpoint.

Example entries (from the sample):
```json
"gemini-2.5-flash": {
  "api_key": "GOOGLE_API_KEY",
  "api_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"
},
"deepseek-chat": {
  "api_key": "DEEPSEEK_API_KEY",
  "api_base_url": "https://api.deepseek.com/v1"
},
"anthropic/claude-sonnet-4.5": {
  "api_key": "OPENROUTER_API_KEY",
  "api_base_url": "https://openrouter.ai/api/v1"
}
```

Set the corresponding environment variables before running the application (e.g., `export GOOGLE_API_KEY=your_actual_key`).

### backup
Configuration for file backup behavior during intelligent code editing:
- **timestamp_format**: strftime format used for timestamps in backup filenames (default: `"%Y%m%d%H%M%S"`).
- **extra_string**: Additional string appended to backup filenames (default: `"thin-wrap"`).
- **backup_old_file**: Boolean controlling whether the original file is backed up before changes are applied (default: `false`).

Users may edit `config.json` to add, remove, or modify models and backup settings as needed.

If `config.json` is missing or invalid, the application will raise an error with guidance.

## Features

- **Multi-LLM Support**: Seamlessly switch between providers like Claude, DeepSeek, Grok, Gemini, and others via the `/model` command.
- **File Context Management**: Interactive three-column file browser (activated with **Ctrl+B**) for selecting editable and readable files, with a new file insertion flow and Ctrl+D shortcut to clear selected files.
- **Proxy Support**: Configure SOCKS5 or HTTP proxies to bypass geographic restrictions (e.g., for Anthropic or Gemini in restricted regions). Recommended providers: [Webshare](https://www.webshare.io/) (tested), [IPRoyal](https://iproyal.com/) (untested), [Proxy-Seller](https://proxy-seller.com/) (untested). Use the `--proxy` flag (e.g., `--proxy socks5://127.0.0.1:1080`).
- **Intelligent Code Editing**:
  - Automatic file versioning with timestamped backups (e.g., `file.py` becomes `file.202601301511.py`).
  - Git-style diff reporting for changes using `git diff`.
  - Preservation of file permissions and formatting.
- **Project Root Selection**: Interactive selection of project root directory with history, Tab autocompletion, and support for `~` (home directory). Change via `/rootdir` command.
- **Multi-line Input**: Compose messages across multiple lines; send with **Alt+Enter**.
- **Message History Navigation**: Navigate through previously sent messages and temporary drafts with **Page Up/Down** keys.
- **Session Logging**: Automatic saving of chat sessions as timestamped text files (e.g., `llm_session_20260130_151145.txt`) in the project root or user data directory.
- **Token Estimation**: Built-in token estimator for input and output messages to monitor usage.
- **Colorized UI Elements**: Enhanced help menu and outputs with colorization for better readability.
- **Improved Reloading**: Debugged `/reload` command for loading previous conversations from the project root.
- **Cross-Platform Compatibility**: Fully functional on Windows, macOS, and Linux, with platform-specific editors (Notepad on Windows, vim/nano on Unix) and path handling.

## Usage

1. Launch the application as described in the Installation section.
2. Select a project root directory (if not specified via `--root-dir`). You can choose "No root directory - Free chatting without file context" to enable free chat mode without file context.
3. Choose an LLM model from the available options.
4. Enter your message and press **Alt+Enter** to send.
5. Use commands starting with `/` for additional functionality (see Commands below).
6. Manage file contexts with **Ctrl+B** to open the file browser menu. In free chat mode, Ctrl+B allows you to select a root directory and switch to file context mode.

Sessions are automatically saved upon exit or after each exchange.

**Navigation**: Use **Page Up** and **Page Down** to navigate through message history (sent messages and temporary drafts).

### Command-Line Arguments

- `--root-dir <path>`: Specify the project root directory.
- `--read <files>`: List of readable files (space-separated).
- `--edit <files>`: List of editable files (space-separated).
- `--message <text>`: Initial message to send to the LLM.
- `--proxy <url>`: Proxy URL (e.g., `socks5://127.0.0.1:1080`).
## Commands

Available in-chat commands:

- `/clear`: Clear the current session context.
- `/bye`: Exit the application (auto-saves the session).
- `/help` or `/?`: Display help for commands.
- `/model`: Switch to a different LLM model.
- `/reload`: Load a previous conversation from available sessions in the project root.
- `/rootdir`: Show or change the current project root directory.
- `/files`: Open the file context management menu (equivalent to Ctrl+B).

## Architecture

The application is modular, with key components:

- `chat.py`: Main entry point and chat loop.
- `config.py`: Configuration settings and model loading.
- `llm_client.py`: Unified LLM API wrapper using the OpenAI library.
- `file_processor.py`: Handles file queries, versioning, and diff generation.
- `input_handler.py`: Manages user input with editing capabilities.
- `menu.py`: Interactive menus for file browsing and selections.
- `proxy_wrapper.py`: Proxy configuration and validation.
- `session_logger.py`: Session saving and reloading.
- `text_utils.py`: Text cleaning and token estimation.
- `ui.py`: User interface elements like banners and colorized outputs.
- Other utilities: `command_handler.py`, `tags.py`.

## Troubleshooting
- Verify environment variables for API keys.
- Ensure proxy format is correct if used.
- Check file permissions for editing.
- Adjust `config.json` backup settings if needed.

## Contributing
Contributions are welcome! Please follow these guidelines:

- Maintain cross-platform compatibility.
- Adhere to Python style (PEP 8).
- Update documentation for new features.
- Test on multiple platforms.
- Submit pull requests to the `main` branch.
## License
This project is licensed under the AGPL-3.0 License. See the [LICENSE](LICENSE) file for details.