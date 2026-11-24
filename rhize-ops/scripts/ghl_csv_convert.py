#!/usr/bin/env python3
"""Convert any CSV into a GoHighLevel (HighLevel / LeadConnector) contact-import CSV.

Standard library only. Offline: never calls the GHL API and never reads credentials.

  ghl_csv_convert.py --input in.csv --output out.csv --mapping map.json [--report report.json]
  ghl_csv_convert.py --self-check

Mapping JSON keys (every one optional; flags of the same meaning extend or override them):
  first_name, last_name, full_name, email, phone   source column names (guessed from the header
                                                   when omitted: "First Name", "Email", ...)
  fields          {"Source Column": "GHL Field Label"}  pass-through, standard fields
  custom_fields   {"Source Column": "GHL Field Label"}  pass-through; label must already exist in GHL
  tag_columns     ["Source Column"]   cell holds comma-separated tags
  value_tags      {"Source Column": "prefix"}  slugified cell value becomes a tag (prefix may be "")
  constant_tags   ["tag", ...]        added to every contact
  max_columns / min_columns  ["Source Column"]  numeric merge rule for duplicates (default: first non-empty)
  contact_source  "text"              constant "Contact Source" for every row

Exit codes: 0 ok, 1 an input row had no first name, email or phone, 2 bad mapping/input.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

CORE = ["First Name", "Last Name", "Email", "Phone"]
RESERVED = set(CORE) | {"Tags", "Contact Source"}
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
GUESS = {
    "first_name": ["first name", "firstname", "first"],
    "last_name": ["last name", "lastname", "last", "surname"],
    "full_name": ["full name", "fullname", "name", "contact name"],
    "email": ["email", "e-mail", "email address"],
    "phone": ["phone", "phone number", "mobile", "cell"],
}


class MappingError(ValueError):
    pass


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def clean_email(raw: str):
    value = raw.strip().lower()
    if not value:
        return "", None
    return (value, None) if EMAIL_RE.match(value) else ("", f"invalid email {raw!r} dropped")


def clean_phone(raw: str):
    """US numbers to E.164; +country numbers kept. Never invents a number."""
    value = raw.strip()
    if not value:
        return "", None
    note = None
    stripped = re.sub(r"(?i)\s*(?:x|ext\.?)\s*\d+$", "", value)
    if stripped != value:
        note, value = f"phone extension removed from {raw!r}", stripped
    digits = re.sub(r"\D", "", value)
    if value.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits, note
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10 and digits[0] not in "01":
        return "+1" + digits, note
    return "", f"invalid phone {raw!r} dropped"


def split_name(full: str):
    """Return (first, last, anomalies). First token is the first name, the rest the last name."""
    full = " ".join(full.split())
    if not full:
        return "", "", []
    tokens = full.split(" ")
    anomalies = []
    if "(" in full or ")" in full:
        anomalies.append("parenthesised nickname")
    if len(tokens) >= 3:
        anomalies.append("three or more name tokens")
    if len(tokens[0].rstrip(".")) <= 2:
        anomalies.append("one- or two-letter first token")
    return tokens[0], " ".join(tokens[1:]), anomalies


def parse_number(raw: str):
    try:
        value = float(raw.replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None  # nan/inf would crash fmt_number


def fmt_number(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(value)


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
E164_RE = re.compile(r"^\+\d+$")
NEGATIVE_NUMBER_RE = re.compile(r"^-(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$")


def neutralise(label: str, value: str, numeric_labels: set):
    """Prefix ' to a cell a spreadsheet would run as a formula. Returns (value, changed)."""
    if not value or not value.startswith(FORMULA_START):
        return value, False
    if label == "Phone" and E164_RE.match(value):  # the script's own normalised phone
        return value, False
    if label in numeric_labels and NEGATIVE_NUMBER_RE.match(value):
        return value, False
    return "'" + value, True


def check_tag(tag: str) -> bool:
    return ";" not in tag and "." not in tag


def normalise_mapping(mapping: dict, header: list) -> dict:
    m = {k: mapping.get(k) for k in GUESS}
    lowered = {h.strip().lower(): h for h in header}
    for key, names in GUESS.items():
        if not m[key]:
            m[key] = next((lowered[n] for n in names if n in lowered), None)
        if m[key] and m[key] not in header:
            raise MappingError(f"column {m[key]!r} for {key} not in the CSV header")
    if m["full_name"] and (m["first_name"] or m["last_name"]):
        m["full_name"] = None  # separate columns win over a guessed or duplicate full-name column
    m["fields"] = dict(mapping.get("fields") or {})
    m["custom_fields"] = dict(mapping.get("custom_fields") or {})
    for group in ("fields", "custom_fields"):
        for source, label in m[group].items():
            if source not in header:
                raise MappingError(f"column {source!r} in {group} not in the CSV header")
            if label in RESERVED:
                raise MappingError(f"label {label!r} is built in; use the dedicated mapping key")
            if label.startswith(FORMULA_START):  # header cells are not neutralised
                raise MappingError(f"label {label!r} starts with a spreadsheet formula character")
    if set(m["fields"].values()) & set(m["custom_fields"].values()):
        raise MappingError("a label appears in both fields and custom_fields")
    m["tag_columns"] = list(mapping.get("tag_columns") or [])
    m["value_tags"] = dict(mapping.get("value_tags") or {})
    for source in m["tag_columns"] + list(m["value_tags"]):
        if source not in header:
            raise MappingError(f"tag column {source!r} not in the CSV header")
    m["constant_tags"] = [t.strip() for t in mapping.get("constant_tags") or [] if t.strip()]
    for tag in m["constant_tags"] + [p for p in m["value_tags"].values() if p]:
        if not check_tag(tag):
            raise MappingError(f"tag text {tag!r} contains ';' or '.', which GHL splits on")
    labelled = {**m["fields"], **m["custom_fields"]}
    m["max_columns"] = list(mapping.get("max_columns") or [])
    m["min_columns"] = list(mapping.get("min_columns") or [])
    for source in m["max_columns"] + m["min_columns"]:
        if source not in labelled:
            raise MappingError(f"max/min column {source!r} must also be in fields or custom_fields")
    m["contact_source"] = (mapping.get("contact_source") or "").strip()
    if m["contact_source"] and "Contact Source" in labelled.values():
        raise MappingError("Contact Source is both constant and mapped")
    return m


def convert(rows: list, header: list, mapping: dict):
    """rows: list of dicts. Returns (output_header, output_rows, report)."""
    m = normalise_mapping(mapping, header)
    labelled = {**m["fields"], **m["custom_fields"]}
    report = {"rows_in": len(rows), "merged_duplicates": [], "rows_dropped": [], "warnings": [],
              "rejected_tags": [], "missing_identifier": []}
    contacts, by_email, by_phone = [], {}, {}

    def warn(line: int, text: str):
        report["warnings"].append(f"row {line}: {text}")

    for line, row in enumerate(rows, start=2):
        get = lambda col: (row.get(col) or "").strip() if col else ""
        if not any((v or "").strip() for v in row.values()):
            report["rows_dropped"].append({"row": line, "reason": "blank row"})
            continue
        first, last = get(m["first_name"]), get(m["last_name"])
        if m["full_name"] and not (first or last):
            first, last, anomalies = split_name(get(m["full_name"]))
            for a in anomalies:
                warn(line, f"name anomaly ({a}): {get(m['full_name'])!r} split as first={first!r} last={last!r}")
        email, note = clean_email(get(m["email"]))
        if note:
            warn(line, note)
        phone, note = clean_phone(get(m["phone"]))
        if note:
            warn(line, note)
        tags = list(m["constant_tags"])
        for col in m["tag_columns"]:
            for tag in (t.strip() for t in get(col).split(",")):
                if not tag:
                    continue
                if check_tag(tag):
                    tags.append(tag)
                else:
                    report["rejected_tags"].append({"row": line, "tag": tag})
                    warn(line, f"tag {tag!r} dropped: contains ';' or '.', which GHL splits on")
        for col, prefix in m["value_tags"].items():
            slug = slugify(get(col))
            if slug:
                tags.append(f"{prefix}{slug}" if prefix else slug)
        if not (first or email or phone):
            report["missing_identifier"].append(line)
            continue
        values = {label: get(col) for col, label in labelled.items()}
        numeric = {}
        for col in m["max_columns"] + m["min_columns"]:
            raw = get(col)
            if raw and parse_number(raw) is None:
                warn(line, f"non-numeric value {raw!r} in {col!r} ignored")
            numeric[labelled[col]] = parse_number(raw) if raw else None
        record = {"First Name": first, "Last Name": last, "Email": email, "Phone": phone,
                  "values": values, "numeric": numeric, "tags": tags, "rows": [line]}
        target = by_email.get(email) if email else by_phone.get(phone) if phone else None
        if target is None:
            contacts.append(record)
            if email:
                by_email[email] = record
            if phone:
                by_phone.setdefault(phone, record)
            continue
        report["merged_duplicates"].append({"row": line, "into_row": target["rows"][0],
                                            "key": email or phone})
        target["rows"].append(line)
        for key in CORE:
            if not target[key]:
                target[key] = record[key]
                if key == "Email" and record[key]:
                    by_email.setdefault(record[key], target)
                if key == "Phone" and record[key]:
                    by_phone.setdefault(record[key], target)
            elif record[key] and record[key] != target[key]:
                warn(line, f"{key} {record[key]!r} differs from kept {target[key]!r} (row {target['rows'][0]})")
        for label, value in values.items():
            if not target["values"][label]:
                target["values"][label] = value
        for label, number in numeric.items():
            if number is None:
                continue
            old = target["numeric"].get(label)
            keep_max = any(labelled[c] == label for c in m["max_columns"])
            target["numeric"][label] = number if old is None else (max if keep_max else min)(old, number)
        target["tags"].extend(t for t in tags if t not in target["tags"])

    out_header = CORE + list(labelled.values())
    if m["contact_source"]:
        out_header.append("Contact Source")
    all_tags = []
    for c in contacts:
        c["tags"] = list(dict.fromkeys(c["tags"]))
        all_tags.extend(t for t in c["tags"] if t not in all_tags)
    if all_tags:
        out_header.append("Tags")
    out_rows = []
    numeric_labels = {labelled[col] for col in m["max_columns"] + m["min_columns"]}
    for c in contacts:
        values = dict(c["values"])
        for label, number in c["numeric"].items():
            if number is not None:
                values[label] = fmt_number(number)
        out = {k: c[k] for k in CORE} | values
        if m["contact_source"]:
            out["Contact Source"] = m["contact_source"]
        if all_tags:
            out["Tags"] = ",".join(c["tags"])
        for label in list(out):
            out[label], changed = neutralise(label, out[label], numeric_labels)
            if changed:
                warn(c["rows"][0], f"column {label!r} value starts with a formula character; "
                     "prefixed with ' (fix the source value instead of importing it)")
        out_rows.append(out)
    if any(label.strip().upper() == "DND" for label in labelled.values()):
        report["warnings"].append("DND is mapped: GHL applies a DND column to ALL channels, not per channel")
    report.update({
        "contacts_out": len(out_rows),
        "tags_used": sorted(all_tags),
        "custom_field_labels_required": list(m["custom_fields"].values()),
        "custom_field_note": "Each custom field label must already exist in GHL with this label and a matching type.",
        "confirm_labels_in_wizard": list(m["fields"].values()),
        "status": "fail" if report["missing_identifier"] else "ok",
    })
    return out_header, out_rows, report


def write_csv(path: Path, header: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(input_path: Path, output_path: Path, mapping: dict, report_path: Path | None):
    with open(input_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = [h.strip() for h in (reader.fieldnames or [])]
        rows = [{(k or "").strip(): v for k, v in r.items()} for r in reader]
    out_header, out_rows, report = convert(rows, header, mapping)
    write_csv(output_path, out_header, out_rows)
    if report_path:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


SAMPLE = (
    "Full Name,Email,Mobile,Company,Score,Rank,Segment,Notes\n"
    "Ann Lee,ANN@Example.com,(919) 555-0101,Acme,5,3,North Hills,hello\n"
    "Ann Lee,ann@example.com,,Acme,9,1,North Hills,\n"
    "J Doe,jdoe@example.com,919.555.0102,,2,4,,\n"
    "Mary Jo Smith,bad-email,+44 20 7946 0958,,,,,\n"
    "Bob (Bobby) Ray,,555-0103,,,,,\n"
    ",,,,,,,\n"
)
SAMPLE_MAP = {
    "full_name": "Full Name", "email": "Email", "phone": "Mobile",
    "fields": {"Company": "Business Name"}, "custom_fields": {"Score": "Lead Score", "Rank": "List Rank"},
    "value_tags": {"Segment": "seg-"}, "constant_tags": ["import-2026-11"],
    "max_columns": ["Score"], "min_columns": ["Rank"], "contact_source": "Test List",
}


def self_check() -> None:
    header, rows, report = convert(*_read_text(SAMPLE), SAMPLE_MAP)
    by_email = {r["Email"]: r for r in rows}
    ann = by_email["ann@example.com"]
    assert ann["Phone"] == "+19195550101" and ann["Lead Score"] == "9" and ann["List Rank"] == "1", ann
    assert ann["Tags"] == "import-2026-11,seg-north-hills", ann["Tags"]
    assert len(report["merged_duplicates"]) == 1 and report["contacts_out"] == 4, report
    assert by_email["jdoe@example.com"]["Phone"] == "+19195550102"
    assert "Contact Source" in header and "DND" not in header
    kinds = " ".join(report["warnings"])
    for needle in ("one- or two-letter", "three or more", "parenthesised", "invalid email", "invalid phone"):
        assert needle in kinds, needle
    assert report["rows_dropped"] == [{"row": 7, "reason": "blank row"}], report["rows_dropped"]
    assert report["missing_identifier"] == [] and report["status"] == "ok"
    assert report["custom_field_labels_required"] == ["Lead Score", "List Rank"]
    _, inj, inj_report = convert(*_read_text("Name,Email,Rank\n=SUM(A1) Lee,a@b.co,-3.5\n"),
                                 {"custom_fields": {"Rank": "Rank"}, "min_columns": ["Rank"]})
    assert inj[0]["First Name"] == "'=SUM(A1)" and inj[0]["Rank"] == "-3.5", inj
    assert any("row 2: column 'First Name'" in w for w in inj_report["warnings"]), inj_report
    _, _, bad = convert(*_read_text("Name,Email,Note\n,,hi\n"), {})
    assert bad["status"] == "fail" and bad["missing_identifier"] == [2], bad
    try:
        convert(*_read_text("Name,Email\nA B,a@b.co\n"), {"constant_tags": ["a.b"]})
    except MappingError:
        pass
    else:
        raise AssertionError("tag with '.' must be rejected")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in.csv"), Path(tmp, "out.csv")
        src.write_text(SAMPLE, encoding="utf-8")
        run(src, dst, SAMPLE_MAP, None)
        assert next(csv.reader(open(dst, encoding="utf-8")))[:4] == CORE
    print("self-check ok")


def _read_text(text: str):
    reader = csv.DictReader(text.splitlines())
    rows = [{k.strip(): v for k, v in r.items()} for r in reader]
    return rows, [h.strip() for h in reader.fieldnames]


def parse_pairs(items, flag):
    out = {}
    for item in items or []:
        source, sep, label = item.partition("=")
        if not sep:
            raise MappingError(f"{flag} expects 'Source=Label', got {item!r}")
        out[source] = label
    return out


def build_mapping(args) -> dict:
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8")) if args.mapping else {}
    for key in ("first_name", "last_name", "full_name", "email", "phone", "contact_source"):
        value = getattr(args, key)
        if value:
            mapping[key] = value
    mapping["fields"] = {**(mapping.get("fields") or {}), **parse_pairs(args.field, "--field")}
    mapping["custom_fields"] = {**(mapping.get("custom_fields") or {}), **parse_pairs(args.custom, "--custom")}
    mapping["value_tags"] = {**(mapping.get("value_tags") or {}), **parse_pairs(args.value_tag, "--value-tag")}
    for key, extra in (("tag_columns", args.tag_column), ("constant_tags", args.constant_tag),
                       ("max_columns", args.max_column), ("min_columns", args.min_column)):
        mapping[key] = list(mapping.get(key) or []) + list(extra or [])
    return mapping


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-check", action="store_true", help="run built-in assertions and exit")
    p.add_argument("--input")
    p.add_argument("--output")
    p.add_argument("--report", help="JSON report path (default: <output>.report.json)")
    p.add_argument("--mapping", help="mapping JSON file")
    for flag in ("first-name", "last-name", "full-name", "email", "phone", "contact-source"):
        p.add_argument(f"--{flag}", dest=flag.replace("-", "_"), metavar="VALUE")
    p.add_argument("--field", action="append", metavar="SRC=LABEL", help="standard field pass-through")
    p.add_argument("--custom", action="append", metavar="SRC=LABEL", help="custom field pass-through")
    p.add_argument("--value-tag", action="append", metavar="SRC=PREFIX", help="slugified value becomes a tag")
    p.add_argument("--tag-column", action="append", metavar="SRC")
    p.add_argument("--constant-tag", action="append", metavar="TAG")
    p.add_argument("--max-column", action="append", metavar="SRC")
    p.add_argument("--min-column", action="append", metavar="SRC")
    args = p.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if not (args.input and args.output):
        p.error("--input and --output are required")
    try:
        report = run(Path(args.input), Path(args.output), build_mapping(args),
                     Path(args.report or args.output + ".report.json"))
    except (MappingError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"rows in {report['rows_in']}, contacts out {report['contacts_out']}, "
          f"merged {len(report['merged_duplicates'])}, dropped {len(report['rows_dropped'])}, "
          f"warnings {len(report['warnings'])}, status {report['status']}")
    if report["missing_identifier"]:
        print(f"FAIL: rows without first name, email or phone: {report['missing_identifier']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
