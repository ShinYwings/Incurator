"""Command-line interface for LLM-Wiki.

Stage 1 commands:
    wiki init [PATH]         Scaffold a new wiki project.
    wiki status              Show the current wiki's stats and config.
    wiki version             Show version.

Stage 2 commands:
    wiki add <path> [-r]     Copy a file or folder into raw/, parse, track.
    wiki sources list        List all tracked sources.
    wiki sources show <id>   Show details for one source (with text preview).
    wiki sources rm <id>     Remove a source from tracking.

Later stages add: ingest, query, lint, serve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from . import config as cfg
from . import db
from . import ingest_llm
from . import ingest_raw
from . import lint as lint_module
from . import query as query_module
from . import search
from .llm import (
    ClaudeClient,
    ClaudeCodeClient,
    ClaudeCodeError,
    ClaudeError,
    DEFAULT_OLLAMA_HOST,
    FailoverClient,
    GeminiClient,
    GeminiCliClient,
    GeminiCliError,
    GeminiError,
    LLMError,
    ModelNotFound,
    OllamaClient,
    OllamaNotRunning,
    OpenAIClient,
    OpenAIError,
    _cli_installed,
    build_client,
    describe_backend,
    list_models_on_host,
    list_ollama_models_with_vision,
    make_client_by_key,
)

app = typer.Typer(
    name="wiki",
    help="LLM-Wiki — an LLM-maintained personal knowledge base.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

sources_app = typer.Typer(
    name="sources",
    help="Manage tracked source files in raw/.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(sources_app, name="sources")

config_app = typer.Typer(
    name="config",
    help="Configure the LLM provider and Ollama models.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(config_app, name="config")

config_models_app = typer.Typer(
    name="models",
    help="Discover and select Ollama models (local or remote).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
config_app.add_typer(config_models_app, name="models")

console = Console()


# ---------------------------------------------------------------------------
# Recommended model catalogue
# ---------------------------------------------------------------------------

_RECOMMENDED_MODELS = [
    {
        "tag": "deepseek-r1:32b",
        "size": "32B",
        "why": "[논리망 추출 및 조립] 복잡한 에피폴라 기하학이나 투영 행렬 유도 과정을 스스로 검증합니다. DAG 형태로 논리를 조립하는 데 현존 로컬 최강입니다.",
        "tip": "일상적 논문 분석·요약 메인 모델로 가장 추천.",
        "vision": False,
    },
    {
        "tag": "gemma4:31b",
        "size": "31B",
        "why": "[시각 지식 추출 및 합성] 논문 속 3D 공간 투영 도식과 텍스트 수식을 완벽히 매칭합니다. 시각 정보가 포함된 PDF 문서를 그림의 맥락까지 메타데이터로 추출합니다.",
        "tip": "3D Vision 논문에 최적화.",
        "vision": True,
    },
    {
        "tag": "qwen3.6:35b",
        "size": "35B",
        "why": "[구조화 및 디렉토리 조립 1위] 추출된 사전 지식을 QMD 포맷이나 JSON, 마크다운 표로 재조립하는 데 압도적입니다. 계층형 디렉토리 트리 구조를 만드는 데 오차가 없습니다.",
        "tip": "대량 텍스트 합성 및 정형화 작업 시 유리.",
        "vision": False,
    },
    {
        "tag": "mistral-small3.1:24b",
        "size": "24B",
        "why": "[핵심 정보 밀집 및 필터링] 방대한 RAG 청크에서 노이즈를 걸러내고 알고리즘의 핵심만 조립합니다. 파이프라인의 핵심 구조만 간결하고 명확하게 합성해 냅니다.",
        "tip": "12GB VRAM에 거의 다 올라가며 텍스트 요약 효율이 매우 높음.",
        "vision": False,
    },
    {
        "tag": "gemma4:26b",
        "size": "26B",
        "why": "[대규모 데이터 병렬 합성] 여러 논문에서 검색된 유사한 개념들을 빠르게 읽고 중복을 제거하여 단일 지식 베이스로 통합합니다. Unified Vault 정보를 단일 노트로 조립할 때 유리합니다.",
        "tip": "여러 지식 소스를 동시에 합성하는 태스크에 효율적.",
        "vision": True,
    },
    {
        "tag": "internlm2:20b",
        "size": "20B",
        "why": "[장문 맥락의 수식 일관성 유지] 수십 페이지의 수학적 증명 과정을 한 번에 RAG로 검색할 때 진가를 발휘합니다. 좌표계 정의를 유지하며 에이전트에게 전달합니다.",
        "tip": "전공 서적 한 권을 통째로 넣고 요약할 때 유리.",
        "vision": False,
    },
    {
        "tag": "phi4:14b",
        "size": "14B",
        "why": "[수식 전처리 및 교정 워커] 소형임에도 수학적 구조 파악 능력이 뛰어납니다. 깨지기 쉬운 LATEX 수식들을 교정하고 정리하여, 중간 필터 역할을 훌륭히 수행합니다.",
        "tip": "간단한 문서들을 광속으로 전처리할 때 최적.",
        "vision": False,
    },
    {
        "tag": "deepseek-r1:14b",
        "size": "14B",
        "why": "[빠른 논리 타당성 검증기] RAG로 검색된 개별 문단들의 로직이 서로 모순되지 않는지 빠르게 검증합니다. 에이전트가 잘못된 정보를 바탕으로 행동하지 않도록 방어하는 쾌속 워커입니다.",
        "tip": "충돌 감지 및 모순 체크 작업에 적합.",
        "vision": False,
    },
    {
        "tag": "llama3.2-vision:11b",
        "size": "11B",
        "why": "[시각 데이터 전용 추출기] 논문 속 카메라 캘리브레이션 이미지나 그래프를 RAG 시스템이 검색할 수 있는 형태의 텍스트와 속성 값으로 분해해 주는 비전 전용 에이전트입니다.",
        "tip": "시각 정보만 빠르게 텍스트로 요약할 때 유용.",
        "vision": True,
    },
    {
        "tag": "deepseek-r1:8b",
        "size": "8B",
        "why": "[단순 구조화 및 분류 보조] 에이전트가 RAG에서 가져온 단순 텍스트나 서지 정보들을 정해진 디렉토리 구조로 빠르게 이동시키고 자동화하는 가벼운 작업에 적합합니다.",
        "tip": "경량 파일 분류 및 정렬 작업에 추천.",
        "vision": False,
    },
]


def _show_recommended_models(host: str) -> None:
    """Print the curated model recommendation table with live install status."""
    from rich.table import Table as RichTable

    installed_raw = list_models_on_host(host, timeout=3.0)
    installed_lower = {m.lower() for m in installed_raw}

    def _is_installed(tag: str) -> bool:
        def normalize(s: str) -> str:
            return s.lower().replace("-", "")

        tag_lower = tag.lower()
        tag_norm = normalize(tag_lower)
        base = tag_lower.split(":")[0]
        rec_version = tag_lower.split(":")[1] if ":" in tag_lower else "latest"

        for m in installed_lower:
            m_lower = m.lower()
            if m_lower == tag_lower or m_lower.startswith(tag_lower) or normalize(m_lower) == tag_norm:
                return True
            
            m_base = m_lower.split(":")[0]
            m_version = m_lower.split(":")[1] if ":" in m_lower else "latest"
            if normalize(m_base) == normalize(base) and m_version == rec_version:
                return True
        return False

    table = RichTable(
        show_header=True,
        box=None,
        padding=(0, 1),
        header_style="bold dim",
        show_lines=False,
    )
    table.add_column("Model Tag",       style="cyan",    min_width=22, no_wrap=True)
    table.add_column("체급",             style="yellow",  min_width=14, no_wrap=True)
    table.add_column("설명",             min_width=60, max_width=85)
    table.add_column("설치",             style="green",   min_width=4,  no_wrap=True, justify="center")

    for m in _RECOMMENDED_MODELS:
        vision_badge = " [magenta]👁[/magenta]" if m["vision"] else ""
        installed_mark = "✓" if _is_installed(m["tag"]) else ""
        desc = f"{m['why']} [dim]({m['tip']})[/dim]"
        table.add_row(
            m["tag"] + vision_badge,
            m["size"],
            desc,
            installed_mark,
        )

    console.print()
    console.print("[bold]추천 모델 목록[/bold]  [dim](👁 = 이미지 추론 지원 / 설치 ✓ = 현재 Ollama에 존재)[/dim]")
    console.print(table)
    console.print(
        "[dim]설치: [bold]wiki config models use <tag>[/bold]  "
        "·  모델 변경 후 [bold]wiki sync[/bold] 재실행 권장[/dim]"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hint(text: str) -> None:
    """Print a one-liner tip in a subdued style."""
    console.print(f"[dim]💡 {text}[/dim]")


def _err(text: str) -> None:
    console.print(f"[bold red]✗[/bold red] {text}")


def _ok(text: str) -> None:
    console.print(f"[bold green]✓[/bold green] {text}")


def _warn(text: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {text}")


def _refresh_qmd_index(paths: cfg.WikiPaths, *, embed: bool = True) -> None:
    """Run `qmd update` (and optionally `qmd embed`) for this project.

    Friendly: emits hints instead of raising when qmd isn't built or fails;
    callers (sync/ingest/lint --fix) are non-fatal — the source of truth is
    on disk regardless.
    """
    if not search.is_available():
        bin_path = search.get_qmd_binary()
        if bin_path and not bin_path.exists():
            _hint(
                "qmd binary not found. Build the bundled copy: "
                "[bold]cd src/qmd && bun install && bun run build[/bold]"
            )
        else:
            _hint(
                "qmd binary present but not responding. "
                "Try `src/qmd/bin/qmd --version` to diagnose."
            )
        return
    try:
        console.print("[dim]Updating qmd index…[/dim]")
        search.update_index(paths, embed=embed)
        _ok("qmd index updated")
    except search.SearchBackendError as e:
        _warn(f"qmd index update failed: {e}")
        _hint("Search is now stale; rerun later with `wiki reindex`.")


def _resolve_root_or_die() -> cfg.WikiPaths:
    """Find the wiki project root from cwd or WIKI_ROOT env var."""
    import os
    env_root = os.environ.get("WIKI_ROOT")
    if env_root:
        root_path = Path(env_root).resolve()
        if (root_path / cfg.INTERNAL_DIR / cfg.CONFIG_FILE).exists():
            cfg.set_last_root(root_path)
            return cfg.paths_from_config(root_path)
    root = cfg.find_wiki_root()
    if root is None:
        last_root = cfg.get_last_root()
        if last_root and (last_root / cfg.INTERNAL_DIR / cfg.CONFIG_FILE).exists():
            return cfg.paths_from_config(last_root)
        _err("Not inside an LLM-Wiki project.")
        _hint("Run [bold]wiki init[/bold] to create one, or set WIKI_ROOT env var.")
        raise typer.Exit(code=1)
    cfg.set_last_root(root)
    return cfg.paths_from_config(root)


def _format_bytes(n: int) -> str:
    """Human-readable byte count: 1234 → '1.2 KB'."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _status_style(status: str) -> str:
    return {
        "pending": "yellow",
        "ingested": "green",
        "error": "red",
        "skipped": "dim",
    }.get(status, "white")


# ---------------------------------------------------------------------------
# Stage 1 commands
# ---------------------------------------------------------------------------

_VALID_CLOUD = ("gemini", "claude", "openai")

# Curated Ollama model list: (model_name, description)
_CURATED_MODELS = [
    ("qwen2.5:3b",      "3B  · ~2 GB VRAM  · very fast"),
    ("qwen2.5:7b",      "7B  · ~5 GB VRAM  · fast, balanced"),
    ("gemma3:12b",      "12B · ~8 GB VRAM  · Google Gemma 3"),
    ("qwen2.5:14b",     "14B · ~9 GB VRAM  · high quality"),
    ("deepseek-r1:14b", "14B · ~9 GB VRAM  · reasoning/thinking  [default]"),
    ("qwen2.5:32b",     "32B · ~20 GB VRAM · very high quality"),
    ("gemma3:27b",      "27B · ~18 GB VRAM · Google Gemma 3, large"),
    ("gemma4:32b",      "32B · ~22 GB VRAM · Google Gemma 4, latest"),
]


def _pick_ollama_model(host: str) -> str:
    """Show model picker. Tries live discovery first, falls back to curated list."""
    console.print()
    console.print(f"[dim]Connecting to Ollama at {host} …[/dim]")
    live_models = list_models_on_host(host, timeout=3.0)
    live_set = set(live_models)

    if live_models:
        console.print(f"[dim green]Found {len(live_models)} model(s) installed on this host.[/dim green]")
    else:
        console.print("[dim yellow]Ollama not reachable — showing curated model list.[/dim yellow]")

    # Build a merged option list: curated first (with Installed badge for local ones),
    # then any locally-installed models not in the curated list.
    curated_names = [m for m, _ in _CURATED_MODELS]
    extra_live = [m for m in live_models if m not in curated_names]
    options = curated_names + extra_live

    _curated_desc = dict(_CURATED_MODELS)
    console.print()
    for i, m in enumerate(options, 1):
        desc = _curated_desc.get(m, "")
        badge = "  [bold green][Installed][/bold green]" if m in live_set else ""
        desc_str = f"  [dim]— {desc}[/dim]" if desc else ""
        console.print(f"  [cyan]{i}[/cyan]  {m}{desc_str}{badge}")
    console.print(f"  [dim]0[/dim]  custom model name")
    console.print()

    default_model = "deepseek-r1:14b"
    # Prefer the first installed model as default if deepseek is not installed
    if live_models and default_model not in live_set:
        default_model = live_models[0]
    default_idx = next(
        (i + 1 for i, m in enumerate(options) if m == default_model), None
    )
    prompt_hint = f"  (1–{len(options)}, or 0 for custom)"
    if default_idx:
        prompt_hint += f"  [default {default_idx}={default_model}]"

    while True:
        raw = typer.prompt(f"Select model{prompt_hint}", default=str(default_idx or "0")).strip()
        if raw == "0":
            custom = typer.prompt("Model name", default=default_model).strip()
            return custom or default_model
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            # Maybe they typed a model name directly
            if raw:
                return raw
        console.print(f"[red]Enter a number between 0 and {len(options)}.[/red]")


def _prompt_api_key(label: str, env_var: str, prefill: str = "") -> str:
    """Prompt for an API key. Skips prompt if env var is already set (with confirm to override)."""
    import os

    env_val = os.environ.get(env_var, "")
    if env_val:
        console.print(f"[dim]{env_var} is already set in the environment.[/dim]")
        if not typer.confirm("Override with a different key?", default=False):
            return ""
    key = (prefill or typer.prompt(f"{label} ({env_var})", default="", hide_input=True)).strip()
    return key


def _prompt_cloud_setup(
    default_cp: str,
    prefill_keys: dict[str, str],
) -> dict:
    """Prompt for cloud provider selection + API key. Returns partial llm overrides."""
    overrides: dict = {}
    while True:
        raw = typer.prompt(
            "Cloud provider (gemini/claude/openai)", default=default_cp
        ).strip().lower()
        if raw in _VALID_CLOUD:
            cp = raw
            break
        console.print(f"[red]Choose: {', '.join(_VALID_CLOUD)}[/red]")
    overrides["cloud_provider"] = cp

    key_map = {
        "gemini": ("Gemini API key", "GEMINI_API_KEY", "gemini_api_key"),
        "claude": ("Anthropic API key", "ANTHROPIC_API_KEY", "anthropic_api_key"),
        "openai": ("OpenAI API key", "OPENAI_API_KEY", "openai_api_key"),
    }
    label, env_var, cfg_key = key_map[cp]
    key = _prompt_api_key(label, env_var, prefill_keys.get(cfg_key, ""))
    if key:
        overrides[cfg_key] = key
    return overrides


def _print_backend_menu(exclude: str | None = None) -> None:
    """Print the 4-option backend menu, optionally skipping one entry."""
    _claude_ok = _cli_installed("claude")
    _gemini_ok = _cli_installed("gemini")
    n = 1
    for key, label in [
        ("ollama",      "Local Ollama      (GPU/CPU — local or remote server)"),
        ("cloud",       "Cloud API         (Gemini / Claude / OpenAI — API key required)"),
        ("claude-code", f"Claude Code CLI   (claude Pro/Max subscription — "
                        f"{'[green]installed[/green]' if _claude_ok else '[yellow]not installed[/yellow]'})"),
        ("gemini-cli",  f"Gemini CLI        (Gemini Advanced subscription — "
                        f"{'[green]installed[/green]' if _gemini_ok else '[yellow]not installed[/yellow]'})"),
    ]:
        if key == exclude:
            continue
        console.print(f"  [cyan]{n}[/cyan]  {label}")
        n += 1
    console.print()


def _pick_backend_menu(exclude: str | None = None, prompt: str = "Choice") -> str:
    """Show 4-option backend menu and return the chosen backend key."""
    _print_backend_menu(exclude)
    keys = [k for k in ("ollama", "cloud", "claude-code", "gemini-cli") if k != exclude]
    valid: dict[str, str] = {}
    for i, k in enumerate(keys, 1):
        valid[str(i)] = k
        valid[k] = k

    while True:
        raw = typer.prompt(f"{prompt} (1–{len(keys)})", default="1").strip().lower()
        if raw in valid:
            return valid[raw]
        console.print(f"[red]Enter 1–{len(keys)}.[/red]")


def _install_ollama_binary() -> bool:
    """Install the Ollama binary if not present. Returns True if now available."""
    import subprocess as _sp
    import sys

    if _cli_installed("ollama"):
        return True

    _warn("Ollama is not installed.")
    if not typer.confirm("Install Ollama now?", default=True):
        _hint("Install manually: [bold]https://ollama.com/download[/bold]")
        return False

    if sys.platform.startswith("linux"):
        console.print("[dim]Running: curl -fsSL https://ollama.com/install.sh | sh[/dim]")
        res = _sp.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
    elif sys.platform == "darwin":
        if _cli_installed("brew"):
            console.print("[dim]Running: brew install ollama[/dim]")
            res = _sp.run(["brew", "install", "ollama"])
        else:
            _hint("Install Homebrew first (https://brew.sh) or download Ollama from https://ollama.com/download")
            return False
    else:
        _hint("Download Ollama from: [bold]https://ollama.com/download[/bold]")
        return False

    if res.returncode == 0 and _cli_installed("ollama"):
        _ok("Ollama installed.")
        return True

    _warn("Ollama install failed. Try manually: https://ollama.com/download")
    return False


def _ensure_ollama_running(host: str) -> bool:
    """Ensure Ollama is installed and running. Returns True if ready."""
    import subprocess as _sp
    import time

    if list_models_on_host(host, timeout=2.0) is not None:
        return True  # already up

    if not _cli_installed("ollama"):
        if not _install_ollama_binary():
            return False

    _warn(f"Ollama not running at {host}.")
    if not typer.confirm("Start Ollama now? (ollama serve)", default=True):
        return False

    console.print("[dim]Starting Ollama in background…[/dim]")
    _sp.Popen(
        ["ollama", "serve"],
        stdout=_sp.DEVNULL,
        stderr=_sp.DEVNULL,
        start_new_session=True,
    )
    for i in range(10):
        time.sleep(1)
        console.print(f"[dim]  waiting… ({i+1}s)[/dim]", end="\r")
        if list_models_on_host(host, timeout=1.0):
            console.print()
            _ok("Ollama is ready.")
            return True
    console.print()
    _warn("Ollama did not respond in 10 s. It may still be starting.")
    return False


def _ensure_npm(install_cmd: str) -> bool:
    """Ensure npm is available; auto-installs Node via nodeenv into the venv if needed."""
    import shutil
    import subprocess as _sp
    import sys
    import os

    if shutil.which("npm"):
        return True

    # Check if already installed in venv node dir
    node_dir = Path(sys.prefix) / "node"
    npm_bin = node_dir / "bin" / "npm"
    if npm_bin.exists():
        bin_dir = str(node_dir / "bin")
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return True

    _warn("npm is not installed.")
    try:
        import nodeenv as _ne  # noqa: F401
    except ImportError:
        _hint("Install Node.js/npm:")
        _hint("  [bold]https://nodejs.org[/bold]  or  [bold]brew install node[/bold]  or  [bold]apt install nodejs npm[/bold]")
        _hint(f"Then run: [bold]{install_cmd}[/bold]")
        return False

    console.print(f"[dim]Installing Node.js into venv ({node_dir})…[/dim]")
    res = _sp.run([sys.executable, "-m", "nodeenv", "--prebuilt", str(node_dir)])
    if res.returncode != 0:
        _warn("nodeenv failed. Install Node.js manually and retry.")
        return False

    bin_dir = str(node_dir / "bin")
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    if not shutil.which("npm"):
        _warn("npm still not found after nodeenv install.")
        return False

    _ok("Node.js ready.")
    return True


def _configure_backend(
    backend: str,
    overrides: dict,
    prefill_keys: dict,
    default_cp: str,
) -> None:
    """Prompt for backend-specific settings, merge into overrides, and offer install."""
    import subprocess as _sp

    if backend == "ollama":
        host = typer.prompt("Ollama host", default="http://localhost:11434").strip()
        overrides["host"] = host
        _ensure_ollama_running(host)
        model = _pick_ollama_model(host)
        overrides["model"] = model
        # Offer to pull if model is missing
        live = list_models_on_host(host, timeout=3.0)
        if live:
            tag = model.split(":")[0]
            if not any(m == model or m.startswith(tag) for m in live):
                console.print()
                _warn(f"Model '{model}' is not pulled yet.")
                if typer.confirm(f"Pull it now? (ollama pull {model})", default=True):
                    console.print(f"[dim]Running: ollama pull {model}[/dim]")
                    res = _sp.run(["ollama", "pull", model])
                    if res.returncode == 0:
                        _ok(f"Model '{model}' pulled.")
                    else:
                        _warn(f"Pull failed. Run manually: ollama pull {model}")
            else:
                _ok(f"Model '{model}' is available.")
        else:
            _hint(f"Once Ollama is running: [bold]ollama pull {model}[/bold]")

    elif backend == "cloud":
        overrides.update(_prompt_cloud_setup(default_cp, prefill_keys))

    elif backend in ("claude-code", "gemini-cli"):
        cli_cmd = "claude" if backend == "claude-code" else "gemini"
        install_cmd = (
            "npm install -g @anthropic-ai/claude-code"
            if backend == "claude-code"
            else "npm install -g @google/gemini-cli"
        )
        if not _cli_installed(cli_cmd):
            console.print()
            _warn(f"'{cli_cmd}' CLI is not installed.")
            if _ensure_npm(install_cmd):
                if typer.confirm(f"Install now? ({install_cmd})", default=True):
                    console.print(f"[dim]Running: {install_cmd}[/dim]")
                    res = _sp.run(install_cmd, shell=True)
                    if res.returncode == 0:
                        _ok(f"'{cli_cmd}' installed.")
                    else:
                        _warn(f"Install failed. Run manually: {install_cmd}")
        else:
            _ok(f"'{cli_cmd}' CLI found.")


def _run_init_wizard(
    *,
    cloud_provider: str,
    gemini_api_key: str,
    anthropic_api_key: str,
    openai_api_key: str,
) -> dict:
    """Run interactive LLM setup wizard. Returns dict of llm config overrides."""
    prefill_keys = {
        "gemini_api_key": gemini_api_key,
        "anthropic_api_key": anthropic_api_key,
        "openai_api_key": openai_api_key,
    }

    console.print()
    console.print("[bold cyan]LLM Setup Wizard[/bold cyan]")
    console.print("[dim]Press Enter to accept the default shown in parentheses.[/dim]")
    console.print()

    # Step 1: Primary backend
    console.print("Which do you [bold]primarily[/bold] use for LLM inference?")
    primary = _pick_backend_menu(prompt="Primary backend")
    overrides: dict = {"primary": primary}

    # Step 2: Configure the primary backend
    console.print(f"[dim]--- {primary} (primary) ---[/dim]")
    if primary in ("claude-code", "gemini-cli"):
        cli_cmd = "claude" if primary == "claude-code" else "gemini"
        install_cmd = (
            "npm install -g @anthropic-ai/claude-code"
            if primary == "claude-code"
            else "npm install -g @google/gemini-cli"
        )
        if not _cli_installed(cli_cmd):
            console.print()
            console.print(f"[yellow]'{cli_cmd}' CLI is not installed.[/yellow]")
            console.print(f"[dim]Install:      {install_cmd}[/dim]")
            console.print(f"[dim]Authenticate: {cli_cmd}[/dim]")
            console.print()
            if not typer.confirm("Save this setting anyway and install later?", default=True):
                console.print("[dim]Switching back to Ollama primary.[/dim]")
                primary = "ollama"
                overrides["primary"] = primary
                _configure_backend("ollama", overrides, prefill_keys, cloud_provider)
                return overrides
        else:
            console.print(f"[dim green]'{cli_cmd}' CLI found.[/dim green]")
    else:
        _configure_backend(primary, overrides, prefill_keys, cloud_provider)

    # Step 3: Fallback backend
    console.print()
    if typer.confirm("Set up automatic fallback?", default=True):
        console.print()
        console.print("Fallback backend:")
        fallback = _pick_backend_menu(exclude=primary, prompt="Fallback")
        overrides["fallback"] = fallback
        console.print(f"[dim]--- {fallback} (fallback) ---[/dim]")
        _configure_backend(fallback, overrides, prefill_keys, cloud_provider)
    else:
        overrides["fallback"] = ""

    return overrides


def _offer_install(overrides: dict, llm_cfg: dict) -> None:
    """After wizard, offer to install CLI tools and/or pull Ollama models."""
    import subprocess

    primary = overrides.get("primary") or llm_cfg.get("primary", "")
    model   = overrides.get("model")   or llm_cfg.get("model", "deepseek-r1:14b")
    host    = overrides.get("host")    or llm_cfg.get("host", DEFAULT_OLLAMA_HOST)

    # CLI tool install
    if primary in ("claude-code", "gemini-cli"):
        cli_cmd     = "claude" if primary == "claude-code" else "gemini"
        install_cmd = (
            "npm install -g @anthropic-ai/claude-code"
            if primary == "claude-code"
            else "npm install -g @google/gemini-cli"
        )
        if not _cli_installed(cli_cmd):
            console.print()
            console.print(f"[yellow]'{cli_cmd}' is not installed.[/yellow]")
            if typer.confirm(f"Install now? ({install_cmd})", default=True):
                console.print(f"[dim]Running: {install_cmd}[/dim]")
                res = subprocess.run(install_cmd, shell=True)
                if res.returncode == 0:
                    _ok(f"'{cli_cmd}' installed.")
                else:
                    _warn(f"Install failed. Run manually: {install_cmd}")

    # Ollama model pull (only when the wizard explicitly picked a model)
    if overrides.get("model") and model:
        live = list_models_on_host(host, timeout=3.0)
        if live:
            tag = model.split(":")[0]
            if not any(m == model or m.startswith(tag) for m in live):
                console.print()
                console.print(f"[yellow]Model '{model}' not found locally on {host}.[/yellow]")
                if typer.confirm(f"Pull it now? (ollama pull {model})", default=True):
                    console.print(f"[dim]Running: ollama pull {model}[/dim]")
                    res = subprocess.run(["ollama", "pull", model])
                    if res.returncode == 0:
                        _ok(f"Model '{model}' pulled.")
                    else:
                        _warn(f"Pull failed. Run manually: ollama pull {model}")
            else:
                _ok(f"Model '{model}' already available.")
        else:
            console.print()
            _hint(
                f"Ollama not reachable at {host}. "
                f"After starting it run: [bold]ollama pull {model}[/bold]"
            )


_ALL_LLM_ERRORS = (
    OllamaNotRunning, ModelNotFound,
    GeminiError, ClaudeError, OpenAIError,
    ClaudeCodeError, GeminiCliError,
    LLMError,
)


def _start_client(config: dict):
    """Build and verify the LLM client.

    - Tries the primary backend first.
    - On ModelNotFound: offers `ollama pull <model>` and retries.
    - On any other failure: if a fallback is configured, asks the user
      whether to use it. The FailoverClient returned afterwards handles
      automatic mid-session switching during actual inference calls.
    """
    import subprocess as _sp

    llm_cfg = config.get("llm", {})
    primary = llm_cfg.get("primary", "")
    fallback = llm_cfg.get("fallback", "")

    # If no explicit primary, fall back to full auto build (legacy mode).
    if not primary:
        client = build_client(config)
        client.ensure_ready()
        return client

    # --- Try primary ---
    p_client = make_client_by_key(primary, config)
    try:
        p_client.ensure_ready()
        # Primary OK.
        # If an explicit fallback is configured, build the full FailoverClient;
        # otherwise return p_client directly to avoid eagerly constructing cloud
        # clients that may require API keys the user hasn't set.
        if fallback:
            return build_client(config)
        return p_client
    except ModelNotFound as e:
        _err(str(e))
        model_name = llm_cfg.get("model", "deepseek-r1:14b")
        if typer.confirm(f"Pull model now? (ollama pull {model_name})", default=True):
            console.print(f"[dim]Running: ollama pull {model_name}[/dim]")
            res = _sp.run(["ollama", "pull", model_name])
            if res.returncode == 0:
                _ok(f"Model '{model_name}' pulled. Retrying…")
                try:
                    p_client.ensure_ready()
                    return p_client if not fallback else build_client(config)
                except Exception:
                    pass  # fall through to fallback logic
            else:
                _warn(f"Pull failed. Run manually: ollama pull {model_name}")
    except _ALL_LLM_ERRORS as e:
        _err(str(e))

    # --- Primary failed, try fallback ---
    if not fallback:
        raise typer.Exit(code=1)

    console.print()
    if not typer.confirm(
        f"Primary ([bold]{primary}[/bold]) is not available. "
        f"Use fallback ([bold]{fallback}[/bold])?",
        default=True,
    ):
        raise typer.Exit(code=1)

    f_client = make_client_by_key(fallback, config)
    try:
        f_client.ensure_ready()
        _ok(f"Using fallback: [bold]{fallback}[/bold]")
        return f_client
    except _ALL_LLM_ERRORS as e:
        _err(f"Fallback also failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Show the LLM-Wiki version."""
    console.print(f"llm-wiki [bold cyan]{__version__}[/bold cyan]")
@app.command()
def init(
    vault_path: str = typer.Argument(
        ...,
        help="Path to the vault root (where 02_Wiki, 03_Notes, etc. live).",
    ),
    raw_dirs: list[str] = typer.Option(
        ["02_Wiki", "03_Notes", "04_Resources", "06_Archives"],
        "--raw",
        "-r",
        help="Source directories to monitor (relative to vault root). Repeatable.",
    ),
    cloud_provider: str = typer.Option(
        "gemini",
        "--cloud-provider",
        "-c",
        help="Cloud LLM provider for low-RAM machines: gemini | claude | openai.",
    ),
    gemini_api_key: str = typer.Option(
        "",
        "--gemini-api-key",
        "-g",
        help="Gemini API key (or set GEMINI_API_KEY env var).",
    ),
    anthropic_api_key: str = typer.Option(
        "",
        "--anthropic-api-key",
        "-a",
        help="Anthropic Claude API key (or set ANTHROPIC_API_KEY env var).",
    ),
    openai_api_key: str = typer.Option(
        "",
        "--openai-api-key",
        "-o",
        help="OpenAI API key (or set OPENAI_API_KEY env var).",
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="Run interactive LLM setup wizard (default: on). Use --no-interactive for CI/scripting.",
    ),
) -> None:
    """Initialise a Curator project inside an Obsidian vault.

    If the directory already exists (or is an existing Obsidian vault), only
    missing topology directories and .curator/ files are created — nothing is
    overwritten.

    Creates:
      .obsidian/                 — Obsidian vault marker (created if absent)
      00_System/ … 06_Archives/ — Vault topology (created if absent)
      .curator/config.yml        — project configuration
      .curator/state.sqlite      — tracking database
      .curator/Collections/      — 01_Summaries/ 02_Atoms/ 03_Concepts/ 04_Synthesis/
      .curator/overview.md       — domain manifest
      .curator/index.md          — DAG routing table
      .curator/log.md            — ingest log
      .curator/ledger.md         — override ledger
    """
    import os
    import shutil

    root = Path(vault_path).resolve()

    # Create vault root if it doesn't exist yet
    if not root.exists():
        root.mkdir(parents=True)
        _ok(f"Created vault root: {root}")

    # Guarantee this is an Obsidian vault (.obsidian/ is the vault marker)
    obsidian_dir = root / ".obsidian"
    if not obsidian_dir.exists():
        obsidian_dir.mkdir()
        _ok(f"Created Obsidian vault marker: .obsidian/")

    paths = cfg.WikiPaths(
        root=root,
        raw_dirs_override=raw_dirs,
    )
    already_initialized = paths.is_initialized()

    # Always ensure the vault topology exists (idempotent, never overwrites)
    created_dirs: list[str] = []
    for d in cfg.VAULT_TOPOLOGY:
        target = root / d
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(d)

    if already_initialized:
        cfg.set_last_root(root)
        console.print()
        console.print(f"[dim cyan]Curator already initialised at {root}[/dim cyan]")
        if created_dirs:
            console.print("[dim]Created missing vault directories:[/dim]")
            for d in created_dirs:
                _ok(d)
        else:
            console.print("[dim]Vault topology is complete — nothing to create.[/dim]")
        console.print()
        _hint("Run [bold]wiki status[/bold] to review current state.")
        raise typer.Exit(code=0)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Initialising LLM-Wiki Curator[/bold cyan]\n"
            f"[dim]{root}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Build config
    config = dict(cfg.DEFAULT_CONFIG)
    config["paths"] = {
        "raw_dirs": raw_dirs,
        "collections_dir": cfg.DEFAULT_COLLECTIONS_DIR,
    }

    # Cloud provider + API keys
    llm = dict(config.get("llm", {}))

    explicit_provider_flags = bool(
        cloud_provider != "gemini"
        or gemini_api_key
        or anthropic_api_key
        or openai_api_key
    )

    if explicit_provider_flags:
        # CLI flags were passed — apply directly, no wizard
        if cloud_provider in _VALID_CLOUD:
            llm["cloud_provider"] = cloud_provider
        for flag_val, env_var, cfg_key in [
            (gemini_api_key, "GEMINI_API_KEY", "gemini_api_key"),
            (anthropic_api_key, "ANTHROPIC_API_KEY", "anthropic_api_key"),
            (openai_api_key, "OPENAI_API_KEY", "openai_api_key"),
        ]:
            resolved = flag_val or os.environ.get(env_var, "")
            if resolved:
                llm[cfg_key] = resolved
    elif not interactive:
        # --no-interactive with no flags: skip provider setup entirely
        _hint("LLM provider not configured. Run [bold]wiki config provider[/bold] to set it up.")
    else:
        # Interactive mode: ask user how they want to configure
        console.print()
        console.print("[bold]LLM Provider Setup[/bold]")
        console.print("  [cyan]1[/cyan]  Interactive wizard  [dim](set up now)[/dim]")
        console.print("  [cyan]2[/cyan]  CLI flags           [dim](I'll run `wiki config-provider --primary ...` later)[/dim]")
        console.print()
        choice = typer.prompt("Choose setup method (1/2)", default="1").strip()
        if choice == "1":
            wizard_overrides = _run_init_wizard(
                cloud_provider=cloud_provider,
                gemini_api_key=gemini_api_key,
                anthropic_api_key=anthropic_api_key,
                openai_api_key=openai_api_key,
            )
            llm.update(wizard_overrides)
            _offer_install(wizard_overrides, llm)
        else:
            _hint("Run [bold]wiki config provider --primary ollama|cloud ...[/bold] to configure.")

    if "provider" in llm:
        del llm["provider"]
    config["llm"] = llm

    # 2. Create directory structure
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)

    # 3. Write config.yml
    cfg.save_config(paths, config)
    _ok(f"Config:    {paths.config_file.relative_to(root)}")

    # 4. Init the state database
    db.init_db(paths.state_db)
    _ok(f"Database:  {paths.state_db.relative_to(root)}")

    # 5. Copy template files
    templates_dir = Path(__file__).parent / "templates"

    # index.md (in .curator/ root, not Collections/)
    index_src = templates_dir / "index.md"
    if index_src.exists() and not paths.index.exists():
        shutil.copy2(index_src, paths.index)
        _ok(f"Index:     {paths.index.relative_to(root)}")

    # overview.md
    if not paths.overview.exists():
        paths.overview.write_text(
            "---\ntitle: Domain Manifest\ntype: overview\n---\n\n"
            "# .curator/overview.md — Domain Manifest\n\n"
            "*List the knowledge domains tracked in this vault.*\n",
            encoding="utf-8",
        )
        _ok(f"Overview:  {paths.overview.relative_to(root)}")

    # ledger.md
    if not paths.ledger.exists():
        paths.ledger.write_text(
            "---\ntitle: Ledger\ntype: ledger\n---\n\n"
            "# .curator/ledger.md — Override Ledger\n\n"
            "*High-priority human corrections that silently override L1-L4 nodes.*\n",
            encoding="utf-8",
        )
        _ok(f"Ledger:    {paths.ledger.relative_to(root)}")

    # log.md
    if not paths.log.exists():
        paths.log.write_text(
            "---\ntitle: Curator Log\ntype: log\n---\n\n# .curator/log.md — Hash Registry\n\n",
            encoding="utf-8",
        )
        _ok(f"Log:       {paths.log.relative_to(root)}")

    # qmd index.yml — pin qmd to this project's collections + per-vault DB
    try:
        if search.write_qmd_config(paths):
            _ok(f"QMD cfg:   {paths.qmd_config_file.relative_to(root)}")
        else:
            _hint(f"qmd config already exists at {paths.qmd_config_file.relative_to(root)}")
    except search.SearchBackendError as e:
        _warn(f"Could not write qmd config: {e}")

    # 6. Summary
    cfg.set_last_root(root)

    console.print()
    console.print("[bold green]Curator initialised![/bold green]")
    console.print()
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=18)
    table.add_column()
    if created_dirs:
        table.add_row("Vault dirs", ", ".join(created_dirs))
    table.add_row("Source dirs", ", ".join(raw_dirs))
    table.add_row("Collections", str(paths.collections.relative_to(root)))
    table.add_row("Config", str(paths.config_file.relative_to(root)))
    table.add_row("LLM backend", describe_backend(config))
    console.print(table)
    console.print()
    if not config.get("llm", {}).get("primary"):
        _hint("LLM provider not set. Run [bold]wiki config provider[/bold] to configure.")
    else:
        _hint("Next: run [bold]wiki sync[/bold] to discover & summarize sources, then [bold]wiki ingest[/bold].")

    llm_cfg = config.get("llm", {})
    ollama_host = llm_cfg.get("host", DEFAULT_OLLAMA_HOST)
    _show_recommended_models(ollama_host)
    console.print()



@config_app.command("provider")
def config_provider(
    primary: str = typer.Option(
        "",
        "--primary", "-p",
        help="Primary backend: ollama | cloud | claude-code | gemini-cli",
    ),
    cloud_provider: str = typer.Option(
        "",
        "--cloud-provider", "-c",
        help="Cloud provider: gemini | claude | openai",
    ),
    model: str = typer.Option(
        "",
        "--model", "-m",
        help="Ollama model name (e.g. deepseek-r1:14b, gemma4:32b).",
    ),
    host: str = typer.Option(
        "",
        "--host",
        help="Ollama host URL (e.g. http://localhost:11434).",
    ),
    gemini_api_key: str = typer.Option("", "--gemini-api-key", help="Gemini API key."),
    anthropic_api_key: str = typer.Option("", "--anthropic-api-key", help="Anthropic API key."),
    openai_api_key: str = typer.Option("", "--openai-api-key", help="OpenAI API key."),
) -> None:
    """Reconfigure the LLM provider for the current project.

    Run without flags for the interactive wizard, or pass flags to set directly:

    \b
      wiki config provider --primary ollama --model gemma4:32b
      wiki config provider --primary cloud --cloud-provider claude
      wiki config provider --primary ollama --cloud-provider gemini  # ollama + cloud fallback
    """
    paths = _resolve_root_or_die()
    current_config = cfg.load_config(paths)
    llm = dict(current_config.get("llm", {}))

    any_flag = bool(primary or cloud_provider or model or host
                    or gemini_api_key or anthropic_api_key or openai_api_key)

    if any_flag:
        # Non-interactive: apply only the flags that were explicitly passed
        _valid_primary = ("ollama", "cloud", "claude-code", "gemini-cli")
        if primary in _valid_primary:
            llm["primary"] = primary
        elif primary:
            _warn(f"Unknown --primary '{primary}'. Use: {' | '.join(_valid_primary)}")
            raise typer.Exit(code=1)

        if cloud_provider in _VALID_CLOUD:
            llm["cloud_provider"] = cloud_provider
        elif cloud_provider:
            _warn(f"Unknown --cloud-provider '{cloud_provider}'. Use: {', '.join(_VALID_CLOUD)}")
            raise typer.Exit(code=1)

        if model:
            llm["model"] = model
        if host:
            llm["host"] = host

        import os
        for flag_val, env_var, cfg_key in [
            (gemini_api_key, "GEMINI_API_KEY", "gemini_api_key"),
            (anthropic_api_key, "ANTHROPIC_API_KEY", "anthropic_api_key"),
            (openai_api_key, "OPENAI_API_KEY", "openai_api_key"),
        ]:
            resolved = flag_val or os.environ.get(env_var, "")
            if resolved:
                llm[cfg_key] = resolved
    else:
        # Interactive wizard
        overrides = _run_init_wizard(
            cloud_provider=llm.get("cloud_provider", "gemini"),
            gemini_api_key="",
            anthropic_api_key="",
            openai_api_key="",
        )
        llm.update(overrides)
        _offer_install(overrides, llm)

    if "provider" in llm:
        del llm["provider"]
    current_config["llm"] = llm
    cfg.save_config(paths, current_config)

    console.print()
    console.print("[bold green]Provider settings saved.[/bold green]")
    console.print(f"[dim]Backend: {describe_backend(current_config)}[/dim]")
    console.print()


@app.command()
def status() -> None:
    """Show the current wiki's stats, paths, and config."""
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)

    def _count_md(folder: Path) -> int:
        if not folder.exists():
            return 0
        return sum(1 for p in folder.glob("*.md") if not p.name.startswith("."))

    raw_files = 0
    for raw_dir in paths.raw_dirs:
        if raw_dir.exists():
            raw_files += sum(1 for p in raw_dir.rglob("*") if p.is_file() and not p.name.startswith("."))

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]LLM-Wiki Curator[/bold cyan]  [dim]@ {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    table = Table(title="Sources", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=22)
    table.add_column()
    table.add_row("Raw source files", str(raw_files))
    table.add_row("Sources tracked (DB)", str(stats["sources_total"]))
    table.add_row("Sources summarized (L1)", str(stats["sources_ingested"]))
    table.add_row("Ingest runs", str(stats["ingest_runs"]))
    console.print(table)

    pages_table = Table(title="Collections", show_header=False, box=None, padding=(0, 2))
    pages_table.add_column(style="dim", width=22)
    pages_table.add_column()

    l1 = _count_md(paths.summaries)
    l2 = _count_md(paths.atoms)
    l3 = _count_md(paths.concepts)
    l4 = _count_md(paths.synthesis)
    pages_table.add_row("L1 Summaries/",  str(l1))
    pages_table.add_row("L2 Atoms/",      str(l2))
    pages_table.add_row("L3 Concepts/",   str(l3))
    pages_table.add_row("L4 Synthesis/",  str(l4))
    pages_table.add_row("[bold]total[/bold]", f"[bold]{l1+l2+l3+l4}[/bold]")
    console.print(pages_table)

    cfg_table = Table(title="Config", show_header=False, box=None, padding=(0, 2))
    cfg_table.add_column(style="dim", width=22)
    cfg_table.add_column()
    llm = config.get("llm", {})
    search_cfg = config.get("search", {})
    cfg_table.add_row("LLM provider", llm.get("provider", "?"))
    cfg_table.add_row("LLM model", llm.get("model", "?"))
    cfg_table.add_row("LLM host", llm.get("host", "?"))
    cfg_table.add_row("Search backend", search_cfg.get("backend", "?"))
    cfg_table.add_row("Reranking", "on" if search_cfg.get("rerank") else "off")
    # Show QMD binary availability + resolved path
    qmd_bin = search.get_qmd_binary()
    if search.is_available():
        version = search.get_version() or "installed"
        cfg_table.add_row("QMD binary", f"[green]{version}[/green]  [dim]{qmd_bin}[/dim]")
    elif qmd_bin is not None:
        cfg_table.add_row("QMD binary", f"[yellow]not built[/yellow]  [dim]{qmd_bin}[/dim]")
    else:
        cfg_table.add_row("QMD binary", "[red]not found[/red]")
    console.print(cfg_table)

    console.print()
    if stats["sources_total"] == 0:
        _hint("No sources yet. Sync them with [bold]wiki sync[/bold]")
    elif stats["sources_ingested"] == 0:
        _hint(
            f"{stats['sources_total']} source(s) tracked but not ingested. "
            f"Stage 3 will add [bold]wiki ingest[/bold] to process them with the LLM."
        )


# ---------------------------------------------------------------------------
# Stage 2 commands
# ---------------------------------------------------------------------------


@app.command()
def sync(
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-generation of L1 Summaries even if they exist"
    ),
) -> None:
    """Sync raw directories with the tracking DB and generate L1 Summaries.

    Phase 1: Discover new/changed files in source dirs (02_Wiki, 03_Notes,
             04_Resources) and register them in the DB.
    Phase 2: For each file with status='pending' and no L1 Summary yet,
             generate an L1 Summary in `.curator/Collections/01_Summaries/`.
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)

    console.print()
    console.print(f"[dim]Scanning source directories for changes...[/dim]")
    console.print()

    # Phase 1: discover and register new/changed files
    discovered, removed = ingest_llm._auto_discover_pending(paths)

    if discovered or removed:
        msg = []
        if discovered:
            msg.append(f"{discovered} new/changed file(s)")
        if removed:
            msg.append(f"{removed} missing file(s) removed")
        _ok("Discovered " + ", ".join(msg) if discovered and not removed else ", ".join(msg))
    else:
        console.print("[dim]No new or changed files found.[/dim]")

    # Phase 2: generate L1 Summaries
    # --force: consider all sources (pending + ingested) so deleted summary files
    # are regenerated even when the source content hasn't changed.
    with db.connect(paths.state_db) as conn:
        if force:
            candidate_rows = conn.execute(
                "SELECT id, relpath, content_hash, summary_id FROM sources "
                "WHERE status IN ('pending', 'ingested') ORDER BY id ASC"
            ).fetchall()
        else:
            # Always include ingested sources too so we can detect missing summary files
            candidate_rows = conn.execute(
                "SELECT id, relpath, content_hash, summary_id FROM sources "
                "WHERE status IN ('pending', 'ingested') ORDER BY id ASC"
            ).fetchall()

    pending_rows = []
    for row in candidate_rows:
        if force:
            # Always re-generate under --force; reset ingested rows back to pending
            with db.connect(paths.state_db) as conn:
                conn.execute(
                    "UPDATE sources SET status = 'pending' WHERE id = ?",
                    (row["id"],),
                )
            pending_rows.append(row)
            continue

        sid = row["summary_id"]
        if not sid:
            pending_rows.append(row)
        else:
            # Smart heal: DB says done but summary file was deleted — regenerate
            summary_path = paths.summaries / f"{sid}.md"
            if not summary_path.exists():
                pending_rows.append(row)

    if not pending_rows:
        if not discovered:
            _hint("All sources are up to date. Run [bold]wiki ingest[/bold] to process any pending atoms.")
        return

    console.print()
    console.print(f"[dim]Generating L1 Summaries for {len(pending_rows)} pending source(s)...[/dim]")
    console.print()

    client = _start_client(config)

    try:
        summarized = 0
        for row in pending_rows:
            console.print(f"  [dim]summarizing[/dim] {row['relpath']}")
            summary_id = ingest_raw.generate_l1_summary(
                paths,
                source_id=row["id"],
                relpath=row["relpath"],
                content_hash=row["content_hash"],
                client=client,
                config=config,
                existing_summary_id=row["summary_id"],
                thinking=False,
            )
            if summary_id:
                _ok(f"  L1 [{summary_id}] ← {row['relpath']}")
                summarized += 1
            else:
                _warn(f"  Summary failed for {row['relpath']}")

        console.print()
        _ok(f"Sync complete: {discovered} discovered, {summarized} summarized")

        # Refresh qmd index so the new L1 summaries are searchable.
        if summarized > 0:
            _refresh_qmd_index(paths, embed=True)

        _hint("Run [bold]wiki ingest[/bold] to build L2 Atoms → L3 Concepts → L4 Synthesis.")
    finally:
        client.close()



@sources_app.command("list")
def sources_list_cmd(
    status_filter: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Only show sources with this status (pending|ingested|error).",
    ),
) -> None:
    """List all tracked sources."""
    paths = _resolve_root_or_die()
    rows = ingest_raw.list_sources(paths, status_filter=status_filter)

    if not rows:
        console.print()
        if status_filter:
            _warn(f"No sources with status '{status_filter}'")
        else:
            _warn("No sources tracked yet.")
            _hint("Discover them with [bold]wiki sync[/bold]")
        return

    table = Table(
        title=f"Sources ({len(rows)})",
        show_header=True,
        header_style="bold",
        row_styles=["", "dim"],
    )
    table.add_column("#", justify="right", style="cyan", width=5)
    table.add_column("Type", width=6)
    table.add_column("Size", justify="right", width=9)
    table.add_column("Added", width=10)
    table.add_column("Status", width=9)
    table.add_column("Path", overflow="fold")

    for row in rows:
        added_short = row["added_at"][:10] if row["added_at"] else ""
        status = row["status"]
        status_styled = f"[{_status_style(status)}]{status}[/{_status_style(status)}]"
        table.add_row(
            str(row["id"]),
            row["file_type"],
            _format_bytes(row["bytes"]),
            added_short,
            status_styled,
            row["relpath"],
        )

    console.print()
    console.print(table)
    console.print()


@sources_app.command("show")
def sources_show_cmd(
    source_id: int = typer.Argument(..., help="The source ID (from `wiki sources list`)."),
    preview_chars: int = typer.Option(
        800,
        "--preview",
        "-p",
        help="Number of characters of parsed text to preview.",
    ),
) -> None:
    """Show details for one source, including a text preview."""
    paths = _resolve_root_or_die()
    row = ingest_raw.get_source(paths, source_id)
    if row is None:
        _err(f"No source with id {source_id}")
        raise typer.Exit(code=1)

    # Re-parse the file to get title and a preview — we don't store parsed text
    # in the DB to keep it small. This is cheap (local file).
    from . import parsers

    file_path = paths.root / row["relpath"]
    if not file_path.exists():
        _err(f"Source file missing from disk: {file_path}")
        raise typer.Exit(code=1)

    try:
        parsed = parsers.parse(file_path)
    except parsers.ParserError as e:
        _err(f"Parse failed: {e}")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]#{row['id']}[/bold]  [cyan]{parsed.title}[/cyan]",
            border_style="cyan",
        )
    )

    meta_table = Table(show_header=False, box=None, padding=(0, 2))
    meta_table.add_column(style="dim", width=16)
    meta_table.add_column()
    meta_table.add_row("Path", row["relpath"])
    meta_table.add_row("Type", parsed.file_type)
    meta_table.add_row("Size", _format_bytes(row["bytes"]))
    meta_table.add_row("Words", f"{parsed.word_count:,}")
    meta_table.add_row("Added", row["added_at"])
    meta_table.add_row("Status", f"[{_status_style(row['status'])}]{row['status']}[/{_status_style(row['status'])}]")
    meta_table.add_row("Hash", row["content_hash"][:16] + "…")
    if row["last_ingested"]:
        meta_table.add_row("Last ingested", row["last_ingested"])
    for k, v in parsed.metadata.items():
        meta_table.add_row(k, str(v)[:80])
    console.print(meta_table)

    console.print()
    console.print("[dim]── text preview ──[/dim]")
    preview = parsed.text[:preview_chars]
    if len(parsed.text) > preview_chars:
        preview += f"\n\n[dim]… ({len(parsed.text) - preview_chars:,} more characters)[/dim]"
    console.print(preview)
    console.print()


@sources_app.command("rm")
def sources_rm_cmd(
    source_id: int = typer.Argument(..., help="The source ID to remove."),
    keep_file: bool = typer.Option(
        False,
        "--keep-file",
        help="Only remove from tracking; don't delete the file from raw/.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Remove a source from tracking (and optionally delete the file)."""
    paths = _resolve_root_or_die()
    row = ingest_raw.get_source(paths, source_id)
    if row is None:
        _err(f"No source with id {source_id}")
        raise typer.Exit(code=1)

    if not yes:
        action = "remove from tracking" if keep_file else "remove from tracking AND delete file"
        confirm = typer.confirm(
            f"About to {action}: #{source_id} {row['relpath']}. Proceed?"
        )
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(code=0)

    ok, msg = ingest_raw.remove_source(paths, source_id, delete_file=not keep_file)
    if ok:
        _ok(msg)
    else:
        _err(msg)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 3 — LLM ingest
# ---------------------------------------------------------------------------


class CliIngestCallbacks(ingest_llm.IngestCallbacks):
    """Rich terminal rendering of ingest progress."""

    def __init__(self, mode: str = "interactive") -> None:
        self.mode = mode
        self._stream_active = False
        self._stream_char_count = 0

    def on_start(self, source_id: int, source_title: str, summary_id: str) -> None:
        console.print()
        console.rule(f"[bold cyan]Source #{source_id}[/bold cyan]  {source_title}")
        if summary_id:
            console.print(f"[dim]L1 Summary: {summary_id}[/dim]")

    def on_pass1_start(self, atom_count: int) -> None:
        console.print(f"[dim]  Pass 1 — drafting {atom_count} Atom(s) (L2)...[/dim]")

    def on_atom_drafting(self, atom_id: str, name: str, operation: str) -> None:
        console.print()
        op_color = "green" if operation == "created" else "yellow"
        console.print(
            f"  [{op_color}]{operation}[/{op_color}] [dim]atom[/dim] "
            f"[cyan]{atom_id}[/cyan]  {name}"
        )
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True
        self._stream_char_count = 0

    def on_stream_chunk(self, chunk: str) -> None:
        if self._stream_active:
            console.print(chunk, end="", style="dim", highlight=False)
            self._stream_char_count += len(chunk)

    def on_atom_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_pass2_start(self, atom_count: int) -> None:
        console.print()
        console.print(f"[dim]  Pass 2 — clustering {atom_count} atom(s) into Concepts (L3)...[/dim]")

    def on_concept_drafting(self, concept_id: str, name: str) -> None:
        console.print(f"  [green]creating[/green] [dim]concept[/dim] [cyan]{concept_id}[/cyan]  {name}")
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True

    def on_concept_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_pass3_start(self, concept_count: int) -> None:
        console.print()
        console.print(f"[dim]  Pass 3 — synthesizing {concept_count} concept(s) into L4...[/dim]")

    def on_synthesis_drafting(self, syn_id: str, topic: str) -> None:
        console.print(f"  [magenta]creating[/magenta] [dim]synthesis[/dim] [cyan]{syn_id}[/cyan]  {topic}")
        console.print("[dim]┄[/dim]" * 60)
        self._stream_active = True

    def on_synthesis_written(self, page: ingest_llm.PageChange) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]┄[/dim]" * 60)
            self._stream_active = False

    def on_finalizing(self) -> None:
        console.print()
        console.print("[dim]finalizing (committing pages, rebuilding index, appending log)...[/dim]")

    def ask_confirm(self, summary: ingest_llm.SummaryData) -> bool:
        return True

    def on_complete(self, result: ingest_llm.IngestResult) -> None:
        console.print()
        if result.skipped:
            _warn(f"Skipped by user: {result.source_title}")
            return
        _ok(
            f"Ingested [bold]{result.source_title}[/bold] — "
            f"{result.atoms_created} atoms created, {result.atoms_updated} updated, "
            f"{result.concepts_created} concepts, {result.synthesis_created} synthesis"
        )

    def on_error(self, error: str) -> None:
        console.print()
        _err(error)


@app.command()
def ingest(
    source_id: Optional[int] = typer.Argument(
        None,
        help="Specific source ID to ingest. If omitted, processes all pending sources.",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Skip the interactive confirmation prompt for each source.",
    ),
    no_discover: bool = typer.Option(
        False,
        "--no-discover",
        help="Don't auto-scan raw/ for untracked files before ingesting.",
    ),
    no_thinking: bool = typer.Option(
        False,
        "--no-thinking",
        help="Disable Qwen3 thinking mode in Pass 1 (faster, slightly lower quality).",
    ),
) -> None:
    """Build the L2-L4 knowledge layer from L1 Summaries in Collections/.

    Writes only to .curator/Collections/ — never to the source vault dirs.

    The pipeline runs three LLM passes per source:
      Pass 1 (thinking mode) — extract irreducible facts → L2 Atoms/
      Pass 2 — cluster atoms into coherent units → L3 Concepts/
      Pass 3 — cross-domain synthesis → L4 Synthesis/

    Then rebuilds index.md and appends to log.md.
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    # Build the right client based on system RAM
    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    client = _start_client(config)

    if isinstance(client, FailoverClient):
        active = client.active_provider
        chain = " → ".join(type(p).__name__ for p in client.providers)
        provider_label = f"Failover [active: {type(active).__name__}] ({chain})"
    elif isinstance(client, GeminiClient):
        provider_label = "Gemini"
    elif isinstance(client, ClaudeClient):
        provider_label = f"Claude [{client.model}]"
    else:
        provider_label = f"Ollama [{llm_cfg.get('model', 'deepseek-r1:14b')}]"
    _ok(f"LLM ready · [bold]{provider_label}[/bold]")

    mode = "batch" if batch else "interactive"
    thinking = not no_thinking

    try:
        if source_id is not None:
            # Single source: run Phase A (atoms), then global Phase B/C/D via ingest_pending
            # We mark it pending temporarily so ingest_pending picks it up, but actually
            # we call ingest_source directly then run the global phases manually.
            cb = CliIngestCallbacks(mode=mode)
            result = ingest_llm.ingest_source(
                paths,
                source_id,
                client,
                cb,
                mode=mode,
                thinking_for_extraction=thinking,
            )
            results = [result]
            if result.ok:
                # Phase B + C + D globally
                console.print()
                console.print("[dim]  Phase B — clustering all Atoms into Concepts (global)...[/dim]")
                console.print("[dim]  Phase C — synthesizing all Concepts (global)...[/dim]")
                global_cb = CliIngestCallbacks(mode=mode)
                today = ingest_llm._now_iso()
                import tempfile, shutil
                staging = __import__("pathlib").Path(tempfile.mkdtemp(prefix="curator-global-"))
                try:
                    con_staged = ingest_llm._run_global_pass2_concepts(paths, client, global_cb, today, staging)
                    for sp, fp, _ in con_staged:
                        fp.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(sp, fp)
                    syn_staged = ingest_llm._run_global_pass3_synthesis(paths, client, global_cb, today, staging)
                    for sp, fp, _ in syn_staged:
                        fp.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(sp, fp)
                    from . import page_writer as _pw
                    _pw.rebuild_index(paths, today)
                    all_ch = [c for _, _, c in con_staged + syn_staged]
                    if all_ch:
                        bullets = [f"{c.operation}: [[{c.path.replace('.md','')}]]" for c in all_ch]
                        _pw.append_log_entry(paths, today, "ingest", result.source_title, bullets)
                    ingest_llm._update_ledger(paths)
                    ingest_llm._update_overview(paths)
                    if con_staged:
                        console.print(f"  [green]+{len(con_staged)} concept(s)[/green]")
                    if syn_staged:
                        console.print(f"  [magenta]+{len(syn_staged)} synthesis page(s)[/magenta]")
                finally:
                    shutil.rmtree(str(staging), ignore_errors=True)
        else:
            # All pending (with auto-discovery) — full global pipeline inside ingest_pending
            results = ingest_llm.ingest_pending(
                paths,
                client,
                lambda: CliIngestCallbacks(mode=mode),
                mode=mode,
                auto_discover=not no_discover,
                thinking_for_extraction=thinking,
            )
    finally:
        client.close()

    if not results:
        console.print()
        _warn("No pending sources to ingest.")
        _hint("Sync sources with [bold]wiki sync[/bold] first.")
        return

    console.print()
    console.rule("[bold]Ingest summary[/bold]")
    ok_count = sum(1 for r in results if r.ok)
    skipped_count = sum(1 for r in results if r.skipped)
    error_count = sum(1 for r in results if r.error)
    total_created = sum(r.pages_created for r in results)
    total_updated = sum(r.pages_updated for r in results)

    parts = []
    if ok_count:
        parts.append(f"[green]{ok_count} ingested[/green]")
    if skipped_count:
        parts.append(f"[yellow]{skipped_count} skipped[/yellow]")
    if error_count:
        parts.append(f"[red]{error_count} errors[/red]")
    console.print("  " + " · ".join(parts))
    console.print(
        f"  [dim]total pages: {total_created} created, {total_updated} updated[/dim]"
    )
    console.print()

    if ok_count > 0:
        console.print()
        _refresh_qmd_index(paths, embed=True)

        console.print()
        _hint("Run [bold]wiki status[/bold] to see updated page counts.")
        _hint("Ask a question with [bold]wiki query \"<your question>\"[/bold]")


# ---------------------------------------------------------------------------
# Stage 4 — query
# ---------------------------------------------------------------------------


class CliQueryCallbacks(query_module.QueryCallbacks):
    """Rich terminal rendering of query progress."""

    def __init__(self) -> None:
        self._stream_active = False

    def on_start(self, question: str, mode: str) -> None:
        console.print()
        console.rule(f"[bold cyan]Query[/bold cyan]")
        console.print(f"[bold]Q:[/bold] {question}")
        console.print(f"[dim]mode: {mode}[/dim]")
        console.print()

    def on_classifying_intent(self) -> None:
        console.print("[dim]  understanding question…[/dim]")

    def on_intent_classified(self, intent: str) -> None:
        if intent == "chitchat":
            console.print("[dim]  → casual question, no search needed[/dim]")
        else:
            console.print("[dim]  → wiki question, searching…[/dim]")

    def on_chitchat_reply(self, reply: str) -> None:
        console.print()
        console.print("[dim]" + "─" * 72 + "[/dim]")
        console.print(reply)
        console.print("[dim]" + "─" * 72 + "[/dim]")
        console.print()

    def on_searching(self) -> None:
        console.print("[dim]  searching wiki (BM25 + vector + rerank)…[/dim]")

    def on_search_done(self, results) -> None:
        if getattr(results, "fallback_mode", ""):
            _warn("GPU OOM — fell back to BM25 search (no vector/rerank).")
        if not len(results):
            return
        console.print(f"[dim]  found {len(results)} relevant page(s):[/dim]")
        for i, hit in enumerate(results.hits, start=1):
            score_color = (
                "green" if hit.score > 0.7 else "yellow" if hit.score > 0.4 else "dim"
            )
            path = hit.full_path or hit.path
            title = hit.title or path
            console.print(
                f"    [dim]{i}.[/dim] [{score_color}]{hit.score:.2f}[/{score_color}] "
                f"[cyan]{path}[/cyan]  [dim]{title[:60]}[/dim]"
            )

    def on_no_results(self) -> None:
        console.print()
        _warn("No matching wiki pages found.")

    def on_synthesizing(self) -> None:
        console.print()
        console.print("[dim]  synthesizing answer…[/dim]")
        console.print("[dim]" + "─" * 72 + "[/dim]")
        self._stream_active = True

    def on_stream_chunk(self, chunk: str) -> None:
        if self._stream_active:
            console.print(chunk, end="", highlight=False)

    def on_saved(self, saved_path: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _ok(f"Saved answer as [cyan]{saved_path}[/cyan]")

    def on_wiki_saved(self, saved_path: str, category: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _ok(
            f"Promoted to [cyan]{saved_path}[/cyan]  "
            f"[dim](category: {category})[/dim]"
        )

    def on_complete(self, result) -> None:
        if self._stream_active:
            console.print()
            console.print("[dim]" + "─" * 72 + "[/dim]")
            self._stream_active = False
        console.print()

    def on_error(self, error: str) -> None:
        if self._stream_active:
            console.print()
            self._stream_active = False
        console.print()
        _err(error)


@app.command()
def query(
    question: Optional[str] = typer.Argument(
        None,
        help="The question to ask the wiki. If omitted, enters interactive chat mode (press Enter on empty line to exit).",
    ),
    mode: str = typer.Option(
        "hybrid",
        "--mode",
        help="Search mode: hybrid | lex | vec",
    ),
    lex: bool = typer.Option(
        False,
        "--lex",
        help="Shortcut for --mode lex (BM25 only, fastest).",
    ),
    vec: bool = typer.Option(
        False,
        "--vec",
        help="Shortcut for --mode vec (vector only).",
    ),
    limit: int = typer.Option(
        8, "--limit", "-n", help="Max number of search hits to consider."
    ),
    min_score: float = typer.Option(
        0.0, "--min-score", help="Drop hits below this score."
    ),
    no_rerank: bool = typer.Option(
        False, "--no-rerank", help="Skip LLM reranking in hybrid mode."
    ),
    save_as: Optional[str] = typer.Option(
        None,
        "--save-as",
        help="Save the answer as a new L4 Synthesis page (filename SYN-UUID.md). "
             "The value is used as the page title hint.",
    ),
    scope: str = typer.Option(
        "all",
        "--scope",
        help="Restrict to a single Curator layer: all | summaries | atoms | concepts | synthesis.",
    ),
    no_intent_classify: bool = typer.Option(
        False,
        "--no-intent-classify",
        help="Skip intent classification step (saves ~3 sec per query).",
    ),
) -> None:
    """Ask a question: search the wiki, synthesize an answer with citations.

    Without an argument, enters interactive chat mode. Type an empty line to exit.
    Within a session you can say '승격해줘' / 'save to wiki' etc. to promote the
    last answer into 02_Wiki under an auto-determined category folder.

    The query pipeline:
      1. Translate question to English (for non-English input)
      2. QMD search (BM25 + vector + rerank by default)
      3. Synthesize a cited answer from Curator pages, streamed to the terminal
      4. Optionally save as a Synthesis page (--save-as) or promote to 02_Wiki
    """
    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)

    # Resolve search mode shortcuts
    if lex:
        mode = "lex"
    elif vec:
        mode = "vec"
    if mode not in ("hybrid", "lex", "vec"):
        _err(f"Invalid mode '{mode}'. Use hybrid, lex, or vec.")
        raise typer.Exit(code=1)

    if scope not in ("all", "summaries", "atoms", "concepts", "synthesis"):
        _err(
            f"Invalid scope '{scope}'. Use all, summaries, atoms, concepts, or synthesis."
        )
        raise typer.Exit(code=1)

    if not search.is_available():
        _err("qmd binary not available.")
        _hint(
            "Build the bundled copy: "
            "[bold]cd src/qmd && bun install && bun run build[/bold]"
        )
        raise typer.Exit(code=1)

    collection_pages = 0
    for layer_dir in (paths.summaries, paths.atoms, paths.concepts, paths.synthesis):
        if layer_dir.exists():
            collection_pages += sum(
                1 for p in layer_dir.glob("*.md") if not p.name.startswith(".")
            )
    if collection_pages == 0:
        _err("Curator collections are empty.")
        _hint("Run [bold]wiki sync[/bold] then [bold]wiki ingest[/bold] first.")
        raise typer.Exit(code=1)

    console.print()
    console.print(f"[dim]{describe_backend(config)}…[/dim]")
    client = _start_client(config)
    _ok(f"LLM ready · [bold]{type(client).__name__}[/bold]")

    run_kwargs = dict(
        mode=mode,
        limit=limit,
        min_score=min_score,
        rerank=not no_rerank,
        save_as=save_as,
        scope=scope,
        classify_intent_first=not no_intent_classify,
    )

    callbacks = CliQueryCallbacks()

    try:
        _run_query_repl(paths, client, callbacks, run_kwargs, initial_question=question)
    finally:
        client.close()


def _run_query_repl(
    paths, client, callbacks, run_kwargs, *, initial_question: str | None = None
) -> None:
    """Interactive REPL: ask questions until the user submits an empty line.

    If initial_question is provided, it is answered first before prompting
    for further input — so `wiki query "question"` enters the same REPL.
    """
    from rich.prompt import Prompt

    last_question: str | None = None
    last_answer: str | None = None

    console.print()
    console.rule("[bold cyan]Wiki Chat[/bold cyan]")
    console.print(
        "[dim]Ask questions about your wiki. "
        "Press [bold]Enter[/bold] (empty line) or [bold]Ctrl+C[/bold] to exit.[/dim]"
    )
    console.print(
        "[dim]Say '승격해줘' / 'save to wiki' to promote the last answer to 02_Wiki.[/dim]"
    )

    pending = initial_question  # consumed on the first iteration, no extra print needed

    while True:
        if pending:
            user_input = pending
            pending = None
        else:
            try:
                user_input = Prompt.ask("\n[bold cyan]Q[/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break

        if not user_input:
            break

        # Run intent classification to detect promote vs wiki vs chitchat
        from . import intent as intent_module

        intent_result = intent_module.classify_intent(client, user_input)

        if intent_result.intent == "promote":
            if last_answer and last_question:
                confirmed = Prompt.ask(
                    "  [yellow]02_Wiki에 저장할까요?[/yellow]",
                    choices=["yes", "no"],
                    default="yes",
                )
                if confirmed == "yes":
                    console.print("[dim]  카테고리/슬러그 분류 중…[/dim]")
                    try:
                        category, slug = query_module.classify_wiki_topic(
                            client, last_question, last_answer
                        )
                        saved = query_module.save_wiki_page(
                            paths, last_question, last_answer, category, slug
                        )
                        callbacks.on_wiki_saved(saved, category)
                    except OSError as e:
                        _err(f"Failed to save wiki page: {e}")
            else:
                _warn("저장할 답변이 없습니다. 먼저 질문해 주세요.")
            continue

        # Normal wiki query (or chitchat — run_query handles it)
        result = query_module.run_query(
            paths,
            client,
            user_input,
            callbacks,
            **{**run_kwargs, "classify_intent_first": False},
        )
        if result.answer:
            last_question = user_input
            last_answer = result.answer


@app.command()
def reindex() -> None:
    """Force a full rebuild of the QMD search index.

    Normally this runs automatically after `wiki ingest`, so you only need
    this if the index gets out of sync (e.g. you edited wiki pages manually).
    """
    paths = _resolve_root_or_die()
    if not search.is_available():
        _err("qmd binary not available.")
        _hint(
            "Build the bundled copy: "
            "[bold]cd src/qmd && bun install && bun run build[/bold]"
        )
        raise typer.Exit(code=1)

    console.print()
    console.print("[dim]Rebuilding search index (this may take a minute)…[/dim]")
    try:
        search.update_index(paths, embed=True)
        _ok("Search index rebuilt")
    except search.SearchBackendError as e:
        _err(f"Index rebuild failed: {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 5 — lint
# ---------------------------------------------------------------------------


_SEVERITY_STYLE = {
    lint_module.Severity.ERROR: ("bold red", "✗"),
    lint_module.Severity.WARNING: ("yellow", "!"),
    lint_module.Severity.INFO: ("cyan", "i"),
}


def _render_lint_report_terminal(report: lint_module.LintReport) -> None:
    """Pretty-print a LintReport to the terminal using Rich."""
    console.print()
    # Summary panel
    score = report.health_score
    score_color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    summary_lines = [
        f"[bold]Health score:[/bold] [{score_color}]{score}/100[/{score_color}]",
        f"[bold]Pages checked:[/bold] {report.pages_checked}",
        f"[bold]Duration:[/bold] {report.duration_seconds:.2f}s",
        "",
        f"  [red]{len(report.errors)} errors[/red]"
        f" · [yellow]{len(report.warnings)} warnings[/yellow]"
        f" · [cyan]{len(report.infos)} infos[/cyan]",
    ]
    if report.auto_fixed:
        summary_lines.append(f"  [green]auto-fixed: {report.auto_fixed}[/green]")
    console.print(
        Panel.fit("\n".join(summary_lines), title="Lint Report", border_style="cyan")
    )

    if not report.issues:
        console.print()
        _ok("No issues found. Your wiki is in good shape!")
        return

    # Group by severity → display
    def _render_group(
        title: str, issues: list[lint_module.LintIssue], color: str
    ) -> None:
        if not issues:
            return
        console.print()
        console.rule(f"[bold {color}]{title} ({len(issues)})[/bold {color}]")

        # Group by page for cleaner reading
        by_page: dict[str, list[lint_module.LintIssue]] = {}
        for issue in issues:
            by_page.setdefault(issue.page, []).append(issue)

        for page, page_issues in by_page.items():
            console.print(f"\n  [cyan]{page}[/cyan]")
            for issue in page_issues:
                style, glyph = _SEVERITY_STYLE[issue.severity]
                # Escape any brackets in the message since wikilinks look
                # like Rich markup tags
                from rich.markup import escape as _escape
                safe_msg = _escape(issue.message)
                safe_suggestion = _escape(issue.suggestion) if issue.suggestion else ""
                console.print(
                    f"    [{style}]{glyph}[/{style}] "
                    f"[dim]{issue.check.value}:[/dim] {safe_msg}"
                )
                if safe_suggestion:
                    console.print(f"      [dim]→ {safe_suggestion}[/dim]")
                if issue.fixable:
                    console.print(
                        f"      [green dim]✓ auto-fixable[/green dim]"
                    )

    _render_group("Errors", report.errors, "red")
    _render_group("Warnings", report.warnings, "yellow")
    _render_group("Info", report.infos, "cyan")


@app.command()
def lint(
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Run LLM-powered contradiction detection (slower, requires Ollama).",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix trivial issues (malformed wikilinks, noise in sources).",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Save the report as .curator/Collections/04_Synthesis/SYN-lint-YYYY-MM-DD.md",
    ),
    max_pairs: int = typer.Option(
        10,
        "--max-pairs",
        help="Max page pairs to check in --deep mode.",
    ),
) -> None:
    """Lint the wiki for broken links, orphans, missing pages, and more.

    Fast checks (default) run entirely in Python and finish in seconds.
    Use --deep to also scan page pairs for contradictions using Qwen3.
    """
    paths = _resolve_root_or_die()

    # Automatically refresh all manifest and log files during lint
    from . import page_writer as _pw
    from . import ingest_llm as _ingest
    today = _pw.today_iso()
    _pw.rebuild_index(paths, today)
    _ingest._update_overview(paths)
    _ingest._update_ledger(paths)
    _pw.append_log_entry(
        paths,
        today,
        "lint",
        "system",
        ["Ran wiki lint and updated all manifests"],
    )


    # If --deep, verify LLM backend up front
    client = None
    if deep:
        config = cfg.load_config(paths)
        console.print(f"[dim]{describe_backend(config)}…[/dim]")
        client = _start_client(config)
        _ok(f"LLM ready · [bold]{type(client).__name__}[/bold]")

    try:
        console.print()
        if deep:
            console.print("[dim]Running fast checks + contradiction detection…[/dim]")
        else:
            console.print("[dim]Running fast checks…[/dim]")

        report = lint_module.run_lint(paths, deep=deep, client=client)
    finally:
        if client is not None:
            client.close()

    # Auto-fix before displaying
    if fix:
        fixed_count = lint_module.apply_fixes(paths, report.issues)
        report.auto_fixed = fixed_count
        if fixed_count > 0:
            # Rebuild inventory + re-run checks so the report reflects post-fix state
            report = lint_module.run_lint(paths, deep=False, client=None)
            report.auto_fixed = fixed_count

    _render_lint_report_terminal(report)

    # Save as an L4 Synthesis page
    if save:
        import uuid as _uuid
        today = lint_module.page_writer.today_iso()
        syn_id = f"SYN-lint-{today}-{_uuid.uuid4().hex[:4]}"
        target_path = paths.synthesis / f"{syn_id}.md"
        content = lint_module.render_report_markdown(report, paths)
        lint_module.page_writer.write_page(target_path, content)
        lint_module.page_writer.rebuild_index(paths, today)
        console.print()
        _ok(f"Saved report to [cyan]04_Synthesis/{syn_id}.md[/cyan]")

    # Exit code: 1 if there are errors, 0 otherwise (for CI use)
    if report.errors:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Stage 6 — web UI removed (per user request)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# wiki config models — Discover and select Ollama models
# ---------------------------------------------------------------------------


@config_models_app.command("list")
def models_list(
    host: str = typer.Option(
        "",
        "--host",
        "-H",
        help="Ollama host URL to query (overrides config).",
    ),
) -> None:
    """List models available on the configured Ollama host(s).

    Checks local Ollama (llm.host) and, if configured, the remote host
    (llm.remote_ollama_host). Use --host to query an arbitrary URL.
    """
    discovered = cfg.find_wiki_root()
    if discovered is not None:
        paths = cfg.paths_from_config(discovered)
        llm_cfg = cfg.load_config(paths).get("llm", {})
    else:
        llm_cfg = {}

    if host:
        targets = [("custom", host)]
    else:
        local_host = llm_cfg.get("host", DEFAULT_OLLAMA_HOST)
        targets = [("local", local_host)]
        remote = (llm_cfg.get("remote_ollama_host") or "").strip()
        if remote:
            targets.append(("remote", remote))

    configured_model = llm_cfg.get("model", "")
    any_found = False

    for label, h in targets:
        console.print(f"\n[bold]Ollama models — {label}[/bold]  [dim]{h}[/dim]")
        models_vision = list_ollama_models_with_vision(h, timeout=5.0)
        if not models_vision:
            _warn(f"  Ollama unreachable at {h}")
            continue
        any_found = True
        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Model", style="cyan")
        table.add_column("Vision", style="magenta")
        table.add_column("Active", style="green")
        for m, vision in sorted(models_vision, key=lambda x: x[0]):
            active = "✓" if configured_model and (m == configured_model or m.startswith(configured_model)) else ""
            vision_mark = "✓" if vision else ""
            table.add_row(m, vision_mark, active)
        console.print(table)
        console.print("[dim]Vision ✓ = model supports image inference[/dim]")

    if not any_found:
        console.print()
        _hint("Start Ollama with [bold]ollama serve[/bold] or set [bold]llm.remote_ollama_host[/bold] in config.")

    # Show the curated recommendation table below the installed-models list
    primary_host = targets[0][1] if targets else DEFAULT_OLLAMA_HOST
    _show_recommended_models(primary_host)


@config_models_app.command("use")
def models_use(
    model: str = typer.Argument(
        None, help="Model tag to activate (e.g. gemma4:31b). Omit to pick from the recommendation list."
    ),
    host: str = typer.Option(
        "",
        "--host",
        "-H",
        help="Ollama host to verify model availability (default: from config).",
    ),
) -> None:
    """Set the active Ollama model in project config.

    With no argument: shows the recommendation list and prompts for a choice.
    If the chosen model is not yet pulled, automatically runs `ollama pull` first.
    If Ollama is unreachable, saves the config without verification.
    """
    import subprocess

    paths = _resolve_root_or_die()
    config = cfg.load_config(paths)
    llm_cfg = config.get("llm", {})

    target_host = host or llm_cfg.get("remote_ollama_host", "").strip() or llm_cfg.get("host", DEFAULT_OLLAMA_HOST)

    # No model given → show recommendation table and prompt interactively
    if not model:
        _show_recommended_models(target_host)
        console.print()
        model = typer.prompt(
            "  모델 태그 입력 (Enter = 취소)",
            default="",
            show_default=False,
        ).strip()
        if not model:
            console.print("[dim]취소됨.[/dim]")
            raise typer.Exit()

    available = list_models_on_host(target_host, timeout=5.0)

    if available:
        if not any(m == model or m.startswith(model) for m in available):
            console.print(f"[dim]Model '{model}' not found locally — pulling…[/dim]")
            try:
                subprocess.run(["ollama", "pull", model], check=True)
            except FileNotFoundError:
                _warn("'ollama' CLI not found in PATH. Is Ollama installed?")
                raise typer.Exit(code=1)
            except subprocess.CalledProcessError as e:
                _warn(f"ollama pull failed (exit {e.returncode}).")
                raise typer.Exit(code=1)
            _ok(f"Pulled {model}")
        else:
            _ok(f"Verified: {model} is available on {target_host}")
    else:
        _warn(f"Ollama unreachable at {target_host} — saving model without verification.")

    config.setdefault("llm", {})["model"] = model
    cfg.save_config(paths, config)
    _ok(f"Model set to [bold]{model}[/bold] in {paths.config_file.relative_to(paths.root)}")
    _hint("Run [bold]wiki sync[/bold] to start using the new model.")


# ---------------------------------------------------------------------------
# Stage 7 — MCP server (workspace agent integration)
# ---------------------------------------------------------------------------


mcp_app = typer.Typer(
    name="mcp",
    help="Run or install the LLM-Wiki MCP server for workspace agents.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)
app.add_typer(mcp_app, name="mcp")


@mcp_app.callback()
def mcp_callback(ctx: typer.Context) -> None:
    """Default `wiki mcp` (no subcommand) starts the stdio server."""
    if ctx.invoked_subcommand is not None:
        return
    paths = _resolve_root_or_die()
    # Pin WIKI_ROOT so the server picks up the same vault even if MCP clients
    # spawn it from an unrelated cwd.
    import os as _os
    _os.environ["WIKI_ROOT"] = str(paths.root)
    try:
        from . import mcp_server
    except ImportError as e:
        _err(str(e))
        _hint("Install with: [bold]uv pip install -e '.[mcp]'[/bold]")
        raise typer.Exit(code=1)
    mcp_server.serve_stdio()


@mcp_app.command("install")
def mcp_install_cmd(
    target: str = typer.Argument(
        "all",
        help="Which client to print a snippet for: claude | gemini | all.",
    ),
) -> None:
    """Print MCP config snippets to paste into your agent's settings.

    Does NOT modify any settings files — copy/paste the printed JSON into
    your client's configuration manually. Both Claude (Code / Desktop) and
    Gemini CLI use the same MCP `mcpServers` format.
    """
    paths = _resolve_root_or_die()
    try:
        from . import mcp_server
    except ImportError as e:
        _err(str(e))
        _hint("Install with: [bold]uv pip install -e '.[mcp]'[/bold]")
        raise typer.Exit(code=1)

    snippets = mcp_server.render_install_snippets(paths)
    target = target.lower()
    if target not in ("claude", "gemini", "all"):
        _err(f"Unknown target '{target}'. Use claude | gemini | all.")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]LLM-Wiki MCP install[/bold]\n[dim]vault: {paths.root}[/dim]",
            border_style="cyan",
        )
    )

    if target in ("claude", "all"):
        console.print()
        console.rule("[bold]Claude Code / Desktop[/bold]")
        console.print(
            "Paste into one of:\n"
            "  • Claude Code:    [cyan]~/.claude/settings.json[/cyan]\n"
            "  • Claude Desktop: [cyan]~/Library/Application Support/Claude/claude_desktop_config.json[/cyan] (macOS)\n"
            "                    [cyan]%APPDATA%\\Claude\\claude_desktop_config.json[/cyan] (Windows)"
        )
        console.print()
        console.print(snippets["claude"])

    if target in ("gemini", "all"):
        console.print()
        console.rule("[bold]Gemini CLI[/bold]")
        console.print(
            "Paste into:\n"
            "  • [cyan]~/.gemini/settings.json[/cyan]"
        )
        console.print()
        console.print(snippets["gemini"])

    console.print()
    _hint(
        "If your client merges with existing `mcpServers`, add only the "
        "[bold]llm-wiki[/bold] entry."
    )
    _hint("After pasting, restart the agent so it reloads MCP config.")


def main() -> None:
    """Entry point used by the `wiki` console script."""
    app()


if __name__ == "__main__":
    main()
