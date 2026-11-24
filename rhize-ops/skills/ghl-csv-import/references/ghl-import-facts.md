# GHL contact-import facts

Three classes, never mixed. **Documented** carries a source and was re-read on 2026-11-23 (the
pages were last modified between 2025-04 and 2026-11 and change; re-open before relying on a
number). **Observed** was seen in one live account on 2026-11-23 (read-only) or in earlier
sessions, and may not hold elsewhere. **Not confirmed** means no source says it.

Converter note (not a GHL fact): any output cell starting with `=`, `+`, `-` or `@` gets a leading
apostrophe, because a spreadsheet would run it as a formula. Exempt: a phone the script normalised to
E.164, and a negative number in a column the mapping declares numeric. Each case is a report warning;
fix the source value rather than import the apostrophe.

Sources (base `https://help.gohighlevel.com/support/solutions/articles/`):
A `155000005056` Getting Started - Import Existing Contacts ·
B `155000003905` Importing Contacts and Opportunities via CSV ·
C `155000005143` CSV File Format for Importing Objects ·
D `48001223155` Troubleshooting Bulk Imports Via CSV ·
E `48001181714` Contact Deduplication Preferences ·
F `155000002486` Workflow Trigger - Contact Created ·
G `155000002482` Contact Tag Workflow Trigger.
API spec: `https://github.com/GoHighLevel/highlevel-api-docs` (`apps/contacts.json`, listed as H).

## Documented

**Mapping and fields**
- Columns are mapped to fields by hand in the wizard; unmapped columns are skipped with "Don't
  import data in unmatched columns" (A; B words it "Don't import data for unmapped columns").
- Every row needs a first name, email or phone (C "Mandatory Fields"; B "Name, Email, or Phone").
- Standard import fields listed in A: Contact ID, Name, First Name, Last Name, Date of Birth,
  Contact Owner, Contact Source, Contact Type, Business Name, Phone, Email, Address, State, City,
  Postal Code, Country, DND, Time Zone, Website, Additional Email, Additional Phones, Notes.
- C's sample file calls the company column "Company"; A says "Business Name". The articles
  disagree: confirm the dropdown label in the wizard.
- Custom fields must already exist with the same label and data type (C tip). A shows creating one
  in Settings > Custom Fields; creating one inside the wizard is not clearly documented (A says
  "create a new custom field" at the mapping step without detail).
- Country values are validated against a list and are case-sensitive: "United States" works, "USA"
  errors (C). Time zones are case-sensitive and must match the list (C).
- Notes: one note per contact, 5,000 characters; use a large-text custom field otherwise (B, D).

**Tags**
- Tags can be several in one cell, separated by commas, semicolons or periods (C, field table).
  Hence the converter rejects tag text containing `;` or `.`.
- The review step can add a new tag to every imported contact and create a Smart List (B). G says
  tags can come from a Tags column or the review step.
- No documented "undo" for an import; D suggests tagging the import so it can be filtered and
  deleted.

**Dedupe and update**
- Existing contacts are found by email, then phone (B default; E "Find existing contacts based on").
- Modes: "Update Only" and "Create & Update" (B). "Don't update Empty Values" keeps a field when
  the file cell is empty (B words it for the opportunity field; wording for contacts is not
  confirmed).
- CSV imports do not create duplicate contacts regardless of "Allow Duplicate Contact" (E). E also
  says once that imports "always respect this setting", which contradicts itself; treat E's
  FAQ ("duplicates cannot be created during CSV imports") as the intent and prove it on the canary.
- Two rows with the same email in one file are listed as an error scenario (B): merge them first,
  which the converter does.

**Size, phone, date**
- File size limits conflict: 50 MB (A), 30 MB (B prerequisites, C), 20 MB or 10,000 rows (D, B's
  own FAQ also says 50 MB). Use the strictest, 20 MB or 10,000 rows, or split the file.
- Phones: E.164 recommended; `123-456-7890` and `(123) 456-7890` accepted for US numbers (C).
  Numbers outside the sub-account's country need the country code (D, error 1007).
- Dates: `MM/DD/YYYY`, `YYYY/MM/DD`, `MM-DD-YYYY`, `YYYY-MM-DD` (C). D only says "format dates
  properly".
- A DND column applies DND to all channels (SMS, email, calls, voicemail); per-channel DND needs a
  workflow and tags (B, D). Hence the converter never emits one unless asked.
- Only Admin users can import; one sheet; header row required (B).

**Workflows**
- "Contact Created" fires for contacts added manually, by form, by API or by integration; bulk
  imports do not trigger it (F FAQ; F's intro says "regardless of how", which contradicts its own
  FAQ).
- Tags added by CSV import (Tags column or review step) can activate a published "Contact Tag"
  workflow when its filters match (G). New, unused tag names are therefore safer; check existing
  tags against published workflows.

**API (v2, `https://services.leadconnectorhq.com`)**
- `POST /contacts/upsert`: the `tags` field "will overwrite all current tags associated with the
  contact"; use the Add Tag or Remove Tag endpoints to change tags (H). It follows the location's
  "Allow Duplicate Contact" configuration (H).
- The public contacts spec has no Smart List path (H, checked 2026-11-23). No other public spec in
  that repo was searched for Smart Lists while writing this file, so the "no endpoint" claim rests
  on `contacts.json` here plus an earlier check of the other specs (observed, not re-run).

## Observed in one account (2026-11-23 and earlier sessions)

- A 401 on contacts calls usually meant the `Version: 2021-07-28` header was missing.
- A 422 on contacts usually meant `customField` was sent instead of `customFields`, an array that
  must be omitted when empty.
- Requests with no `User-Agent` get a Cloudflare 403 (error 1010); it is not an auth failure.
- A plain `POST /contacts/` silently created a second contact for an existing email when the
  location allowed duplicates.
- The workflows endpoint returns names and status, never triggers: infer triggers from names only
  and say so.
- A daily digest in that account counted every new contact without an opportunity: ask whether
  any downstream report counts new contacts before a large import.

**Import wizard, one real run (2026-11-23)**
- Consent attestation: the final Verify step will not enable "Start import" until a box is ticked.
  Exact wording: "I confirm all contacts in this import have consented to hear from us. I've
  previously contacted them within the last past year, and this list is not from a third party".
  Only the human may tick it; the skill treats it as a hard stop (SKILL.md step 0).
- Mapping: every header that matched a GHL field name exactly was auto-mapped, including "Business
  Name", "Contact Source" and custom-field labels created beforehand. Custom fields were created
  first with `POST /locations/{locationId}/customFields` (types TEXT and NUMERICAL worked).
- Options: import mode defaulted to "Create and update contacts". Each mapped field offers "Skip
  empty values" (default) or "Update empty values". No explicit match-on-email control was shown.
- Verify step offers three unticked options: "Create a Smartlist for new contacts created by the
  import" (default name is a timestamp; it covers new contacts only, so updated existing contacts
  are missing from it), "Add imported contacts to a workflow", "Add tags to imported contacts". A
  tag filter is the complete Smart List.
- Closing the wizard before "Start import" created nothing (checked by API afterwards).
- The Import history page lists earlier imports and who ran them: use it as a duplicate-work check.

## Not documented / not confirmed

- Whether a CSV import keeps or replaces a contact's existing tags: prove it on the canary.
- Whether "Don't update Empty Values" applies to contact fields (B words it for opportunities).
- Creating a custom field inside the wizard.
- Which of 20, 30 or 50 MB is current.
- Any Smart List endpoint outside `contacts.json`.

## Pre-flight checks (read-only, optional)

Credentials come from `GHL_API_KEY`, `GHL_LOCATION_ID`, `GHL_API_BASE_URL` in the environment or a
file the user names; never print them. Send `Authorization: Bearer ...`, `Version: 2021-07-28`,
`Accept: application/json` and a `User-Agent`. Do: count the file's emails already present (and
their tags) with `POST /contacts/search`; read the location's duplicate setting; list custom
fields; list workflows and flag names that suggest contact-created or tag triggers. Never write.
