# Gerador determinístico da unidade de oráculo R `var_test_cases` (Stage 6.3).
#
# Oráculo: rugarch::VaRTest (Christoffersen 1998 / Kupiec 1995) congelado como fixture
# (ADR 6.3.0002); formato da fixture do Step: ADR 6.2.0006. Uso (host com Docker, raiz
# do repo; o literal executado vai para provenance.command via FF_R_ORACLE_COMMAND):
#   docker build -t ff-r-oracle:4.4.1 tests/fixtures/r_oracle
#   CMD="docker run --rm -v \"$(pwd -W)/tests/fixtures/r_oracle:/work\" -w /work ff-r-oracle:4.4.1 Rscript var_test_cases.R"
#   MSYS_NO_PATHCONV=1 docker run --rm -e FF_R_ORACLE_COMMAND="$CMD" \
#     -v "$(pwd -W)/tests/fixtures/r_oracle:/work" -w /work ff-r-oracle:4.4.1 Rscript var_test_cases.R
#
# Grava `var_test_cases.json` (provenance + casos) e `var_test_cases.sessionInfo.txt`.
#
# Cada caso roda VaRTest em DOIS feeds (ADR 6.3.0003): a sequência inteira e a
# sequência a partir de t = 2 (`v[-1]`), com actual = -1 na violação e VaR = 0
# (violação <=> actual < VaR). Por feed grava uc.LRstat e cc.LRstat, ou a mensagem de
# erro do R. Errata do ADR 6.3.0003 (Checkpoint C, bloco 3): quando o feed t >= 2
# falha, grava também `lr_uc_internal` = rugarch:::.LR.uc(p, T - 1, sum(v[-1])) — a
# mesma função que o uc.LRstat desse feed chamaria (o LR_uc puro), para o trio ser
# comparado em todo caso com o feed inteiro válido.
#
# Convenção do Step (ADR 6.2.0006 item 1): a taxa p (única entrada de ponto flutuante)
# é {"dec": %.17g, "hex": %a}; as violações 0/1 são inteiros JSON; as saídas são números
# %.17g escritos VERBATIM (`json_verbatim = TRUE`; `toJSON(digits = NA)` só escreveria
# 15 dígitos). O gerador para sem escrever diante de saída não-finita ou de T > 500.

suppressPackageStartupMessages({
  library(rugarch)
  library(jsonlite)
})

T_MAX <- 500L
BASE_SEED <- 20260928L

command <- Sys.getenv("FF_R_ORACLE_COMMAND")
stopifnot(nzchar(command))

verbatim <- function(text) structure(text, class = "json")

dec17 <- function(x) {
  s <- sprintf("%.17g", x)
  stopifnot(all(as.numeric(s) == x))
  s
}

float_input <- function(x) {
  stopifnot(is.double(x), length(x) == 1L, is.finite(x))
  list(dec = verbatim(dec17(x)), hex = sprintf("%a", x))
}

output <- function(x) {
  stopifnot(length(x) == 1L, is.finite(x))
  verbatim(dec17(x))
}

var_test <- function(v, p) {
  tryCatch(
    VaRTest(alpha = p, actual = ifelse(v == 1L, -1, 1), VaR = rep(0, length(v))),
    error = function(e) e
  )
}

feed <- function(v, p) {
  res <- var_test(v, p)
  if (inherits(res, "error")) {
    return(list(error = conditionMessage(res)))
  }
  list(uc_lrstat = output(res$uc.LRstat), cc_lrstat = output(res$cc.LRstat))
}

feed_ok <- function(v, p) !inherits(var_test(v, p), "error")

make_case <- function(id, description, category, p, v) {
  v <- as.integer(v)
  stopifnot(length(v) >= 2L, length(v) <= T_MAX, all(v %in% c(0L, 1L)))
  from_t2 <- feed(v[-1], p)
  if (!is.null(from_t2$error)) {
    from_t2$lr_uc_internal <- output(rugarch:::.LR.uc(p = p, TN = length(v) - 1L, N = sum(v[-1])))
  }
  list(
    id = id,
    description = description,
    category = category,
    violation_rate = float_input(p),
    violations = I(v),
    whole = feed(v, p),
    from_t2 = from_t2
  )
}

cases <- list()
add <- function(case) cases[[length(cases) + 1L]] <<- case

# Busca determinística: a partir de `start`, a primeira seed cujo sorteio `draw(seed)`
# satisfaz `accept(v)`; a seed usada entra na descrição do caso.
search_seed <- function(start, draw, accept, max_tries = 10000L) {
  for (seed in start:(start + max_tries - 1L)) {
    v <- draw(seed)
    if (accept(v)) {
      return(list(seed = seed, v = v))
    }
  }
  stop(sprintf("no accepted draw from seed %d", start))
}

both_feeds_ok <- function(p) function(v) feed_ok(v, p) && feed_ok(v[-1], p)

set.seed(BASE_SEED)
block <- 0L

# 1. iid: Bern(p) para p x T; só sorteios com os dois feeds válidos.
for (p in c(0.01, 0.02, 0.05, 0.1)) {
  for (n in c(100L, 250L, 500L)) {
    block <- block + 1L
    draw <- function(seed) {
      set.seed(seed)
      rbinom(n, 1L, p)
    }
    hit <- search_seed(BASE_SEED + 1000L * block, draw, both_feeds_ok(p))
    add(make_case(
      sprintf("iid_p%s_T%d", format(p), n),
      sprintf("Bern(%s) iid, T = %d, seed %d (primeira seed com os dois feeds válidos)",
              format(p), n, hit$seed),
      "iid", p, hit$v
    ))
  }
}

# 2. clustered: cadeia de Markov com pi01 = p/2 e pi11 = 0.3 (violações agrupadas).
markov <- function(n, p01, p11) {
  v <- integer(n)
  v[1] <- rbinom(1L, 1L, p01)
  for (t in 2:n) {
    v[t] <- rbinom(1L, 1L, if (v[t - 1L] == 1L) p11 else p01)
  }
  v
}
for (p in c(0.02, 0.05, 0.1)) {
  for (n in c(250L, 500L)) {
    block <- block + 1L
    draw <- function(seed) {
      set.seed(seed)
      markov(n, p / 2, 0.3)
    }
    hit <- search_seed(BASE_SEED + 1000L * block, draw, both_feeds_ok(p))
    add(make_case(
      sprintf("clustered_p%s_T%d", format(p), n),
      sprintf("Markov pi01 = %s, pi11 = 0.3, taxa nominal %s, T = %d, seed %d",
              format(p / 2), format(p), n, hit$seed),
      "clustered", p, hit$v
    ))
  }
}

# 3. first_violation: I_1 = 1 forçado; o primeiro caso exige |uc(t>=2) - uc(inteira)| > 0.1
# (sonda do ADR 6.3.0003: Bern(0.05), T = 250).
uc_gap <- function(v, p) {
  abs(var_test(v[-1], p)$uc.LRstat - var_test(v, p)$uc.LRstat)
}
first_specs <- list(
  list(p = 0.05, n = 250L, gap = TRUE),
  list(p = 0.02, n = 100L, gap = FALSE),
  list(p = 0.1, n = 50L, gap = FALSE)
)
for (spec in first_specs) {
  block <- block + 1L
  draw <- function(seed) {
    set.seed(seed)
    v <- rbinom(spec$n, 1L, spec$p)
    v[1] <- 1L
    v
  }
  accept <- function(v) {
    both_feeds_ok(spec$p)(v) && (!spec$gap || uc_gap(v, spec$p) > 0.1)
  }
  hit <- search_seed(BASE_SEED + 1000L * block, draw, accept)
  add(make_case(
    sprintf("first_violation_p%s_T%d", format(spec$p), spec$n),
    sprintf("Bern(%s), T = %d, I_1 = 1 forçado, seed %d%s", format(spec$p), spec$n, hit$seed,
            if (spec$gap) " (|uc(t>=2) - uc(inteira)| > 0.1)" else ""),
    "first_violation", spec$p, hit$v
  ))
}

# 4. n11_zero: violações isoladas (sem 1 -> 1); inclui violação isolada em t = 1 e em t = T.
at <- function(n, positions) {
  v <- integer(n)
  v[positions] <- 1L
  v
}
add(make_case("n11_zero_middle", "T = 60, violações isoladas em 10, 25 e 40", "n11_zero",
              0.05, at(60L, c(10L, 25L, 40L))))
add(make_case("n11_zero_first", "T = 60, violações isoladas em 1, 20 e 45 (t = 1)",
              "n11_zero", 0.05, at(60L, c(1L, 20L, 45L))))
add(make_case("n11_zero_last", "T = 60, violações isoladas em 15, 35 e 60 (t = T)",
              "n11_zero", 0.05, at(60L, c(15L, 35L, 60L))))

# 5. r_error: onde o table(head, tail) do R perde um símbolo em algum feed.
add(make_case("r_error_zero_violations", "T = 50, nenhuma violação", "r_error", 0.05,
              integer(50L)))
add(make_case("r_error_all_violations", "T = 20, todas as posições violam", "r_error", 0.05,
              rep(1L, 20L)))
add(make_case("r_error_single_first", "T = 30, uma violação, em t = 1", "r_error", 0.05,
              at(30L, 1L)))
add(make_case("r_error_single_last", "T = 30, uma violação, em t = T", "r_error", 0.05,
              at(30L, 30L)))
add(make_case("r_error_first_and_last", "T = 30, violações só em t = 1 e t = T", "r_error",
              0.05, at(30L, c(1L, 30L))))

# 6. t2_feed_error (errata do ADR 6.3.0003): feed inteiro válido e feed t >= 2 com erro.
add(make_case("t2_feed_error_T3_101", "T = 3, [1, 0, 1]", "t2_feed_error", 0.05,
              c(1L, 0L, 1L)))
add(make_case("t2_feed_error_T3_010", "T = 3, [0, 1, 0]", "t2_feed_error", 0.05,
              c(0L, 1L, 0L)))
add(make_case("t2_feed_error_head11_only", "T = 20, violações só em t = 1 e t = 2",
              "t2_feed_error", 0.05, at(20L, c(1L, 2L))))

provenance <- list(
  generator = "tests/fixtures/r_oracle/var_test_cases.R",
  image = "rocker/r-ver:4.4.1",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  packages = list(
    rugarch = packageDescription("rugarch")$Version,
    jsonlite = packageDescription("jsonlite")$Version
  ),
  cran_snapshot = getOption("repos")[["CRAN"]],
  generated_at = format(Sys.Date(), "%Y-%m-%d"),
  session_info = "var_test_cases.sessionInfo.txt",
  command = command,
  t_max = T_MAX
)

writeLines(
  toJSON(list(provenance = provenance, cases = cases), auto_unbox = TRUE, pretty = TRUE,
         json_verbatim = TRUE, na = "null", null = "null"),
  "var_test_cases.json",
  useBytes = TRUE
)
writeLines(capture.output(sessionInfo()), "var_test_cases.sessionInfo.txt")
cat(sprintf("wrote %d cases\n", length(cases)))
