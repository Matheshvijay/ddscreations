# Paste this into the WSGI configuration file on PythonAnywhere (Web tab -> WSGI configuration file).
# Replace YOUR_PA_USERNAME with your PythonAnywhere username.
import os, sys
project = "/home/YOUR_PA_USERNAME/ddscreations/forum"
if project not in sys.path:
    sys.path.insert(0, project)
os.environ.setdefault("VV_DB_PATH", project + "/ddscreations.db")
os.environ.setdefault("VV_ADMIN", "mathesh")   # this username becomes the forum admin
from app import app as application  # noqa: E402
