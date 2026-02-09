#!/bin/bash
# Run all tests and show summary

echo "Running all tests..."
echo "===================="

# Use python from venv if available
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

# Run pytest
$PYTHON -m pytest tests/ -v --tb=short 2>&1 | tail -30

# Check exit code
if [ $? -eq 0 ]; then
    echo "✅ All tests passed!"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi