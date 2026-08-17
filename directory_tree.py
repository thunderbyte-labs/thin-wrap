"""Smart directory tree generation for LLM context.

Pure-Python, cross-platform (pathlib + os.scandir, no external ``tree`` binary).
Respects only .gitignore files (no custom ignore files). Directories whose
direct non-text file ratio exceeds ``RATIO_THRESHOLD`` are summarized compactly.
"""

import logging
import os
from pathlib import Path

from pathspec import GitIgnoreSpec

logger = logging.getLogger(__name__)

# Exhaustive list of textual file extensions (matched case-insensitively, no dot).
TEXT_EXTENSIONS = {
    # Web / JS / TS
    "js",
    "jsx",
    "mjs",
    "cjs",
    "ts",
    "tsx",
    "mts",
    "cts",
    "mtsx",
    "ctsx",
    "vue",
    "svelte",
    "astro",
    "css",
    "scss",
    "sass",
    "less",
    "styl",
    "html",
    "htm",
    "xhtml",
    "xml",
    "svg",
    "xsl",
    "xslt",
    # Markup / Docs
    "md",
    "mdx",
    "markdown",
    "rst",
    "adoc",
    "asciidoc",
    "org",
    "tex",
    "latex",
    "bib",
    "txt",
    "text",
    "log",
    "csv",
    "tsv",
    # Data / Config
    "json",
    "jsonc",
    "json5",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "conf",
    "config",
    "env",
    "properties",
    "editorconfig",
    # Shell / Scripts
    "sh",
    "bash",
    "zsh",
    "fish",
    "ksh",
    "csh",
    "ps1",
    "psm1",
    "psd1",
    "cmd",
    "bat",
    "awk",
    "sed",
    # Python
    "py",
    "pyi",
    "pyw",
    "pyx",
    "pxd",
    "ipynb",
    # Systems languages
    "c",
    "h",
    "cpp",
    "cc",
    "cxx",
    "c++",
    "hpp",
    "hh",
    "hxx",
    "h++",
    "rs",
    "go",
    "zig",
    "zon",
    "nim",
    "d",
    "v",
    # JVM / .NET
    "java",
    "kt",
    "kts",
    "scala",
    "sc",
    "groovy",
    "cs",
    "csx",
    "fs",
    "fsi",
    "fsx",
    # Other popular languages
    "php",
    "phtml",
    "rb",
    "rake",
    "gemspec",
    "ru",
    "lua",
    "vim",
    "r",
    "R",
    "jl",
    "swift",
    "dart",
    "ex",
    "exs",
    "elm",
    "hs",
    "lhs",
    "clj",
    "cljs",
    "cljc",
    "edn",
    "ml",
    "mli",
    "erl",
    "hrl",
    "pl",
    "pm",
    "t",
    "tcl",
    "raku",
    "p6",
    # Build / Infra
    "cmake",
    "make",
    "mk",
    "dockerfile",
    "containerfile",
    "tf",
    "hcl",
    "nix",
    "proto",
    "thrift",
    "graphql",
    "gql",
    # SQL & query
    "sql",
    "pgsql",
    "mysql",
    "plsql",
    # Misc useful
    "diff",
    "patch",
    "gitignore",
    "gitattributes",
    "gitmodules",
    "npmrc",
    "nvmrc",
    "prettierrc",
    "eslintrc",
    "babelrc",
    "stylelintrc",
    "lock",  # text lockfiles
}

# Special filenames (no extension or exact basename) always treated as text.
TEXT_FILENAMES = {
    "dockerfile",
    "containerfile",
    "makefile",
    "gnumakefile",
    "cmakelists.txt",
    "license",
    "licence",
    "copying",
    "readme",
    "changelog",
    "authors",
    "contributors",
    "notice",
    "todo",
    "cargo.toml",
    "go.mod",
    "go.sum",
    "package.json",
    "tsconfig.json",
    "jsconfig.json",
    "pyproject.toml",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "meson.build",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".dockerignore",
    ".npmignore",
    ".eslintignore",
    ".prettierignore",
    ".editorconfig",
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".nvmrc",
    ".node-version",
    ".python-version",
    ".ruby-version",
    ".tool-versions",
    ".prettierrc",
    ".eslintrc",
    ".babelrc",
    ".stylelintrc",
    ".yarnrc",
    ".npmrc",
}

# A directory is summarized when non-text files exceed this ratio of its
# direct files. Ratio-based only (never an absolute file-count threshold).
RATIO_THRESHOLD = 0.70


def _is_text(name: str) -> bool:
    """Return True when the entry name denotes a textual file."""
    low = name.lower()
    if low in TEXT_FILENAMES:
        return True
    suffix = Path(low).suffix
    return bool(suffix) and suffix[1:] in TEXT_EXTENSIONS


def _parent_dirs(path: Path) -> list[Path]:
    """Return ancestor directories of ``path``, closest first."""
    dirs = []
    current = path.parent
    while True:
        dirs.append(current)
        if current.parent == current:
            break
        current = current.parent
    return dirs


class GitIgnoreRules:
    """Strict .gitignore handling using pathspec.

    Collects .gitignore files from the project root, its ancestors, and any
    nested directories discovered during traversal. For each path the deepest
    .gitignore that makes a decision wins (git semantics).
    """

    def __init__(self, root_dir: str | os.PathLike[str]) -> None:
        self._root = Path(root_dir)
        self._specs: list[tuple[Path, GitIgnoreSpec]] = []
        for base in _parent_dirs(self._root):
            self.add_nested(base)
        self.add_nested(self._root)

    def add_nested(self, base: Path) -> None:
        """Register the .gitignore of ``base`` (idempotent by directory)."""
        if any(base == existing for existing, _ in self._specs):
            return
        gitignore = base / ".gitignore"
        if not gitignore.is_file():
            return
        try:
            text = gitignore.read_text(encoding="utf-8", errors="replace")
            spec = GitIgnoreSpec.from_lines(text.splitlines())
        except Exception as e:
            logger.warning(f"Failed to parse .gitignore at {gitignore}: {e}")
            return
        self._specs.append((base, spec))

    def check(self, path: Path, is_dir: bool) -> bool:
        """Return True when ``path`` is ignored (deepest matching rule wins)."""
        for base, spec in reversed(self._specs):
            if not path.is_relative_to(base):
                continue
            rel = path.relative_to(base).as_posix()
            if is_dir:
                rel += "/"
            result = spec.check_file(rel)
            if result is not None and result.include is not None:
                return bool(result.include)
        return False


def _count_files(dir_path: Path, rules: GitIgnoreRules) -> int:
    """Recursive count of files under ``dir_path`` (gitignore-respecting)."""
    rules.add_nested(dir_path)
    total = 0
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.name == ".git":
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False
                if rules.check(dir_path / entry.name, is_dir):
                    continue
                if is_dir:
                    total += _count_files(dir_path / entry.name, rules)
                else:
                    total += 1
    except OSError:
        pass
    return total


def _walk(
    dir_path: Path,
    depth: int,
    prefix: str,
    lines: list[str],
    rules: GitIgnoreRules,
    max_depth: int,
) -> None:
    if depth >= max_depth:
        return

    try:
        with os.scandir(dir_path) as it:
            entries = list(it)
    except OSError:
        return

    items: list[tuple[str, bool]] = []
    for entry in entries:
        if entry.name == ".git":
            continue
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            is_dir = False
        if rules.check(dir_path / entry.name, is_dir):
            continue
        items.append((entry.name, is_dir))

    items.sort(key=lambda item: (not item[1], item[0]))

    direct_files = [name for name, is_dir in items if not is_dir]
    non_text = sum(1 for name in direct_files if not _is_text(name))
    summarize = bool(direct_files) and (non_text / len(direct_files)) > RATIO_THRESHOLD

    for i, (name, is_dir) in enumerate(items):
        last = i == len(items) - 1
        branch = "└── " if last else "├── "
        child_prefix = prefix + ("    " if last else "│   ")
        if is_dir:
            child = dir_path / name
            if depth + 1 >= max_depth or summarize:
                count = _count_files(child, rules)
                lines.append(f"{prefix}{branch}{name}/      → {count} files")
            else:
                lines.append(f"{prefix}{branch}{name}/")
                rules.add_nested(child)
                _walk(child, depth + 1, child_prefix, lines, rules, max_depth)
        else:
            if summarize and not _is_text(name):
                continue
            lines.append(f"{prefix}{branch}{name}")


def build_directory_tree(root_dir: str | os.PathLike[str], max_depth: int) -> str:
    """Build the smart tree of ``root_dir`` up to ``max_depth`` levels.

    Args:
        root_dir: Project root directory.
        max_depth: Maximum directory depth to expand (1 = direct children).
    """
    root = Path(root_dir).resolve()
    rules = GitIgnoreRules(root)
    root_label = root.name if root.name else str(root)
    lines = [f"{root_label}/"]
    _walk(root, 0, "", lines, rules, max_depth)
    return "\n".join(lines)


def tree_char_count(tree: str) -> int:
    """Number of characters in the final tree string."""
    return len(tree)
