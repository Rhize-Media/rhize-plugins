#!/usr/bin/python3
# Global protected-file + secret-leak gate (PreToolUse: Edit|Write|MultiEdit|NotebookEdit)
# 1) Path gates: CI workflows, env/secret files, billing/payment code
# 2) Content gates: NEXT_PUBLIC_* secret-named vars; Supabase service-role in client code
# Exit 2 = block (stderr is fed back to Claude as the reason).
import json, sys, re, os

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

ti = data.get("tool_input") or {}
path = ti.get("file_path") or ""

def block(msg):
    sys.stderr.write("BLOCKED: " + msg + " Escalate to the user instead of editing. "
        "If the user already explicitly approved this exact change, ask them to make it "
        "or to lift the gate.")
    sys.exit(2)

# --- Path gates ---
PATH_PATTERNS = [
    (r"\.github/workflows/", "CI workflow files require human review"),
    (r"(^|/)\.env($|\.)", "env/secret files must not be edited by agents"),
    (r"(^|/)(billing|payments?)(/|\.)", "billing/payment code requires explicit approval + security review"),
]
if path:
    for pat, reason in PATH_PATTERNS:
        if re.search(pat, path):
            block("protected file %s - %s." % (path, reason))

# --- Content gates (new text being written) ---
new_text = ti.get("content") or ti.get("new_string") or ""
if isinstance(ti.get("edits"), list):  # MultiEdit
    new_text += "\n".join((e or {}).get("new_string", "") for e in ti["edits"])

if new_text:
    # NEXT_PUBLIC_* vars with secret-looking names ship in the browser bundle.
    m = re.search(r"NEXT_PUBLIC_[A-Z0-9_]*(SECRET|TOKEN|PRIVATE|SERVICE_ROLE|API_KEY|PASSWORD)", new_text)
    if m:
        block("'%s' - NEXT_PUBLIC_* vars are inlined into the browser bundle; "
              "secret-named vars must be server-only (drop the NEXT_PUBLIC_ prefix)." % m.group(0))

    # Supabase service-role key must never appear in client code.
    if re.search(r"(SUPABASE_SERVICE_ROLE_KEY|service_role)", new_text):
        is_client = "'use client'" in new_text or '"use client"' in new_text
        if not is_client and path and os.path.isfile(path):
            try:
                head = open(path, "r", errors="ignore").read(600)
                is_client = "'use client'" in head or '"use client"' in head
            except Exception:
                pass
        if is_client:
            block("Supabase service-role reference in a 'use client' file (%s) - the key "
                  "bypasses RLS and would ship to every browser. Move it to a Server Action, "
                  "route handler, or server-only module; use the anon key client-side." % (path or "new file"))

sys.exit(0)
