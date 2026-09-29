# Gerador determinístico das fixtures do oráculo R `forecast::dm.test` (Stage 6.2, ADR 6.2.0006).
#
# Uso (host com Docker, a partir da raiz do repo):
#   docker build -t ff-r-oracle:4.4.1 tests/fixtures/r_oracle &&
#   docker run --rm -v "$PWD/tests/fixtures/r_oracle:/work" -w /work \
#     ff-r-oracle:4.4.1 Rscript dm_test_cases.R
#
# Grava `dm_test_cases.json` (provenance + casos) e `dm_test_cases.sessionInfo.txt`.
# Convenção do Step (ADR 6.2.0006 item 1): toda entrada de ponto flutuante é
# {"dec": %.17g, "hex": %a} com a mesma forma (escalar ou lista); inteiros e strings
# ficam em JSON simples; saídas em %.17g. Os números entram VERBATIM no JSON
# (`json_verbatim = TRUE`): `toJSON(digits = NA)` só escreveria 15 dígitos.
# Chamada do oráculo: dm.test(e1 = candidato, e2 = comparador, alternative = "less",
# h, power = 1, varestimator) — d = |e1| - |e2| = L_cand - L_comp (perdas >= 0).
# Nenhum caso tem h = T (ADR 6.2.0001: T > h sempre, fora os de erro h > T).

suppressPackageStartupMessages({
  library(forecast)
  library(jsonlite)
})

verbatim <- function(text) structure(text, class = "json")

dec17 <- function(x) {
  s <- sprintf("%.17g", x)
  stopifnot(all(as.numeric(s) == x))
  s
}

# {"dec": ..., "hex": ...} para uma entrada de ponto flutuante (lista se length > 1).
float_input <- function(x) {
  stopifnot(is.double(x), all(is.finite(x)))
  if (length(x) == 1L) {
    list(dec = verbatim(dec17(x)), hex = sprintf("%a", x))
  } else {
    list(
      dec = verbatim(paste0("[", paste(dec17(x), collapse = ", "), "]")),
      hex = I(sprintf("%a", x))
    )
  }
}

output <- function(x) verbatim(dec17(x))

run_case <- function(id, description, cand, comp, h, varestimator) {
  stopifnot(length(cand) == length(comp), all(cand >= 0), all(comp >= 0))
  stopifnot(h != length(cand))
  warn <- NA_character_
  result <- tryCatch(
    withCallingHandlers(
      dm.test(e1 = cand, e2 = comp, alternative = "less", h = h, power = 1,
              varestimator = varestimator),
      warning = function(w) {
        warn <<- conditionMessage(w)
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  inputs <- list(
    candidate_losses = float_input(cand),
    comparator_losses = float_input(comp),
    horizon = as.integer(h),
    varestimator = varestimator,
    alternative = "less",
    power = 1L
  )
  case <- list(id = id, description = description, inputs = inputs)
  if (inherits(result, "error")) {
    case$expected_error <- conditionMessage(result)
    case$warning <- warn
  } else {
    case$expected <- list(
      statistic = output(unname(result$statistic)),
      p_value = output(result$p.value),
      horizon_used = as.integer(result$parameter[["Forecast horizon"]]),
      warning = warn
    )
  }
  case
}

cases <- list()
add <- function(case) cases[[length(cases) + 1L]] <<- case

# 1. T = 60: h em {1, 7} x {acf, bartlett} x candidato melhor/pior (8 casos).
# Perdas independentes com escala 0,8 / 1,2: sinal moderado (p longe de 0 e de 1), para
# exercitar a t no miolo e na cauda sem saturar.
set.seed(20260928)
base60 <- abs(rnorm(60))
better60 <- 0.8 * abs(rnorm(60))
worse60 <- 1.2 * abs(rnorm(60))
for (h in c(1L, 7L)) {
  for (v in c("acf", "bartlett")) {
    add(run_case(sprintf("t60_h%d_%s_candidate_better", h, v),
                 "T = 60, candidato com perda menor (mean(d) < 0)", better60, base60, h, v))
    add(run_case(sprintf("t60_h%d_%s_candidate_worse", h, v),
                 "T = 60, candidato com perda maior (mean(d) > 0)", worse60, base60, h, v))
  }
}

# 2. T = 250, h = 7, retangular: perdas com dependência serial (AR(1) em |.|), candidato melhor.
set.seed(114)
ar250 <- as.numeric(arima.sim(list(ar = 0.6), n = 250))
comp250 <- abs(ar250) + 0.05
cand250 <- abs(0.9 * ar250 + rnorm(250, sd = 0.2)) + 0.02
add(run_case("t250_h7_acf_dependent_candidate_better",
             "T = 250, h = 7, perdas com dependência AR(1), candidato melhor",
             cand250, comp250, 7L, "acf"))

# 3. T pequeno sem erro: T = 8, h = 1 e h = 2.
set.seed(8)
cand8 <- abs(rnorm(8))
comp8 <- abs(rnorm(8)) + 0.3
add(run_case("t8_h1_acf_small_sample", "T = 8, h = 1 (T pequeno)", cand8, comp8, 1L, "acf"))
add(run_case("t8_h2_acf_small_sample", "T = 8, h = 2 (T pequeno)", cand8, comp8, 2L, "acf"))

# 4. Fallback h = 7 -> 1: busca determinística de seed com variância retangular <= 0.
found <- FALSE
for (seed in 1:5000) {
  set.seed(seed)
  cand_fb <- abs(rnorm(20))
  comp_fb <- abs(rnorm(20))
  probe <- run_case("probe", "", cand_fb, comp_fb, 7L, "acf")
  if (is.null(probe$expected_error) && probe$expected$horizon_used == 1L) {
    found <- TRUE
    break
  }
}
stopifnot(found)
add(run_case(sprintf("t20_h7_acf_fallback_seed%d", seed),
             sprintf("T = 20, h = 7 retangular com variância <= 0 (seed %d) -> fallback h = 1", seed),
             cand_fb, comp_fb, 7L, "acf"))
add(run_case(sprintf("t20_h7_bartlett_same_data_seed%d", seed),
             "o mesmo dado do fallback, com Bartlett", cand_fb, comp_fb, 7L, "bartlett"))

# 5. Fallback analítico: d = +-1 alternado (T = 10), h = 2 retangular.
add(run_case("t10_h2_acf_alternating_fallback",
             "d = +-1 alternado, h = 2 retangular: variância < 0 -> fallback h = 1",
             rep(c(3, 1), 5), rep(2, 10), 2L, "acf"))

# 6. Diferencial constante com h = 2: aviso de fallback e depois o erro de variância nula.
add(run_case("t6_h2_acf_constant_differential_error",
             "d constante com h = 2: fallback e depois 'Variance of DM statistic is zero'",
             c(3, 4, 5, 6, 7, 8), c(1, 2, 3, 4, 5, 6), 2L, "acf"))

# 7. Erro h > T (T = 6, h = 7).
add(run_case("t6_h7_acf_horizon_above_t_error", "h > T (T = 6, h = 7)",
             c(1, 2, 3, 4, 5, 6), c(2, 2, 2, 2, 2, 2), 7L, "acf"))

# 8. Erro de variância nula com h = 1 (d constante).
add(run_case("t6_h1_acf_zero_variance_error", "d constante com h = 1: variância nula",
             c(3, 4, 5, 6, 7, 8), c(1, 2, 3, 4, 5, 6), 1L, "acf"))

# 9. d constante com média inexata em float (0,1 x 12): o R ergue variância nula (h = 1)
#    e, com h = 2, cai no fallback e ergue — o domínio não pode devolver S1* ~1e16.
add(run_case("t12_h1_acf_constant_inexact_mean_error",
             "d = 0.1 constante (média inexata em float), h = 1: variância nula",
             rep(0.1, 12), rep(0, 12), 1L, "acf"))
add(run_case("t12_h2_acf_constant_inexact_mean_error",
             "d = 0.1 constante (média inexata em float), h = 2: fallback e variância nula",
             rep(0.1, 12), rep(0, 12), 2L, "acf"))

provenance <- list(
  generator = "tests/fixtures/r_oracle/dm_test_cases.R",
  image = "rocker/r-ver:4.4.1",
  r_version = paste(R.version$major, R.version$minor, sep = "."),
  packages = list(
    forecast = packageDescription("forecast")$Version,
    jsonlite = packageDescription("jsonlite")$Version
  ),
  cran_snapshot = getOption("repos")[["CRAN"]],
  generated_at = format(Sys.Date(), "%Y-%m-%d"),
  session_info = "dm_test_cases.sessionInfo.txt",
  command = paste(
    "docker build -t ff-r-oracle:4.4.1 tests/fixtures/r_oracle &&",
    "docker run --rm -v \"$PWD/tests/fixtures/r_oracle:/work\" -w /work",
    "ff-r-oracle:4.4.1 Rscript dm_test_cases.R"
  )
)

writeLines(
  toJSON(list(provenance = provenance, cases = cases), auto_unbox = TRUE, pretty = TRUE,
         json_verbatim = TRUE, na = "null", null = "null"),
  "dm_test_cases.json",
  useBytes = TRUE
)
writeLines(capture.output(sessionInfo()), "dm_test_cases.sessionInfo.txt")
cat(sprintf("wrote %d cases\n", length(cases)))
