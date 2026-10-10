import io
import logging
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("answer, action", [("approved\n", "accept"), ("cancel\n", "decline"), ("", "decline")])
async def test_manual_live_approval_requires_explicit_acknowledgment(answer, action, capsys):
    script = Path(__file__).resolve().parents[1] / "scripts" / "live_stdio_check.py"
    with patch.object(sys, "argv", [str(script), "--offline"]), patch.object(logging, "disable"):
        namespace = runpy.run_path(str(script))
    assert namespace["options"].manual_approval is True
    with patch.object(sys, "stdin", io.StringIO(answer)):
        result = await namespace["approve"](None, None)
    assert result.action == action
    assert result.content == ({"approved": True} if action == "accept" else None)
    assert "PUSH TAN:" in capsys.readouterr().out
