#!/bin/bash
# WAFA — CloudShell Quick Start
#
# Usage:
#   git clone <repo-url> && cd wafa
#   ./run.sh

set -e

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Running WAFA Assessment..."
python -m src.main --output .

echo ""
echo "Reports saved locally. Download from CloudShell file browser."
