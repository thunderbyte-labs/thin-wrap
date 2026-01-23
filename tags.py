class Xml:
    """
    Centralized constants and helper methods for all XML-style tags used in the prompt engineering system.
    All tag constructions and parsing patterns are defined here to ensure consistency and maintainability.
    """

    # Query tags
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
        return rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>"

    @staticmethod
    def file_pattern(tag: str) -> str:
        """Regex pattern to extract path and content from a file tag (tolerant to whitespace around attributes)."""
        return rf"<{tag}\b[^>]*\s*path\s*=\s*\"([^\"]+)\"\s*>([\s\S]*?)</{tag}>"

    @staticmethod
    def removal_pattern(tag: str) -> str:
        """Regex pattern to remove an entire section (including its content) for extraneous content cleanup."""
        return rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>"