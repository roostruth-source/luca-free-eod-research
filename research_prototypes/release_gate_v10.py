"""LUCA release gate: unit tests are not trading validation. NO_ORDERS."""
import json, subprocess, sys, hashlib
from pathlib import Path
BLOCKERS = [
 "MARKET_UNIVERSE_NOT_VERIFIED",
 "SEC_CONTRACT_TERMS_NOT_VERIFIED",
 "POINT_IN_TIME_FLOAT_NOT_VERIFIED",
 "CORPORATE_ACTIONS_NOT_VERIFIED",
 "DELISTED_SYMBOL_COVERAGE_NOT_VERIFIED",
 "OUT_OF_SAMPLE_PERFORMANCE_NOT_VERIFIED",
 "EXECUTION_COSTS_NOT_VERIFIED",
]
def check(root, output):
 root=Path(root)
 run=subprocess.run([sys.executable,"-m","unittest","discover","-q"],cwd=root,capture_output=True,text=True,timeout=120)
 report={"status":"NOT_VALIDATED","orders_enabled":False,"production_approved":False,
 "tests_passed":run.returncode==0,"test_exit_code":run.returncode,
 "release_blockers":BLOCKERS,"test_output":(run.stdout+"\n"+run.stderr)[-5000:]}
 Path(output).write_text(json.dumps(report,indent=2)+"\n")
 return report
if __name__=="__main__":
 import argparse
 p=argparse.ArgumentParser();p.add_argument("--root",default=".");p.add_argument("--output",default="release_status.json")
 a=p.parse_args();r=check(a.root,a.output)
 print("TESTS_OK" if r["tests_passed"] else "TESTS_FAILED","PRODUCTION_BLOCKED")
 sys.exit(0 if r["tests_passed"] else 1)
