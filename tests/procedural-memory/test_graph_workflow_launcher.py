import os
from pathlib import Path
import subprocess

PLUGIN=Path(__file__).resolve().parents[2]/"procedural-memory"
LAUNCHER=PLUGIN/"skills/graph-workflow-builder/scripts/graph-workflow.sh"

def invoke(tmp_path, supported):
    binary=tmp_path/"bin"
    binary.mkdir()
    runtime=binary/"rhize-skill"
    runtime.write_text('#!/bin/sh\nif [ "$1 $2 $3" = "graph workflow --help" ]; then exit '+str(0 if supported else 2)+'; fi\nprintf "%s\\n" "$@"\n')
    interpreter=binary/"python3"
    interpreter.write_text('#!/bin/sh\necho 0.1.0\n')
    runtime.chmod(0o755)
    interpreter.chmod(0o755)
    return subprocess.run(["bash",str(LAUNCHER),"graph","validate","candidate path"],
                          env={**os.environ,"RHIZE_SKILL_BIN":str(runtime),"HOME":str(tmp_path)},
                          text=True,capture_output=True,timeout=10,cwd=tmp_path)

def test_workflow_launcher_preserves_arguments(tmp_path):
    result=invoke(tmp_path,True)
    assert result.returncode==0,result.stderr
    assert result.stdout.splitlines()==["graph","validate","candidate path"]

def test_workflow_launcher_refuses_old_runtime_before_action(tmp_path):
    result=invoke(tmp_path,False)
    assert result.returncode==78
    assert not result.stdout
    assert "lacks the native workflow contract" in result.stderr
