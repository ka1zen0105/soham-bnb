import sys
import os

# Ensure repository root is on sys.path so 'backend' package imports work
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.main import app

# Provide Mangum Lambda handler for AWS Lambda / Vercel Serverless environment
try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except ImportError:
    handler = app
