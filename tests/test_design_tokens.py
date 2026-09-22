"""The fork is enforceable, not documentary."""

import re

from sitegen import design


def test_every_token_is_sm_namespaced():
    """The sibling repo carries two token sets with a comment insisting one is
    'a port, not a fork'. That comment is a scar from syncing them by hand
    twice. Across two repositories not even grep reaches both copies, so the
    namespace is what makes the decision hold."""
    css = design.stylesheet()
    tokens = set(re.findall(r"(--[a-z0-9-]+)", css))
    stray = sorted(t for t in tokens if not t.startswith("--sm-"))
    assert not stray, f"tokens not namespaced --sm-: {stray}"


def test_every_token_used_is_defined_and_every_token_defined_is_used():
    css = design.stylesheet()
    used = set(re.findall(r"var\((--sm-[a-z0-9-]+)", css))
    defined = set(re.findall(r"^\s*(--sm-[a-z0-9-]+)\s*:", css, re.M))
    assert not (used - defined), f"used but never defined: {sorted(used - defined)}"
    assert not (defined - used), f"defined but never used: {sorted(defined - used)}"
    assert len(used) >= 10


def test_colour_values_are_well_formed():
    """#16151338 is an 8-digit hex, which makes a background 22% transparent.
    That shipped once and was invisible until a dark-mode page looked wrong."""
    css = design.stylesheet()
    checked = 0
    for m in re.finditer(r"(--sm-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]+)\s*;", css):
        name, value = m.groups()
        assert len(value) in (4, 7, 9), f"{name}: {value} is not a valid hex colour"
        if len(value) == 9:
            raise AssertionError(
                f"{name}: {value} carries an alpha channel. If translucency is "
                "intended, say so explicitly rather than hiding it in a hex.")
        checked += 1
    assert checked >= 8


def test_the_version_changes_when_the_stylesheet_does(monkeypatch):
    before = design.stylesheet_version()
    monkeypatch.setattr(design, "_CODE", design._CODE + "\n.sm-extra{color:red}\n")
    assert design.stylesheet_version() != before


def test_print_rules_exist_and_force_ink_on_white():
    """A dark page that prints as heavy grey is worse at the one job it has."""
    css = design.stylesheet()
    assert "@page" in css, "no real @page rule — this is print-register design"
    assert "@media print" in css
    printed = css[css.index("@media print"):]
    assert "--sm-paper: #fff" in printed or "--sm-paper:#fff" in printed
