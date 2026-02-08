#!/usr/bin/env python3
"""Test draft navigation logic."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from input_handler import InputHandler

def simulate():
    ih = InputHandler()
    
    print("=== Simulation ===")
    print("1. Type 'hello'")
    # Simulate buffer with 'hello'
    buffer = "hello"
    
    print("2. Page Down (save draft, clear buffer)")
    # Call navigate_history_down logic manually
    if buffer.strip():
        ih.draft_stack.insert(0, buffer)
        buffer = ""
    print(f"   draft_stack: {ih.draft_stack}")
    print(f"   buffer: '{buffer}'")
    
    print("3. Type 'hi'")
    buffer = "hi"
    
    print("4. Page Up (should save 'hi' to draft_stack and show 'hi')")
    if buffer.strip():
        ih.draft_stack.insert(0, buffer)
        buffer = ""
    if ih._get_combined_count() > 0:
        ih.history_index = 0
        buffer = ih._get_combined_item(ih.history_index)
    print(f"   draft_stack: {ih.draft_stack}")
    print(f"   history_index: {ih.history_index}")
    print(f"   buffer: '{buffer}'")
    
    print("5. Page Up again (should show 'hello')")
    if ih.history_index < ih._get_combined_count() - 1:
        ih.history_index += 1
        buffer = ih._get_combined_item(ih.history_index)
    print(f"   history_index: {ih.history_index}")
    print(f"   buffer: '{buffer}'")
    
    print("6. Page Down (should show 'hi')")
    if ih.history_index > 0:
        ih.history_index -= 1
        buffer = ih._get_combined_item(ih.history_index)
    print(f"   history_index: {ih.history_index}")
    print(f"   buffer: '{buffer}'")
    
    print("7. Page Down again (should exit navigation, buffer empty)")
    if ih.history_index == 0:
        ih.history_index = -1
        buffer = ""
    print(f"   history_index: {ih.history_index}")
    print(f"   buffer: '{buffer}'")
    
    print("\n=== Test 2: Empty buffer, Page Up to navigate ===")
    ih.clear_history()
    ih.add_to_history("sent1")
    ih.add_to_history("sent2")
    print(f"History: {ih.history}")
    buffer = ""
    ih.history_index = -1
    
    print("Page Up (should show 'sent2' - most recent sent)")
    if ih._get_combined_count() > 0:
        ih.history_index = 0
        buffer = ih._get_combined_item(ih.history_index)
    print(f"   buffer: '{buffer}'")
    
    print("Page Up again (should show 'sent1')")
    if ih.history_index < ih._get_combined_count() - 1:
        ih.history_index += 1
        buffer = ih._get_combined_item(ih.history_index)
    print(f"   buffer: '{buffer}'")
    
    print("\nAll simulations completed.")

if __name__ == "__main__":
    simulate()