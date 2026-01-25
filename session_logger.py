"""Session logging functionality with JSON format and automatic zipped saving"""
import os
import json
import zipfile
from datetime import datetime
from pathlib import Path
import config

class SessionLogger:
    def __init__(self, script_directory):
        self.script_directory = script_directory
        self.session_start_time = datetime.now()
        self.session_filename = f"{config.LOG_PREFIX}{self.session_start_time.strftime('%Y%m%d_%H%M%S')}.json.zip"
        self.session_path = os.path.join(self.script_directory, self.session_filename)

    def save_session(self, conversation_history):
        """
        Save conversation history to a zipped JSON file.
        Overwrites previous session file.
        
        Args:
            conversation_history: List of conversation messages with timestamps
        """
        try:
            # Create session data structure
            session_data = {
                "metadata": {
                    "session_start_time": self.session_start_time.isoformat(),
                    "last_saved_time": datetime.now().isoformat(),
                    "interaction_count": len([m for m in conversation_history if m["role"] == "user"])
                },
                "conversation_history": conversation_history
            }
            
            # Convert to JSON with proper formatting for human readability
            # Use indent=2 for pretty printing and ensure_ascii=False to preserve Unicode
            json_str = json.dumps(session_data, indent=2, ensure_ascii=False)
            
            # Create zip file with JSON content
            with zipfile.ZipFile(self.session_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
                # Add JSON file to zip with proper encoding
                zipf.writestr('session.json', json_str.encode('utf-8'))
                
            return self.session_path
            
        except Exception as e:
            print(f"⚠️  Error saving session: {e}")
            return None

    def load_session(self, zip_path=None):
        """
        Load session from a zipped JSON file.
        
        Args:
            zip_path: Path to the zipped session file. If None, loads the current session.
            
        Returns:
            Dictionary with session data or None if loading fails
        """
        if zip_path is None:
            zip_path = self.session_path
            
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                # Read the JSON file from the zip
                with zipf.open('session.json') as f:
                    json_bytes = f.read()
                    session_data = json.loads(json_bytes.decode('utf-8'))
                    
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
        """List all available session files in the script directory"""
        sessions = []
        for file in os.listdir(self.script_directory):
            if file.startswith(config.LOG_PREFIX) and file.endswith('.json.zip'):
                sessions.append(os.path.join(self.script_directory, file))
        return sorted(sessions, reverse=True)  # Most recent first

    def get_interaction_count(self):
        """Get the number of logged interactions from current session"""
        session_data = self.load_session()
        if session_data and "metadata" in session_data:
            return session_data["metadata"].get("interaction_count", 0)
        return 0
