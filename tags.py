class Xml:
    """
    Centralized constants and helper methods for all XML-style tags used in the prompt engineering system.
    All tag constructions and parsing patterns are defined here to ensure consistency and maintainability.
    """

    # Query tags
    DIRECTORY_TREE = "prompt_engineering_query_directory_tree"
    SOURCE_CODE_FILES = "prompt_engineering_query_source_code_files"
    ROOT_DIRECTORY_OF_PROJECT = "prompt_engineering_query_root_directory_of_project"
    READ_ONLY_FILES = "prompt_engineering_query_read_only_files"
    READ_ONLY_FILE = "prompt_engineering_query_read_only_file"
    EDITABLE_FILES = "prompt_engineering_query_editable_files"
    EDITABLE_FILE = "prompt_engineering_query_editable_file"
    USER_REQUEST = "prompt_engineering_query_user_request"
    RESPONSE_FORMATTING = "prompt_engineering_query_response_formatting"

    # Answer tags
    EDITED_FILES = "prompt_engineering_answer_edited_files"
    EDITED_FILE = "prompt_engineering_answer_edited_file"
    NEW_FILES = "prompt_engineering_answer_new_files"
    NEW_FILE = "prompt_engineering_answer_new_file"
    COMMENTS = "prompt_engineering_answer_comments"

    @staticmethod
    def o(tag: str, attr: str = "") -> str:
        """Generate opening tag, with optional attribute string (must include the attribute name and value)."""
        if attr:
            return f"<{tag} {attr}>"
        return f"<{tag}>"

    @staticmethod
    def c(tag: str) -> str:
        """Generate closing tag."""
        return f"</{tag}>"

    @staticmethod
    def section_pattern(tag: str) -> str:
        """Regex pattern to extract content from a section tag (tolerant to attributes and whitespace)."""
        return rf"<{tag}\\b[^>]*>([\\s\\S]*?)</{tag}>"

    @staticmethod
    def file_pattern(tag: str) -> str:
        """Regex pattern to extract path and content from a file tag (tolerant to whitespace around attributes)."""
        return rf"<{tag}\\b[^>]*\\s*path\\s*=\\s*\"([^\"]+)\"\\s*>([\\s\\S]*?)</{tag}>"

    @staticmethod
    def removal_pattern(tag: str) -> str:
        """Regex pattern to remove an entire section (including its content) for extraneous content cleanup."""
        return rf"<{tag}\\b[^>]*>[\\s\\S]*?</{tag}>"

    @staticmethod
    def opening_pattern(tag: str) -> str:
        """Regex pattern matching an opening tag, including optional attributes."""
        return rf"<{tag}\\b[^>]*>"

    @staticmethod
    def closing_pattern(tag: str) -> str:
        """Regex pattern matching a closing tag."""
        return rf"</{tag}>"

    # Any prompt-engineering answer tag. Used to bound an unclosed comments body
    # so a later edited/new-files block is not swallowed as display text.
    ANSWER_OPENING_PATTERN = r"<prompt_engineering_answer_[a-z_]+\\b[^>]*>"
