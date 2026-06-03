#!/bin/bash
# Reservoir Release Optimizer - Launch Script (Mac / Linux)
# Run with: bash run.sh

echo "Starting Reservoir Release Optimizer..."

if [ -f "myenv/bin/activate" ]; then
    source myenv/bin/activate
else
    echo "Warning: Virtual environment not found. Run 'bash setup.sh' first."
    echo "         Attempting to use system Python..."
fi

streamlit run app.py
