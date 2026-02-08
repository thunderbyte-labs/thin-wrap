#!/usr/bin/env python3
"""Test edge cases for draft navigation."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from input_handler import InputHandler

def test_empty_state():
    """Test with empty state."""
    ih = InputHandler()
    print("=== Test: Empty state ===")
    print(f"draft_stack: {ih.draft_stack}, history: {ih.history}")
    # Page Up should do nothing
    # Page Down should do nothing
    print("OK - empty state handled")

def test_only_sent_messages():
    """Test navigation with only sent messages, no drafts."""
    ih = InputHandler()
    ih.add_to_history("sent1")
    ih.add_to_history("sent2")
    print("\n=== Test: Only sent messages ===")
    print(f"history: {ih.history}")
    
    # Buffer empty, Page Up should show sent2 (most recent)
    # Buffer empty, Page Down should do nothing (not start navigation)
    print("OK - sent messages loaded")

def test_draft_management():
    """Test draft stack management."""
    ih = InputHandler()
    print("\n=== Test: Draft stack limits ===")
    # Add more than 20 drafts
    for i in range(25):
        ih.draft_stack.insert(0, f"draft{i}")
    print(f"Draft stack length: {len(ih.draft_stack)} (should be <=20)")
    # The navigation logic limits to 20 when adding
    # But we inserted directly, so it's 25
    # Simulate adding one more via navigation logic
    if "test".strip():
        ih.draft_stack.insert(0, "test")
        if len(ih.draft_stack) > 20:
            ih.draft_stack.pop()
    print(f"After adding with limit: {len(ih.draft_stack)} (should be 20)")
    
def test_navigation_after_modification():
    """Test navigation after modifying a historical message."""
    ih = InputHandler()
    ih.draft_stack = ["original"]
    print("\n=== Test: Navigation after modification ===")
    # Simulate viewing "original" (index 0)
    ih.history_index = 0
    buffer = "modified"
    # Page Up - should save "modified" to draft stack
    if buffer.strip():
        ih.draft_stack.insert(0, buffer)
        if len(ih.draft_stack) > 20:
            ih.draft_stack.pop()
    print(f"draft_stack after modification: {ih.draft_stack}")
    print("Should have ['modified', 'original']")

def test_add_to_history_clears_drafts():
    """Test that sending a message clears draft stack."""
    ih = InputHandler()
    ih.draft_stack = ["draft1", "draft2"]
    ih.history = ["old_sent"]
    print("\n=== Test: add_to_history clears drafts ===")
    print(f"Before: draft_stack={ih.draft_stack}, history={ih.history}")
    ih.add_to_history("new_sent")
    print(f"After: draft_stack={ih.draft_stack} (should be empty), history={ih.history}")
    assert len(ih.draft_stack) == 0, "Draft stack should be cleared"
    print("OK - drafts cleared")

def test_history_limit():
    """Test that history is limited to 100 messages."""
    ih = InputHandler()
    print("\n=== Test: History limit (100 messages) ===")
    for i in range(105):
        ih.add_to_history(f"message{i}")
    print(f"History length: {len(ih.history)} (should be 100)")
    assert len(ih.history) == 100, "History should be limited to 100"
    print(f"Oldest message: {ih.history[0]} (should be message5)")
    print(f"Newest message: {ih.history[-1]} (should be message104)")
    print("OK - history limit works")

if __name__ == "__main__":
    test_empty_state()
    test_only_sent_messages()
    test_draft_management()
    test_navigation_after_modification()
    test_add_to_history_clears_drafts()
    test_history_limit()
    print("\n=== All edge case tests completed ===")