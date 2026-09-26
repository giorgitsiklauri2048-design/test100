"""Tools extracted from repo/curve_curator/curve_curator/__main__.py (the CurveCurator command-line pipeline)."""

import os
import re
import shutil
import subprocess
import time
import tomllib
import uuid
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

REFERENCE = "https://github.com/kusterlab/curve_curator/blob/71e46f7222f825f446e9aff3fb5a3bee9473e309/curve_curator/__main__.py"

cli_wrapper_mcp = FastMCP(name="cli_wrapper")

# For the src/tools/<module>.py layout the generated project root is two levels up from this file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Console entry point installed into the project environment (curve_curator 0.6.0, pinned checkout
# repo/curve_curator @ 71e46f7222f825f446e9aff3fb5a3bee9473e309). CURVECURATOR_EXECUTABLE overrides it.
EXECUTABLE_ENV_VAR = "CURVECURATOR_EXECUTABLE"
EXECUTABLE_CANDIDATES = (
    PROJECT_ROOT / ".venv" / "bin" / "CurveCurator",
    PROJECT_ROOT / "curve_curator-env" / "bin" / "CurveCurator",
)

# `CurveCurator -h` is the only supported identity invocation; the program has no --version flag.
# Its argparse description renders as "CurveCurator (v0.6.0)".
_IDENTITY_RE = re.compile(r"CurveCurator\s*\(v(?P<version>[^)]+)\)")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# curve_curator/toml_parser.py resolves every ['Paths'] entry relative to the toml file's own
# directory and skips entries that are already absolute (update_toml_paths:
# `if not os.path.isabs(path)`), so absolute entries are passed through unchanged.
INPUT_PATH_KEY = "input_file"
# Output entries and the basenames toml_parser.set_default_values() falls back to when the user's
# toml omits them. Redirected into the fresh per-call run directory, keeping the user's own basename
# when the toml declares one (the shipped examples use suffixed names such as curves_40.0.txt).
OUTPUT_PATH_DEFAULTS = {
    "curves_file": "curves.txt",
    "decoys_file": "decoys.txt",
    "fdr_file": "fdr.txt",
    "mad_file": "mad.txt",
    "dashboard": "dashboard.html",
}
# set_default_values() gives normalization_file no default, so quantification.run_pipeline writes it
# only when the user's toml declares it. It is therefore redirected only when already present.
OPTIONAL_OUTPUT_KEYS = ("normalization_file",)
ALL_PATH_KEYS = (INPUT_PATH_KEY, *OUTPUT_PATH_DEFAULTS, *OPTIONAL_OUTPUT_KEYS)

# user_interface.setup_logger() always writes this next to the toml file that is executed.
LOG_FILENAME = "curveCurator.log"
STDOUT_FILENAME = "cli_stdout.log"
STDERR_FILENAME = "cli_stderr.log"
_DIAGNOSTIC_TAIL_CHARS = 4000

_SECTION_RE = re.compile(r"^\s*\[\s*(?:'([^']*)'|\"([^\"]*)\"|([^\[\]]*?))\s*\]\s*(?:#.*)?$")
_ASSIGNMENT_RE = re.compile(r"^\s*(?:'([^']*)'|\"([^\"]*)\"|([A-Za-z0-9_-]+))\s*=")

_executable_identity: dict[str, str] = {}


def _clean(text: str) -> str:
    """Strip the CLI's ANSI colour codes so captured diagnostics stay readable."""
    return _ANSI_RE.sub("", text or "")


def _tail(text: str, limit: int = _DIAGNOSTIC_TAIL_CHARS) -> str:
    """Bound a captured stream to its last `limit` characters."""
    cleaned = _clean(text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return "...[truncated]...\n" + cleaned[-limit:]


def _resolve_executable() -> tuple[str, str]:
    """Locate the CurveCurator executable and verify its identity with the supported -h invocation."""
    override = os.environ.get(EXECUTABLE_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            raise ToolError(f"{EXECUTABLE_ENV_VAR}={override} does not point to an existing file.")
        candidates = [candidate]
    else:
        candidates = [path for path in EXECUTABLE_CANDIDATES if path.is_file()]
        found = shutil.which("CurveCurator")
        if found:
            candidates.append(Path(found))
    if not candidates:
        raise ToolError(
            "The CurveCurator executable was not found. Install the pinned curve_curator checkout "
            f"into the project environment or set {EXECUTABLE_ENV_VAR} to its console entry point."
        )

    executable = str(candidates[0].resolve())
    cached = _executable_identity.get(executable)
    if cached:
        return executable, cached

    if not os.access(executable, os.X_OK):
        raise ToolError(f"CurveCurator executable at {executable} is not executable.")
    try:
        probe = subprocess.run(
            [executable, "-h"],
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
            check=False,
        )
    except OSError as exc:
        raise ToolError(f"Could not run {executable} -h: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{executable} -h did not return within 120 s.") from exc

    help_text = _clean(probe.stdout) + "\n" + _clean(probe.stderr)
    identity = _IDENTITY_RE.search(help_text)
    # An exit code of 0 and empty output would also be produced by an unrelated program, so require
    # the CurveCurator identity banner and its documented positional argument in the help text.
    if probe.returncode != 0 or identity is None or "<PATH>" not in help_text:
        raise ToolError(
            f"{executable} is not a usable CurveCurator runtime: `-h` returned exit code "
            f"{probe.returncode} without the expected 'CurveCurator (v<version>)' help banner. "
            f"Help output tail:\n{_tail(help_text, 800)}"
        )
    version = identity.group("version").strip()
    _executable_identity[executable] = version
    return executable, version


def _load_toml(path: Path) -> dict:
    """Read a toml parameter file with the stdlib parser used by curve_curator.toml_parser."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ToolError(f"{path} is not a valid TOML parameter file: {exc}") from exc
    except OSError as exc:
        raise ToolError(f"Could not read the TOML parameter file {path}: {exc}") from exc


def _section_name(line: str) -> str | None:
    """Return the table name of a toml section header line, or None for other lines."""
    match = _SECTION_RE.match(line)
    if not match or line.lstrip().startswith("[["):
        return None
    return next(group for group in match.groups() if group is not None)


def _assigned_key(line: str) -> str | None:
    """Return the key assigned by a toml line, or None when the line is not an assignment."""
    match = _ASSIGNMENT_RE.match(line)
    if not match:
        return None
    return next(group for group in match.groups() if group is not None)


def _toml_string(value: str) -> str:
    """Quote a filesystem path as a toml basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _stage_parameter_file(toml_path: Path, run_dir: Path) -> tuple[Path, dict[str, str]]:
    """Copy the user's toml into the fresh run directory with every ['Paths'] entry made absolute."""
    config = _load_toml(toml_path)
    paths_section = config.get("Paths")
    if not isinstance(paths_section, dict):
        raise ToolError(f"{toml_path} has no ['Paths'] section; CurveCurator requires one.")
    declared_input = paths_section.get(INPUT_PATH_KEY)
    if not isinstance(declared_input, str) or not declared_input:
        raise ToolError(
            f"{toml_path} does not declare ['Paths'] {INPUT_PATH_KEY}; CurveCurator requires it."
        )

    input_path = Path(declared_input)
    if not input_path.is_absolute():
        input_path = toml_path.parent / input_path
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise ToolError(
            f"The input file declared by {toml_path} does not exist: {input_path} "
            f"(['Paths'] {INPUT_PATH_KEY} = {declared_input!r}, resolved against the toml directory)."
        )

    # The user's input stays where it is and is referenced absolutely; only outputs are redirected.
    resolved: dict[str, str] = {INPUT_PATH_KEY: str(input_path)}
    for key, default_name in OUTPUT_PATH_DEFAULTS.items():
        declared = paths_section.get(key)
        name = Path(declared).name if isinstance(declared, str) and declared else default_name
        resolved[key] = str(run_dir / name)
    for key in OPTIONAL_OUTPUT_KEYS:
        declared = paths_section.get(key)
        if isinstance(declared, str) and declared:
            resolved[key] = str(run_dir / Path(declared).name)

    try:
        original_text = toml_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"Could not read the TOML parameter file {toml_path}: {exc}") from exc

    lines = original_text.splitlines()
    staged_lines: list[str] = []
    inserted = False
    in_paths = False
    for line in lines:
        section = _section_name(line)
        if section is not None:
            in_paths = section == "Paths"
            staged_lines.append(line)
            if in_paths:
                staged_lines.append("# ['Paths'] rewritten by the MCP wrapper to absolute paths.")
                staged_lines.extend(
                    f"{key} = {_toml_string(value)}" for key, value in resolved.items()
                )
                inserted = True
            continue
        if in_paths and _assigned_key(line) in ALL_PATH_KEYS:
            # Drop the original relative assignment; the absolute one was inserted above.
            continue
        staged_lines.append(line)
    if not inserted:
        raise ToolError(f"Could not locate the ['Paths'] section header in {toml_path}.")

    staged_toml = run_dir / toml_path.name
    staged_toml.write_text("\n".join(staged_lines) + "\n", encoding="utf-8")

    # Verify the staged file really parses and really carries the absolute paths, rather than
    # assuming the rewrite worked.
    staged_paths = _load_toml(staged_toml).get("Paths")
    if not isinstance(staged_paths, dict):
        raise ToolError(f"Staged parameter file {staged_toml} lost its ['Paths'] section.")
    for key, value in resolved.items():
        if staged_paths.get(key) != value or not os.path.isabs(value):
            raise ToolError(
                f"Staged parameter file {staged_toml} does not carry the absolute path for {key!r}."
            )
    return staged_toml, resolved


def _count_data_rows(path: Path) -> int | None:
    """Count the data rows of a tab-separated output file without loading it into memory."""
    try:
        newlines = 0
        with open(path, "rb") as handle:
            while chunk := handle.read(1 << 20):
                newlines += chunk.count(b"\n")
    except OSError:
        return None
    return max(newlines - 1, 0)


def _parse_fdr_file(path: Path) -> dict[str, float]:
    """Parse the two FDR values thresholding.estimate_fdr writes."""
    values: dict[str, float] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        match = re.match(r"\s*(Global|Filtered)\s+FDR:\s*(\S+)", line)
        if match:
            try:
                values[f"{match.group(1).lower()}_fdr"] = float(match.group(2))
            except ValueError:
                continue
    return values


def _parse_mad_file(path: Path, limit: int = 100) -> dict[str, float]:
    """Parse the per-experiment median absolute deviations quality_control.mad_analysis writes."""
    values: dict[str, float] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        name, _, raw = line.rpartition("\t")
        try:
            values[name.strip()] = float(raw)
        except ValueError:
            continue
        if len(values) >= limit:
            break
    return values


@cli_wrapper_mcp.tool()
def run_dose_response_pipeline(
    toml_path: Annotated[
        str,
        "Path to a completed CurveCurator parameters .toml file; its ['Paths'] input_file (relative to that toml) names the search-engine output or dose-response table to fit",
    ],
    estimate_fdr: Annotated[
        bool,
        "Pass --fdr to estimate the false discovery rate with the target-decoy approach, which also writes the decoys and fdr files and roughly doubles the runtime",
    ] = False,
    run_mad: Annotated[
        bool,
        "Pass --mad to run the median-absolute-deviation analysis that flags noisy dose channels and writes the mad file",
    ] = False,
    output_dir: Annotated[
        str | None,
        "Base output directory; a fresh subdirectory is created per call (default: <project root>/outputs)",
    ] = None,
    timeout_seconds: Annotated[
        int,
        "Maximum seconds the CurveCurator process may run before the call fails; large proteomics inputs need thousands of seconds",
    ] = 3600,
) -> dict:
    """Fit, threshold and visualise dose-response curves by running the CurveCurator pipeline on one parameter file.
    Input is a CurveCurator parameters .toml plus its declared data table; output is the curves table, the interactive dashboard and the optional FDR/MAD files.
    """
    executable, cli_version = _resolve_executable()

    if timeout_seconds <= 0:
        raise ToolError("timeout_seconds must be a positive number of seconds.")

    # Resolve every user path to absolute form before the subprocess working directory changes.
    source_toml = Path(toml_path).expanduser()
    if not source_toml.is_absolute():
        source_toml = Path.cwd() / source_toml
    source_toml = source_toml.resolve()
    if not source_toml.is_file():
        raise ToolError(f"TOML parameter file not found: {source_toml}")
    if source_toml.suffix.lower() != ".toml":
        raise ToolError(
            f"{source_toml} is not a .toml parameter file; CurveCurator requires one "
            "(batch files are not supported by this tool)."
        )

    base_dir = Path(output_dir).expanduser() if output_dir else PROJECT_ROOT / "outputs"
    if not base_dir.is_absolute():
        base_dir = (Path.cwd() / base_dir).resolve()
    else:
        base_dir = base_dir.resolve()
    # A fresh directory per invocation: the identifier is built per call, so repeated requests to a
    # long-running server never share an output directory.
    run_dir = base_dir / f"curvecurator_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:12]}"
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ToolError(f"Could not create the output directory {run_dir}: {exc}") from exc

    # CurveCurator writes its outputs to the ['Paths'] entries resolved against the toml's own
    # directory, so the user's toml is never executed in place and never modified: a copy with
    # absolute paths is executed from the fresh run directory instead.
    staged_toml, resolved_paths = _stage_parameter_file(source_toml, run_dir)

    argv = [executable]
    if estimate_fdr:
        argv.append("--fdr")
    if run_mad:
        argv.append("--mad")
    argv.append(str(staged_toml))

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_tail = _tail(exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        stderr_tail = _tail(exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
        raise ToolError(
            f"CurveCurator did not finish within {timeout_seconds} s and was terminated. "
            f"Partial outputs are in {run_dir}. Increase timeout_seconds for large inputs.\n"
            f"stdout tail:\n{stdout_tail}\nstderr tail:\n{stderr_tail}"
        ) from exc
    except OSError as exc:
        raise ToolError(f"Could not start CurveCurator: {exc}") from exc
    runtime_seconds = round(time.monotonic() - started, 2)

    # Keep full diagnostics on disk and off the server's protocol stdout.
    stdout_path = run_dir / STDOUT_FILENAME
    stderr_path = run_dir / STDERR_FILENAME
    stdout_path.write_text(_clean(completed.stdout), encoding="utf-8")
    stderr_path.write_text(_clean(completed.stderr), encoding="utf-8")
    stdout_tail = _tail(completed.stdout)
    stderr_tail = _tail(completed.stderr)

    if completed.returncode != 0:
        raise ToolError(
            f"CurveCurator failed with exit code {completed.returncode}. "
            f"Diagnostics were written to {stdout_path} and {stderr_path}.\n"
            f"stdout tail:\n{stdout_tail}\nstderr tail:\n{stderr_tail}"
        )

    # curve_curator/toml_parser.py reports a rejected parameter or missing input file through
    # ui.error() followed by a bare exit(), which leaves the process exit code at 0. The exit status
    # alone therefore cannot establish success: the declared artifacts must actually be present.
    required = {"curves table": Path(resolved_paths["curves_file"]), "dashboard": Path(resolved_paths["dashboard"])}
    if estimate_fdr:
        required["decoy curves"] = Path(resolved_paths["decoys_file"])
        required["FDR estimate"] = Path(resolved_paths["fdr_file"])
    if run_mad:
        required["MAD analysis"] = Path(resolved_paths["mad_file"])
    missing = [f"{label} ({path})" for label, path in required.items() if not (path.is_file() and path.stat().st_size > 0)]
    if missing:
        raise ToolError(
            "CurveCurator exited without producing its declared outputs: "
            + "; ".join(missing)
            + f". Diagnostics were written to {stdout_path} and {stderr_path}.\n"
            f"stdout tail:\n{stdout_tail}\nstderr tail:\n{stderr_tail}"
        )

    descriptions = {
        "curves_file": "per-curve fit results (pEC50, curve slope/front/back, fold change, F/p values, relevance score, regulation)",
        "dashboard": "interactive bokeh dashboard of the fitted curves",
        "decoys_file": "fitted decoy curves from the target-decoy simulation",
        "fdr_file": "global and filtered FDR estimates",
        "mad_file": "median absolute deviation per dose channel",
        "normalization_file": "median-centric normalization factor per experiment",
    }
    artifacts = []
    for key, description in descriptions.items():
        path = resolved_paths.get(key)
        if path and Path(path).is_file():
            artifacts.append({"description": description, "path": str(Path(path).resolve())})
    log_path = run_dir / LOG_FILENAME
    if log_path.is_file():
        artifacts.append({"description": "CurveCurator run log", "path": str(log_path.resolve())})
    artifacts.append({"description": "resolved parameter file that was executed", "path": str(staged_toml.resolve())})
    artifacts.append({"description": "captured CurveCurator stdout", "path": str(stdout_path.resolve())})
    artifacts.append({"description": "captured CurveCurator stderr", "path": str(stderr_path.resolve())})

    result = {
        "message": (
            f"CurveCurator v{cli_version} completed the dose-response pipeline for "
            f"{source_toml.name} in {runtime_seconds} s (--fdr={estimate_fdr}, --mad={run_mad}). "
            f"Outputs are in {run_dir}."
        ),
        "reference": REFERENCE,
        "artifacts": artifacts,
        "cli_version": cli_version,
        "command": argv,
        "source_toml": str(source_toml),
        "input_file": resolved_paths[INPUT_PATH_KEY],
        "output_dir": str(run_dir),
        "resolved_paths": resolved_paths,
        "estimate_fdr": estimate_fdr,
        "run_mad": run_mad,
        "runtime_seconds": runtime_seconds,
        "exit_code": completed.returncode,
        "stdout_tail": stdout_tail,
    }
    num_curves = _count_data_rows(Path(resolved_paths["curves_file"]))
    if num_curves is not None:
        result["num_curves"] = num_curves
    if estimate_fdr:
        fdr_values = _parse_fdr_file(Path(resolved_paths["fdr_file"]))
        if fdr_values:
            result["fdr"] = fdr_values
        num_decoys = _count_data_rows(Path(resolved_paths["decoys_file"]))
        if num_decoys is not None:
            result["num_decoy_curves"] = num_decoys
    if run_mad:
        mad_values = _parse_mad_file(Path(resolved_paths["mad_file"]))
        if mad_values:
            result["mad"] = mad_values
    return result
