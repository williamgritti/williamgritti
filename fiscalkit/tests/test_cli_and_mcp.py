"""Tests for the CLI surface and the MCP tool functions."""

from __future__ import annotations

import json

import pytest

from fiscalkit.cli import main
from fiscalkit.mcp.server import (
    TOOL_FUNCTIONS,
    analisar_nfe,
    calcular_dv_cnpj,
    classificar_cfop,
    consultar_uf,
    decodificar_chave,
    listar_ufs,
    validar_cnpj,
    validar_cpf,
)

from .test_chave import build_key
from .test_parser import SAMPLE

VALID_KEY = build_key()


# ---------------------------------------------------------------------------
# MCP tool functions
# ---------------------------------------------------------------------------


def test_every_tool_has_a_description() -> None:
    """FastMCP surfaces the docstring to the agent, so an empty one is a bug."""
    assert set(TOOL_FUNCTIONS) == {
        "validar_cpf",
        "validar_cnpj",
        "calcular_dv_cnpj",
        "decodificar_chave",
        "analisar_nfe",
        "escanear_codigo",
        "escanear_projeto",
        "classificar_cfop",
        "consultar_uf",
        "listar_ufs",
    }
    for name, func in TOOL_FUNCTIONS.items():
        assert (func.__doc__ or "").strip(), f"{name} has no docstring"


def test_tools_return_json_serializable_payloads() -> None:
    """An agent transport cannot carry Decimal or dataclass instances."""
    payloads = [
        validar_cpf("111.444.777-35"),
        validar_cnpj("11.222.333/0001-81"),
        calcular_dv_cnpj("112223330001"),
        decodificar_chave(VALID_KEY),
        analisar_nfe(SAMPLE),
        classificar_cfop("6102"),
        consultar_uf("RS"),
        listar_ufs(),
    ]
    for payload in payloads:
        json.dumps(payload, ensure_ascii=False)


def test_invalid_input_returns_payload_not_exception() -> None:
    """Agents handle a structured 'no' far better than a raised exception."""
    assert validar_cpf("123")["valido"] is False
    assert validar_cnpj("123")["valido"] is False
    assert decodificar_chave("123")["valido"] is False
    assert classificar_cfop("9999")["valido"] is False
    assert calcular_dv_cnpj("1")["ok"] is False
    assert analisar_nfe("<broken")["ok"] is False
    assert consultar_uf("XX")["encontrado"] is False


def test_validar_cnpj_reports_alphanumeric() -> None:
    base = "12ABC34501DE"
    full = base + calcular_dv_cnpj(base)["digitos_verificadores"]
    result = validar_cnpj(full)
    assert result["valido"] is True
    assert result["alfanumerico"] is True


def test_decodificar_chave_exposes_issuer_state() -> None:
    result = decodificar_chave(VALID_KEY)
    assert result["valido"] is True
    assert result["uf_sigla"] == "RS"
    assert result["cnpj_emitente"] == "11222333000181"


def test_analisar_nfe_summary() -> None:
    result = analisar_nfe(SAMPLE)
    assert result["ok"] is True
    assert result["quantidade_itens"] == 2
    assert result["autorizada"] is True
    assert result["totais_conferem"] is True
    assert result["totais"]["total_nota"] == "233.90"
    assert result["emitente"]["tipo"] == "PJ"
    assert result["destinatario"]["tipo"] == "PF"


def test_listar_ufs_is_complete() -> None:
    assert listar_ufs()["total"] == 27


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["chave", VALID_KEY], 0),
        (["chave", "123"], 1),
        (["cnpj", "11.222.333/0001-81"], 0),
        (["cnpj", "11.222.333/0001-82"], 1),
        (["cpf", "111.444.777-35"], 0),
        (["cpf", "111.444.777-36"], 1),
        (["cfop", "6102"], 0),
        (["cfop", "9999"], 1),
    ],
)
def test_cli_exit_codes(argv: list[str], expected: int, capsys) -> None:
    """Non-zero on invalid input is what makes this usable in a CI check."""
    assert main(argv) == expected
    capsys.readouterr()


def test_cli_json_output_is_parseable(capsys) -> None:
    assert main(["chave", VALID_KEY, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["uf_sigla"] == "RS"


def test_cli_human_output_mentions_state(capsys) -> None:
    main(["chave", VALID_KEY])
    assert "RS" in capsys.readouterr().out


def test_cli_nfe_reads_file(tmp_path, capsys) -> None:
    path = tmp_path / "nota.xml"
    path.write_text(SAMPLE, encoding="utf-8")
    assert main(["nfe", str(path)]) == 0
    out = capsys.readouterr().out
    assert "233.90" in out
    assert "Comercio Exemplo Ltda" in out


def test_cli_nfe_missing_file_returns_2(tmp_path, capsys) -> None:
    assert main(["nfe", str(tmp_path / "nope.xml")]) == 2
    capsys.readouterr()


def test_cli_nfe_flags_broken_totals(tmp_path, capsys) -> None:
    path = tmp_path / "nota.xml"
    path.write_text(
        SAMPLE.replace("<vProd>226.40</vProd>", "<vProd>1.00</vProd>"), encoding="utf-8"
    )
    main(["nfe", str(path)])
    assert "NÃO" in capsys.readouterr().out


def test_build_server_works_or_names_the_fix() -> None:
    """With the SDK present the server builds; without it, the error names the fix.

    The SDK renamed FastMCP to MCPServer in 2.0, so this must pass on both.
    """
    from fiscalkit.mcp.server import build_server

    try:
        import mcp  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match=r"fiscalkit\[mcp\]"):
            build_server()
        return

    server = build_server()
    assert server is not None


def test_registered_tools_match_tool_functions() -> None:
    """Every function in TOOL_FUNCTIONS must actually reach the agent."""
    pytest.importorskip("mcp")
    import asyncio

    from fiscalkit.mcp.server import build_server

    names = {tool.name for tool in asyncio.run(build_server().list_tools())}
    assert names == set(TOOL_FUNCTIONS)


def test_scan_tools_are_exposed_to_agents() -> None:
    """The 2026 scanner is the differentiator; it must reach the agent surface."""
    from fiscalkit.mcp.server import escanear_codigo, escanear_projeto

    dirty = escanear_codigo('cnpj = int(row["cnpj"])', "python")
    assert dirty["ok"] is True
    assert dirty["pronto_para_2026"] is False
    assert dirty["total"] >= 1

    clean = escanear_codigo("from fiscalkit import is_valid_cnpj", "python")
    assert clean["pronto_para_2026"] is True

    # This once asserted `ok is True` for a path that does not exist, which is how
    # the false all-clear survived: the suite did not merely miss the defect, it
    # pinned it down as correct. A scan that read nothing is a failure.
    missing = escanear_projeto("/nonexistent/path/xyz")
    assert missing["ok"] is False
    assert missing["arquivos_analisados"] == 0


def test_cli_scan_exit_codes(tmp_path, capsys) -> None:
    """Non-zero only on certain breakage, so it can gate a build."""
    broken = tmp_path / "bad.py"
    broken.write_text('cnpj = int(row["cnpj"])\n', encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 1
    assert "QUEBRA" in capsys.readouterr().out

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "ok.py").write_text("from fiscalkit import is_valid_cnpj\n", encoding="utf-8")
    assert main(["scan", str(clean)]) == 0
    capsys.readouterr()

    assert main(["scan", str(tmp_path / "nope")]) == 2
    capsys.readouterr()


def test_cli_scan_json(tmp_path, capsys) -> None:
    (tmp_path / "s.sql").write_text("CREATE TABLE e (cnpj BIGINT);\n", encoding="utf-8")
    main(["scan", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["pronto_para_2026"] is False
    assert payload["ocorrencias"][0]["regra"] == "CNPJ011"


def test_cli_scan_sarif_always_exits_zero(tmp_path, capsys) -> None:
    """A SARIF upload must succeed even when the scan found problems."""
    (tmp_path / "bad.py").write_text('cnpj = int(row["cnpj"])\n', encoding="utf-8")
    assert main(["scan", str(tmp_path), "--format", "sarif"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["results"]


def test_cli_scan_empty_returns_2(tmp_path, capsys) -> None:
    """An empty scan must not exit 0; silence from looking at nothing is not a pass."""
    (tmp_path / "readme.md").write_text("nothing here\n", encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 2
    assert "nenhum arquivo analisado" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# The MCP protocol itself, not just the functions behind it
# ---------------------------------------------------------------------------


def _call(server, name: str, args: dict) -> str:
    """Round-trip one tool call and return the text content."""
    import asyncio

    result = asyncio.run(server.call_tool(name, args))
    content = result[0] if isinstance(result, tuple) else result
    if hasattr(content, "content"):
        content = content.content
    if isinstance(content, list) and content and hasattr(content[0], "text"):
        return str(content[0].text)
    return str(content)


def test_every_tool_generates_a_usable_schema() -> None:
    """Schema generation is where a bad annotation surfaces, not at call time."""
    pytest.importorskip("mcp")
    import asyncio

    from fiscalkit.mcp.server import build_server

    tools = asyncio.run(build_server().list_tools())
    assert {t.name for t in tools} == set(TOOL_FUNCTIONS)
    for tool in tools:
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {})
        assert schema.get("type") == "object", f"{tool.name} has no object schema"
        for name, prop in schema.get("properties", {}).items():
            # Every parameter must be expressible in JSON Schema; a bare union or
            # an unrepresentable type shows up here as a missing declaration.
            assert "type" in prop or "anyOf" in prop, f"{tool.name}.{name} is untyped"


def test_tools_answer_over_the_protocol() -> None:
    """Calling the function directly is not evidence the tool works over MCP."""
    pytest.importorskip("mcp")

    from fiscalkit.mcp.server import build_server

    server = build_server()
    assert '"valido": true' in _call(server, "validar_cnpj", {"cnpj": "12ABC34501DE35"})
    assert '"total": 27' in _call(server, "listar_ufs", {})
    assert '"uf_sigla": "RS"' in _call(
        server, "decodificar_chave", {"chave": "43240311222333000181550010000001231000000010"}
    )


def test_optional_parameter_may_be_omitted_over_the_protocol() -> None:
    """`linguagem` is optional; omitting it must not be a schema violation."""
    pytest.importorskip("mcp")

    from fiscalkit.mcp.server import build_server

    server = build_server()
    text = _call(server, "escanear_codigo", {"codigo": "from fiscalkit import is_valid_cnpj"})
    assert '"pronto_para_2026": true' in text


def test_invalid_input_is_a_payload_over_the_protocol_too() -> None:
    """The no-exceptions contract has to hold through the transport, not just in-process."""
    pytest.importorskip("mcp")

    from fiscalkit.mcp.server import build_server

    server = build_server()
    assert '"valido": false' in _call(server, "validar_cnpj", {"cnpj": "nope"})
    assert '"valido": false' in _call(server, "decodificar_chave", {"chave": "123"})


def test_precommit_manifest_is_valid() -> None:
    """The hook manifest must satisfy pre-commit's own schema, not just parse."""
    from pathlib import Path

    import yaml

    manifest = Path(__file__).resolve().parents[1] / ".pre-commit-hooks.yaml"
    hooks = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert isinstance(hooks, list) and len(hooks) == 1
    hook = hooks[0]
    assert hook["id"] == "cnpj-2026"
    assert hook["entry"] == "fiscalkit scan"
    assert hook["language"] == "python"
    # pass_filenames must be off: the directory rules and the summary line only
    # behave correctly when the hook is handed the root rather than a file list.
    assert hook["pass_filenames"] is False
    assert hook["args"] == ["."]


def test_action_manifest_declares_what_the_readme_promises() -> None:
    """action.yml is user-facing configuration; its shape is part of the API."""
    from pathlib import Path

    import yaml

    action = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "action.yml").read_text(encoding="utf-8")
    )
    assert action["runs"]["using"] == "composite"
    assert set(action["inputs"]) >= {"path", "fail-on-break", "sarif-file"}
    assert set(action["outputs"]) == {"total", "breaking", "ready"}
    # The scan steps must tolerate a non-zero exit; GitHub runs composite bash
    # steps with -e, and `scan` exits non-zero by design when it finds breakage.
    scan_step = next(s for s in action["runs"]["steps"] if s.get("id") == "scan")
    assert scan_step["run"].count("|| true") >= 2
    # The resolved SARIF path is logged because composite steps run at the
    # workspace root regardless of the caller's working-directory, which is a
    # mismatch that already broke this project's own CI once.
    assert "wrote $(pwd)" in scan_step["run"]
    assert "workspace root" in action["inputs"]["sarif-file"]["description"]


def test_scan_report_lines_stay_within_a_terminal(tmp_path, capsys) -> None:
    """A remediation sentence must wrap instead of running off the screen.

    Several fixes are long enough to reach 140 columns unwrapped, and an
    unwrapped line is precisely the part a reader skips. The wrap also has to
    keep a hanging indent, so the continuation reads as part of the fix rather
    than as a new finding.
    """
    (tmp_path / "f.py").write_text(
        'import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8"
    )
    assert main(["scan", str(tmp_path)]) == 1
    lines = capsys.readouterr().out.splitlines()

    too_long = [ln for ln in lines if len(ln) > 95]
    assert not too_long, f"unwrapped report lines: {too_long}"

    label = next(i for i, ln in enumerate(lines) if "correção:" in ln)
    continuation = lines[label + 1]
    assert continuation.startswith(" " * len("       correção: ")), continuation
    assert continuation.strip(), "the long fix must actually have wrapped"


def test_scan_output_is_written_in_portuguese(tmp_path, capsys) -> None:
    """The chrome and the rule prose must be in one language, not two.

    The CLI addresses Brazilian developers and every other string it prints is
    Portuguese; rule text in English made the report read half-translated.
    """
    (tmp_path / "f.py").write_text(
        'import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8"
    )
    assert main(["scan", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "correção:" in out
    assert "dígitos" in out
    assert "arquivo(s) analisado(s)" in out


def test_every_reason_code_has_a_translation() -> None:
    """A new reason code must not silently fall back to English.

    The codes are discovered from the package source rather than listed here, so
    adding one to a validator without translating it fails this test instead of
    reaching a user as a stray English sentence in a Portuguese report.
    """
    import re
    from pathlib import Path

    import fiscalkit
    from fiscalkit.cli import _REASON_PT

    root = Path(fiscalkit.__file__).parent
    found: set[str] = set()
    for path in root.rglob("*.py"):
        found |= set(re.findall(r'reason="([a-z_]+)"', path.read_text(encoding="utf-8")))

    assert found, "no reason codes discovered -- the search itself is broken"
    missing = found - set(_REASON_PT)
    assert not missing, f"reason codes with no Portuguese translation: {sorted(missing)}"


def test_escanear_projeto_rejects_a_path_that_does_not_exist(tmp_path) -> None:
    """A scan that read nothing must not answer `ok: true`.

    `scan_path` does not raise for a missing path: `rglob` over a directory that
    is not there simply yields nothing. So the `except OSError` branch never fired
    for the case it was written for, and an agent that mistyped a path, or passed
    one relative to the wrong directory, was told the scan succeeded and the
    project was clean. That is the same false all-clear that directory pruning
    once produced, arriving through the agent-facing surface instead of the CLI.
    """
    from fiscalkit.mcp.server import escanear_projeto

    missing = escanear_projeto(str(tmp_path / "nao-existe"))
    assert missing["ok"] is False
    assert "não encontrado" in missing["detalhe"]

    # A real directory with nothing scannable in it is the same failure: the CLI
    # exits 2 for it, and this must not disagree.
    (tmp_path / "leiame.txt").write_text("sem codigo aqui", encoding="utf-8")
    empty = escanear_projeto(str(tmp_path))
    assert empty["ok"] is False
    assert empty["nada_analisado"] is True

    # And a directory that does have something must still succeed.
    (tmp_path / "f.py").write_text(
        'import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8"
    )
    found = escanear_projeto(str(tmp_path))
    assert found["ok"] is True
    assert found["total"] == 1


def test_escanear_projeto_accepts_a_single_file(tmp_path) -> None:
    """The agent-facing tool must handle a file target, like the CLI does."""
    from fiscalkit.mcp.server import escanear_projeto

    target = tmp_path / "f.py"
    target.write_text('import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8")

    result = escanear_projeto(str(target))
    assert result["ok"] is True
    assert result["total"] == 1
    assert result["ocorrencias"][0]["arquivo"] == "f.py"


#: Words that are correct Portuguese only with their accents. Each of these
#: shipped unaccented at some point in this project and had to be corrected by
#: hand, which is why they are enumerated rather than trusted to review.
_UNACCENTED_MISSPELLINGS = (
    "numerico",
    "alfanumerico",
    "digitos",
    "codigo",
    "correcao",
    "ocorrencia",
    "extensao",
    "diretorio",
    "revisao",
    "obrigatorio",
    "analisavel",
    "comecar",
    "padrao",
    "saida",
    "util",
)


def _misspellings_in(text: str) -> list[str]:
    lowered = text.lower()
    return [word for word in _UNACCENTED_MISSPELLINGS if word in lowered]


def test_cli_help_is_written_in_correct_portuguese() -> None:
    """Help text is prose, so an unaccented word there is simply a misspelling.

    Checked against rendered help rather than the source, because the source also
    contains JSON keys and identifiers that are ASCII on purpose -- ``alfanumerico``
    is a correct dict key and a misspelt sentence, depending on where it sits.
    """
    from fiscalkit.cli import build_parser

    parser = build_parser()
    texts = [parser.format_help()]
    # argparse hides subparser help until you ask each one for it.
    for action in parser._actions:  # argparse exposes no public accessor
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            texts.extend(sub.format_help() for sub in choices.values())

    found = {t: _misspellings_in(t) for t in texts}
    bad = {k: v for k, v in found.items() if v}
    assert not bad, (
        f"unaccented Portuguese in CLI help: {sorted({w for v in bad.values() for w in v})}"
    )


def test_mcp_server_instructions_are_written_in_correct_portuguese() -> None:
    """The instructions string is the first thing an agent reads about this tool."""
    pytest.importorskip("mcp", reason="the MCP extra is not installed")
    from fiscalkit.mcp.server import build_server

    instructions = getattr(build_server(), "instructions", "") or ""
    assert instructions, "the server must still carry instructions"
    assert not _misspellings_in(instructions), (
        f"unaccented Portuguese in MCP instructions: {_misspellings_in(instructions)}"
    )


def test_incluir_tudo_controls_pruning_and_the_default_prunes(tmp_path, capsys) -> None:
    """The flag's sense was untested, so inverting it went unnoticed.

    Pruning is not a detail: reading `node_modules` by default makes a scan of any
    real project slow and noisy, and NOT reading it when asked to is how the
    earlier false all-clear happened. Both directions are asserted here because
    the mutation that swaps them is a single dropped `not`.
    """
    (tmp_path / "app").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "app" / "f.py").write_text(
        'import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8"
    )
    (tmp_path / "node_modules" / "dep.js").write_text(
        "var CNPJ_RE = /^\\d{14}$/;\n", encoding="utf-8"
    )

    assert main(["scan", str(tmp_path), "--json"]) == 1
    pruned = json.loads(capsys.readouterr().out)
    assert pruned["arquivos_analisados"] == 1, "the default must skip node_modules"
    assert pruned["arquivos_podados"] == 1
    assert "node_modules" in pruned["diretorios_podados"]

    assert main(["scan", str(tmp_path), "--incluir-tudo", "--json"]) == 1
    everything = json.loads(capsys.readouterr().out)
    assert everything["arquivos_analisados"] == 2, "--incluir-tudo must read node_modules"
    assert everything["arquivos_podados"] == 0


def test_the_failure_reason_goes_to_stderr_and_success_is_quiet(capsys) -> None:
    """`_emit` prints the reason only when the payload reports failure.

    Dropping the `not` from its guard inverts that: reasons on success, silence on
    failure. Nothing caught it, because no test looked at stderr for either case.
    """
    assert main(["cnpj", "11222333000182"]) == 1
    failed = capsys.readouterr()
    assert "motivo:" in failed.err
    assert "não conferem" in failed.err

    assert main(["cnpj", "12ABC34501DE35"]) == 0
    ok = capsys.readouterr()
    assert ok.err == "", f"a successful command must print nothing to stderr: {ok.err!r}"


def test_an_untranslated_reason_code_falls_back_instead_of_crashing(capsys) -> None:
    """The fallback in `_reason_text` had never been reached.

    Every code the library raises has a translation, enforced by its own test, so
    the only way here is a payload from elsewhere. It must degrade to the raw
    detail rather than raise KeyError at the user.
    """
    from fiscalkit.cli import _reason_text

    assert _reason_text({"motivo": "check_digit"}) == "dígitos verificadores não conferem"
    assert _reason_text({"motivo": "codigo_novo", "detalhe": "algo inesperado"}) == (
        "algo inesperado"
    )
    assert _reason_text({"motivo": "codigo_novo"}) == "codigo_novo"


def test_fix_respects_pruning_when_counting_what_remains(tmp_path, capsys) -> None:
    """The re-scan after `--fix` prunes too, so its count means what it says.

    `--fix` scans, patches, then scans again to report what is left for a human.
    That second scan has its own pruning argument, and inverting it makes the
    remaining-work count include vendored dependencies -- telling the user there
    is work left in code they do not own, right after the tool rewrote their
    files. The first scan's pruning was covered; this one was not.
    """
    (tmp_path / "app").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "app" / "f.py").write_text(
        'import re\nCNPJ_RE = re.compile(r"^\\d{14}$")\n', encoding="utf-8"
    )
    (tmp_path / "node_modules" / "dep.js").write_text(
        "var CNPJ_RE = /^\\d{14}$/;\n", encoding="utf-8"
    )

    assert main(["scan", str(tmp_path), "--fix"]) == 0
    out = capsys.readouterr().out
    assert "1 arquivo(s) alterado(s)" in out
    assert "0 ocorrência(s) restante(s)" in out, (
        "the vendored file must not be counted as remaining work"
    )
    # And the vendored file must be untouched.
    assert "\\d{14}" in (tmp_path / "node_modules" / "dep.js").read_text(encoding="utf-8")


def test_readme_has_no_relative_links_because_it_is_the_pypi_page() -> None:
    """`pyproject.toml` sets readme = "README.md", so this file IS the PyPI page.

    PyPI does not resolve relative links against the repository, so `](LICENSE)`
    renders as a link to pypi.org/project/fiscalkit/LICENSE and 404s. The badge
    images were absolute and displayed correctly, which is exactly why nobody
    would notice that their link targets were not.
    """
    import re
    from pathlib import Path

    import fiscalkit

    readme = Path(fiscalkit.__file__).resolve().parents[2] / "README.md"
    if not readme.is_file():
        pytest.skip("README is not on disk beside the package")

    # Markdown links whose target is neither absolute nor an intra-page anchor.
    relative = re.findall(r"\]\((?!https?://|#|mailto:)([^)]+)\)", readme.read_text("utf-8"))
    assert not relative, f"relative links break on the PyPI page: {relative}"


def test_readme_pins_adopters_to_the_version_this_package_is() -> None:
    """The snippets people paste must name the version being shipped.

    The Action snippet said `@main` while the pre-commit one pinned `v0.1.0`, so
    the two disagreed about how to consume the same release, and `@main` told a
    compliance-sensitive codebase to run whatever is on a branch at build time.
    Both are pinned now, and pinned numbers in prose drift on the next release
    exactly the way "twelve rules" did -- so they are checked against
    `__version__` rather than trusted.
    """
    import re
    from pathlib import Path

    import fiscalkit

    readme = Path(fiscalkit.__file__).resolve().parents[2] / "README.md"
    if not readme.is_file():
        pytest.skip("README is not on disk beside the package")
    text = readme.read_text(encoding="utf-8")

    pinned = re.findall(r"williamgritti/fiscalkit@(\S+)", text)
    assert pinned, "the Action snippet must pin a version"
    revs = re.findall(r"^\s*rev:\s*(\S+)", text, re.M)
    assert revs, "the pre-commit snippet must pin a rev"

    expected = f"v{fiscalkit.__version__}"
    wrong = [r for r in pinned + revs if r != expected]
    assert not wrong, f"snippets pin {wrong}, but this package is {expected}"


def test_readme_tool_list_matches_what_the_server_exposes() -> None:
    """The README names every MCP tool and counts them; both drift on the next one.

    An agent user reads that list to decide whether this server does what they
    need, and a tool added without touching the README is invisible to them while
    a tool removed leaves a name that resolves to nothing.
    """
    import re
    from pathlib import Path

    import fiscalkit
    from fiscalkit.mcp.server import TOOL_FUNCTIONS

    readme = Path(fiscalkit.__file__).resolve().parents[2] / "README.md"
    if not readme.is_file():
        pytest.skip("README is not on disk beside the package")
    text = readme.read_text(encoding="utf-8")

    start = text.index("tools are exposed")
    # Bounded to that paragraph. A wider window swept up `mcp` from the sentence
    # about SDK versions further down, which is a backticked lowercase word and
    # not a tool.
    paragraph = text[start : text.index("\n\n", start)]
    listed = set(re.findall(r"`([a-z_]+)`", paragraph))
    exposed = set(TOOL_FUNCTIONS)

    assert listed >= exposed, f"README omits MCP tools: {sorted(exposed - listed)}"
    assert listed <= exposed, f"README names tools that do not exist: {sorted(listed - exposed)}"

    words = {10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen"}
    claimed = text[max(0, start - 20) : start].strip().split()[-1]
    assert claimed.lower() == words.get(len(exposed), str(len(exposed))).lower(), (
        f"README claims {claimed!r} tools; the server exposes {len(exposed)}"
    )
