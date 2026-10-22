"""Opt-in local Docker boundary for test evidence; never falls back to host execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import uuid

POLICY = "docker-v1:local-image,no-network,readonly-snapshot,empty-env,nonroot,cap-drop,limits,no-logs"
ASSERTION_FAILURE = 10
PYTHON_RUNNER = r'''
import importlib.util, io, pathlib, sys, unittest
source, target = sys.argv[1:]
if source == 'python_unittest':
 class Result(unittest.TextTestResult):
  assertion_failures = 0
  def addFailure(self, test, error):
   trace = error[2]
   while trace:
    if trace.tb_frame.f_globals.get('__name__') == 'unittest.case' and trace.tb_frame.f_code.co_name == '_callTestMethod':
     self.assertion_failures += 1
     break
    trace = trace.tb_next
   super().addFailure(test, error)
 path = pathlib.Path(target)
 sys.path.insert(0,str(pathlib.Path.cwd()))
 spec = importlib.util.spec_from_file_location('_rhize_selected_test',path)
 module = importlib.util.module_from_spec(spec)
 sys.modules[spec.name] = module
 spec.loader.exec_module(module)
 suite = unittest.defaultTestLoader.loadTestsFromModule(module)
 result = unittest.TextTestRunner(stream=io.StringIO(),resultclass=Result).run(suite)
 if not result.testsRun or result.errors or result.skipped or result.expectedFailures or result.unexpectedSuccesses:
  sys.exit(20)
 sys.exit(10 if result.failures and result.assertion_failures == len(result.failures) else 20 if result.failures else 0)
else:
 import pytest
 sys.path.insert(0,str(pathlib.Path.cwd()))
 class Results:
  failures = 0
  unexpected = False
  count = 0
  def pytest_collection_finish(self, session): self.count = session.testscollected
  def pytest_collectreport(self, report):
   if report.failed: self.unexpected = True
  @pytest.hookimpl(hookwrapper=True)
  def pytest_runtest_makereport(self, item, call):
   report = (yield).get_result()
   if report.skipped or hasattr(report,'wasxfail'): self.unexpected = True
   if report.failed:
    if call.when == 'call' and call.excinfo and issubclass(call.excinfo.type,AssertionError): self.failures += 1
    else: self.unexpected = True
 result = Results()
 code = pytest.main(['-p','no:cacheprovider','--',target],plugins=[result])
 sys.exit(20 if result.unexpected or not result.count else 0 if code == 0 else 10 if code == 1 and result.failures else 20)
'''


class SandboxUnavailable(ValueError):
    pass


class CleanupFailed(ValueError):
    pass


def policy_hash():
    return hashlib.sha256(POLICY.encode() + Path(__file__).read_bytes() + Path(__file__).with_name("test_evidence.py").read_bytes()).hexdigest()


def private_root():
    root = Path.home() / ".rhize/test-evidence/receipts"
    for part in (root, *root.parents):
        if part.is_symlink():
            raise SandboxUnavailable("receipt path is symlinked")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SandboxUnavailable("receipt directory must be caller-owned and mode0700")
    return root


def packet_digest(packet):
    return hashlib.sha256(json.dumps({k: v for k, v in packet.items() if k != "sandbox"},
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record(packet, image):
    identity = uuid.uuid4().hex
    data = {"packetSha256": packet_digest(packet), "policySha256": policy_hash(), "imageId": image}
    raw = json.dumps(data, sort_keys=True).encode()
    path = private_root() / (identity + ".json")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as out:
        out.write(raw)
    return {"receiptId": identity, "receiptSha256": hashlib.sha256(raw).hexdigest(), **data}


def verify(packet):
    evidence = packet.get("sandbox")
    keys = {"receiptId", "receiptSha256", "packetSha256", "policySha256", "imageId"}
    if not isinstance(evidence, dict) or set(evidence) != keys or not re.fullmatch(r"[0-9a-f]{32}", str(evidence["receiptId"])):
        raise SandboxUnavailable("execution-backed verdicts require a trusted sandbox adapter receipt")
    path = private_root() / (evidence["receiptId"] + ".json")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096:
            raise SandboxUnavailable("sandbox receipt is not a private regular file")
        raw = stream.read(4097)
    expected = {"packetSha256": packet_digest(packet), "policySha256": policy_hash(), "imageId": evidence["imageId"]}
    if json.loads(raw) != expected or any(evidence[k] != v for k, v in expected.items()) or hashlib.sha256(raw).hexdigest() != evidence["receiptSha256"]:
        raise SandboxUnavailable("sandbox execution receipt binding mismatch")


class DockerSandbox:
    def __init__(self, image, config):
        if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise SandboxUnavailable("sandbox image must be an explicit local sha256 image ID")
        self.image = image
        self.binary = shutil.which("docker", path="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin")
        if not self.binary:
            raise SandboxUnavailable("Docker is unavailable")
        self.config = config
        config.mkdir(mode=0o700)
        self.env = {"HOME": str(config), "PATH": "/usr/local/bin:/usr/bin:/bin"}
        sockets = (Path("/var/run/docker.sock"), Path.home() / ".docker/run/docker.sock", Path.home() / ".colima/default/docker.sock")
        endpoint = os.environ.get("DOCKER_HOST") or next(("unix://" + str(p) for p in sockets if p.is_socket()), "")
        if not endpoint.startswith("unix://") or not Path(endpoint[7:]).is_absolute():
            raise SandboxUnavailable("only a local Unix Docker socket is supported")
        self.endpoint = endpoint
        metadata = json.loads(self.client("image", "inspect", image, "--format", "{{json .}}"))
        if metadata["Id"] != image or metadata["Config"].get("Volumes"):
            raise SandboxUnavailable("local image identity does not match")

    def client(self, *args, timeout=20):
        command = [self.binary, "--config", str(self.config)]
        if hasattr(self, "endpoint"):
            command += ["--host", self.endpoint]
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                process = subprocess.Popen(command + list(args), env=self.env, stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=err, start_new_session=True)
            except OSError as exc:
                raise SandboxUnavailable("Docker operation unavailable") from exc
            try:
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    if time.monotonic() >= deadline or os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > 1024 * 1024:
                        raise SandboxUnavailable("Docker operation exceeded deadline/output budget")
                    time.sleep(0.02)
                if process.returncode:
                    raise SandboxUnavailable("Docker operation failed")
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    raise CleanupFailed("Docker client group could not be terminated") from exc
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired as exc:
                    raise CleanupFailed("Docker client could not be reaped") from exc
            if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > 1024 * 1024:
                raise SandboxUnavailable("Docker output exceeded budget")
            out.seek(0)
            return out.read(1024 * 1024 + 1).decode().strip()

    def run(self, snapshot, command, timeout):
        name = "rhize-test-evidence-" + uuid.uuid4().hex
        # The candidate never sees a writable host mount, socket or host environment.
        args = ["run", "--detach", "--pull=never", "--name", name, "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534", "--init",
                "--pids-limit=64", "--memory=512m", "--cpus=1", "--log-driver=none", "--restart=no", "--no-healthcheck",
                "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=67108864,mode=1777", "--workdir=/workspace",
                "--mount", f"type=bind,source={snapshot},target=/workspace,readonly", "--entrypoint=/usr/bin/env",
                self.image, "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp", "LANG=C.UTF-8",
                "PYTHONDONTWRITEBYTECODE=1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", *command]
        try:
            self.client(*args)
            value = self.client("wait", name, timeout=timeout)
            if not re.fullmatch(r"\d{1,3}", value) or not 0 <= int(value) <= 255:
                raise SandboxUnavailable("invalid container exit status")
            return int(value)
        finally:
            try:
                try:
                    self.client("rm", "--force", "--volumes", name)
                except SandboxUnavailable:
                    pass  # A failed create may have left no container; prove absence below.
                if self.client("ps", "-aq", "--filter", "name=^/" + name + "$"):
                    raise CleanupFailed("container still exists after removal: " + name)
            except (SandboxUnavailable, CleanupFailed) as exc:
                raise CleanupFailed("container removal could not be verified: " + name) from exc


def snapshot(repo, destination, git):
    """Copy regular tracked files only; no Git metadata, credentials or host dependencies."""
    result = git(repo, "ls-tree", "-rz", "--full-tree", "HEAD")
    if result.returncode:
        raise SandboxUnavailable("cannot inventory tracked files")
    total = 0
    hashes = {}
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, blob = metadata.split()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise SandboxUnavailable("unsafe tracked path")
        if any(part.startswith(".env") or part in {".git", ".ssh", ".aws", ".config", "secrets", "credentials", "node_modules", ".venv"} for part in relative.parts):
            continue
        if mode not in {"100644", "100755"} or kind != "blob":
            raise SandboxUnavailable("snapshot contains a symlink, submodule or nonregular entry")
        source = repo / relative
        if any(p.is_symlink() for p in (source, *source.parents)) or not source.is_file():
            raise SandboxUnavailable("tracked snapshot has symlink or nonregular file")
        info = source.stat()
        total += info.st_size
        if info.st_size > 16 * 1024 * 1024 or total > 128 * 1024 * 1024 or len(hashes) >= 10000:
            raise SandboxUnavailable("snapshot exceeds budget")
        content = source.read_bytes()
        if len(content) != info.st_size or hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() != blob:
            raise SandboxUnavailable("source changed during snapshot")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o755)
        target.write_bytes(content)
        target.chmod(0o555 if mode == "100755" else 0o444)
        hashes[name] = {"sha256": hashlib.sha256(content).hexdigest(), "mode": stat.S_IMODE(target.stat().st_mode)}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def tree_digest(root):
    entries = {str(path.relative_to(root)): {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "mode": stat.S_IMODE(path.stat().st_mode)}
               for path in root.rglob("*") if path.is_file()}
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def execute(repo, spec, image, git):
    with tempfile.TemporaryDirectory(prefix="rhize-evidence-") as temporary:
        temporary = Path(temporary).resolve()
        sandbox = DockerSandbox(image, temporary / "docker-client")
        root = temporary / "source"
        root.mkdir()
        root.chmod(0o755)
        original = snapshot(repo, root, git)
        invocation = spec["test_invocation"]
        if invocation["source"] == "package_script":
            command = ["npm", "--ignore-scripts", "run", invocation["name"]]
        else:
            command = ["python3", "-I", "-B", "-c", PYTHON_RUNNER, invocation["source"], invocation["name"]]
        results = {"before": original, "after": original, "baseline": sandbox.run(root, command, spec["timeout_seconds"]), "mutant": None, "final": None}
        mutation = spec["mutation"]
        if results["baseline"] == 0:
            if mutation is not None:
                path = root / mutation["target_path"]
                content = path.read_bytes()
                search, replacement = mutation["search"].encode(), mutation["replace"].encode()
                mode = stat.S_IMODE(path.stat().st_mode)
                if content.count(search) != 1:
                    raise SandboxUnavailable("snapshot mutation does not match")
                pending_cleanup = None
                try:
                    path.chmod(0o600)
                    path.write_bytes(content.replace(search, replacement, 1))
                    path.chmod(mode)
                    results["after"] = tree_digest(root)
                    results["mutant"] = sandbox.run(root, command, spec["timeout_seconds"])
                except CleanupFailed as exc:
                    pending_cleanup = exc
                    raise
                finally:
                    try:
                        path.chmod(0o600)
                        path.write_bytes(content)
                        path.chmod(mode)
                    except OSError as exc:
                        if pending_cleanup is None:
                            raise SandboxUnavailable("temporary snapshot restoration failed") from exc
            if tree_digest(root) != original:
                raise SandboxUnavailable("restored snapshot does not match original bytes/modes")
            results["final"] = sandbox.run(root, command, spec["timeout_seconds"])
        return results
