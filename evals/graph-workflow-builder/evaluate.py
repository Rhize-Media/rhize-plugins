#!/usr/bin/env python3
"""Independent fixture outcomes; never calls a model or changes the task outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SOFTWARE_ORACLE = """import importlib.util,sys
s=importlib.util.spec_from_file_location('candidate',sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for value,expected in [(None,None),(' A@EXAMPLE.COM ','a@example.com'),('',None),('  ',None),('x@y.com','x@y.com')]:
    assert m.normalize_email(value)==expected
"""

def evaluate(case, root):
    root=Path(root).resolve()
    def read(name):
        path=root/name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing or symlinked output: "+name)
        return json.loads(path.read_text())
    if case=="research":
        packet=read("report.json")
        if packet!={"claims":[
            {"question":"alpha workers","answer":2,"sources":["alpha"]},
            {"question":"beta workers","answer":3,"sources":["beta"]},
            {"question":"beta dynamic","answer":True,"sources":["beta"]}]} or packet["claims"][2]["answer"] is not True:
            raise ValueError("claim coverage, answer, or source mismatch")
        article=root/"report.md"
        if article.is_symlink() or not article.is_file() or len(article.read_text().strip())<80:
            raise ValueError("missing substantive article; subjective quality still needs review")
    elif case=="software":
        source=root/"normalizer.py"
        if source.is_symlink() or not source.is_file():
            raise ValueError("missing owned source")
        result=subprocess.run([sys.executable,"-I","-c",SOFTWARE_ORACLE,str(source)],
                              capture_output=True,timeout=10)
        if result.returncode:
            raise ValueError("normalizer behavior failed")
    elif case=="reconciliation":
        if read("reconciliation.json")!={
            "dispositions":{"a":"settled","b":"hold","c":"hold","d":"unavailable"},
            "events":[{"key":"settled:a:receipt-a","id":"a","from":"pending","to":"settled"}]}:
            raise ValueError("incorrect attribution, missing hold, or duplicate transition")
    else:
        raise ValueError("unknown case")
    return {"case":case,"objective_pass":True,"subjective_review":"pending" if case=="research" else "not_required"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",choices=["research","software","reconciliation"],required=True)
    parser.add_argument("--root",type=Path,required=True)
    args=parser.parse_args()
    try:
        result=evaluate(args.case,args.root)
    except (ValueError,OSError,subprocess.SubprocessError):
        result={"case":args.case,"objective_pass":False,"reason":"independent_oracle_failed"}
    result["oracle_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(json.dumps(result,sort_keys=True))
    return 0 if result["objective_pass"] else 1

if __name__=="__main__":
    raise SystemExit(main())
