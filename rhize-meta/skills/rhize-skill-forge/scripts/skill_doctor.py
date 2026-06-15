#!/usr/bin/env python3
"""skill_doctor.py — readiness check for the skills.sh discovery + SkillSpector safety tooling.

A diagnostic (always exits 0) that reports what's configured and how to fix gaps, so the forge /
project-launcher workflows can tell the user exactly what to set up. This IS the lightweight setup
step — no multi-screen wizard.

Checks:
  - SkillSpector CLI on PATH        (deep local safety scan)
  - VERCEL_OIDC_TOKEN               (skills.sh discovery + partner audits)
  - optional SkillSpector LLM stage (semantic analysis; static works without it)

Stdlib only.
"""
import os
import shutil


def status(ok: bool, label: str, detail: str) -> None:
    print(f"  [{'OK ' if ok else '-- '}] {label}: {detail}")


def token_present() -> bool:
    if os.environ.get("VERCEL_OIDC_TOKEN"):
        return True
    for p in (".env.local", ".env"):
        try:
            if "VERCEL_OIDC_TOKEN" in open(p, encoding="utf-8").read():
                return True
        except OSError:
            pass
    return False


def main() -> None:
    print("Skill tooling doctor (skills.sh discovery + SkillSpector safety):\n")

    ss = shutil.which("skillspector")
    status(bool(ss), "SkillSpector CLI",
           ss or "NOT installed — github.com/NVIDIA/skillspector (git clone + make install; Python 3.12+)")

    status(token_present(), "skills.sh auth (VERCEL_OIDC_TOKEN)",
           "present" if token_present()
           else "missing — enable OIDC Federation on your Vercel project, then `vercel link && vercel env pull`")

    prov = os.environ.get("SKILLSPECTOR_PROVIDER")
    keymap = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "nv_build": "NVIDIA_INFERENCE_KEY"}
    has_llm = bool(prov and os.environ.get(keymap.get(prov, "")))
    status(has_llm, "SkillSpector LLM stage (optional)",
           f"{prov} key set" if has_llm
           else "not set — static scan works without it (use --no-llm); set SKILLSPECTOR_PROVIDER + key for semantic analysis")

    print("\nMinimum to gate skills on safety: install SkillSpector (no API key needed for static scan).")
    print("skills.sh discovery + partner audits additionally require the Vercel OIDC token.")


if __name__ == "__main__":
    main()
