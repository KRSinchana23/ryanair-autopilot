#!/bin/bash
# One-command startup script
echo "🚀 Starting Ryanair Corporate Finance Autopilot..."
echo ""

# Check for .env
if [ ! -f .env ]; then
  echo "⚠️  No .env file found. Copying from .env.example..."
  cp .env.example .env
  echo "👉 Please edit .env and add your ANTHROPIC_API_KEY, then run this script again."
  exit 1
fi

# Check for venv
if [ ! -d venv ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv venv
fi

# Activate and install
source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "✅ Ready! Starting server at http://localhost:8000"
echo "   Open your browser to http://localhost:8000"
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
