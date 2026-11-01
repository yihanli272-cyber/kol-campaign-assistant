"""Historical demo entry for regression tests; excluded from the current formal pool."""
from pathlib import Path
import runpy
import streamlit as st

st.query_params['workspace'] = 'legacy'
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
