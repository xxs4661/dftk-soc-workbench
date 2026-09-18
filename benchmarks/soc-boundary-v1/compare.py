#!/usr/bin/env python3
"""Compare this experiment's new same-map B0 or K4 pair; no numerical solve."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('boundary_shared_comparison',ROOT/'benchmarks/soc-timing-v1/compare.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('profile',choices=['B0','K4']);a=p.parse_args()
    try:
        result=shared.pair(ROOT,boundary_profile=a.profile)
        print(json.dumps(result,indent=2,allow_nan=False));sys.exit(0 if result['status']=='PASS' else 1)
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
