# Entrypoint wrapper for Vercel deployment
import sys
import os

# Ensure the backend directory is in the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app
