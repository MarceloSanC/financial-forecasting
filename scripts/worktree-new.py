"""Cria uma worktree git pronta para implementação de uma nova branch.

Permite trabalhar em uma branch separada em paralelo com a branch atual,
sem `git stash`/checkout no checkout principal. Em um único comando:

  1. Valida o nome da branch contra o padrão de CONVENTIONS.md §4.
  2. Confere que a issue referenciada existe no backlog do GitHub
     (gate "issue-first" — GIT-WORKFLOW.md §Princípios fundamentais #1).
     Opcionalmente cria a issue antes via `gh issue create`.
  3. Cria a worktree em `../<repo>-worktrees/<branch-slug>/` saindo de
     `origin/<base>` (default `develop`; `main` para `hotfix/...`).
  4. Copia `.env` (e `.env.local` se existir) do checkout principal.
  5. Roda `make setup` na worktree (uv venv + deps + pre-commit hooks),
     com fallback para `uv` direto se `make` não estiver disponível.
  6. Abre uma nova janela do VS Code na worktree (`code -n <path>`).

Uso:
    uv run python scripts/worktree-new.py <branch>
    uv run python scripts/worktree-new.py feat/42-add-google-login
    uv run python scripts/worktree-new.py feat/89-2-3-s3-adapter
    uv run python scripts/worktree-new.py hotfix/103-prod-bug

    # Criar issue automaticamente antes (substitui <num> no nome):
    uv run python scripts/worktree-new.py feat/-add-google-login \\
        --create-issue --issue-title "feat: adicionar login com Google"

    # Skips:
    uv run python scripts/worktree-new.py fix/57-timeout --no-setup --no-vscode

Convenções respeitadas:
    - Nome de branch em inglês (kebab-case ASCII) — CONVENTIONS.md §1.
    - Formato `<tipo>/<num-issue>-<slug>` ou Stage
      `<tipo>/<num-issue>-<N-M>-<slug>` — CONVENTIONS.md §4.
    - Base remota: `develop` (feat/fix/refactor/...) ou `main` (hotfix).
    - "Uma branch em voo por vez" deixa de ser bloqueio quando o
      paralelismo acontece em **worktrees separadas** (cada worktree é
      um checkout independente). Ver GIT-WORKFLOW.md §Worktrees paralelas.

Exit codes:
  0  worktree criada com sucesso
  1  validação falhou (nome de branch inválido, issue ausente, etc.)
  2  erro de execução de subprocess (git/gh/uv/make)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tipos aceitos no prefixo do branch — espelha CONVENTIONS.md §4.
BRANCH_TYPES = {
    "feat", "fix", "refactor", "test", "docs", "style",
    "perf", "chore", "ci", "build", "hotfix",
}

# Slug do branch: <tipo>/<num>-<slug>  ou  <tipo>/<num>-<N-M>-<slug>
# - <tipo>: um dos BRANCH_TYPES
# - <num>: dígitos (id da issue)
# - <slug>: kebab-case ASCII (a-z, 0-9, -)
# - <N-M> (opcional, só para Stages): dois números separados por '-'
_BRANCH_RE = re.compile(
    r"^(?P<type>[a-z]+)/(?P<num>\d+)-(?:(?P<stage>\d+-\d+)-)?(?P<slug>[a-z0-9][a-z0-9-]{1,})$"
)
# Limite de chars do nome completo do branch (mesma ordem do CONVENTIONS.md §1).
BRANCH_MAX_LEN = 60


# ---------------------------------------------------------------------------
# helpers de IO / processo
# ---------------------------------------------------------------------------

def _force_utf8_stdio() -> None:
    """Garante UTF-8 em stdout/stderr (Windows defaulta cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() == "utf-8":
            continue
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Wrapper de subprocess.run com mensagens claras de falha."""
    printable = " ".join(cmd)
    if not capture:
        print(f"  $ {printable}")
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=check,
            text=True,
            capture_output=capture,
        )
    except FileNotFoundError as e:
        print(f"ERRO: executável não encontrado: {cmd[0]} ({e})", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERRO: comando falhou (exit {e.returncode}): {printable}",
              file=sys.stderr)
        if capture and e.stdout:
            print(e.stdout, file=sys.stderr)
        if capture and e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(2)


def _info(msg: str) -> None:
    print(f"  • {msg}")


def _section(title: str) -> None:
    print()
    print(f"== {title} ==")


def _fail(msg: str, *, exit_code: int = 1) -> None:
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# validação de nome de branch
# ---------------------------------------------------------------------------

def parse_branch(branch: str) -> dict[str, str]:
    """Valida e decompõe o nome do branch conforme CONVENTIONS.md §4.

    Retorna dict com keys: type, num, stage (pode ser ''), slug, full.
    """
    if len(branch) > BRANCH_MAX_LEN:
        _fail(f"branch tem {len(branch)} chars (limite {BRANCH_MAX_LEN}). "
              "Use slug mais curto.")
    m = _BRANCH_RE.match(branch)
    if m is None:
        _fail(
            f"nome de branch inválido: {branch!r}\n"
            "Esperado: <tipo>/<num-issue>-<slug>  ou  <tipo>/<num-issue>-<N-M>-<slug>\n"
            "Exemplos:\n"
            "  feat/42-add-google-login\n"
            "  fix/57-fix-timeout\n"
            "  feat/89-2-3-s3-source-adapter   (Stage 2.3)\n"
            "  hotfix/103-prod-cors\n"
            "Tipo deve ser um de: " + ", ".join(sorted(BRANCH_TYPES))
        )
    parts = m.groupdict()
    if parts["type"] not in BRANCH_TYPES:
        _fail(f"tipo de branch inválido: {parts['type']!r}. "
              f"Use um de: {', '.join(sorted(BRANCH_TYPES))}")
    parts["stage"] = parts["stage"] or ""
    parts["full"] = branch
    return parts


def default_base(branch_type: str) -> str:
    """Default da base remota: hotfix → main; resto → develop."""
    return "main" if branch_type == "hotfix" else "develop"


# ---------------------------------------------------------------------------
# git / gh helpers
# ---------------------------------------------------------------------------

def git_top() -> Path:
    """Raiz do worktree principal (não da worktree atual, se aninhada)."""
    cp = _run(["git", "rev-parse", "--show-toplevel"], capture=True)
    return Path(cp.stdout.strip()).resolve()


def git_common_dir() -> Path:
    """`.git/` comum (no main checkout). Útil pra checar refs/branches."""
    cp = _run(["git", "rev-parse", "--git-common-dir"], capture=True)
    return Path(cp.stdout.strip()).resolve()


def branch_exists(branch: str) -> tuple[bool, bool]:
    """Retorna (local_exists, remote_exists)."""
    local = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0
    remote = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
        check=False,
    ).returncode == 0
    return local, remote


def gh_available() -> bool:
    if shutil.which("gh") is None:
        return False
    cp = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, check=False,
    )
    return cp.returncode == 0


def gh_issue_exists(num: int) -> bool:
    cp = subprocess.run(
        ["gh", "issue", "view", str(num), "--json", "number,state"],
        capture_output=True, text=True, check=False,
    )
    if cp.returncode != 0:
        return False
    try:
        data = json.loads(cp.stdout)
        return data.get("number") == num
    except json.JSONDecodeError:
        return False


def gh_issue_create(title: str, body: str) -> int:
    """Cria issue via `gh issue create` e retorna o número."""
    cp = _run(
        ["gh", "issue", "create", "--title", title, "--body", body],
        capture=True,
    )
    # `gh issue create` imprime a URL no stdout, no formato:
    #   https://github.com/<owner>/<repo>/issues/<num>
    last_line = cp.stdout.strip().splitlines()[-1]
    m = re.search(r"/issues/(\d+)\s*$", last_line)
    if m is None:
        _fail(f"não foi possível extrair o número da issue criada: {last_line!r}",
              exit_code=2)
    return int(m.group(1))


# ---------------------------------------------------------------------------
# passos principais
# ---------------------------------------------------------------------------

def ensure_issue(num: int, *, create_title: str | None, create_body: str | None) -> int:
    """Garante que a issue existe; cria se solicitado. Retorna o número final."""
    if not gh_available():
        print(
            "  AVISO: `gh` indisponível ou não autenticado — não posso validar a issue\n"
            "  no GitHub. Prosseguindo (best-effort). Para ativar, instale `gh` e\n"
            "  rode `gh auth login`.",
            file=sys.stderr,
        )
        return num

    if create_title is not None:
        if num != 0:
            _info(f"--create-issue ignorado: já há issue #{num} no nome do branch.")
        else:
            body = create_body or "_criada via scripts/worktree-new.py_"
            _info(f"criando issue: {create_title!r}")
            num = gh_issue_create(create_title, body)
            _info(f"issue criada: #{num}")
            return num

    if num == 0:
        _fail("nome de branch sem número de issue (use `<tipo>/<num>-<slug>` ou "
              "`--create-issue --issue-title ...` para criar uma).")

    if not gh_issue_exists(num):
        _fail(
            f"issue #{num} não encontrada no GitHub (`gh issue view {num}` falha).\n"
            "Toda branch precisa carregar uma issue válida — GIT-WORKFLOW.md "
            "§Princípios fundamentais #1. Crie a issue antes (ou passe "
            "`--create-issue --issue-title ...`)."
        )
    _info(f"issue #{num} OK")
    return num


def compute_worktree_path(repo_root: Path, branch: str, override: str | None) -> Path:
    """Calcula onde a nova worktree vai morar."""
    if override:
        return Path(override).resolve()
    # Slug do branch usado como nome de pasta — substitui '/' por '-'.
    slug = branch.replace("/", "-")
    parent = repo_root.parent / f"{repo_root.name}-worktrees"
    return (parent / slug).resolve()


def create_worktree(branch: str, base: str, path: Path,
                    local_exists: bool, remote_exists: bool) -> None:
    """`git worktree add` saindo de origin/<base> ou da branch existente."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if local_exists:
        _info("branch local já existe — fazendo checkout dela na worktree")
        _run(["git", "worktree", "add", str(path), branch])
    elif remote_exists:
        _info(f"branch remota existe (origin/{branch}) — checkout com tracking")
        _run(["git", "worktree", "add", "--track",
              "-b", branch, str(path), f"origin/{branch}"])
    else:
        _info(f"criando branch {branch} a partir de origin/{base}")
        _run(["git", "worktree", "add",
              "-b", branch, str(path), f"origin/{base}"])


def copy_env_files(src: Path, dst: Path) -> None:
    """Copia .env e .env.local do checkout principal, se existirem."""
    for name in (".env", ".env.local"):
        f = src / name
        if f.is_file():
            shutil.copy2(f, dst / name)
            _info(f"copiado {name}")


def setup_env(path: Path, use_make: bool) -> None:
    """Roda `make setup` na worktree, com fallback para `uv` direto."""
    if use_make and shutil.which("make") is not None:
        _run(["make", "setup"], cwd=path, check=False)
        return

    if shutil.which("uv") is None:
        print("  AVISO: `uv` não encontrado no PATH — pulando setup do venv.",
              file=sys.stderr)
        return
    _info("`make` indisponível — usando `uv` direto")
    # `uv sync --locked` e não `uv pip install`: só a interface de projeto
    # consome o `uv.lock`, então é o que garante o MESMO conjunto de versões
    # revisado no PR. `uv sync` cria o venv sozinho (o `uv venv` era redundante).
    _run(["uv", "sync", "--locked", "--extra", "dev"], cwd=path)
    if (path / ".pre-commit-config.yaml").is_file():
        _run(["uv", "run", "pre-commit", "install",
              "--install-hooks",
              "--hook-type", "pre-commit",
              "--hook-type", "commit-msg"],
             cwd=path, check=False)


def open_vscode(path: Path) -> None:
    code = shutil.which("code") or shutil.which("code.cmd")
    if code is None:
        print(f"\n  `code` não está no PATH. Abra manualmente:\n     {path}")
        return
    # `-n` força nova janela (não reaproveita a janela atual).
    _run([code, "-n", str(path)], check=False)


# ---------------------------------------------------------------------------
# auto-geração de portas para worktrees paralelas
# ---------------------------------------------------------------------------

# Defaults espelham os do docker-compose.yml e .env.example.
PORT_DEFAULTS: dict[str, int] = {
    "APP_PORT": 8000,
    "POSTGRES_PORT": 5432,
    "REDIS_PORT": 6379,
}
# Limite de offset para detectar caso degenerado (>100 worktrees).
PORT_OFFSET_MAX = 100


def _list_worktree_paths() -> list[Path]:
    """Caminhos de todas as worktrees registradas (inclui a principal)."""
    cp = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=False,
    )
    if cp.returncode != 0:
        return []
    out: list[Path] = []
    for line in cp.stdout.splitlines():
        if line.startswith("worktree "):
            out.append(Path(line.split(" ", 1)[1]))
    return out


def _collect_used_ports(skip: Path | None = None) -> dict[str, set[int]]:
    """Lê `.env` de todas as worktrees existentes e retorna as portas já
    em uso por chave. Os defaults (8000/5432/6379) entram como "usados"
    porque a worktree principal os herda do compose quando não há `.env`.
    """
    used: dict[str, set[int]] = {k: {v} for k, v in PORT_DEFAULTS.items()}
    skip_resolved = skip.resolve() if skip else None
    for wt in _list_worktree_paths():
        try:
            if skip_resolved and wt.resolve() == skip_resolved:
                continue
        except OSError:
            continue
        envfile = wt / ".env"
        if not envfile.is_file():
            continue
        try:
            text = envfile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if key not in used:
                continue
            try:
                used[key].add(int(value.strip().split()[0]))
            except (ValueError, IndexError):
                continue
    return used


def assign_worktree_ports(new_wt: Path) -> dict[str, int]:
    """Escolhe portas livres para a worktree paralela, evitando colidir
    com as portas já em uso pela principal e por outras worktrees.
    """
    used = _collect_used_ports(skip=new_wt)
    chosen: dict[str, int] = {}
    for key, default in PORT_DEFAULTS.items():
        for offset in range(1, PORT_OFFSET_MAX + 1):
            candidate = default + offset
            if candidate not in used[key]:
                chosen[key] = candidate
                used[key].add(candidate)
                break
        else:
            _fail(f"sem porta livre para {key} dentro de "
                  f"+{PORT_OFFSET_MAX} do default {default}.")
    return chosen


def write_worktree_env_ports(wt_path: Path, ports: dict[str, int]) -> None:
    """Mescla `APP_PORT`/`POSTGRES_PORT`/`REDIS_PORT` no `.env` da
    worktree, sobrescrevendo se já existirem.
    """
    envfile = wt_path / ".env"
    existing = envfile.read_text(encoding="utf-8") if envfile.is_file() else ""
    lines = existing.splitlines()

    pending = dict(ports)
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                out_lines.append(f"{key}={pending.pop(key)}")
                continue
        out_lines.append(line)

    if pending:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append(
            "# Portas auto-geradas para esta worktree paralela "
            "(scripts/worktree-new.py)"
        )
        for key in PORT_DEFAULTS:
            if key in pending:
                out_lines.append(f"{key}={pending[key]}")

    envfile.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    summary = ", ".join(f"{k}={v}" for k, v in ports.items())
    _info(f".env atualizado: {summary}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "branch",
        help="Nome completo da branch (ex.: feat/42-add-google-login). "
             "Para criar a issue dentro do script, use `<tipo>/-<slug>` "
             "(sem número) + --create-issue --issue-title.",
    )
    parser.add_argument(
        "--base", default=None,
        help="Branch base remota (default: develop; main para hotfix/).",
    )
    parser.add_argument(
        "--path", default=None,
        help="Override do diretório da worktree "
             "(default: ../<repo>-worktrees/<branch-slug>).",
    )
    parser.add_argument(
        "--create-issue", action="store_true",
        help="Cria a issue via `gh issue create` antes (precisa de --issue-title).",
    )
    parser.add_argument("--issue-title", default=None,
                        help="Título da issue a criar (Conventional PT).")
    parser.add_argument("--issue-body", default=None,
                        help="Corpo da issue a criar (markdown PT).")
    parser.add_argument("--no-setup", action="store_true",
                        help="Pula `make setup` na nova worktree.")
    parser.add_argument("--no-env", action="store_true",
                        help="Não copia .env / .env.local do checkout principal.")
    parser.add_argument("--no-port-assign", action="store_true",
                        help="Não escreve APP_PORT/POSTGRES_PORT/REDIS_PORT no "
                             ".env da worktree (default: gera portas livres).")
    parser.add_argument("--no-vscode", action="store_true",
                        help="Não abre VS Code ao final.")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Pula `git fetch --prune origin` (assume base já fresca).")
    return parser


def _validate_branch(branch: str, *, create_issue: bool
                     ) -> tuple[dict[str, str], int, bool]:
    """Valida o nome do branch (aceita placeholder `<tipo>/-<slug>` se
    --create-issue). Retorna (parts, num, create_mode_no_num).
    """
    create_mode_no_num = (
        create_issue
        and "/" in branch
        and branch.split("/", 1)[1].startswith("-")
    )
    if create_mode_no_num:
        tipo, rest = branch.split("/", 1)
        # "feat/-add-foo" → "feat/0-add-foo" só pra passar no regex
        branch_for_validation = f"{tipo}/0{rest}"
    else:
        branch_for_validation = branch
    parts = parse_branch(branch_for_validation)
    num = 0 if create_mode_no_num else int(parts["num"])
    return parts, num, create_mode_no_num


def _assemble_branch(parts: dict[str, str], final_num: int) -> str:
    tipo, slug, stage = parts["type"], parts["slug"], parts["stage"]
    if stage:
        return f"{tipo}/{final_num}-{stage}-{slug}"
    return f"{tipo}/{final_num}-{slug}"


def _print_summary(*, branch: str, path: Path, issue: int, base: str) -> None:
    print()
    print("=" * 60)
    print(f"  ✓ Worktree pronta — branch {branch}")
    print(f"  ✓ Path: {path}")
    if issue:
        print(f"  ✓ Issue: #{issue}")
    print(f"  ✓ Base: origin/{base}")
    print("=" * 60)
    print()
    print("Próximos passos:")
    print(f"  cd {path}")
    print("  # implementar, commitar (1 commit = 1 mudança, body em bullets);")
    print(f"  # depois: git push -u origin {branch} && gh pr create --base {base}")
    print()
    print("Quando terminar a worktree (após PR mergeado):")
    print(f"  git worktree remove {path}")


def main() -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args()

    parts, num, create_mode_no_num = _validate_branch(
        args.branch, create_issue=args.create_issue,
    )
    base = args.base or default_base(parts["type"])

    _section("1. Validando nome do branch")
    _info(f"tipo={parts['type']}  num={num or '(será criado)'}  "
          f"stage={parts['stage'] or '-'}  slug={parts['slug']}")
    _info(f"base remota: origin/{base}")

    _section("2. Verificando repositório git")
    repo_root = git_top()
    _info(f"repositório raiz: {repo_root}")

    if not args.no_fetch:
        _section("3. Atualizando refs remotas")
        _run(["git", "fetch", "--prune", "origin"])

    _section("4. Validando issue (gate issue-first)")
    if args.create_issue and not args.issue_title:
        _fail("--create-issue requer --issue-title")
    final_num = ensure_issue(
        num,
        create_title=args.issue_title if args.create_issue else None,
        create_body=args.issue_body,
    )

    final_branch = (
        _assemble_branch(parts, final_num) if create_mode_no_num else args.branch
    )
    if create_mode_no_num:
        _info(f"nome final do branch: {final_branch}")

    _section("5. Preparando path da worktree")
    wt_path = compute_worktree_path(repo_root, final_branch, args.path)
    if wt_path.exists():
        _fail(f"path já existe: {wt_path}. Remova ou passe --path.")
    _info(f"worktree em: {wt_path}")

    _section("6. Criando worktree")
    local_e, remote_e = branch_exists(final_branch)
    create_worktree(final_branch, base, wt_path, local_e, remote_e)

    if not args.no_env:
        _section("7. Copiando arquivos de ambiente")
        copy_env_files(repo_root, wt_path)

    if not args.no_port_assign:
        _section("8. Atribuindo portas livres (worktree paralela)")
        ports = assign_worktree_ports(wt_path)
        write_worktree_env_ports(wt_path, ports)

    if args.no_setup:
        _info("setup pulado (--no-setup)")
    else:
        _section("9. Instalando dependências (`make setup` / `uv`)")
        setup_env(wt_path, use_make=True)

    if not args.no_vscode:
        _section("10. Abrindo VS Code")
        open_vscode(wt_path)

    _print_summary(branch=final_branch, path=wt_path, issue=final_num, base=base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
