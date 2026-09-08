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
    assert "NAO" in capsys.readouterr().out


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

    missing = escanear_projeto("/nonexistent/path/xyz")
    assert missing["ok"] is True
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
