"""Independent verification of the `run_dose_response_pipeline` MCP tool (module `cli_wrapper`).

Every call in this file goes through a real FastMCP client
(``async with Client(cli_wrapper_mcp) as client: await client.call_tool(...)``) and reads
``result.data``; the decorated function is never called directly.

Expected-value sources, all independent of the wrapper:
  * ``repo/curve_curator/example_datasets/viability_CTRP_40/curves_40.0.txt`` -- the shipped
    upstream reference from the pinned checkout (71e46f7).
  * ``notebooks/viability_ctrp_40/work/{base,fdr_run1,fdr_run2}`` -- Stage 2 evidence produced by
    running the standalone executable directly, outside the wrapper.

Tolerance policy (see `reports/coordinator-reference-agreement-analysis.md`):
  * ``Curve Regulation`` must match the shipped reference EXACTLY on every curve. It reproduces
    perfectly and is the sharpest available regression signal.
  * Tight numerical tolerances are applied ONLY to curves the pipeline itself classified ``up`` or
    ``down``. Curve parameters of non-significant curves are not reproducible run to run (a nearly
    flat least-squares objective leaves pEC50 weakly identified), so a loose global tolerance would
    hide a real regression in a significant curve. Instead, the number and identity of curves whose
    pEC50 deviates by more than 0.01 is asserted exactly against the Stage 2 observation.
  * ``--fdr`` is verified structurally/statistically only: ``data_simulator`` draws unseeded and no
    seed is exposed anywhere in this CLI, so no exact FDR or decoy value can be asserted.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tools import cli_wrapper as cli_wrapper_module  # noqa: E402
from tools.cli_wrapper import cli_wrapper_mcp  # noqa: E402

TOOL = "run_dose_response_pipeline"

EXECUTABLE = PROJECT_ROOT / ".venv" / "bin" / "CurveCurator"
REFERENCE_DIR = PROJECT_ROOT / "repo" / "curve_curator" / "example_datasets" / "viability_CTRP_40"
STAGE2_BASE = PROJECT_ROOT / "notebooks" / "viability_ctrp_40" / "work" / "base"
STAGE2_FDR1 = PROJECT_ROOT / "notebooks" / "viability_ctrp_40" / "work" / "fdr_run1"
STAGE2_FDR2 = PROJECT_ROOT / "notebooks" / "viability_ctrp_40" / "work" / "fdr_run2"

# Scratch tree for this verification run; tmp/ is gitignored project scratch space.
WORK_ROOT = PROJECT_ROOT / "tmp" / "verify_cli_wrapper"
INPUTS = WORK_ROOT / "inputs"
INPUTS_WITH_SPACES = WORK_ROOT / "inputs with spaces"
OUTPUTS = WORK_ROOT / "outputs"
OUTPUTS_WITH_SPACES = WORK_ROOT / "outputs with spaces"

# The 155 KiB viability example is the fastest reference example; a run still takes ~5 min on this
# box, so every full pipeline invocation is a session-scoped fixture and is reused by many tests.
LONG_TIMEOUT = 3000
FDR_TIMEOUT = 5400

EXPECTED_CURVES = 1211
EXPECTED_EXPERIMENTS = 17  # ['Experiment'] experiments = [0..16]
EXPECTED_CLI_VERSION = "0.6.0"

# Bounds stated up front, not tuned to make the suite pass. Observed maxima on the 539 significant
# curves of this example, produced-vs-shipped-reference: pEC50 1.99e-06, Curve Slope 3.03e-05,
# every other listed column <= 3.41e-06; the fitted-parameter standard errors reach 1.62e-03.
SIG_TOL = 1e-4
SIG_TOL_PEC50 = 1e-5
SIG_TOL_ERRORS = 1e-2
CORE_COLUMNS = [
    "pEC50",
    "Curve Slope",
    "Curve Front",
    "Curve Back",
    "Curve Fold Change",
    "Curve AUC",
    "Curve RMSE",
    "Curve R2",
    "Curve F_Value",
    "Curve P_Value",
    "Curve Log P_Value",
    "Curve F_Value SAM Corrected",
    "Curve Relevance Score",
]
ERROR_COLUMNS = ["pEC50 Error", "Curve Slope Error", "Curve Front Error", "Curve Back Error"]
# The single non-significant curve whose pEC50 is not reproducible, established at Stage 2.
KNOWN_UNSTABLE_CURVES = {"GSU_NPC-26"}


# --------------------------------------------------------------------------------------- utilities


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def call_tool(arguments: dict, raise_on_error: bool = True):
    """Invoke the tool through a real MCP client and return the CallToolResult."""

    async def _run():
        async with Client(cli_wrapper_mcp) as client:
            return await client.call_tool(TOOL, arguments, raise_on_error=raise_on_error)

    return asyncio.run(_run())


def call_data(arguments: dict) -> dict:
    """Invoke the tool through MCP and return `result.data` for a successful call."""
    return call_tool(arguments).data


def list_tools():
    async def _run():
        async with Client(cli_wrapper_mcp) as client:
            return await client.list_tools()

    return asyncio.run(_run())


def artifact_path(result: dict, basename: str) -> Path:
    matches = [Path(entry["path"]) for entry in result["artifacts"] if Path(entry["path"]).name == basename]
    assert matches, f"artifact {basename!r} missing from {[Path(e['path']).name for e in result['artifacts']]}"
    assert len(matches) == 1, f"artifact {basename!r} returned more than once"
    return matches[0]


def read_curves(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t")


def assert_positionally_aligned(left: pd.DataFrame, right: pd.DataFrame) -> None:
    """Align two curves tables by row order.

    Never join on `Name`: kinobeads_Dasatinib/curves.txt carries a duplicated Name (TMPO), so an
    index join cross-expands and compares mismatched row pairs.
    """
    assert len(left) == len(right), f"row counts differ: {len(left)} vs {len(right)}"
    mismatched = [
        (i, a, b) for i, (a, b) in enumerate(zip(left["Name"].tolist(), right["Name"].tolist())) if a != b
    ]
    assert not mismatched, f"identifier sequence differs position-by-position, first: {mismatched[:3]}"


def _section_header(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped.strip("[]").strip().strip("'\"")
    return None


def drop_section(text: str, section: str) -> str:
    kept, dropping = [], False
    for line in text.splitlines():
        header = _section_header(line)
        if header is not None:
            dropping = header == section
        if not dropping:
            kept.append(line)
    return "\n".join(kept) + "\n"


def drop_assignments(text: str, section: str, keys: set[str]) -> str:
    kept, in_section = [], False
    for line in text.splitlines():
        header = _section_header(line)
        if header is not None:
            in_section = header == section
            kept.append(line)
            continue
        match = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
        if in_section and match and match.group(1) in keys:
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def replace_assignment(text: str, section: str, key: str, value: str) -> str:
    out, in_section, replaced = [], False, False
    for line in text.splitlines():
        header = _section_header(line)
        if header is not None:
            in_section = header == section
            out.append(line)
            continue
        match = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
        if in_section and match and match.group(1) == key:
            out.append(f"{key} = {value}")
            replaced = True
            continue
        out.append(line)
    assert replaced, f"{key} not found in [{section}]"
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def inputs() -> dict:
    """Independent working copies of the viability example plus derived broken variants."""
    for directory in (INPUTS, INPUTS_WITH_SPACES, OUTPUTS, OUTPUTS_WITH_SPACES):
        directory.mkdir(parents=True, exist_ok=True)

    source_toml = STAGE2_BASE / "parameters_40.0.toml"
    source_data = STAGE2_BASE / "dose_responses_40.0.tsv"
    original = source_toml.read_text(encoding="utf-8")

    toml = INPUTS / "parameters_40.0.toml"
    data = INPUTS / "dose_responses_40.0.tsv"
    toml.write_text(original, encoding="utf-8")
    data.write_bytes(source_data.read_bytes())

    # Only ['Paths'] input_file declared: exercises the upstream default output basenames
    # (curves.txt / dashboard.html from toml_parser.set_default_values). Placed in a directory
    # whose name contains spaces, together with its own copy of the input table.
    minimal = drop_assignments(
        original,
        "Paths",
        {"curves_file", "decoys_file", "fdr_file", "normalization_file", "mad_file", "dashboard"},
    )
    minimal_toml = INPUTS_WITH_SPACES / "parameters with spaces.toml"
    minimal_toml.write_text(minimal, encoding="utf-8")
    (INPUTS_WITH_SPACES / "dose_responses_40.0.tsv").write_bytes(source_data.read_bytes())

    broken = WORK_ROOT / "broken"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "dose_responses_40.0.tsv").write_bytes(source_data.read_bytes())

    no_paths = broken / "no_paths_section.toml"
    no_paths.write_text(drop_section(original, "Paths"), encoding="utf-8")

    no_input_key = broken / "no_input_file_key.toml"
    no_input_key.write_text(drop_assignments(original, "Paths", {"input_file"}), encoding="utf-8")

    missing_input = broken / "missing_input_file.toml"
    missing_input.write_text(
        replace_assignment(original, "Paths", "input_file", "'./absent_table.tsv'"), encoding="utf-8"
    )

    malformed = broken / "malformed.toml"
    malformed.write_text("['Meta'\nid = 'unterminated\n", encoding="utf-8")

    # Passes every wrapper pre-check, but toml_parser.check_toml_params raises and __main__ calls a
    # bare exit() -> SystemExit(None) -> process exit status 0 with no outputs at all.
    no_meta = broken / "no_meta_section.toml"
    no_meta.write_text(drop_section(original, "Meta"), encoding="utf-8")

    # Same exit-0 trap from a different upstream site: ui.verify_columns_exist -> exit().
    bad_columns_dir = WORK_ROOT / "bad_columns"
    bad_columns_dir.mkdir(parents=True, exist_ok=True)
    lines = source_data.read_text(encoding="utf-8").splitlines()
    header = ["BOGUS_" + col if col.startswith("Raw") else col for col in lines[0].split("\t")]
    lines[0] = "\t".join(header)
    (bad_columns_dir / "dose_responses_40.0.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bad_columns_toml = bad_columns_dir / "parameters_40.0.toml"
    bad_columns_toml.write_text(original, encoding="utf-8")

    not_toml = broken / "parameters_40.0.txt"
    not_toml.write_text(original, encoding="utf-8")

    return {
        "toml": toml,
        "data": data,
        "toml_sha": _sha256(toml),
        "data_sha": _sha256(data),
        "minimal_toml": minimal_toml,
        "minimal_data_sha": _sha256(INPUTS_WITH_SPACES / "dose_responses_40.0.tsv"),
        "no_paths": no_paths,
        "no_input_key": no_input_key,
        "missing_input": missing_input,
        "malformed": malformed,
        "no_meta": no_meta,
        "bad_columns": bad_columns_toml,
        "not_toml": not_toml,
    }


@pytest.fixture(scope="session")
def base_run(inputs) -> dict:
    """One real pipeline run, no flags, through MCP."""
    return call_data(
        {"toml_path": str(inputs["toml"]), "output_dir": str(OUTPUTS), "timeout_seconds": LONG_TIMEOUT}
    )


@pytest.fixture(scope="session")
def mad_run(inputs) -> dict:
    return call_data(
        {
            "toml_path": str(inputs["toml"]),
            "run_mad": True,
            "output_dir": str(OUTPUTS),
            "timeout_seconds": LONG_TIMEOUT,
        }
    )


@pytest.fixture(scope="session")
def fdr_run(inputs) -> dict:
    return call_data(
        {
            "toml_path": str(inputs["toml"]),
            "estimate_fdr": True,
            "output_dir": str(OUTPUTS),
            "timeout_seconds": FDR_TIMEOUT,
        }
    )


@pytest.fixture(scope="session")
def spaces_run(inputs) -> dict:
    """A TOML declaring only input_file, run from and into directories whose names have spaces."""
    return call_data(
        {
            "toml_path": str(inputs["minimal_toml"]),
            "output_dir": str(OUTPUTS_WITH_SPACES),
            "timeout_seconds": LONG_TIMEOUT,
        }
    )


@pytest.fixture(scope="session")
def all_runs(base_run, mad_run, fdr_run, spaces_run) -> list[dict]:
    return [base_run, mad_run, fdr_run, spaces_run]


@pytest.fixture
def clean_identity_cache():
    """Isolate the module's executable-identity cache so an override cannot leak between tests."""
    saved = dict(cli_wrapper_module._executable_identity)
    yield
    cli_wrapper_module._executable_identity.clear()
    cli_wrapper_module._executable_identity.update(saved)


# ------------------------------------------------------------------- tool contract / format review


def test_tool_is_exposed_with_the_declared_schema():
    tools = list_tools()
    assert [tool.name for tool in tools] == [TOOL]
    schema = tools[0].inputSchema
    assert set(schema["properties"]) == {
        "toml_path",
        "estimate_fdr",
        "run_mad",
        "output_dir",
        "timeout_seconds",
    }
    assert schema.get("required") == ["toml_path"]
    for name, prop in schema["properties"].items():
        assert prop.get("description"), f"parameter {name} has no Annotated description"
    assert schema["properties"]["estimate_fdr"]["type"] == "boolean"
    assert schema["properties"]["run_mad"]["type"] == "boolean"
    assert schema["properties"]["timeout_seconds"]["type"] == "integer"
    assert schema["properties"]["estimate_fdr"]["default"] is False
    assert schema["properties"]["run_mad"]["default"] is False
    assert schema["properties"]["timeout_seconds"]["default"] == 3600
    assert schema["properties"]["output_dir"]["default"] is None
    description = tools[0].description or ""
    assert len([line for line in description.strip().splitlines() if line.strip()]) == 2


def test_wrapper_does_not_reimplement_any_scientific_computation():
    """No curve fitting, thresholding, FDR or MAD maths may live in the wrapper."""
    source = (PROJECT_ROOT / "src" / "tools" / "cli_wrapper.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import scipy", "import pandas", "import curve_curator", "from curve_curator"):
        assert banned not in source, f"wrapper imports scientific code: {banned}"
    for banned in ("np.", "scipy.", "curve_fit", "least_squares", "logistic", "np.median"):
        assert banned not in source, f"wrapper appears to compute science itself: {banned}"
    # The only way the science can run is the external executable, with shell=False.
    assert source.count("subprocess.run(") == 2  # the -h identity probe and the pipeline run
    assert "shell=True" not in source
    assert source.count("shell=False") == 2


# ------------------------------------------------------------------------------ successful base run


@pytest.mark.slow
def test_base_run_returns_the_declared_contract(base_run):
    assert base_run["exit_code"] == 0
    assert base_run["cli_version"] == EXPECTED_CLI_VERSION
    assert base_run["num_curves"] == EXPECTED_CURVES
    assert base_run["estimate_fdr"] is False
    assert base_run["run_mad"] is False
    assert base_run["reference"].endswith("curve_curator/__main__.py")
    assert "71e46f7222f825f446e9aff3fb5a3bee9473e309" in base_run["reference"]
    assert EXPECTED_CLI_VERSION in base_run["message"]
    assert base_run["runtime_seconds"] > 0
    # No FDR/MAD keys may appear when the flags were not requested.
    assert "fdr" not in base_run and "num_decoy_curves" not in base_run and "mad" not in base_run

    assert base_run["command"][0] == str(EXECUTABLE.resolve())
    assert "--fdr" not in base_run["command"] and "--mad" not in base_run["command"]
    assert Path(base_run["command"][-1]) == Path(base_run["output_dir"]) / "parameters_40.0.toml"
    assert len(base_run["command"]) == 2

    run_dir = Path(base_run["output_dir"])
    assert run_dir.is_dir() and run_dir.parent == OUTPUTS
    assert run_dir.name.startswith("curvecurator_")

    for entry in base_run["artifacts"]:
        path = Path(entry["path"])
        assert path.is_absolute(), f"artifact path not absolute: {path}"
        assert path.is_file(), f"artifact missing on disk: {path}"
        assert path.stat().st_size > 0, f"artifact empty: {path}"
        assert entry["description"]
    names = {Path(entry["path"]).name for entry in base_run["artifacts"]}
    assert {
        "curves_40.0.txt",
        "dashboard_40.0.html",
        "curveCurator.log",
        "parameters_40.0.toml",
        "cli_stdout.log",
        "cli_stderr.log",
    } <= names
    # normalization = true is not set in this TOML, so upstream writes no normalization file.
    assert "normalization_factors_40.0.txt" not in names
    # Flags were not requested, so no decoy/fdr/mad artifact may be claimed.
    assert not {"decoys_40.0.txt", "fdr_40.0.txt", "mad_40.0.txt"} & names


@pytest.mark.slow
def test_base_run_reproduces_the_stage2_standalone_run_byte_for_byte(base_run):
    """The wrapper's curves table must equal the table produced by the standalone command."""
    produced = artifact_path(base_run, "curves_40.0.txt")
    assert _sha256(produced) == _sha256(STAGE2_BASE / "curves_40.0.txt")


@pytest.mark.slow
def test_base_run_agrees_with_the_shipped_upstream_reference(base_run):
    produced = read_curves(artifact_path(base_run, "curves_40.0.txt"))
    reference = read_curves(REFERENCE_DIR / "curves_40.0.txt")
    assert_positionally_aligned(reference, produced)
    assert list(produced.columns) == list(reference.columns)
    assert len(produced) == EXPECTED_CURVES

    # Sharpest available signal: the pipeline's own verdict must match exactly on every curve.
    ref_reg = reference["Curve Regulation"].fillna("<none>").tolist()
    new_reg = produced["Curve Regulation"].fillna("<none>").tolist()
    assert new_reg == ref_reg

    # Input passthrough columns must be bit-exact.
    passthrough = [c for c in produced.columns if c.startswith(("Raw ", "Ratio "))] + [
        "N duplicates",
        "Signal Quality",
        "Null RMSE",
    ]
    for column in passthrough:
        assert np.array_equal(
            reference[column].to_numpy(), produced[column].to_numpy(), equal_nan=True
        ), f"passthrough column {column} changed"

    significant = produced["Curve Regulation"].isin(["up", "down"]).to_numpy()
    assert significant.sum() == 539

    # Tight tolerances apply ONLY to curves classified up/down (see the module docstring).
    for column in CORE_COLUMNS:
        assert (reference[column].isna().to_numpy() == produced[column].isna().to_numpy()).all(), (
            f"nonfinite pattern differs in {column}"
        )
        delta = np.abs(reference[column].to_numpy() - produced[column].to_numpy())
        worst = np.nanmax(delta[significant])
        tolerance = SIG_TOL_PEC50 if column == "pEC50" else SIG_TOL
        assert worst <= tolerance, f"significant curves deviate in {column}: {worst:.3e} > {tolerance:.0e}"
    for column in ERROR_COLUMNS:
        delta = np.abs(reference[column].to_numpy() - produced[column].to_numpy())
        worst = np.nanmax(delta[significant])
        assert worst <= SIG_TOL_ERRORS, f"significant curves deviate in {column}: {worst:.3e}"

    # Non-significant curves: assert the exact set of poorly identified fits observed at Stage 2
    # rather than widening the tolerance, which would mask a regression in a significant curve.
    delta_pec50 = np.abs(reference["pEC50"].to_numpy() - produced["pEC50"].to_numpy())
    drifting = set(produced["Name"].to_numpy()[delta_pec50 > 0.01])
    assert drifting == KNOWN_UNSTABLE_CURVES
    assert not significant[delta_pec50 > 0.01].any()


@pytest.mark.slow
def test_base_run_dashboard_is_a_bokeh_html_document(base_run):
    dashboard = artifact_path(base_run, "dashboard_40.0.html")
    head = dashboard.read_text(encoding="utf-8", errors="replace")[:4000].lower()
    assert "<!doctype html>" in head
    assert "bokeh" in head
    assert dashboard.stat().st_size > 100_000


@pytest.mark.slow
def test_staged_parameter_file_is_a_faithful_copy_with_absolute_paths(base_run, inputs):
    staged = artifact_path(base_run, "parameters_40.0.toml")
    assert staged.parent == Path(base_run["output_dir"])
    import tomllib

    with open(staged, "rb") as handle:
        config = tomllib.load(handle)
    original_text = inputs["toml"].read_text(encoding="utf-8")
    with open(inputs["toml"], "rb") as handle:
        original = tomllib.load(handle)
    # Every non-Paths section must survive the text rewrite untouched: no scientific parameter may
    # be altered, added or dropped by the staging step.
    for section, values in original.items():
        if section == "Paths":
            continue
        assert config[section] == values, f"staging changed [{section}]"
    assert set(config) == set(original)
    for key, value in base_run["resolved_paths"].items():
        assert config["Paths"][key] == value
        assert os.path.isabs(value)
    assert config["Paths"]["input_file"] == str(inputs["data"])
    # Outputs all land inside the fresh per-call directory; the input is referenced in place.
    for key, value in base_run["resolved_paths"].items():
        if key == "input_file":
            continue
        assert Path(value).parent == Path(base_run["output_dir"])
    # Comments and every other line of the user's file are preserved verbatim.
    assert "# Paramters for the datanalysis pipeline" in staged.read_text(encoding="utf-8")
    assert "Paramters for the datanalysis pipeline" in original_text


# --------------------------------------------------------------------------------- --mad (flagged)


@pytest.mark.slow
def test_mad_run_returns_mad_artifact_and_parsed_values(mad_run, inputs):
    assert mad_run["exit_code"] == 0
    assert mad_run["run_mad"] is True
    assert "--mad" in mad_run["command"] and "--fdr" not in mad_run["command"]
    mad_file = artifact_path(mad_run, "mad_40.0.txt")
    assert mad_file.stat().st_size > 0

    values = mad_run["mad"]
    assert set(values) == {f"Ratio {i}" for i in range(EXPECTED_EXPERIMENTS)}
    for name, value in values.items():
        assert np.isfinite(value), f"{name} MAD is not finite"
        assert value > 0, f"{name} MAD is not positive"

    # The reported dict must match the file the CLI actually wrote, not a wrapper computation.
    on_disk = {}
    for line in mad_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, raw = line.rpartition("\t")
        on_disk[name.strip()] = float(raw)
    assert on_disk == pytest.approx(values)
    assert "fdr" not in mad_run and "num_decoy_curves" not in mad_run


@pytest.mark.slow
def test_mad_run_leaves_the_curves_table_identical_to_the_base_run(mad_run, base_run):
    """--mad is a quality-control side analysis: it must not perturb the fits."""
    assert _sha256(artifact_path(mad_run, "curves_40.0.txt")) == _sha256(
        artifact_path(base_run, "curves_40.0.txt")
    )
    assert mad_run["num_curves"] == base_run["num_curves"] == EXPECTED_CURVES


# --------------------------------------------------------------------------------- --fdr (flagged)


@pytest.mark.slow
def test_fdr_run_produces_the_decoy_and_fdr_contract(fdr_run):
    """Structural/statistical only: data_simulator draws unseeded, so no value is reproducible."""
    assert fdr_run["exit_code"] == 0
    assert fdr_run["estimate_fdr"] is True
    assert "--fdr" in fdr_run["command"] and "--mad" not in fdr_run["command"]

    decoys = artifact_path(fdr_run, "decoys_40.0.txt")
    fdr_file = artifact_path(fdr_run, "fdr_40.0.txt")
    assert decoys.stat().st_size > 0 and fdr_file.stat().st_size > 0

    # ['F Statistic'] decoy_ratio defaults to 1.0, so one decoy per target curve.
    assert fdr_run["num_curves"] == EXPECTED_CURVES
    assert fdr_run["num_decoy_curves"] == EXPECTED_CURVES

    values = fdr_run["fdr"]
    assert set(values) == {"global_fdr", "filtered_fdr"}
    for name, value in values.items():
        assert np.isfinite(value), f"{name} is not finite"
        assert 0.0 <= value <= 1.0, f"{name}={value} outside [0, 1]"
    text = fdr_file.read_text(encoding="utf-8")
    assert re.search(r"Global FDR:\s*\S+", text)
    assert re.search(r"Filtered FDR:\s*\S+", text)

    decoy_table = read_curves(decoys)
    assert len(decoy_table) == EXPECTED_CURVES
    assert "Curve Regulation" in decoy_table.columns


@pytest.mark.slow
def test_fdr_run_adds_qvalues_without_changing_the_target_fits(fdr_run, base_run):
    """Proven at Stage 2: --fdr leaves target fits bit-identical; only decoy-derived output moves."""
    produced = read_curves(artifact_path(fdr_run, "curves_40.0.txt"))
    base = read_curves(artifact_path(base_run, "curves_40.0.txt"))
    assert_positionally_aligned(base, produced)
    assert [c for c in produced.columns if c not in base.columns] == ["Decoy", "Curve q_Value"]

    for column in CORE_COLUMNS:
        delta = np.abs(base[column].to_numpy() - produced[column].to_numpy())
        assert np.nanmax(delta) == 0.0, f"--fdr changed target column {column}"
    assert (
        produced["Curve Regulation"].fillna("<none>").tolist()
        == base["Curve Regulation"].fillna("<none>").tolist()
    )

    qvalues = produced["Curve q_Value"].to_numpy()
    finite = qvalues[np.isfinite(qvalues)]
    assert finite.size > 0
    assert finite.min() >= 0.0 and finite.max() <= 1.0

    # Decoy-derived output is genuinely run-dependent: the two Stage 2 runs disagree, which is why
    # no exact FDR or decoy value is asserted anywhere in this file.
    stage2_q1 = read_curves(STAGE2_FDR1 / "curves_40.0.txt")["Curve q_Value"].to_numpy()
    stage2_q2 = read_curves(STAGE2_FDR2 / "curves_40.0.txt")["Curve q_Value"].to_numpy()
    assert np.nanmax(np.abs(stage2_q1 - stage2_q2)) > 0.0


# ------------------------------------------------------ default output basenames + paths with spaces


@pytest.mark.slow
def test_paths_with_spaces_and_upstream_default_output_names(spaces_run, base_run, inputs):
    assert spaces_run["exit_code"] == 0
    assert " " in spaces_run["source_toml"]
    assert " " in spaces_run["output_dir"]
    assert " " in spaces_run["input_file"]
    run_dir = Path(spaces_run["output_dir"])
    assert run_dir.is_dir() and run_dir.parent == OUTPUTS_WITH_SPACES

    # This TOML declares only ['Paths'] input_file, so the basenames come from
    # toml_parser.set_default_values(), not from the wrapper inventing names.
    names = {Path(entry["path"]).name for entry in spaces_run["artifacts"]}
    assert {"curves.txt", "dashboard.html", "parameters with spaces.toml"} <= names
    assert spaces_run["num_curves"] == EXPECTED_CURVES

    # Same data and same scientific parameters as the base run: only the output names differ.
    assert _sha256(artifact_path(spaces_run, "curves.txt")) == _sha256(
        artifact_path(base_run, "curves_40.0.txt")
    )


# ---------------------------------------------------------------------------------- repeated calls


@pytest.mark.slow
def test_repeated_calls_get_isolated_fresh_output_directories(all_runs):
    run_dirs = [run["output_dir"] for run in all_runs]
    assert len(set(run_dirs)) == len(run_dirs), f"output directories collided: {run_dirs}"
    seen: dict[str, str] = {}
    for run in all_runs:
        for entry in run["artifacts"]:
            path = entry["path"]
            assert path not in seen, f"artifact path reused across calls: {path}"
            seen[path] = run["output_dir"]
            assert path.startswith(run["output_dir"] + os.sep)
    # Each call executed its own staged parameter file inside its own directory.
    for run in all_runs:
        assert Path(run["command"][-1]).parent == Path(run["output_dir"])


@pytest.mark.slow
def test_user_inputs_are_never_modified(all_runs, inputs):
    assert _sha256(inputs["toml"]) == inputs["toml_sha"]
    assert _sha256(inputs["data"]) == inputs["data_sha"]
    assert _sha256(INPUTS_WITH_SPACES / "dose_responses_40.0.tsv") == inputs["minimal_data_sha"]
    # No pipeline output may have been dropped next to the user's files.
    assert sorted(p.name for p in INPUTS.iterdir()) == [
        "dose_responses_40.0.tsv",
        "parameters_40.0.toml",
    ]
    assert sorted(p.name for p in INPUTS_WITH_SPACES.iterdir()) == [
        "dose_responses_40.0.tsv",
        "parameters with spaces.toml",
    ]


@pytest.mark.slow
def test_pinned_source_and_stage2_evidence_are_untouched(all_runs):
    for tree in ("repo/curve_curator", "notebooks"):
        status = subprocess.run(
            ["git", "status", "--short", "--", "."] if tree == "notebooks" else ["git", "status", "--short"],
            cwd=str(PROJECT_ROOT / tree),
            capture_output=True,
            text=True,
            check=True,
        )
        assert status.stdout.strip() == "", f"{tree} was modified: {status.stdout}"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(PROJECT_ROOT / "repo" / "curve_curator"),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == "71e46f7222f825f446e9aff3fb5a3bee9473e309"


# ------------------------------------------------------------------------ failures must be MCP errors


def test_missing_toml_file_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(WORK_ROOT / "does_not_exist.toml")})
    assert "not found" in str(excinfo.value)


def test_non_toml_input_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["not_toml"])})
    assert ".toml" in str(excinfo.value)


def test_malformed_toml_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["malformed"]), "output_dir": str(OUTPUTS)})
    assert "not a valid TOML" in str(excinfo.value)


def test_toml_without_paths_section_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["no_paths"]), "output_dir": str(OUTPUTS)})
    assert "Paths" in str(excinfo.value)


def test_toml_without_input_file_key_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["no_input_key"]), "output_dir": str(OUTPUTS)})
    assert "input_file" in str(excinfo.value)


def test_nonexistent_declared_input_file_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["missing_input"]), "output_dir": str(OUTPUTS)})
    message = str(excinfo.value)
    assert "does not exist" in message
    assert "absent_table.tsv" in message


def test_zero_exit_with_no_outputs_is_still_an_mcp_error(inputs):
    """The single most important check.

    curve_curator/toml_parser.py reports a rejected parameter file with ui.error() followed by a
    bare exit(), i.e. SystemExit(None) -> process exit status 0. Exit status alone therefore cannot
    mean success, and this must surface as an MCP error, never as a successful transport carrying an
    error-shaped dict.
    """
    arguments = {"toml_path": str(inputs["no_meta"]), "output_dir": str(OUTPUTS)}
    with pytest.raises(ToolError) as excinfo:
        call_tool(arguments)
    message = str(excinfo.value)
    assert "exited without producing its declared outputs" in message, message
    assert "curves" in message and "dashboard" in message

    # And the transport itself must mark it as an error rather than returning data.
    result = call_tool(arguments, raise_on_error=False)
    assert result.is_error is True
    assert result.data is None
    rendered = "".join(getattr(block, "text", "") for block in result.content)
    assert "exited without producing its declared outputs" in rendered

    # Independent confirmation that the underlying process really did exit 0 here.
    run_dirs = sorted(OUTPUTS.glob("curvecurator_*"))
    trap_dirs = [d for d in run_dirs if (d / "no_meta_section.toml").is_file()]
    assert trap_dirs, "no staged run directory found for the exit-0 case"
    latest = max(trap_dirs, key=lambda d: d.stat().st_mtime)
    assert not (latest / "curves_40.0.txt").exists()
    assert not (latest / "dashboard_40.0.html").exists()
    stderr = (latest / "cli_stderr.log").read_text(encoding="utf-8")
    assert "[Meta] section is missing" in stderr
    direct = subprocess.run(
        [str(EXECUTABLE), str(latest / "no_meta_section.toml")],
        cwd=str(latest),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert direct.returncode == 0, "upstream quirk no longer reproduces; revisit the post-condition"


def test_malformed_input_table_is_an_mcp_error(inputs):
    """Second exit-0 trap: ui.verify_columns_exist() -> exit() after the data are loaded."""
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["bad_columns"]), "output_dir": str(OUTPUTS)})
    message = str(excinfo.value)
    assert "exited without producing its declared outputs" in message
    assert "was not found in your data" in message


def test_nonpositive_timeout_is_an_mcp_error(inputs):
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["toml"]), "timeout_seconds": 0, "output_dir": str(OUTPUTS)})
    assert "timeout_seconds" in str(excinfo.value)


def test_timeout_terminates_the_process_and_raises_an_mcp_error(inputs):
    """A full run of this example takes ~5 min, so a 5 s budget must be reported as a timeout."""
    with pytest.raises(ToolError) as excinfo:
        call_tool(
            {"toml_path": str(inputs["toml"]), "output_dir": str(OUTPUTS), "timeout_seconds": 5}
        )
    message = str(excinfo.value)
    assert "did not finish within 5 s" in message
    assert "Increase timeout_seconds" in message


def test_default_output_directory_is_used_when_none_is_given(inputs):
    """output_dir=None must resolve to <project root>/outputs, created per call."""
    default_base = PROJECT_ROOT / "outputs"
    before = set(default_base.glob("curvecurator_*")) if default_base.exists() else set()
    with pytest.raises(ToolError):
        call_tool({"toml_path": str(inputs["no_meta"])})
    after = set(default_base.glob("curvecurator_*"))
    created = after - before
    assert len(created) == 1, f"expected exactly one fresh run directory, got {created}"
    new_dir = created.pop()
    assert (new_dir / "no_meta_section.toml").is_file()
    shutil.rmtree(new_dir)


# ------------------------------------------------------------------------------ executable identity


@pytest.mark.parametrize("program", ["true", "echo", "ls"])
def test_wrong_runtime_override_is_rejected(monkeypatch, clean_identity_cache, inputs, program):
    """An executable bit plus exit code 0 must not be accepted as a CurveCurator runtime.

    `true` exits 0 with no output at all, and `echo -h` / `ls -h` exit 0 with plausible-looking
    output; none of them may be silently accepted.
    """
    override = shutil.which(program)
    if not override:
        pytest.skip(f"{program} not present on this system")
    monkeypatch.setenv(cli_wrapper_module.EXECUTABLE_ENV_VAR, override)
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["toml"]), "output_dir": str(OUTPUTS)})
    assert "not a usable CurveCurator runtime" in str(excinfo.value)
    assert str(Path(override).resolve()) not in cli_wrapper_module._executable_identity


def test_nonexistent_executable_override_is_rejected(monkeypatch, clean_identity_cache, inputs):
    monkeypatch.setenv(cli_wrapper_module.EXECUTABLE_ENV_VAR, str(WORK_ROOT / "no_such_binary"))
    with pytest.raises(ToolError) as excinfo:
        call_tool({"toml_path": str(inputs["toml"]), "output_dir": str(OUTPUTS)})
    assert "does not point to an existing file" in str(excinfo.value)


def test_pinned_executable_identity_matches_the_recorded_version(clean_identity_cache):
    executable, version = cli_wrapper_module._resolve_executable()
    assert executable == str(EXECUTABLE.resolve())
    assert version == EXPECTED_CLI_VERSION
    probe = subprocess.run([executable, "-h"], capture_output=True, text=True, timeout=120)
    assert probe.returncode == 0
    assert f"CurveCurator (v{EXPECTED_CLI_VERSION})" in re.sub(r"\x1b\[[0-9;]*m", "", probe.stdout)
