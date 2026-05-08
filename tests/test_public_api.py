"""Public package-root import tests for installed library usage."""

from __future__ import annotations

import subprocess
import sys


def test_package_root_exports_installed_library_surface() -> None:
    import docugym
    from docugym import (
        AppSettings,
        DocuWrapper,
        NarrationContext,
        PromptTuningSample,
        RunResult,
        VLMNarrator,
        docuwrapper,
        get_system_prompt,
        load_settings,
        reset_system_prompt,
        run_prompt_tuning,
        run_session_sync,
        set_system_prompt,
    )

    expected_exports = {
        "AppSettings",
        "DocuWrapper",
        "NarrationContext",
        "PromptTuningSample",
        "RunResult",
        "VLMNarrator",
        "docuwrapper",
        "get_system_prompt",
        "load_settings",
        "reset_system_prompt",
        "run_prompt_tuning",
        "run_session_sync",
        "set_system_prompt",
    }

    assert expected_exports <= set(docugym.__all__)
    assert AppSettings is not None
    assert DocuWrapper is not None
    assert NarrationContext is not None
    assert PromptTuningSample is not None
    assert RunResult is not None
    assert VLMNarrator is not None
    assert callable(docuwrapper)
    assert callable(get_system_prompt)
    assert callable(load_settings)
    assert callable(reset_system_prompt)
    assert callable(run_prompt_tuning)
    assert callable(run_session_sync)
    assert callable(set_system_prompt)
    assert load_settings().run.env_id == "ALE/SpaceInvaders-v5"


def test_plain_package_import_does_not_eagerly_load_runtime_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, docugym; print('docugym.wrapper' in sys.modules)",
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"
