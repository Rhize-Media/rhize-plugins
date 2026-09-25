---
name: reconcile-outreach-delivery
description: Explain the current email delivery boundary for Rhize Outreach and identify when a reviewed draft is ready for a separately configured sender.
metadata:
  rhize:
    topics: [outreach, data-consistency]
    stacks: []
---

# Outreach Delivery Status

The current runtime has no GHL or Gmail adapter and cannot create or reconcile provider drafts. A reviewed email remains a local draft artifact. Do not claim provider delivery or update suppression based on a local draft.

When a delivery adapter is added, require an immutable intent with recipient and payload digest, inspect provider state after ambiguous failures, and never retry an unknown outcome automatically. Sending must remain an explicit user action on the exact reviewed message.
