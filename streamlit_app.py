"""Streamlit Community Cloud entry point.

Run the dashboard script as a script on every Streamlit rerun. Importing
main caches the module in sys.modules, so a star import can leave subsequent
Streamlit reruns with no UI commands to execute.
"""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("main.py")))
