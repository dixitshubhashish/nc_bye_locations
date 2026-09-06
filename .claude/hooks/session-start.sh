#!/bin/bash
set -euo pipefail

# SessionStart hook: Install dependencies and validate environment
# This runs once when a Claude Code session starts, ensuring all dependencies
# are available before the user tries to run code or tests.

# Only run this hook in Claude Code on the web (remote environment)
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo "Setting up environment for nc_bye_locations project..."

# Install Python dependencies
# In containerized environments, use --ignore-installed to bypass system package conflicts
echo "Installing Python dependencies from requirements.txt..."
python -m pip install -q --ignore-installed -r requirements.txt

# Set PYTHONPATH for module imports
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export PYTHONPATH="."' >> "$CLAUDE_ENV_FILE"
fi

# Validate: run a quick import test
echo "Validating Python environment..."
python -c "import google.cloud.bigquery; import pandas; print('✓ Dependencies validated')"

# Validate: run one small unit test to ensure pytest works
echo "Validating test framework..."
python -m pytest unit_tests/test_demo_data_validation.py -q || {
  echo "⚠ Test validation failed, but environment may still be usable"
}

echo "✓ Environment setup complete"
