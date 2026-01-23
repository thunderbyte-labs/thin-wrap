import os
from pathlib import Path
import datetime
import re
import subprocess
import logging
import shutil

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

def generate_query(root_dir: str, readable_files: list[str], writable_files: list[str], user_request: str) -> str:
    """
    Generate the LLM query in the requested XML format using absolute paths.
    Minimal whitespace and no unnecessary blank lines.
    """
    query = '<prompt_engineering_query_source_code_files guidance="USER\'S REQUEST SOURCE CODE FILES CONTEXT FOR THIS SOLE REQUEST (THIS CONTEXT SHALL PREVAIL ON ANY PAST CONTEXT)">\n'

    query += '<prompt_engineering_query_root_directory_of_project>' + root_dir + '</prompt_engineering_query_root_directory_of_project>\n'

    # Read-only files
    query += '<prompt_engineering_query_read_only_files guidance="FILES TO BE READ ONLY (DO NOT EDIT)">\n'
    if readable_files:
        for path in readable_files:
            try:
                content = _read_file_content(path, root_dir)
                query += f'<prompt_engineering_query_read_only_file path="{path}">\n{content}\n</prompt_engineering_query_read_only_file>\n'
            except Exception as e:
                logger.error(f"Failed to read readable file {path}: {e}")
                query += f'<prompt_engineering_query_read_only_file path="{path}">\n[Error reading file: {str(e)}]\n</prompt_engineering_query_read_only_file>\n'
    else:
        query += 'No files inputted by the user to be read.\n'
    query += '</prompt_engineering_query_read_only_files>\n'

    # Editable files
    query += '<prompt_engineering_query_editable_files guidance="FILES THAT ARE EDITABLE BY YOU, THE LLM">\n'
    if writable_files:
        for path in writable_files:
            try:
                content = _read_file_content(path, root_dir)
                query += f'<prompt_engineering_query_editable_file path="{path}">\n{content}\n</prompt_engineering_query_editable_file>\n'
            except Exception as e:
                logger.error(f"Failed to read editable file {path}: {e}")
                query += f'<prompt_engineering_query_editable_file path="{path}">\n[Error reading file: {str(e)}]\n</prompt_engineering_query_editable_file>\n'
    else:
        query += 'No editable files inputted by the user.\n'
    query += '</prompt_engineering_query_editable_files>\n'

    query += '</prompt_engineering_query_source_code_files>\n'

    # User request
    query += '<prompt_engineering_query_user_request>\n'
    query += user_request.strip() + '\n'
    query += '</prompt_engineering_query_user_request>\n'

    # Response formatting instructions
    query += '<prompt_engineering_query_response_formatting guidance="STRICT RESPONSE FORMATTING INSTRUCTIONS">\n'
    query += f"""You, the LLM, must respond using ONLY the custom XML-style tags prefixed with "prompt_engineering_answer_".
Instructions in square brackets [] are for you and should not appear in your response.

Required format (in this exact order: edited files, then new files, then comments):

<prompt_engineering_answer_edited_files>
[Leave empty if no files to edit]
<prompt_engineering_answer_edited_file path="{root_dir}/absolute/path/to/existing_editable_file.py">
[Full new content of the file that YOU, THE LLM edited - insert here your edited version and make sure it adds value for a senior world class software engineer]
</prompt_engineering_answer_edited_file>
[Additional edited files by YOU, THE LLM if needed]
</prompt_engineering_answer_edited_files>

<prompt_engineering_answer_new_files>
[Leave empty if no new files are required - create new files only when necessary for clarity or structure]
<prompt_engineering_answer_new_file path="{root_dir}/absolute/path/to/new_file.py">
[Full content of the new file]
</prompt_engineering_answer_new_file>
[Additional new files if needed]
</prompt_engineering_answer_new_files>

<prompt_engineering_answer_comments>
[Detailed comments, explanations, or reasoning. Optional but recommended for clarity.]
</prompt_engineering_answer_comments>

CRITICAL RULES:
- Your entire response must consist solely of the tags prefixed with "prompt_engineering_answer_" and their contents. No introductory text, summaries, or any content outside these tags.
- You may edit ONLY files listed in the <prompt_engineering_query_editable_files> section.
- Use the exact absolute paths provided in the query.
- For new files, use absolute paths consistent with the project structure.
- The root directory of the project is {root_dir}
- Preserve exact code formatting: indentation, trailing newlines, and existing comments must remain unchanged.
- Any new code comments you add must be professional and intended for future readers of the codebase.
- If multiple viable approaches exist for the user's request, summarize the options in <prompt_engineering_answer_comments> without editing or creating files. Include brief code snippets if helpful, and provide clear pros and cons from a professional software engineering perspective. The user will then select the preferred approach.\n"""
    query += '</prompt_engineering_query_response_formatting>'

    return query

def _extract_section_content(response: str, section_tag: str) -> str:
    """Extract section content; tolerant to missing tags or whitespace."""
    pattern = rf'<{section_tag}\b[^>]*>([\s\S]*?)</{section_tag}>'
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""

def _extract_files(section_content: str, file_tag: str) -> list[tuple[str, str]]:
    """
    Extract (path, content) pairs; tolerant to malformed entries.

    Example:
        Given the following section_content:
            <file path="src/main.py">
            def hello():
                print("Hello, world!")
            </file>

            <file path="src/utils.py">
            def add(a, b):
                return a + b
            </file>

        The function call:
            _extract_files(section_content, "file")

        Returns:
            [
                ("src/main.py", "def hello():\\n    print(\"Hello, world!\")\\n"),
                ("src/utils.py", "def add(a, b):\\n    return a + b\\n")
            ]
    """
    if not section_content:
        return []
    
    pattern = rf'<{file_tag}\b[^>]*\spath="([^"]+)">([\s\S]*?)</{file_tag}>'
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
        logger.warning(f"Section <{section_tag}> present but no valid files extracted")
    
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

def _diff_report(old_path: str | None, new_path: str) -> None:
    """Display concise git-style diff summary."""
    if old_path is None:
        old_path = '/dev/null'
    
    result = subprocess.run(
        ['git', 'diff', '--no-index', '--stat', old_path, new_path],
        capture_output=True, text=True
    )
    
    output = result.stdout.strip()
    if not output:
        print("No differences.")
        return
    
    lines = output.splitlines()
    summary = lines[-1]
    
    ins_match = re.search(r'(\d+) insertion\(s?\)\(\+\)', summary)
    del_match = re.search(r'(\d+) deletion\(s?\)\(\-\)', summary)
    
    insertions = int(ins_match.group(1)) if ins_match else 0
    deletions = int(del_match.group(1)) if del_match else 0
    
    file_line = lines[0].split('|')[0].strip()
    filename = Path(new_path if ' => ' not in file_line else file_line.split(' => ')[-1].strip('{}')).name
    
    if insertions == deletions == 0:
        print(f"{filename}: no changes")
    elif deletions == 0:
        print(f"{filename}: {insertions} insertions(+)")
    elif insertions == 0:
        print(f"{filename}: {deletions} deletions(-)")
    else:
        print(f"{filename}: {insertions} insertions(+), {deletions} deletions(-)")

def parse_response(llm_response: str) -> tuple[str, str]:
    """
    Parse LLM response with maximum tolerance:
    - Missing or empty sections are treated as no action.
    - Malformed file entries are skipped with warnings.
    - Extraneous text is logged but does not halt processing.
    """
    logger.debug("Starting parse_response")

    edited_section = _extract_section_content(llm_response, 'prompt_engineering_answer_edited_files')
    new_section = _extract_section_content(llm_response, 'prompt_engineering_answer_new_files')
    comments = _extract_section_content(llm_response, 'prompt_engineering_answer_comments')
    
    for path_str, content in _extract_files(edited_section, 'prompt_engineering_answer_edited_file'):
        try:
            path = Path(path_str)
            _secure_path(path, should_exist=True)
            
            timestamp = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')
            backup = path.with_name(f"{path.stem}.{timestamp}{path.suffix}")
            os.replace(path, backup)
            
            _write_file(path, content, src_for_perms=backup)
            print(f"Edited: {path}")
            _diff_report(str(backup), str(path))
        except Exception as e:
            logger.error(f"Failed to edit {path_str}: {e}")
            print(f"ERROR editing {path_str}: {e}")
    
    for path_str, content in _extract_files(new_section, 'prompt_engineering_answer_new_file'):
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
    for tag in ['prompt_engineering_answer_edited_files', 'prompt_engineering_answer_new_files', 'prompt_engineering_answer_comments']:
        clean = re.sub(rf'<{tag}\b[^>]*>[\s\S]*?</{tag}>', '', clean, flags=re.DOTALL | re.IGNORECASE)
    
    extraneous = re.sub(r'\s+', ' ', clean).strip()
    if extraneous:
        logger.warning(f"Extraneous content in response: {extraneous[:500]}{'...' if len(extraneous) > 500 else ''}")
        print(f"Warning: LLM added extra text outside allowed tags (logged).")
    
    logger.info(f"Parsing complete. Edited: {len(list(_extract_files(edited_section, 'prompt_engineering_answer_edited_file')))}, "
                f"Created: {len(list(_extract_files(new_section, 'prompt_engineering_answer_new_file')))}")
   
    return comments.strip(), extraneous


def should_generate_plain_query(readable_files: list[str], writable_files: list[str]) -> bool:
    """
    Determine if a plain query (without XML formatting) should be generated.
    
    Args:
        readable_files: List of readable file paths
        writable_files: List of writable file paths
        
    Returns:
        True if there are no readable or writable files and the user confirms
        they want to send a plain message, False otherwise
    """
    if readable_files or writable_files:
        return False
    
    print(
        "No Editable or Readable files are included in the context.\n"
        "Do you want to send purely your message? "
        "(Select 'n' if you are expecting new files to be created)"
    )
    
    while True:
        response = input("(y/n): ").strip().lower()
        
        if response in {'y', 'yes'}:
            return True
        if response in {'n', 'no'}:
            return False
        
        print("Invalid input. Please enter 'y' for yes or 'n' for no.")


def generate_plain_query(user_request: str) -> str:
    """
    Generate a plain text query without XML formatting.
    
    Args:
        user_request: The user's request text
        
    Returns:
        Plain text query string
    """
    return user_request.strip()


def generate_conditional_query(
    root_dir: str, 
    readable_files: list[str], 
    writable_files: list[str], 
    user_request: str
) -> str:
    """
    Generate query based on whether files exist and user preference.
    
    Args:
        root_dir: Root directory of the project
        readable_files: List of readable file paths
        writable_files: List of writable file paths
        user_request: The user's request text
        
    Returns:
        Either a plain text query or full XML-formatted query
    """
    if should_generate_plain_query(readable_files, writable_files):
        return generate_plain_query(user_request)
    else:
        return generate_query(root_dir, readable_files, writable_files, user_request)
