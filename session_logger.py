
"""Session logging functionality"""
import os
from datetime import datetime
import config

class SessionLogger:
    def __init__(self, script_directory):
        self.session_log = []
        self.session_start_time = datetime.now()
        self.script_directory = script_directory

    def log_interaction(self, user_input, assistant_response, original_user_input=None):
        """Log user input and assistant response to session log"""
        timestamp = datetime.now()
        logged_user_input = original_user_input if original_user_input else user_input
        self.session_log.append({
            'timestamp': timestamp,
            'user_input': logged_user_input,
            'assistant_response': assistant_response
        })

    def save_session_log(self):
        """Save the complete session log to a file in the script directory"""
        if not self.session_log:
            return None
            
        session_timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        log_filename = f"{config.LOG_PREFIX}{session_timestamp}.txt"
        log_path = os.path.join(self.script_directory, log_filename)
        
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("CHAT SESSION LOG\n")
                f.write("=" * 80 + "\n")
                f.write(f"Session started: {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total interactions: {len(self.session_log)}\n")
                f.write("=" * 80 + "\n\n")
                
                for i, interaction in enumerate(self.session_log, 1):
                    timestamp_str = interaction['timestamp'].strftime('%H:%M:%S')
                    f.write(f"[{i:03d}] {timestamp_str}\n")
                    f.write("-" * 50 + "\n")
                    f.write("USER:\n")
                    f.write(interaction['user_input'] + "\n\n")
                    f.write("LLM:\n")
                    f.write(interaction['assistant_response'] + "\n")
                    f.write("\n" + "=" * 50 + "\n\n")
            
            return log_path
        except Exception as e:
            print(f"⚠️  Error saving session log: {e}")
            return None

    def get_interaction_count(self):
        """Get the number of logged interactions"""
        return len(self.session_log)
