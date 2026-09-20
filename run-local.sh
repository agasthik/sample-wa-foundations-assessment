#!/bin/bash
# Well-Architected Foundations Assessment — Local / CloudShell Quick Start
#
# Usage:
#   git clone <repo-url> && cd sample-wa-foundations-assessment
#   ./run-local.sh

set -e

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Running Well-Architected Foundations Assessment..."
python -m src.main --output .

echo ""
echo "Reports saved locally. Download from CloudShell file browser."
