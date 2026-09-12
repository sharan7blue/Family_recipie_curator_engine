"""
Guardrail: every custom Tailwind design-token class used across the static
UI pages must actually be defined in app/static/design-tokens.js.

Why this exists: app/static/*.html use custom Tailwind tokens (e.g.
"text-headline-sm", "p-space-sm", "px-margin-mobile") instead of Tailwind's
built-in scale. The Tailwind CDN silently renders an unrecognized utility
class as nothing -- no error, no warning, just missing CSS -- so a typo'd or
undefined token looks fine in a code review and only shows up as visibly
broken spacing/typography in an actual browser. Five of the six static pages
shipped with their own copy of the config missing these entries entirely
before this was consolidated into one shared design-tokens.js file; this
test would have caught that at review time instead of requiring someone to
notice broken CSS in a live page.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
TOKENS_FILE = STATIC_DIR / "design-tokens.js"

# Matches text-/font- classes built from our custom Material-3-style type
# scale, e.g. "text-headline-sm", "font-body-md" -- but not Tailwind's own
# single-segment utilities like "font-bold" or "text-center".
TYPOGRAPHY_CLASS_RE = re.compile(
    r"^(?:text|font)-((?:display|headline|body|label|title)(?:-[a-z0-9]+)+)$"
)

# Matches any utility ending in one of our custom spacing tokens, e.g.
# "p-space-sm", "gap-space-2xs", "px-margin-mobile", "min-h-touch-min".
SPACING_CLASS_RE = re.compile(
    r"(?:^|-)(space-[a-z0-9]+|margin-mobile|gutter-mobile|touch-min)$"
)


def _extract_block_keys(source: str, block_name: str) -> set[str]:
    """Keys of a `name: { "key": ... }` object with no nested braces."""
    match = re.search(rf"{block_name}:\s*\{{(.*?)\}}", source, re.S)
    assert match, f"Could not find a `{block_name}: {{ ... }}` block in {TOKENS_FILE.name}"
    return set(re.findall(r'"([a-zA-Z0-9-]+)"\s*:', match.group(1)))


def _defined_tokens() -> tuple[set[str], set[str]]:
    source = TOKENS_FILE.read_text()
    spacing_keys = _extract_block_keys(source, "spacing")
    # fontFamily and fontSize both key on the same token names
    # ("headline-sm", "body-md", ...); both are `"key": [...]` shaped, so a
    # single sweep over the whole extend object covers both sections
    # without needing to bracket-match the nested per-entry option objects.
    typography_keys = set(re.findall(r'"([a-zA-Z0-9-]+)"\s*:\s*\[', source))
    return spacing_keys, typography_keys


def _used_classes() -> set[str]:
    classes: set[str] = set()
    for html_file in STATIC_DIR.glob("*.html"):
        for class_attr in re.findall(r'class="([^"]*)"', html_file.read_text()):
            classes.update(class_attr.split())
    return classes


def test_every_typography_class_is_defined():
    _, typography_keys = _defined_tokens()
    used = _used_classes()
    missing = set()
    for cls in used:
        m = TYPOGRAPHY_CLASS_RE.match(cls)
        if m and m.group(1) not in typography_keys:
            missing.add(cls)
    assert not missing, (
        f"These classes reference type-scale tokens not defined in "
        f"design-tokens.js's fontFamily/fontSize (renders as unstyled text): {sorted(missing)}"
    )


def test_every_spacing_class_is_defined():
    spacing_keys, _ = _defined_tokens()
    used = _used_classes()
    missing = set()
    for cls in used:
        m = SPACING_CLASS_RE.search(cls)
        if m and m.group(1) not in spacing_keys:
            missing.add(cls)
    assert not missing, (
        f"These classes reference spacing tokens not defined in "
        f"design-tokens.js's spacing scale (renders with zero spacing): {sorted(missing)}"
    )


def test_every_page_loads_the_shared_design_tokens_file():
    missing_pages = []
    for html_file in STATIC_DIR.glob("*.html"):
        if 'src="design-tokens.js"' not in html_file.read_text():
            missing_pages.append(html_file.name)
    assert not missing_pages, (
        f"These pages don't load design-tokens.js and likely have their own "
        f"(possibly incomplete) inline tailwind.config instead: {sorted(missing_pages)}"
    )
