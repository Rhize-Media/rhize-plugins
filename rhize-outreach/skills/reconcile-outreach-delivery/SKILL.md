---
name: reconcile-outreach-delivery
description: Reconcile Gmail or GHL draft/delivery intent state after an ambiguous, failed or manually completed action without duplicate contact.
metadata:
  rhize:
    topics: [outreach, data-consistency, automation]
    stacks: []
---

# Reconcile Outreach Delivery

Read the immutable delivery intent and latest provider receipt. Compare recipient, sender, payload and attachment digests. Gmail draft creation and GHL preparation are reversible; a send outcome is not.

Never retry an unknown provider outcome automatically. Verify provider state, record the receipt or explicit manual-send confirmation, and update the shared suppression before another route becomes eligible. Do not send as part of reconciliation unless the user separately requests the exact reviewed message action.
