#!/bin/bash
# Reservoir Release Optimizer - First-Time Setup (Mac / Linux)
# Run once: bash setup.sh
set -e

echo "============================================================"
echo " Reservoir Release Optimizer - First-Time Setup"
echo "============================================================"
echo

# Require Python 3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "       Install Python 3.8+ from https://www.python.org/downloads/"
    echo "       On Mac you can also run: brew install python"
    exit 1
fi

echo "Python version: $(python3 --version)"
echo

echo "Creating virtual environment (myenv/)..."
python3 -m venv myenv

echo "Activating virtual environment..."
source myenv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip -q

echo "Installing dependencies..."
pip install -r requirements.txt

echo
echo "============================================================"
echo " Setup complete!"
echo
echo " To run the app:"
echo "   bash run.sh"
echo
echo " Or manually:"
echo "   source myenv/bin/activate"
echo "   streamlit run app.py"
echo "============================================================"
