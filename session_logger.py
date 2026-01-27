"""Session logging functionality with TOML format and automatic zipped saving"""
import os
import zipfile
import tomlkit
from datetime import datetime
from pathlib import Path
import config
import re

class SessionLogger:
    def __init__(self, script_directory, root_dir):
        self.script_directory = script_directory
        self.root_dir = root_dir
        
        # Create conversation directory for this root_dir
        self.conversation_dir = self._get_conversation_dir()
        os.makedirs(self.conversation_dir, exist_ok=True)
        
        self.session_start_time = datetime.now()
        self.session_filename = f"session_{self.session_start_time.strftime('%Y%m%d_%H%M%S')}.toml.zip"
        self.session_path = os.path.join(self.conversation_dir, self.session_filename)

    def _get_conversation_dir(self):
        """Get the conversation directory for the current root_dir"""
        # Normalize the root_dir path to create a safe directory name
        root_path = Path(self.root_dir).resolve()
        # Create a hash or use the absolute path (we'll use a safe version of the path)
        # Replace path separators and other special characters
        safe_name = re.sub(r'[^\w\-_\. ]', '_', str(root_path))
        # Limit length to avoid issues with long paths
        if len(safe_name) > 100:
            # Use a hash for very long paths
            import hashlib
            safe_name = hashlib.md5(str(root_path).encode()).hexdigest()
        
        return os.path.join(config.CONVERSATIONS_DIR, safe_name)

    def save_session(self, conversation_history):
        """
        Save conversation history to a zipped TOML file with multi-line literal strings for readable content.
        """
        try:
            doc = tomlkit.document()
            
            metadata = tomlkit.table()
            metadata.add("session_start_time", self.session_start_time.isoformat())
            metadata.add("last_saved_time", datetime.now().isoformat())
            metadata.add("interaction_count", len([m for m in conversation_history if m["role"] == "user"]))
            metadata.add("root_dir", self.root_dir)
            doc.add("metadata", metadata)
            
            conv_array = tomlkit.aot()
            
            for msg in conversation_history:
                msg_table = tomlkit.table()
                msg_table.add("timestamp", msg["timestamp"])
                msg_table.add("role", msg["role"])
                
                content = msg["content"].replace('\\n', '\n')
                content_item = tomlkit.string(content, literal=True, multiline=True)
                
                msg_table.add("content", content_item)
                
                conv_array.append(msg_table)
            
            doc.add("conversation_history", conv_array)
            
            toml_str = tomlkit.dumps(doc)
            
            with zipfile.ZipFile(self.session_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
                zipf.writestr('session.toml', toml_str.encode('utf-8'))
                
            return self.session_path
            
        except Exception as e:
            print(f"⚠️  Error saving session: {e}")
            return None
        
    def load_session(self, zip_path):
        """
        Load session from a zipped TOML file.
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                with zipf.open('session.toml') as f:
                    toml_bytes = f.read()
                    session_data = tomlkit.loads(toml_bytes.decode('utf-8'))
                    
            return session_data
            
        except FileNotFoundError:
            print(f"⚠️  Session file not found: {zip_path}")
            return None
        except Exception as e:
            print(f"⚠️  Error loading session: {e}")
            return None

    def get_session_path(self):
        """Get the path to the current session file"""
        return self.session_path

    def list_available_sessions(self):
        """List all available session files for the current root_dir"""
        sessions = []
        if os.path.exists(self.conversation_dir):
            for file in os.listdir(self.conversation_dir):
                if file.endswith('.toml.zip'):
                    file_path = os.path.join(self.conversation_dir, file)
                    sessions.append(file_path)
        return sorted(sessions, reverse=True)  # Most recent first

    def get_interaction_count(self):
        """Get the number of logged interactions from current session"""
        session_data = self.load_session(self.session_path)
        if session_data and "metadata" in session_data:
            return session_data["metadata"].get("interaction_count", 0)
        return 0

