---
name: ghl-csv-import
description: Convert a CSV, spreadsheet or contact list into GoHighLevel (GHL, HighLevel, LeadConnector) contact-import format and guide a safe import. Use when asked to import, upload or bulk-add a CSV or list into GoHighLevel, HighLevel, LeadConnector or GHL; turn a list into a GHL Smart List; map columns to GHL fields, tags or custom fields; or clean a CSV for GHL import. Not for single-contact edits or building GHL workflows.
metadata:
  rhize:
    topics: [automation, workflow-patterns]
    stacks: [python]
---

# GHL CSV import

Turn any contact CSV into a file the GoHighLevel import wizard accepts, then load it without
surprising the account. Facts, sources and what is only observed live in
[references/ghl-import-facts.md](references/ghl-import-facts.md); read it before step 3 and
whenever a limit or label is in doubt. Resolve the plugin root through the current host
(Claude Code: `CLAUDE_PLUGIN_ROOT`; Codex: the root holding `.codex-plugin/plugin.json`) and set a
process-local `RHIZE_OPS_ROOT`.

## 0. Consent gate (hard stop, before converting anything)

Ask where the list came from and whether these people consented: did they agree to hear from
us, were they contacted within the last year, is the list from a third party (purchased list,
directory, MLS or association roster, scrape)? Tell the user up front that the wizard's final
Verify step will not enable "Start import" until a box is ticked reading (observed): "I confirm all
contacts in this import have consented to hear from us. I've previously contacted them within the
last past year, and this list is not from a third party".

- The human reads that statement and decides. Never tick the box for the user and never instruct an
  agent or browser automation to tick it.
- If the user cannot truthfully make the statement, stop. Present the alternatives: do not import;
  import only people who replied or opted in; ask HighLevel support for the correct path. Do not
  quietly switch to the API to get around the screen.
- If the user explicitly chooses the API route anyway, state the consequences first (Contact Created
  workflows fire, duplicates are possible when the location allows them, upsert replaces tags) and
  proceed only on their explicit choice. Record the choice in the report.

## 1. Choose the route

- **Default: UI import wizard.** Contacts, then Import, then upload, mode "Create and update
  contacts", fields left on "Skip empty values". Documented: CSV imports match on email, then
  phone, and do not create duplicates. Whether existing tags survive is not documented; the canary
  proves it. Check the Import history page first for earlier imports of the same list. Closing the
  wizard before "Start import" creates nothing (observed).
- **API upsert only** when the user asks for it after the consent gate, or the file is too large or
  repeated. Upsert replaces a contact's whole tag list; check tags first (reference file, "API").
- Never print, store or ask the user to paste a token. API checks are optional, read-only, and read
  `GHL_API_KEY`, `GHL_LOCATION_ID`, `GHL_API_BASE_URL` from the environment or a file path the user
  names. Send `Version: 2021-07-28` and a `User-Agent` header.

## 2. Convert

Agree the mapping with the user first: which column is the email, phone and name, which columns
become fields, custom fields, tags (per row, constant, or value-derived) and which columns are
dropped. Output headers are the exact GHL labels; the wizard auto-mapped every header that matched
a field name exactly (observed), so create each custom field first (Settings > Custom Fields, or
the API; TEXT and NUMERICAL worked) and use its exact label. Write the mapping as a small JSON file
(keys are listed in the script docstring), then:

```bash
python3 "${RHIZE_OPS_ROOT}/scripts/ghl_csv_convert.py" \
  --input /path/source.csv --output /path/ghl-import.csv --mapping /path/mapping.json
```

It writes the CSV and `<output>.report.json`. Exit 1 means rows had no first name, email or phone:
show them and fix the mapping or source; do not import around them. Read the report and surface
every warning (name splits, dropped emails and phones, rejected tags, merged duplicates) rather than
summarising them away. Never add DND or consent columns unless the user maps one: a DND column
applies to all channels. A cell starting with `=`, `+`, `-` or `@` gets a leading `'` and a warning
(spreadsheet formula injection); ask the user to fix the source value rather than import it.

## 3. Pre-flight (read-only)

Ask before running any API check. Report: how many of the file's emails already exist and with
which tags; whether the location allows duplicate contacts; which custom fields in the report exist
(label and type must match, or the user creates them in Settings first); which published
workflows have names suggesting a contact-created or tag trigger; whether any daily or weekly
report counts new contacts. Choose tag names that no existing workflow listens to. Confirm the
dropdown labels listed in the report's `confirm_labels_in_wizard` when mapping in the wizard.

## 4. Canary

Import a 2-row file first: one new contact, one existing. Confirm the fields and tags landed,
existing tags survived, no workflow enrolled the contact, and no duplicate appeared. Stop on any
miss.

## 5. Full import, then Smart List

Run the full file with the same settings and tag the whole import with one batch tag (also the undo
handle). Check the import's bulk-action stats and error log. Make the Smart List last, as a saved
filter on that tag; the public API has no Smart List endpoint, so this is a UI step. The Verify
step's unticked "Create a Smartlist for new contacts created by the import" covers NEW contacts
only (observed), so existing contacts that were updated would be missing; the tag filter is the
complete list. Leave "Add imported contacts to a workflow" unticked unless the user asks.

## 6. Report

State: rows in, contacts out, duplicates merged, rows dropped and why, warnings, tags used, custom
fields required, canary result, final import counts, the Smart List name, and anything not verified.
Label each GHL fact as documented, observed in one account, or not confirmed.
