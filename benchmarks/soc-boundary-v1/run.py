#!/usr/bin/env python3
"""Four registered boundary-validation diagnostics; reuse the existing launcher."""
import importlib.util
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parents[1]/'soc-timing-v1'
sys.path.insert(0,str(BASE))
spec=importlib.util.spec_from_file_location('boundary_shared_launcher',BASE/'run.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)

if __name__=='__main__':
    sys.exit(shared.main(tasks=shared.route.BOUNDARY_TASKS))
