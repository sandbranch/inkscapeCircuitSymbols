# Copyright 2026 David
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every page of both dialogs draws, and the same real size in any document."""

import pytest
from conftest import document, inx_args, tabs

CASES = [(inx, tab, sub) for inx in ("circuitSymbols_general.inx", "circuitSymbols_semiconductors.inx") for tab, sub in tabs(inx) if tab != "Help"]  # help pages draw nothing


@pytest.mark.parametrize("inx,tab,sub", CASES, ids=[f"{i[15:-4]}-{t}-{'-'.join(s.values())}" for i, t, s in CASES])
def test_draws_the_same_size_everywhere(run, inx, tab, sub):
    from conftest import new_drawing_px

    sizes = {}
    for kind in ("mm", "px", "half"):
        code, err, out = run("circuitSymbols.py", document(kind), inx_args(inx, tab=tab, **sub))
        assert code == 0 and not err.strip(), err
        sizes[kind] = new_drawing_px(out)
    assert sizes["mm"] == sizes["px"] == sizes["half"]
