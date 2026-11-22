
#!/usr/bin/env python
"""
Diagnose missing source documents on a generated story page.

Run from the project root:
    python check_story_sources.py

Read-only: does not change any project files.
"""

import json
import re
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent

STORY_ID = "berry-palmer-1931-still-explosion"

STORIES_JSON = ROOT / "data" / "stories.json"
SOURCES_JSON = ROOT / "data" / "sources.json"
BUILD_SCRIPT = ROOT / "build_site.py"
STORY_TEMPLATE = ROOT / "templates" / "story.html"
GENERATED_HTML = ROOT / "docs" / "stories" / f"{STORY_ID}.html"

errors = []
warnings = []


def report(status, message):
    print(f"[{status}] {message}")

    if status == "FAIL":
        errors.append(message)
    elif status == "WARN":
        warnings.append(message)


def read_text(path):
    if not path.exists():
        report("FAIL", f"Missing file: {path.relative_to(ROOT)}")
        return None

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        report("FAIL", f"Cannot read {path.name}: {exc}")
        return None


def read_json(path):
    content = read_text(path)

    if content is None:
        return None

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        report("FAIL", f"Invalid JSON in {path.name}: {exc}")
        return None

    if not isinstance(data, list):
        report(
            "FAIL",
            f"{path.name} must contain a list of records"
        )
        return None

    report("PASS", f"{path.name} is valid JSON")
    return data


class SourceSectionParser(HTMLParser):
    """Find the source heading and links in generated HTML."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.links = []
        self.current_href = None
        self.current_link_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current_href = dict(attrs).get("href")
            self.current_link_text = []

    def handle_data(self, data):
        self.text_parts.append(data)

        if self.current_href is not None:
            self.current_link_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_href is not None:
            self.links.append({
                "href": self.current_href,
                "text": "".join(self.current_link_text).strip()
            })
            self.current_href = None


print("=" * 65)
print("STORY SOURCE DIAGNOSTIC")
print(f"Story: {STORY_ID}")
print("=" * 65)

# --------------------------------------------------
# 1. Check stories.json
# --------------------------------------------------

print("\n1. CHECKING STORIES.JSON")

stories = read_json(STORIES_JSON)
story = None
source_ids = []

if stories is not None:
    matches = [
        item for item in stories
        if isinstance(item, dict)
        and item.get("id") == STORY_ID
    ]

    if len(matches) == 1:
        story = matches[0]
        report("PASS", "Berry Palmer story exists")

        status = story.get("status")

        if status == "published":
            report("PASS", "Story status is published")
        else:
            report("WARN", f"Story status is {status!r}")

        source_ids = story.get("sources", [])

        if isinstance(source_ids, list):
            report(
                "PASS",
                f"Story references {len(source_ids)} sources"
            )

            for source_id in source_ids:
                print(f"       - {source_id}")
        else:
            report("FAIL", "Story sources must be a list")
            source_ids = []

    elif len(matches) == 0:
        report("FAIL", "Berry Palmer story not found")
    else:
        report("FAIL", "Duplicate Berry Palmer story IDs found")


# --------------------------------------------------
# 2. Check sources.json
# --------------------------------------------------

print("\n2. CHECKING SOURCES.JSON")

sources = read_json(SOURCES_JSON)
matched_sources = []

if sources is not None:
    sources_by_id = {}

    for source in sources:
        if not isinstance(source, dict):
            continue

        source_id = source.get("id")

        if source_id in sources_by_id:
            report("FAIL", f"Duplicate source ID: {source_id}")

        sources_by_id[source_id] = source

    for source_id in source_ids:
        if source_id not in sources_by_id:
            report("FAIL", f"Source ID not found: {source_id}")
            continue

        source = sources_by_id[source_id]
        matched_sources.append(source)

        report("PASS", f"Source found: {source_id}")

        if not source.get("title"):
            report("WARN", f"Missing title: {source_id}")

        filename = source.get("file")

        if not filename:
            report("FAIL", f"Missing file field: {source_id}")
            continue

        local_file = ROOT / "documents" / filename

        if local_file.is_file():
            report("PASS", f"Document exists: {filename}")
        else:
            report(
                "WARN",
                f"Document not found locally: {filename}"
            )

        people = source.get("people", [])

        if "asberry-ides-palmer-1886" in people:
            report(
                "WARN",
                f"{source_id} is still associated with "
                "Berry's individual profile"
            )

    report(
        "PASS",
        f"Resolved {len(matched_sources)} of "
        f"{len(source_ids)} story sources"
    )


# --------------------------------------------------
# 3. Check build_site.py
# --------------------------------------------------

print("\n3. CHECKING BUILD_SITE.PY")

build_code = read_text(BUILD_SCRIPT)

if build_code is not None:

    checks = {
        "Source lookup dictionary":
            r"\bsources_by_id\b",

        "Reads story source IDs":
            r"story\.get\(\s*['\"]sources['\"]",

        "Creates source_details":
            r"story_data\s*\[\s*['\"]source_details['\"]\s*\]",

        "Renders story template":
            r"story_template\.render\s*\("
    }

    for label, pattern in checks.items():
        if re.search(pattern, build_code):
            report("PASS", label)
        else:
            report("FAIL", f"Missing: {label}")

    if "source_details" in build_code:
        report(
            "PASS",
            "Build script references source_details"
        )


# --------------------------------------------------
# 4. Check story.html template
# --------------------------------------------------

print("\n4. CHECKING STORY.HTML TEMPLATE")

template_code = read_text(STORY_TEMPLATE)

if template_code is not None:

    checks = {
        "References story.source_details":
            r"story\.source_details",

        "Loops through story sources":
            r"for\s+source\s+in\s+story\.source_details",

        "Displays source title":
            r"source\.title",

        "Displays source file":
            r"source\.file",

        "Creates document links":
            r"documents/"
    }

    for label, pattern in checks.items():
        if re.search(pattern, template_code):
            report("PASS", label)
        else:
            report("FAIL", f"Missing: {label}")


# --------------------------------------------------
# 5. Check generated HTML
# --------------------------------------------------

print("\n5. CHECKING GENERATED STORY HTML")

generated_code = read_text(GENERATED_HTML)

if generated_code is not None:

    parser = SourceSectionParser()
    parser.feed(generated_code)

    page_text = " ".join(parser.text_parts)

    if "Historical Documents & Sources" in page_text:
        report("PASS", "Historical Documents & Sources heading found")
    else:
        report("FAIL", "Historical Documents & Sources heading missing")

    document_links = [
        link for link in parser.links
        if "/documents/" in (link["href"] or "")
    ]

    report(
        "PASS" if document_links else "FAIL",
        f"Generated page contains {len(document_links)} document links"
    )

    for source in matched_sources:
        filename = source.get("file")

        if not filename:
            continue

        matching_links = [
            link for link in document_links
            if link["href"].split("?")[0].endswith("/" + filename)
        ]

        if matching_links:
            report("PASS", f"Linked in story: {filename}")
        else:
            report("FAIL", f"Missing story link: {filename}")

    if (
        STORY_TEMPLATE.exists()
        and GENERATED_HTML.stat().st_mtime
        < STORY_TEMPLATE.stat().st_mtime
    ):
        report(
            "WARN",
            "Generated story is older than story.html. "
            "Rebuild the site."
        )

    if (
        BUILD_SCRIPT.exists()
        and GENERATED_HTML.stat().st_mtime
        < BUILD_SCRIPT.stat().st_mtime
    ):
        report(
            "WARN",
            "Generated story is older than build_site.py. "
            "Rebuild the site."
        )


# --------------------------------------------------
# 6. Summary
# --------------------------------------------------

print("\n" + "=" * 65)
print("DIAGNOSTIC SUMMARY")
print("=" * 65)

print(f"Errors:   {len(errors)}")
print(f"Warnings: {len(warnings)}")

if errors:
    print("\nProblems requiring attention:")

    for number, message in enumerate(errors, 1):
        print(f"{number}. {message}")

if warnings:
    print("\nWarnings:")

    for number, message in enumerate(warnings, 1):
        print(f"{number}. {message}")

if not errors:
    print("\nNo blocking problems detected.")

    if warnings:
        print("Review the warnings above.")
    else:
        print("Story source configuration appears correct.")
else:
    print("\nResolve the errors above and run this script again.")

print("\nDiagnostic complete. No files were modified.")
