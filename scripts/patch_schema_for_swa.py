"""Make a CI-only copy of system.schema.json that accepts the Static Web App the brief requires.

The assignment PDF (§1a, §5, §7.1, §7.2) puts the UI on an Azure Static Web App, and its own
system.yaml example uses `ui.static_web_app`. The provided system.schema.json instead requires
`ui.storage_account` and rejects any other field. The PDF is followed (ADR-8), so system.yaml
names the Static Web App, and CI validates it against a copy of the schema with exactly one
change: the ui object accepts `static_web_app` as an alternative to `storage_account`
(exactly one of the two). Everything else, including additionalProperties: false, is kept.

The original system.schema.json is never modified. If a corrected schema that already allows
static_web_app is provided, this script copies it unchanged and says so; then the script and
its CI step can be removed.

    python scripts/patch_schema_for_swa.py                     # writes the copy to the temp dir, prints the diff
    python scripts/patch_schema_for_swa.py --diff              # prints the diff only
    python scripts/patch_schema_for_swa.py --output /tmp/s.json

Standard library only, so it runs anywhere CI or a laptop has Python.
"""

import argparse
import copy
import difflib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "system.schema.json"
# outside the repository, so nothing generated can be committed by accident
DEFAULT_OUTPUT = Path(tempfile.gettempdir()) / "system.schema.ci.json"

STATIC_WEB_APP = {
    "description": (
        "Name of the Azure Static Web App serving the UI (<prefix>-ui), as the assignment PDF "
        "requires. Added for CI by scripts/patch_schema_for_swa.py; not in the provided schema."
    ),
    "type": "string",
    "pattern": "^[a-z0-9][a-z0-9-]{0,58}[a-z0-9]$",
}


def dump(schema):
    # one serialiser for both sides, so the diff shows only real changes
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def patch(original):
    """Return (patched schema, note). Raises SystemExit if the ui object is not the expected shape."""
    ui = original.get("properties", {}).get("ui")
    if not isinstance(ui, dict) or "properties" not in ui:
        sys.exit("system.schema.json has no properties.ui object: the patch does not apply, check the schema")
    if "static_web_app" in ui["properties"]:
        return copy.deepcopy(original), "the schema already accepts ui.static_web_app: this patch can be removed"
    if ui.get("additionalProperties") is not False or "storage_account" not in ui.get("required", []):
        sys.exit(
            "properties.ui is not the expected shape (storage_account required, no extra fields): check the schema"
        )

    patched = copy.deepcopy(original)
    ui = patched["properties"]["ui"]
    ui["properties"]["static_web_app"] = STATIC_WEB_APP
    # storage_account stops being required on its own; exactly one of the two must be present
    ui["required"] = [name for name in ui["required"] if name != "storage_account"]
    ui["oneOf"] = [{"required": ["storage_account"]}, {"required": ["static_web_app"]}]
    return patched, "ui accepts static_web_app as an alternative to storage_account"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema", type=Path, default=SCHEMA, help="the provided schema (only read)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="where to write the CI copy")
    parser.add_argument("--diff", action="store_true", help="only print the diff, write nothing")
    args = parser.parse_args()

    original = json.loads(args.schema.read_text(encoding="utf-8"))
    patched, note = patch(original)
    diff = difflib.unified_diff(
        dump(original).splitlines(keepends=True),
        dump(patched).splitlines(keepends=True),
        fromfile=f"{args.schema.name} (provided, unchanged)",
        tofile="system.schema.ci.json (used by CI)",
    )
    sys.stdout.writelines(diff)
    print(f"\n{note}")
    if not args.diff:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(dump(patched), encoding="utf-8")
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
