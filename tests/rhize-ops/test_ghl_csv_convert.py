"""Converter behaviour for rhize-ops:ghl-csv-import. Offline; no GHL calls, invented sample data."""
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "rhize-ops/scripts/ghl_csv_convert.py"
SPEC = importlib.util.spec_from_file_location("ghl_csv_convert", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def convert(text, mapping=None):
    reader = csv.DictReader(text.strip().splitlines())
    rows = list(reader)
    return mod.convert(rows, list(reader.fieldnames), mapping or {})


def cli(tmp_path, text, mapping, *extra):
    src, dst, rep = tmp_path / "in.csv", tmp_path / "out.csv", tmp_path / "rep.json"
    src.write_text(text, encoding="utf-8")
    mp = tmp_path / "map.json"
    mp.write_text(json.dumps(mapping))
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(src), "--output", str(dst), "--report", str(rep),
         "--mapping", str(mp), *extra], capture_output=True, text=True)
    return done, dst, rep


def test_self_check_passes():
    done = subprocess.run([sys.executable, str(SCRIPT), "--self-check"], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "self-check ok" in done.stdout


def test_dedupe_on_email_unions_tags_and_takes_max_min():
    text = "First Name,Email,Score,Rank,Tag\nAnn,A@X.com,5,3,red\nAnn,a@x.com,9,1,blue\nAnn,a@x.com,7,2,red\n"
    mapping = {"custom_fields": {"Score": "Lead Score", "Rank": "Rank"}, "tag_columns": ["Tag"],
               "max_columns": ["Score"], "min_columns": ["Rank"]}
    header, rows, report = convert(text, mapping)
    assert len(rows) == 1 and len(report["merged_duplicates"]) == 2
    assert rows[0]["Email"] == "a@x.com"
    assert rows[0]["Lead Score"] == "9" and rows[0]["Rank"] == "1"
    assert rows[0]["Tags"] == "red,blue"


def test_dedupe_falls_back_to_phone():
    text = "First Name,Phone\nAnn,(919) 555-0101\nAnn,919-555-0101\nBo,919-555-0102\n"
    _, rows, report = convert(text)
    assert [r["Phone"] for r in rows] == ["+19195550101", "+19195550102"]
    assert len(report["merged_duplicates"]) == 1


def test_phone_never_invented():
    text = "First Name,Email,Phone\nAnn,a@x.com,12345\nBo,b@x.com,\n"
    _, rows, report = convert(text)
    assert rows[0]["Phone"] == "" and rows[1]["Phone"] == ""
    assert any("invalid phone" in w for w in report["warnings"])


def test_tags_joined_constant_value_and_rejected():
    text = "First Name,Email,Tag,Segment\nAnn,a@x.com,\"one, two;bad, three.x\",North Hills!\n"
    mapping = {"tag_columns": ["Tag"], "value_tags": {"Segment": "seg-"}, "constant_tags": ["batch-1"]}
    _, rows, report = convert(text, mapping)
    assert rows[0]["Tags"] == "batch-1,one,seg-north-hills"
    assert {t["tag"] for t in report["rejected_tags"]} == {"two;bad", "three.x"}
    assert report["tags_used"] == ["batch-1", "one", "seg-north-hills"]


def test_constant_tag_with_separator_is_a_mapping_error():
    with pytest.raises(mod.MappingError):
        convert("First Name,Email\nAnn,a@x.com\n", {"constant_tags": ["a;b"]})
    with pytest.raises(mod.MappingError):
        convert("First Name,Email\nAnn,a@x.com\n", {"constant_tags": ["a.b"]})


@pytest.mark.parametrize("name,first,last,anomaly", [
    ("Ann Lee", "Ann", "Lee", None),
    ("J Doe", "J", "Doe", "one- or two-letter"),
    ("Al Park", "Al", "Park", "one- or two-letter"),
    ("Mary Jo Smith", "Mary", "Jo Smith", "three or more"),
    ("Bob (Bobby) Ray", "Bob", "(Bobby) Ray", "parenthesised"),
])
def test_full_name_split_and_anomalies(name, first, last, anomaly):
    _, rows, report = convert(f"Name,Email\n{name},a@x.com\n")
    assert (rows[0]["First Name"], rows[0]["Last Name"]) == (first, last)
    flagged = " ".join(report["warnings"])
    assert (anomaly in flagged) if anomaly else not report["warnings"]


def test_separate_name_columns_win_over_full_name():
    _, rows, report = convert("First,Last,Name,Email\nAnn,Lee,Q R S T,a@x.com\n")
    assert (rows[0]["First Name"], rows[0]["Last Name"]) == ("Ann", "Lee")
    assert not report["warnings"]


def test_invalid_email_dropped_but_row_kept_with_name():
    _, rows, report = convert("First Name,Email\nAnn,not-an-email\n")
    assert rows[0]["Email"] == "" and rows[0]["First Name"] == "Ann"
    assert any("invalid email" in w for w in report["warnings"])


def test_blank_rows_dropped_with_reason():
    _, rows, report = convert("First Name,Email\nAnn,a@x.com\n,\n")
    assert len(rows) == 1 and report["rows_dropped"] == [{"row": 3, "reason": "blank row"}]


def test_missing_identifier_exits_nonzero_and_reports(tmp_path):
    done, dst, rep = cli(tmp_path, "Name,Email,Note\nAnn Lee,a@x.com,x\n,,orphan\n", {})
    assert done.returncode == 1, done.stdout + done.stderr
    report = json.loads(rep.read_text())
    assert report["missing_identifier"] == [3] and report["status"] == "fail"
    with open(dst, newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 1 and written[0]["Email"] == "a@x.com"


def test_cli_ok_report_fields_and_no_consent_columns(tmp_path):
    text = "Name,Email,Company,Score,Consent\nAnn Lee,a@x.com,Acme,5,yes\n"
    mapping = {"fields": {"Company": "Business Name"}, "custom_fields": {"Score": "Lead Score"},
               "contact_source": "Test List"}
    done, dst, rep = cli(tmp_path, text, mapping)
    assert done.returncode == 0, done.stderr
    report = json.loads(rep.read_text())
    assert report["rows_in"] == 1 and report["contacts_out"] == 1
    assert report["custom_field_labels_required"] == ["Lead Score"]
    assert report["confirm_labels_in_wizard"] == ["Business Name"]
    header = next(csv.reader(open(dst, encoding="utf-8")))
    assert "DND" not in header and "Consent" not in header and "Contact Source" in header


def test_dnd_only_when_explicitly_mapped_and_warned():
    _, _, report = convert("Name,Email,Opt\nAnn Lee,a@x.com,yes\n", {"fields": {"Opt": "DND"}})
    assert any("ALL channels" in w for w in report["warnings"])


def test_reserved_label_and_unknown_column_rejected():
    with pytest.raises(mod.MappingError):
        convert("Name,Email,X\nAnn,a@x.com,1\n", {"fields": {"X": "Tags"}})
    with pytest.raises(mod.MappingError):
        convert("Name,Email\nAnn,a@x.com\n", {"fields": {"Nope": "City"}})


def test_formula_leading_name_is_neutralised_with_warning():
    _, rows, report = convert("Name,Email\n=cmd Lee,a@x.com\n")
    assert rows[0]["First Name"] == "'=cmd"
    assert any("row 2: column 'First Name'" in w for w in report["warnings"])


@pytest.mark.parametrize("lead", ["=", "+", "-", "@"])
def test_formula_leading_custom_field_is_neutralised(lead):
    _, rows, report = convert(f"Name,Email,Note\nAnn,a@x.com,{lead}1+2\n", {"custom_fields": {"Note": "Note"}})
    assert rows[0]["Note"] == f"'{lead}1+2"
    assert any("column 'Note'" in w for w in report["warnings"])


def test_leading_tab_is_stripped_on_read_so_never_a_formula():
    _, rows, report = convert("Name,Email,Note\nAnn,a@x.com,\"\tx\"\n", {"fields": {"Note": "City"}})
    assert rows[0]["City"] == "x" and not any("formula" in w for w in report["warnings"])
    assert mod.neutralise("City", "\tx", set()) == ("'\tx", True)


def test_formula_leading_tag_is_neutralised():
    _, rows, report = convert("Name,Email,Tag\nAnn,a@x.com,=bad\n", {"tag_columns": ["Tag"]})
    assert rows[0]["Tags"] == "'=bad"
    assert any("column 'Tags'" in w for w in report["warnings"])


def test_e164_phone_is_exempt():
    _, rows, report = convert("Name,Phone\nAnn,+44 20 7946 0958\nBo,(919) 555-0101\n")
    assert [r["Phone"] for r in rows] == ["+442079460958", "+19195550101"]
    assert not any("formula" in w for w in report["warnings"])


def test_negative_number_exempt_only_in_numeric_column():
    text = "Name,Email,Score,Other\nAnn,a@x.com,-12,-12\n"
    mapping = {"custom_fields": {"Score": "Score", "Other": "Other"}, "max_columns": ["Score"]}
    _, rows, report = convert(text, mapping)
    assert rows[0]["Score"] == "-12" and rows[0]["Other"] == "'-12"
    assert [w for w in report["warnings"] if "formula" in w and "'Score'" in w] == []
    _, rows, _ = convert("Name,Email,Score\nAnn,a@x.com,-3.5x\n", {"custom_fields": {"Score": "Score"}})
    assert rows[0]["Score"] == "'-3.5x"


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "-1+cmd"])
def test_non_finite_or_formula_value_in_numeric_column_is_not_a_number(raw):
    mapping = {"custom_fields": {"Score": "Score"}, "max_columns": ["Score"]}
    _, rows, report = convert(f"Name,Email,Score\nAnn,a@x.com,{raw}\nAnn,a@x.com,4\n", mapping)
    assert rows[0]["Score"] == "4"
    assert any("non-numeric value" in w for w in report["warnings"])
    _, rows, _ = convert(f"Name,Email,Score\nAnn,a@x.com,{raw}\n", mapping)
    assert rows[0]["Score"] == ("'-1+cmd" if raw == "-1+cmd" else ("'-inf" if raw == "-inf" else raw))
