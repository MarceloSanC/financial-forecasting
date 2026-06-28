"""Validador da seção §7 ("Execução — post-hoc") de `technical.md`.

Uso:
    python scripts/check_technical_postexec.py docs/stages/<N.M-slug>/technical.md
    python scripts/check_technical_postexec.py            # varre todos os technicals

Regra (CONVENTIONS.md §3.4):

Depois que o `technical.md` recebeu `status: done` (gate da Fase 3B,
commit reservado `stage N.M: technical approved`), **a única parte
editável é a seção §7 "Execução"**, delimitada por:

    <!-- BEGIN: post-execution -->
    ...
    <!-- END: post-execution -->

O freeze §7 vale apenas **durante a janela de execução** da Stage —
isto é, enquanto a branch da Stage **ainda não mergeou** em `develop`/
`main`. O objetivo é impedir que a execução reescreva o plano aprovado
sem rastro; desvios vão para a §7, onde são revisados. **Depois do
merge**, o `technical.md` vira doc de referência e pode ser alinhado à
realidade livremente (o plano original permanece no git). Por isso a
checagem 2 é pulada quando o commit de aprovação já é ancestral de uma
branch de integração.

O script faz duas checagens:

1. **Estrutural (sempre):** o arquivo contém exatamente uma ocorrência
   dos marcadores `BEGIN/END: post-execution`, na ordem correta, com
   `END` depois de `BEGIN`. (Se o frontmatter ainda é `draft`, isso
   serve só de sanity check do template; se é `done`, é pré-requisito
   para a checagem 2.)
2. **Diff vs. baseline (`status: done` E Stage não mergeada):** compara
   o arquivo atual com a versão do último commit reservado de aprovação
   (`stage N.M: technical approved`) localizado via `git log`. Se há
   alteração em linhas fora da janela `BEGIN..END`, falha. É pulada se a
   Stage já mergeou (ver `_stage_is_merged`).

Retorna código de saída 0 se tudo OK, 1 se houver violações.

Limitações conhecidas:
- Renomeação do arquivo entre commits não é seguida. Mantém-se o
  pressuposto de que `technical.md` não é renomeado durante a Stage.
- Se não houver commit reservado de aprovação no histórico (ex.: Stage
  ainda em 3A/3B, ou clone raso sem histórico), a checagem 2 é pulada
  com status 0.
- A detecção de merge depende de uma branch de integração resolvível
  (`develop`/`main`, local ou `origin/*`). Sem nenhuma (clone raso),
  cai em fail-open: não bloqueia.
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path

BEGIN_MARKER = "<!-- BEGIN: post-execution -->"
END_MARKER = "<!-- END: post-execution -->"

# git log --format=%H%x09%s emite "<sha>\t<subject>" — 2 partes após split("\t", 1).
GIT_LOG_PARTS_EXPECTED = 2

# Captura a Stage N.M a partir do caminho do arquivo (docs/stages/N.M-slug/technical.md)
_STAGE_DIR_PATTERN = re.compile(r"docs/stages/(\d+)\.(\d+)-[^/]+/technical\.md$")

# Regex de status: done no frontmatter (linha começa com 'status:', case-insensitive).
_STATUS_DONE_PATTERN = re.compile(r"^status:\s*done\s*$", re.MULTILINE)


class CheckError(Exception):
    """Falha de validação reportável ao usuário."""


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_status_done(content: str) -> bool:
    # O frontmatter é o bloco entre o fence inicial `---\n` e o próximo `\n---`.
    # Strip do fence inicial (4 chars) antes do split para não confundir o
    # fechamento do frontmatter com o seu conteúdo.
    if not content.startswith("---\n"):
        return False
    head = content[4:].split("\n---", 1)
    frontmatter = head[0] if head else ""
    return bool(_STATUS_DONE_PATTERN.search(frontmatter))


def _check_markers(content: str, path: Path) -> tuple[int, int]:
    """Valida presença e ordem dos marcadores. Retorna (begin_line, end_line)."""
    lines = content.splitlines()
    begin_indices = [i for i, line in enumerate(lines) if line.strip() == BEGIN_MARKER]
    end_indices = [i for i, line in enumerate(lines) if line.strip() == END_MARKER]

    if len(begin_indices) != 1 or len(end_indices) != 1:
        msg = (
            f"{path}: marcadores de §7 inválidos — "
            f"esperava 1 BEGIN e 1 END, encontrei "
            f"{len(begin_indices)} BEGIN e {len(end_indices)} END."
        )
        raise CheckError(msg)

    begin = begin_indices[0]
    end = end_indices[0]
    if end <= begin:
        msg = (
            f"{path}: marcador END (linha {end + 1}) deve vir depois do "
            f"BEGIN (linha {begin + 1})."
        )
        raise CheckError(msg)

    return begin, end


def _approved_commit_for(path: Path) -> str | None:
    """SHA do commit `stage N.M: technical approved` mais recente que tocou o arquivo, ou None."""
    match = _STAGE_DIR_PATTERN.search(path.as_posix())
    if not match:
        return None
    stage_n, stage_m = match.group(1), match.group(2)
    needle = f"stage {stage_n}.{stage_m}: technical approved"

    result = subprocess.run(
        ["git", "log", "--format=%H%x09%s", "--", path.as_posix()],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == GIT_LOG_PARTS_EXPECTED and parts[1].strip() == needle:
            return parts[0]
    return None


def _repo_relative_posix(path: Path) -> str:
    """Caminho relativo à raiz do repositório, em formato posix.

    `git show <sha>:<path>` exige um caminho **relativo à raiz do repo**;
    caminhos absolutos falham. No modo de descoberta (`_discover_targets`
    glob a partir de `Path.cwd()`) os caminhos são absolutos, então a
    conversão é obrigatória para a checagem 2 funcionar via `make docs-check`.
    """
    if not path.is_absolute():
        return path.as_posix()
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
    )
    if toplevel.returncode == 0:
        root = Path(toplevel.stdout.decode("utf-8").strip())
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


# Branches de integração onde "Stage mergeada" é verdade. Ordem de tentativa;
# cobre execução local (`develop`/`main`) e CI (`origin/*`).
_INTEGRATION_REFS = ("origin/develop", "develop", "origin/main", "main")


def _stage_is_merged(approved_sha: str) -> bool:
    """True se o commit de aprovação já alcançou uma branch de integração.

    O freeze §7 (CONVENTIONS §3.4) vale só durante a execução da Stage —
    enquanto a branch da Stage não mergeou. Enquanto em execução, o commit
    `stage N.M: technical approved` não é ancestral de `develop`/`main` →
    a §7 fica congelada. Depois do merge, vira ancestral → o technical é
    doc de referência mutável.

    Fail-open: se nenhuma branch de integração for resolvível (ex.: clone
    raso sem histórico no CI), não dá pra afirmar que a Stage está em
    execução, então não bloqueia.
    """
    resolved_any = False
    for ref in _INTEGRATION_REFS:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", approved_sha, ref],
            capture_output=True,
            check=False,
        )
        # 0 = é ancestral (mergeada); 1 = ref existe mas não é ancestral
        # (em execução); 128 = ref/objeto ausente — tenta a próxima.
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            resolved_any = True
    # Nenhuma integração contém o commit. Se ao menos uma ref resolveu, a
    # Stage realmente não mergeou → enforce. Se nenhuma resolveu → fail-open.
    return not resolved_any


def _git_show(sha: str, path: Path) -> str | None:
    # `git show <sha>:<path>` precisa de caminho relativo à raiz do repo.
    # Captura bytes e decodifica explicitamente como UTF-8 para casar com
    # `_read_file` (`read_text(encoding="utf-8")`). Com `text=True` o
    # subprocess decodificaria usando o locale do SO (cp1252 no Windows),
    # gerando mojibake em acentos/travessões e diffs espúrios fora dos
    # marcadores em qualquer technical não-ASCII.
    result = subprocess.run(
        ["git", "show", f"{sha}:{_repo_relative_posix(path)}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8")


def _diff_outside_window(
    baseline: list[str],
    current: list[str],
    baseline_window: tuple[int, int],
    current_window: tuple[int, int],
) -> list[str]:
    """Retorna linhas do diff que caem fora da janela post-execution em ambos os lados."""
    sm = difflib.SequenceMatcher(a=baseline, b=current, autojunk=False)
    offending: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # Verifica se o intervalo afetado está completamente dentro da janela post-execution
        baseline_inside = baseline_window[0] <= i1 and i2 <= baseline_window[1] + 1
        current_inside = current_window[0] <= j1 and j2 <= current_window[1] + 1
        if baseline_inside and current_inside:
            continue
        # Pelo menos um lado caiu fora — registrar
        offending.append(
            f"  {tag}: baseline[{i1}:{i2}] (lines {i1 + 1}-{i2}) vs "
            f"current[{j1}:{j2}] (lines {j1 + 1}-{j2})"
        )
    return offending


def _check_postexec_diff(path: Path, content: str, window: tuple[int, int]) -> list[str]:
    """Checagem 2: diff vs. baseline aprovada, se a Stage ainda está em execução.

    Pulada (retorna `[]`) quando: não há commit de aprovação no histórico,
    a Stage já mergeou, ou a baseline é anterior ao contrato §7.
    """
    sha = _approved_commit_for(path)
    if sha is None:
        # Sem commit reservado de aprovação no histórico — não dá pra
        # comparar com baseline. Permitido (ex.: arquivo recém-criado
        # ainda não foi aprovado, clone raso, ou rodando fora de git).
        return []

    if _stage_is_merged(sha):
        # Stage já mergeada — o freeze §7 vale só durante a execução
        # (approved..merge). Pós-merge, o technical é doc de referência
        # mutável; o plano original permanece no git. CONVENTIONS §3.4.
        return []

    baseline_content = _git_show(sha, path)
    if baseline_content is None:
        return [
            f"{path}: não foi possível recuperar a versão de baseline "
            f"do commit {sha[:8]}."
        ]

    try:
        b_begin, b_end = _check_markers(baseline_content, path)
    except CheckError:
        # Baseline anterior à introdução do contrato §7 (CONVENTIONS §3.4)
        # — Stage aprovada quando os marcadores ainda não existiam. A
        # migração one-time (adicionar BEGIN/END à §7) é parte de
        # estabelecer o contrato; sem janela no baseline não dá pra
        # comparar diff. Aceita o estado atual: a checagem estrutural do
        # current (no chamador) já garante markers válidos.
        return []

    offending = _diff_outside_window(
        baseline_content.splitlines(),
        content.splitlines(),
        (b_begin, b_end),
        window,
    )
    if not offending:
        return []

    header = (
        f"{path}: status=done mas há mudanças fora dos marcadores "
        f"post-execution (baseline: {sha[:8]} `stage technical approved`):"
    )
    return [header, *offending]


def check_file(path: Path) -> list[str]:
    """Roda checagens em um único arquivo. Retorna lista de erros (vazia = OK)."""
    content = _read_file(path)

    try:
        begin, end = _check_markers(content, path)
    except CheckError as exc:
        return [str(exc)]

    if not _has_status_done(content):
        # Status ainda draft — checagem estrutural basta.
        return []

    return _check_postexec_diff(path, content, (begin, end))


def _discover_targets(root: Path) -> list[Path]:
    return sorted(root.glob("docs/stages/*/technical.md"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Caminhos de `technical.md` a validar. Vazio = varre docs/stages/*/technical.md.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Raiz do repo para descoberta automática (default: cwd).",
    )
    args = parser.parse_args(argv)

    targets = list(args.paths) if args.paths else _discover_targets(args.root)
    if not targets:
        print("Nenhum technical.md encontrado para validar.", file=sys.stderr)
        return 0

    all_errors: list[str] = []
    for path in targets:
        if not path.is_file():
            all_errors.append(f"{path}: arquivo não encontrado.")
            continue
        all_errors.extend(check_file(path))

    if all_errors:
        for line in all_errors:
            print(line, file=sys.stderr)
        print(
            f"\n{len(all_errors)} erro(s) em {len(targets)} arquivo(s).",
            file=sys.stderr,
        )
        return 1

    print(f"OK — {len(targets)} arquivo(s) validado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
