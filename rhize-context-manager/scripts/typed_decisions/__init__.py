"""Typed-decision layer: earned-authority decisions scored by the local Laya server.

Contract modules (coordinator-owned; lanes import, never edit):
  contract.py   - record/label/outcome/cohort/registry validators, occurrence key, arm, scoring rules
  instrument.py - laya-choice-v1 request builder and response decoder (mirrors hooks/lib/laya-instrument.js)

See docs/superpowers/specs/2026-10-11-laya-earned-authority-plan.md.
"""
