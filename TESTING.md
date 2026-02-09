# Testing and CI/CD Guide

## Overview

This document provides comprehensive testing guidelines and CI/CD setup instructions for the Thin Wrap LLM Terminal Chat application. The test suite is designed to protect key functionalities and ensure code quality before merging to the main branch.

## Key Functionalities Protected by Tests

### 1. Configuration Management (`test_config_validation.py`)
- **Purpose**: Validate config.json loading and validation
- **Key Tests**:
  - Config validation with proxy fields
  - Missing required fields detection
  - Invalid proxy type rejection
  - Backup defaults application
  - Config reloading on changes
- **Critical Protection**: Ensures application starts correctly with valid configuration

### 2. Proxy Suggestion Feature (`test_proxy_suggestion.py`)
- **Purpose**: Test proxy suggestion logic for models
- **Key Tests**:
  - Proxy suggestion logic (when to prompt)
  - Proxy field defaults to False
  - Integration with config loading
  - Proxy field validation (boolean only)
- **Critical Protection**: Ensures proxy prompting works correctly for models needing proxies

### 3. Session Metadata (`test_session_metadata.py`)
- **Purpose**: Test session logging with metadata previews
- **Key Tests**:
  - Session metadata includes preview field
  - Free chat mode metadata handling
  - `load_session_metadata` method functionality
  - Preview truncation and formatting
- **Critical Protection**: Ensures session reloading shows meaningful previews

### 4. Command Handler Proxy (`test_command_handler_proxy.py`)
- **Purpose**: Test proxy command handling
- **Key Tests**:
  - Proxy command argument parsing
  - Interactive proxy selection logic
  - Integration with model config
  - Error handling
  - Proxy history management
- **Critical Protection**: Ensures `/proxy` command works correctly

### 5. Input Handling (`test_draft_nav.py`, `test_edge_cases.py`)
- **Purpose**: Test draft navigation and input handling
- **Key Tests**:
  - Draft management
  - Navigation after modification
  - History limits
  - Edge cases
- **Critical Protection**: Ensures user input experience is smooth

### 6. File Context Management (`test_rootdir_file_clear.py`, `test_rootdir_freechat.py`)
- **Purpose**: Test file context and root directory handling
- **Key Tests**:
  - File clearing when switching roots
  - Free chat mode functionality
  - User scenario simulations
- **Critical Protection**: Ensures file context management works correctly

### 7. Free Chat Mode (`test_free_chat.py`)
- **Purpose**: Test free chat mode without file context
- **Key Tests**:
  - Session logger in free chat mode
  - Directory structure for free chat
- **Critical Protection**: Ensures free chat mode works independently

### 8. Proxy Command (`test_proxy_command.py`)
- **Purpose**: Test proxy command functionality
- **Key Tests**:
  - Proxy history loading/saving
  - Proxy command parsing
- **Critical Protection**: Ensures proxy configuration works

## Running Tests Locally

### Prerequisites
```bash
pip install -r requirements.txt
```

### Running All Tests
```bash
python -m pytest tests/ -v
```

### Running Specific Test Files
```bash
python -m pytest tests/test_config_validation.py -v
python -m pytest tests/test_proxy_suggestion.py -v
python -m pytest tests/test_session_metadata.py -v
python -m pytest tests/test_command_handler_proxy.py -v
```

### Running Tests with Coverage
```bash
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=html
```

## GitHub CI/CD Setup

### Workflow Configuration
The `.github/workflows/run-tests.yml` file defines the CI/CD pipeline that runs on:
- Push to `main`, `develop`, `feature/*`, `bugfix/*`, `hotfix/*` branches
- Pull requests targeting `main` branch

### Workflow Steps
1. **Checkout code**: Get the latest code
2. **Setup Python**: Multiple versions (3.11, 3.12, 3.13)
3. **Install dependencies**: From requirements.txt
4. **Run tests**: Execute all test suites
5. **Module tests**: Run tests by module for granular reporting

### Viewing Test Results
- Go to GitHub repository → Actions → Workflow runs
- Click on a specific run to see detailed test results
- Download artifacts if configured

## Branch Protection Rules

To ensure all tests pass before merging to main, configure the following branch protection rules:

### Required Status Checks
1. **Test Suite**: `test / test (3.11)`
2. **Test Suite**: `test / test (3.12)` 
3. **Test Suite**: `test / test (3.13)`

### Protection Settings
- **Require status checks to pass before merging**: ✅ Enabled
- **Require branches to be up to date before merging**: ✅ Enabled
- **Require conversation resolution before merging**: ✅ Enabled
- **Require approvals**: Optional (configure as needed)
- **Restrict who can push to matching branches**: Configure as needed

### Configuration Steps
1. Go to repository Settings → Branches
2. Click "Add branch protection rule"
3. Branch name pattern: `main`
4. Enable "Require status checks to pass before merging"
5. Select all test status checks from the list
6. Enable other protection options as desired
7. Click "Save changes"

## Adding New Tests

### Test Structure Guidelines
1. **File naming**: `test_<feature>_<subfeature>.py`
2. **Function naming**: `test_<scenario>_<expected_behavior>()`
3. **Imports**: Always include sys.path modification for local imports
4. **Setup/Teardown**: Use temp directories and cleanup in finally blocks
5. **Assertions**: Use descriptive assert messages
6. **Mocks**: Use unittest.mock for external dependencies

### Example Test Template
```python
#!/usr/bin/env python3
"""Test <feature> functionality."""
import sys
import os
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import modules to test
import config
from module import Class

def test_feature_scenario():
    """Test specific scenario with expected behavior."""
    # Setup
    original_value = None
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Test logic
        result = function_under_test()
        
        # Assertions
        assert result == expected, f"Expected {expected}, got {result}"
        
        print("✓ Test passed")
    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
```

## Test Coverage Goals

### Current Coverage (Approximate)
- Configuration validation: ✅ Comprehensive
- Proxy suggestion: ✅ Comprehensive  
- Session metadata: ✅ Comprehensive
- Command handler: ✅ Comprehensive
- Input handling: ✅ Good
- File context: ✅ Good
- Free chat: ✅ Good
- Proxy command: ✅ Good (except interactive test)

### Areas for Future Test Expansion
1. **LLM Client Integration**: Mock API calls for LLM interactions
2. **File Processor**: Test file editing and backup functionality
3. **UI Components**: Test colorization and banner display
4. **Menu System**: Test file browser menu interactions
5. **Cross-platform Compatibility**: Test platform-specific behaviors

## Troubleshooting Failed Tests

### Common Issues
1. **Missing dependencies**: Run `pip install -r requirements.txt`
2. **Path issues**: Ensure tests are run from project root
3. **Environment variables**: Some tests require specific env vars
4. **Temp directory permissions**: Tests create temp dirs in `/tmp`

### Test-Specific Issues
- `test_proxy_history`: May fail due to interactive prompt requirements
  - This test requires mocking prompt_toolkit interactions
  - Considered acceptable failure for CI/CD

### Debugging Tips
```bash
# Run with detailed output
python -m pytest tests/test_file.py -v --tb=long

# Run with pdb on failure
python -m pytest tests/test_file.py --pdb

# Run single test function
python -m pytest tests/test_file.py::test_function -v
```

## Continuous Improvement

### Test Maintenance
- Review test failures after each PR
- Update tests when features change
- Add tests for bug fixes
- Remove obsolete tests

### Coverage Monitoring
Consider adding coverage reporting to CI/CD:
```yaml
- name: Test coverage
  run: |
    pip install pytest-cov
    python -m pytest tests/ --cov=. --cov-report=xml
```

### Performance Considerations
- Tests should run quickly (< 1 minute)
- Use mocks for slow operations
- Clean up temp resources promptly
- Avoid network calls in unit tests

## Contributors Guide

### For New Contributors
1. Run existing tests before making changes
2. Add tests for new features
3. Update tests for modified features
4. Ensure all tests pass before submitting PR

### For Maintainers
1. Review test coverage in PRs
2. Ensure new tests follow guidelines
3. Monitor CI/CD pipeline health
4. Update this document as needed