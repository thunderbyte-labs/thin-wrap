import os
import config
import datetime
import logging
import re
import shutil
import subprocess
import difflib
from tags import Xml
from pathlib import Path

logger = logging.getLogger(__name__)

def _resolve_file_path(path: str, root_dir: str) -> str:
    """
    Resolve a file path to absolute path.
    
    Args:
        path: File path (can be absolute or relative)
        root_dir: Root directory for resolving relative paths
    
    Returns:
        Absolute file path
    """
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj)
    else:
        # Resolve relative to root directory
        resolved = (Path(root_dir) / path).resolve()
        return str(resolved)

def _read_file_content(full_path: str, root_dir: str) -> str:
    """Read file content with robust error handling and path resolution."""
    try:
        # Resolve the path first
        resolved_path = _resolve_file_path(full_path, root_dir)
        path = Path(resolved_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {full_path} (resolved to: {resolved_path})")
        
        return path.read_text(encoding='utf-8')
    except PermissionError:
        raise PermissionError(f"Cannot read file due to permissions: {full_path}")
    except UnicodeDecodeError:
        raise UnicodeDecodeError(f"Cannot decode file with UTF-8: {full_path}")
    except Exception as e:
        raise Exception(f"Error reading file {full_path}: {str(e)}")

def generate_file_query(root_dir: str, readable_files: list[str], writable_files: list[str], user_request: str) -> str:
    """
    Generate the LLM query in the requested XML format using absolute paths.
    Minimal whitespace and no unnecessary blank lines.
    """
    query = Xml.o(Xml.SOURCE_CODE_FILES, 
                         'guidance="USER\'S REQUEST SOURCE CODE FILES CONTEXT FOR THIS SOLE REQUEST (THIS CONTEXT SHALL PREVAIL ON ANY PAST CONTEXT)"') + "\n"

    query += Xml.o(Xml.ROOT_DIRECTORY_OF_PROJECT) + root_dir + Xml.c(Xml.ROOT_DIRECTORY_OF_PROJECT) + "\n"

    # Read-only files
    query += Xml.o(Xml.READ_ONLY_FILES, 'guidance="FILES TO BE READ ONLY (DO NOT EDIT)"') + "\n"
    if readable_files:
        for path in readable_files:
            try:
                content = _read_file_content(path, root_dir)
                query += Xml.o(Xml.READ_ONLY_FILE, f'path="{path}"') + "\n" + content + "\n" + Xml.c(Xml.READ_ONLY_FILE) + "\n"
            except Exception as e:
                logger.error(f"Failed to read readable file {path}: {e}")
                query += Xml.o(Xml.READ_ONLY_FILE, f'path="{path}"') + "\n[Error reading file: {str(e)}]\n" + Xml.c(Xml.READ_ONLY_FILE) + "\n"
    else:
        query += "No files inputted by the user to be read.\n"
    query += Xml.c(Xml.READ_ONLY_FILES) + "\n"

    # Editable files
    query += Xml.o(Xml.EDITABLE_FILES, 'guidance="FILES THAT ARE EDITABLE BY YOU, THE LLM"') + "\n"
    if writable_files:
        for path in writable_files:
            try:
                content = _read_file_content(path, root_dir)
                query += Xml.o(Xml.EDITABLE_FILE, f'path="{path}"') + "\n" + content + "\n" + Xml.c(Xml.EDITABLE_FILE) + "\n"
            except Exception as e:
                logger.error(f"Failed to read editable file {path}: {e}")
                query += Xml.o(Xml.EDITABLE_FILE, f'path="{path}"') + "\n[Error reading file: {str(e)}]\n" + Xml.c(Xml.EDITABLE_FILE) + "\n"
    else:
        query += "No editable files inputted by the user.\n"
    query += Xml.c(Xml.EDITABLE_FILES) + "\n"

    query += Xml.c(Xml.SOURCE_CODE_FILES) + "\n"

    # User request
    query += Xml.o(Xml.USER_REQUEST) + "\n"
    query += user_request.strip() + "\n"
    query += Xml.c(Xml.USER_REQUEST) + "\n"

    # Response formatting instructions
    query += Xml.o(Xml.RESPONSE_FORMATTING, 'guidance="STRICT RESPONSE FORMATTING INSTRUCTIONS"') + "\n"
    query += f"""You, the LLM, must respond using ONLY the custom XML-style tags prefixed with "prompt_engineering_answer_".
Instructions in square brackets [] are for you and should not appear in your response.

Required format (in this exact order: edited files, then new files, then comments):

{Xml.o(Xml.EDITED_FILES)}
[Leave empty if no files to edit]
{Xml.o(Xml.EDITED_FILE, f'path="{root_dir}/absolute/path/to/existing_editable_file.py"')}
[Full new content of the file that YOU, THE LLM edited - insert here your edited version and make sure it adds value for a senior world class software engineer]
{Xml.c(Xml.EDITED_FILE)}
[Additional edited files by YOU, THE LLM if needed]
{Xml.c(Xml.EDITED_FILES)}

{Xml.o(Xml.NEW_FILES)}
[Leave empty if no new files are required - create new files only when necessary for clarity or structure]
{Xml.o(Xml.NEW_FILE, f'path="{root_dir}/absolute/path/to/new_file.py"')}
[Full content of the new file]
{Xml.c(Xml.NEW_FILE)}
[Additional new files if needed]
{Xml.c(Xml.NEW_FILES)}

{Xml.o(Xml.COMMENTS)}
[Detailed comments, explanations, or reasoning. Optional but recommended for clarity.]
{Xml.c(Xml.COMMENTS)}

CRITICAL RULES:
- Your entire response must consist solely of the tags prefixed with "prompt_engineering_answer_" and their contents. No introductory text, summaries, or any content outside these tags.
- You may edit ONLY files listed in the <{Xml.EDITABLE_FILES}> section.
- Use the exact absolute paths provided in the query.
- For new files, use absolute paths consistent with the project structure.
- The root directory of the project is {root_dir}
- Preserve exact code formatting: indentation, trailing newlines, and existing comments must remain unchanged.
- Any new code comments you add must be professional and intended for future readers of the codebase.
- If multiple viable approaches exist for the user's request, summarize the options in <{Xml.COMMENTS}> without editing or creating files. Include brief code snippets if helpful, and provide clear pros and cons from a professional software engineering perspective. The user will then select the preferred approach.\n"""
    query += Xml.c(Xml.RESPONSE_FORMATTING)

    return query

def _extract_section_content(response: str, section_tag: str) -> str:
    """Extract section content; tolerant to missing tags or whitespace."""
    pattern = Xml.section_pattern(section_tag)
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""

def _extract_files(section_content: str, file_tag: str) -> list[tuple[str, str]]:
    """Extract (path, content) pairs; tolerant to malformed entries."""
    if not section_content:
        return []
    
    pattern = Xml.file_pattern(file_tag)
    matches = re.findall(pattern, section_content, re.DOTALL | re.IGNORECASE)
    
    extracted = []
    for path, content in matches:
        cleaned_path = path.strip()
        if cleaned_path:
            content = content.lstrip('\n')
            extracted.append((cleaned_path, content))
        else:
            logger.warning(f"Skipping {file_tag} entry with empty path")
    
    if not extracted and section_content.strip():
        logger.warning(f"Section <{file_tag}> present but no valid files extracted")
    
    return extracted

def _secure_path(full_path: Path, should_exist: bool) -> None:
    """Validate that the path is absolute and its existence matches expectation."""
    if not full_path.is_absolute():
        raise ValueError(f"Path must be absolute: {full_path}")
    if should_exist != full_path.exists():
        raise FileNotFoundError(f"File {'does not exist' if should_exist else 'already exists'}: {full_path}")

def _write_file(full_path: Path, content: str, src_for_perms: Path | None = None) -> None:
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding='utf-8')
    
    if src_for_perms and src_for_perms.exists():
        shutil.copymode(src_for_perms, full_path)
    else:
        full_path.chmod(0o644)

def _compute_git_stat_diff(old_content: str, new_content: str) -> tuple[int, int]:
    """
    Compute insertions and deletions between two file contents.
    
    Args:
        old_content: Content of old file
        new_content: Content of new file
        
    Returns:
        Tuple of (insertions, deletions) similar to git diff --stat
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    # Use difflib's unified_diff to get changes
    diff_gen = difflib.unified_diff(old_lines, new_lines, n=0, lineterm='')
    
    insertions = 0
    deletions = 0
    
    for line in diff_gen:
        # Skip header lines (---, +++, @@)
        if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
            continue
        
        if line.startswith('+'):
            insertions += 1
        elif line.startswith('-'):
            deletions += 1
    
    return insertions, deletions

def _diff_report(old_path: str | None, new_path: str) -> None:
    """Display concise git-style diff summary without relying on git subprocess."""
    filename = Path(new_path).name
    
    try:
        if old_path is None or old_path == '/dev/null':
            # New file
            insertions = sum(1 for _ in open(new_path, 'r', encoding='utf-8'))
            deletions = 0
        else:
            # Read both files and compute diff
            with open(old_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
            with open(new_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            insertions, deletions = _compute_git_stat_diff(old_content, new_content)
        
        # Format output similar to git diff --stat
        if insertions == 0 and deletions == 0:
            print(f"{filename}: no changes")
        elif deletions == 0:
            print(f"{filename}: {insertions} insertions(+)")
        elif insertions == 0:
            print(f"{filename}: {deletions} deletions(-)")
        else:
            print(f"{filename}: {insertions} insertions(+), {deletions} deletions(-)")
            
    except Exception as e:
        logger.error(f"Error computing diff for {filename}: {e}")
        print(f"{filename}: error computing diff")

def parse_plain_response(llm_response: str) -> str:
    """
    Simple parser for plain text LLM responses.
    No file operations are performed.
    The entire response is treated as comments/explanation.
    """
    comments = llm_response.strip()
    return comments

def parse_xml_response(llm_response: str) -> str:
    """
    Parse LLM response with maximum tolerance:
    - Missing or empty sections are treated as no action.
    - Malformed file entries are skipped with warnings.
    - Extraneous text is logged but does not halt processing.
    """
    logger.debug("Starting parse_response")

    edited_section = _extract_section_content(llm_response, Xml.EDITED_FILES)
    new_section = _extract_section_content(llm_response, Xml.NEW_FILES)
    comments = _extract_section_content(llm_response, Xml.COMMENTS)
    
    for path_str, content in _extract_files(edited_section, Xml.EDITED_FILE):
        try:
            path = Path(path_str)
            _secure_path(path, should_exist=True)
            
            timestamp = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')
            backup = path.with_name(f"{path.stem}.{config.APP_NAME}.{timestamp}{path.suffix}")
            os.replace(path, backup)
            
            _write_file(path, content, src_for_perms=backup)
            print(f"Edited: {path}")
            _diff_report(str(backup), str(path))
        except Exception as e:
            logger.error(f"Failed to edit {path_str}: {e}")
            print(f"ERROR editing {path_str}: {e}")
    
    for path_str, content in _extract_files(new_section, Xml.NEW_FILE):
        try:
            path = Path(path_str)
            _secure_path(path, should_exist=False)
            
            _write_file(path, content, src_for_perms=None)
            print(f"Created: {path}")
            _diff_report(None, str(path))
        except Exception as e:
            logger.error(f"Failed to create {path_str}: {e}")
            print(f"ERROR creating {path_str}: {e}")
    
    clean = llm_response
    for tag in [Xml.EDITED_FILES, Xml.NEW_FILES, Xml.COMMENTS]:
        clean = re.sub(Xml.removal_pattern(tag), '', clean, flags=re.DOTALL | re.IGNORECASE)
    
    extraneous = re.sub(r'\s+', ' ', clean).strip()
    if extraneous:
        logger.warning(f"Extraneous content in response:\n{extraneous[:500]}")
    
    logger.info(f"Parsing complete. Edited: {len(_extract_files(edited_section, Xml.EDITED_FILE))}, "
                f"Created: {len(_extract_files(new_section, Xml.NEW_FILE))}")
   
    return comments.strip()


def should_generate_plain_query(readable_files: list[str], writable_files: list[str]) -> tuple[str, bool]:
    """
    Determine if a plain query (without XML formatting) should be generated.
    
    Args:
        readable_files: List of readable file paths
        writable_files: List of writable file paths
        
    Returns:
        Tuple of (action, should_generate_plain) where:
        - action: 'send_plain', 'send_with_files', or 'insert_files'
        - should_generate_plain: True for plain message, False for file context
    """
    if len(readable_files) + len(writable_files) > 0:
        return ('send_with_files', False)
    
    print(
        "No files are currently included in the context. "
        "What would you like to do?\n"
        "  [Y] - Send a plain message (without file context and file creation)\n"
        "  [n] - Send with file context (allow thin-wrap to create files)\n"
        "  [i] - Insert a file into the context (returns to text editor)\n"
    )
    
    while True:
        try:
            response = input("[Y/n/i]: ").strip().lower()
        except KeyboardInterrupt:
            # Ctrl+C should behave like choosing 'i' to insert files
            print()  # Add a newline after ^C
            return ('insert_files', False)
        
        if response == '' or response in {'y', 'yes'}:
            return ('send_plain', True)
        if response in {'n', 'no'}:
            return ('send_with_files', False)
        if response in {'i', 'insert'}:
            return ('insert_files', False)
        
        print("Invalid input. Please enter 'y', 'n', or 'i' (or press Enter for default 'y').")


def generate_plain_query(user_request: str) -> str:
    """
    Generate a plain text query without XML formatting.
    
    Args:
        user_request: The user's request text
        
    Returns:
        Plain text query string
    """
    return user_request.strip()


def generate_query(
    root_dir: str, 
    readable_files: list[str], 
    writable_files: list[str], 
    user_request: str
) -> tuple[str, callable]:
    """
    Generate the query and return the appropriate parser function.
    
    Returns:
        (query_string, parser_function) or (None, None) if user chose to insert files
        where parser_function is either parse_xml_response or parse_plain_response
    """
    action, should_generate_plain = should_generate_plain_query(readable_files, writable_files)
    
    if action == 'insert_files':
        # User chose to insert files - abort send and return to text editor
        print("Returning to text editor. Use Ctrl+B to add files before sending.")
        return None, None
    elif should_generate_plain:
        query = generate_plain_query(user_request)
        return query, parse_plain_response
    else:
        query = generate_file_query(root_dir, readable_files, writable_files, user_request)
        return query, parse_xml_response


