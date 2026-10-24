# Dossiê final de rastreabilidade

Como regenerar: regenerar em qualquer commit com code.src = 9763b31699b981cd768d0cc48fe7ad174444ed02: `report-artifacts --data-root <data_root> --cohort <arquivo de cohort> --preregistration aapl_confirmatory --revision 3 --preregistration-ref aapl_confirmatory-r3-00fd83d9cd39`.

## Ponteiros das afirmações do texto

### H1 em h+1

| campo | valor |
|---|---|
| afirmação | o gate H1 de h+1 passa |
| valor | sim |
| poder declarado | width_5pp_wide (primary, n = 1511): P(reprovar) = 0.9740399941924118; width_5pp_narrow (primary, n = 1511): P(reprovar) = 0.9848282874752274; location_0_2_sigma (primary, n = 1511): P(reprovar) = 0.9997408955227709; width_3pp_wide (secondary, n = 1511): P(reprovar) = 0.6320785436805769; width_3pp_narrow (secondary, n = 1511): P(reprovar) = 0.6064446640098773; location_0_1_sigma (secondary, n = 1511): P(reprovar) = 0.7333595338098631 |
| tabela/documento | gold_model_comparison_confirmatory_scorecard.json |
| chave | verdict.horizons[horizon=1] |
| campo | h1.passed |

### H1 em h+7

| campo | valor |
|---|---|
| afirmação | o gate H1 de h+7 passa |
| valor | sim |
| poder declarado | width_5pp_wide (primary, n = 1505): P(reprovar) = 0.9757927127614499; width_5pp_narrow (primary, n = 1505): P(reprovar) = 0.9870197535116085; location_0_2_sigma (primary, n = 1505): P(reprovar) = 0.9997746891045858; width_3pp_wide (secondary, n = 1505): P(reprovar) = 0.6438031806682214; width_3pp_narrow (secondary, n = 1505): P(reprovar) = 0.6291460672968752; location_0_1_sigma (secondary, n = 1505): P(reprovar) = 0.746490085184189 |
| tabela/documento | gold_model_comparison_confirmatory_scorecard.json |
| chave | verdict.horizons[horizon=7] |
| campo | h1.passed |

### H2 em h+1

| campo | valor |
|---|---|
| afirmação | desfecho de H2 em h+1 |
| valor | beats_naive_only |
| tabela/documento | gold_model_comparison_confirmatory_scorecard.json |
| chave | verdict.horizons[horizon=1] |
| campo | h2 |

### H2 em h+7

| campo | valor |
|---|---|
| afirmação | desfecho de H2 em h+7 |
| valor | beats_naive_ties_strong |
| tabela/documento | gold_model_comparison_confirmatory_scorecard.json |
| chave | verdict.horizons[horizon=7] |
| campo | h2 |

### Vencedor primário

| campo | valor |
|---|---|
| afirmação | vencedor primário por horizonte |
| valor | h+1: —; h+7: tft_quantile |
| tabela/documento | gold_model_comparison_confirmatory_scorecard.json |
| chave | verdict.horizons[] |
| campo | primary_winner |

### Sucesso do estudo

| campo | valor |
|---|---|
| afirmação | H1 não rejeitado em pelo menos um horizonte |
| valor | sim |
| tabela/documento | gold_model_comparison_confirmatory_scorecard.json |
| chave | verdict |
| campo | study_success_h1 |

### Leitura de H3

| campo | valor |
|---|---|
| afirmação | leitura descritiva de H3 (C4/C5) |
| tabela/documento | gold_h3_reading |
| chave | reading_rule |
| campo | label, status |

### Benchmark conformal

| campo | valor |
|---|---|
| afirmação | cobertura empírica (não garantida) do CQR e do nativo |
| tabela/documento | gold_conformal_coverage |
| chave | horizon, variant, kind, lower_level, upper_level, seed, band_level |
| campo | coverage, mpiw, label |

## Poder declarado do gate H1

### Poder do gate H1 em h+1

| campo | valor |
|---|---|
| width_5pp_wide | primary; n = 1511; P(reprovar) = 0.9740399941924118; independência assumida = não |
| width_5pp_narrow | primary; n = 1511; P(reprovar) = 0.9848282874752274; independência assumida = não |
| location_0_2_sigma | primary; n = 1511; P(reprovar) = 0.9997408955227709; independência assumida = não |
| width_3pp_wide | secondary; n = 1511; P(reprovar) = 0.6320785436805769; independência assumida = não |
| width_3pp_narrow | secondary; n = 1511; P(reprovar) = 0.6064446640098773; independência assumida = não |
| location_0_1_sigma | secondary; n = 1511; P(reprovar) = 0.7333595338098631; independência assumida = não |

### Poder do gate H1 em h+7

| campo | valor |
|---|---|
| width_5pp_wide | primary; n = 1505; P(reprovar) = 0.9757927127614499; independência assumida = sim |
| width_5pp_narrow | primary; n = 1505; P(reprovar) = 0.9870197535116085; independência assumida = sim |
| location_0_2_sigma | primary; n = 1505; P(reprovar) = 0.9997746891045858; independência assumida = sim |
| width_3pp_wide | secondary; n = 1505; P(reprovar) = 0.6438031806682214; independência assumida = sim |
| width_3pp_narrow | secondary; n = 1505; P(reprovar) = 0.6291460672968752; independência assumida = sim |
| location_0_1_sigma | secondary; n = 1505; P(reprovar) = 0.746490085184189; independência assumida = sim |

## Identidade da entrada

### Entrada

| campo | valor |
|---|---|
| cohort | aapl_confirmatory-r0-665f45d9169a (hash 665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1) |
| partição | AAPL/aapl_confirmatory-r0-665f45d9169a |
| fingerprint do dataset | 00e4406dcd96658d557f7d4d86face9874fac42385e3cb182d54c5d2286695bd |
| hash de conteúdo do silver lido | 7ac4c759c966b8e1914cd33492a8a598a3b57bcb63eff1e80e9ede1bd02a74e2 |
| feature_set_hash | 7df0e1b4d6e93e3edb5695414a47d2d77882a2ffc674d00037f2a9f87a6409e0 |
| cohort da ablação | aapl_ablation-r0-8a2d1de2dd8c (hash 8a2d1de2dd8c74558e32c80538b35ee2d57158ebb689ee210628967c9c61ce6d) |

### Tags do cohort (convenção do freeze)

| campo | valor |
|---|---|
| tag do cohort | cohort/aapl_confirmatory-r0-665f45d9169a |
| tag do cohort da ablação | cohort/aapl_ablation-r0-8a2d1de2dd8c |

Fonte: [`docs/adr/5_5_0001-frozen-hashed-cohort-spec.md`](../adr/5_5_0001-frozen-hashed-cohort-spec.md)

### Runs do cohort (dim_run)

| campo | valor |
|---|---|
| 0766819d6ddc1184d260487e3435eb0c0cf651c9b42996cca7cf7dd5bf3f75f5 | tft_quantile; seed 6; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 0a1d5940c7e43cfd684be63b1f2d7d345e14d6b3eea02848e5d202be1fec6dcf | baseline_ewma_vol; seed —; fold 5; feature_set fs_all; config_signature c2c16ba068619c1a1e1d4bba798417a532f08b5afb3b65458c6bb4a4b03c66e6; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 0d5cbc8820b5d43acb219d6d0140a263c4dadc5310af83a57545f0a413a1d1c0 | baseline_ar1; seed —; fold 3; feature_set fs_all; config_signature 64da2ca20d4bf317cf6e02d009e8f5a957b7da965cfcd84adacb353a56f9ff12; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 0ff22a8b1344a4cd34a7bda585bea3aa753789059d96a29bcd5bc34a466d55bd | baseline_historical_quantiles; seed —; fold 5; feature_set fs_all; config_signature 6d302d9e5f8ae18d359cc22193ebef886d77d5f69df99da65657e6f1d28939a6; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 13890b27dd521750684d29af28796bcedaaf106a9e1f225d57d7138a1631e088 | tft_quantile; seed 10; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 144fc2fe4b47374e894ecfd11c6b439c7b86bc4a6f2ca94beb6ebd399b98d4b4 | baseline_zero_return; seed —; fold 5; feature_set fs_all; config_signature 48e4bab7b909c20aa6850fb27b4a7a61b3495ace4620f0708eb553dc128e3723; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 15eaf9972764242d510bbd3b9455baef25310da9e6058c9fa5deb9433a6d1ffa | baseline_historical_quantiles; seed —; fold 0; feature_set fs_all; config_signature 6d302d9e5f8ae18d359cc22193ebef886d77d5f69df99da65657e6f1d28939a6; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 16c465086c9c49a8f821408217dbf7cfc26d374cd7a3a61c8f3b35f34feaa887 | baseline_historical_quantiles; seed —; fold 4; feature_set fs_all; config_signature 6d302d9e5f8ae18d359cc22193ebef886d77d5f69df99da65657e6f1d28939a6; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 198ae307d3e3ebbce72b73e857da2256193206e220e3eaa009e82397187ccf94 | tft_quantile; seed 8; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 1ab0fcae772c9a19cc201864100d2d38e82b1b8d5e142867cc25a6d0296b27a7 | tft_quantile; seed 10; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 1cc20c868a6cd2a95bcccb909266858fdb6a8f0bcd194591767b9e28e9ff6d80 | baseline_zero_return; seed —; fold 4; feature_set fs_all; config_signature 48e4bab7b909c20aa6850fb27b4a7a61b3495ace4620f0708eb553dc128e3723; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 1e65d16335874d851124d6ec153d691c71e11e1838515a23c1cba1c7de55a099 | tft_quantile; seed 9; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 1fa13fc68c6af42fee998958176f31f96286af535f590bb4ffbd7fb7e9c4815b | tft_quantile; seed 3; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 2269115eed4ed383f34bc473c9aea5e04f6f011541a81b20c4e1f1ea5826f303 | tft_quantile; seed 3; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 23cdefe3e4500fb192663a56aacfedd3f5f2aaaf8d89ee7b5a5890daa6ab253a | tft_quantile; seed 1; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 249fc509c9dddc34a7e8b0669cca3689ee388c166fb6dfcae52a832060dcb37c | gbm_quantile; seed 0; fold 3; feature_set fs_all; config_signature b5880892d4c127312db3a917fd726da7aa47b0317bfc7ac1abe85e7f1e4d1323; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 30414d3d02adb0e4879753d551e8f07e1fc986e6178c60ec5cdd64d5fbd4c660 | tft_quantile; seed 9; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 32b3d050ea6905e1270bd2e48cca495c39e0d1614a11dc63660f6479bfa1636d | tft_quantile; seed 1; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 358bca246dffd8e89e139f81e331ac291e32264fe1768599453fa21165f953ac | baseline_ar1; seed —; fold 5; feature_set fs_all; config_signature 64da2ca20d4bf317cf6e02d009e8f5a957b7da965cfcd84adacb353a56f9ff12; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 3741d9072e9c98a4fb203e47a2fbdd8be77ab06136838c7bbd25f89924cbe3b5 | tft_quantile; seed 1; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 38d98ba5746f0f47d46bbd9233d31854ed672e4693ae46927d995191fd127181 | tft_quantile; seed 10; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 391dabd15df357bec6f353ff39b2c24e6a3538c7f0f444939df63cc702f9d6aa | tft_quantile; seed 4; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 3d454a3d4a3b876b932b2d4f12d64574e497c480fdd364a4a0081b2f4c3441ac | baseline_ar1; seed —; fold 1; feature_set fs_all; config_signature 64da2ca20d4bf317cf6e02d009e8f5a957b7da965cfcd84adacb353a56f9ff12; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 404485eb99e5b31ef6c530da52e0e8a41229972482c280dc2b96429fb3a050ee | tft_quantile; seed 3; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 4192e355a559b3f93e09027d329ab50f951efab9044771a8e24f31c6131d88a3 | tft_quantile; seed 3; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 465e922d0b53fe660eef29f117166eebd997891a44c7c4d8f7f2351133bea143 | baseline_ar1; seed —; fold 0; feature_set fs_all; config_signature 64da2ca20d4bf317cf6e02d009e8f5a957b7da965cfcd84adacb353a56f9ff12; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 46b1e6d561c79ce690883661b772325ca08a865470d0606f8d8a965491edb58b | tft_quantile; seed 5; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 46e5126d3c378683830e105e2026b2d366a80fa6c7cb1435a46f59b25b651dfa | tft_quantile; seed 6; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 48b653ed5c8086ced68733648aa598e1394115557c82eaca7d4b3452f264a0b3 | tft_quantile; seed 9; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 4b3e9c447bb083137bb1100f807f74358aa487fa86c17708541227813940e4aa | baseline_historical_quantiles; seed —; fold 3; feature_set fs_all; config_signature 6d302d9e5f8ae18d359cc22193ebef886d77d5f69df99da65657e6f1d28939a6; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 4d8295d0cf0340a01c71a4231164508fdf11374cf80ace3a36a0377aeff5c078 | baseline_zero_return; seed —; fold 3; feature_set fs_all; config_signature 48e4bab7b909c20aa6850fb27b4a7a61b3495ace4620f0708eb553dc128e3723; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 4fd81be34d4d5bd678de9c5c2832e30a8d3a55a9700b0370d03054e775dbb1b0 | tft_quantile; seed 5; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 51d8f8138afbb1c4abdc061db8adf3ce4199b09d50cdbeef9c60d3db348d3cb7 | baseline_ewma_vol; seed —; fold 1; feature_set fs_all; config_signature c2c16ba068619c1a1e1d4bba798417a532f08b5afb3b65458c6bb4a4b03c66e6; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 5281d78c3692f4f24de81517f10489f3345ff800218e90094d8f365e3266476e | gbm_quantile; seed 0; fold 2; feature_set fs_all; config_signature b5880892d4c127312db3a917fd726da7aa47b0317bfc7ac1abe85e7f1e4d1323; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 5388035be75ac0cbf4dd5c8398568fb5409420cefbb70d68808d0cea7e8b955b | tft_quantile; seed 2; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 538d9036ec0be7050f0789c3b61b92bb489c9987af49d9801d2d549be6d892db | tft_quantile; seed 5; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 5497266998cdf64b8ae43ddcb1f19d392b96c6d71d92ae8349946e322870ded6 | baseline_ar1; seed —; fold 4; feature_set fs_all; config_signature 64da2ca20d4bf317cf6e02d009e8f5a957b7da965cfcd84adacb353a56f9ff12; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 59043442e6212e36773c80623c407fd31e979e5d39f1d77350c057dd5f342bf6 | tft_quantile; seed 4; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 59d595b6750462483fbb61e3902adec2211c8d349d5e3ceb769aafaa971d500a | gbm_quantile; seed 0; fold 5; feature_set fs_all; config_signature b5880892d4c127312db3a917fd726da7aa47b0317bfc7ac1abe85e7f1e4d1323; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 5b829f7fe5efc4f764327d12e3ff3265d5ae7711831db6fd8773a8ac92f06e79 | tft_quantile; seed 5; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 5c1c2fce6aa5b038b039d45dedcf03e2f061fb60a4ae71b2f05192671dfb5196 | tft_quantile; seed 2; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 5c590bd68217140ebced3ce9f5e3ee1d22f4545f419a1a1e4ba7993bdbe6b33c | baseline_historical_mean; seed —; fold 5; feature_set fs_all; config_signature dd9d92cc8699bcf2f2334e0bb114eb25af7d1e0a7984bf84a4eeec32b3d67097; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 5cda13c091497019c24b5fc8665465c74e3b7439418777e12ea58ec9165aaa44 | tft_quantile; seed 9; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 62de9095ab09bf24a52e19be7e7d9d207ebb6cda162ee9273e05ec1d9b864501 | tft_quantile; seed 7; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| 645a4f406510893847c6687edc91c41fccf88363999a4e1f0c5614dea45a8679 | tft_quantile; seed 2; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 65249179e487b851af47d0b1d313a01cfd0f5aeebd0ae5726b38764d3c7683ad | tft_quantile; seed 4; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 6c5295fd7c63200f4bf3cda7a9359fac329a1f89ed7e411ee9022054c1fa8544 | tft_quantile; seed 6; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 75950b102fcf4d68b99c2482ee2a2dc9c93b0f3c3ac9465a7e839f4ff86effd6 | tft_quantile; seed 7; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 7a5cc858b06c7d721dab5e1c00689ab5abd17060a41d59369ee08b2adb040736 | tft_quantile; seed 2; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 7ebde89d16ae6f312e1c08991a5074bc716b51f7ae9e8bf3bd9efbc15f585144 | baseline_historical_mean; seed —; fold 2; feature_set fs_all; config_signature dd9d92cc8699bcf2f2334e0bb114eb25af7d1e0a7984bf84a4eeec32b3d67097; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 829e4f2855d98c2594e8fb561f548fca936c61796080b48270db88f57d699535 | baseline_zero_return; seed —; fold 2; feature_set fs_all; config_signature 48e4bab7b909c20aa6850fb27b4a7a61b3495ace4620f0708eb553dc128e3723; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| 8be4c1e309ce1577a0af8b65387116f3be931f2eb44d745c5fc8ae2eb9085ece | tft_quantile; seed 3; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 8d33c38fa137b0a34c54ad6df085c692a875060c5ac8acf6662429704bd77227 | tft_quantile; seed 7; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 93bab78b788e88ebcdf5a5718ba88236b27ee6b2a9db96ee15510d821cfab4c6 | gbm_quantile; seed 0; fold 0; feature_set fs_all; config_signature b5880892d4c127312db3a917fd726da7aa47b0317bfc7ac1abe85e7f1e4d1323; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| 95853614e79c2bc926d7b9620ca390bfbcb4bbd4722fdd8666d5ec1e6fd82a03 | baseline_historical_mean; seed —; fold 4; feature_set fs_all; config_signature dd9d92cc8699bcf2f2334e0bb114eb25af7d1e0a7984bf84a4eeec32b3d67097; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| 980b0160799c0d2ca596b4292cebcab7fe193823ff045455814419bc95013bb6 | baseline_historical_mean; seed —; fold 3; feature_set fs_all; config_signature dd9d92cc8699bcf2f2334e0bb114eb25af7d1e0a7984bf84a4eeec32b3d67097; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 9bf31a0507a0d36ef21be5fde558afd7eee0d389a5852a64faee339fdba4071f | baseline_ewma_vol; seed —; fold 3; feature_set fs_all; config_signature c2c16ba068619c1a1e1d4bba798417a532f08b5afb3b65458c6bb4a4b03c66e6; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| 9c92445b8ba773398af9c13a347e0c0a025c21b593c98c2eb8f587f0abf351f3 | tft_quantile; seed 1; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| 9e47d38a4fe506fd3d9e38c153560e9ff83380ad5f709944a4a1aa6452d177bd | baseline_ewma_vol; seed —; fold 0; feature_set fs_all; config_signature c2c16ba068619c1a1e1d4bba798417a532f08b5afb3b65458c6bb4a4b03c66e6; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| ad1a755a139eae338f81d084cdb33917e8e5a8e45015b6c9c7449594c640c828 | gbm_quantile; seed 0; fold 1; feature_set fs_all; config_signature b5880892d4c127312db3a917fd726da7aa47b0317bfc7ac1abe85e7f1e4d1323; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| ae12908e61f99a395820ddfb8c27d7920f19f45f42e912b1730097715ab5b8d8 | baseline_ewma_vol; seed —; fold 2; feature_set fs_all; config_signature c2c16ba068619c1a1e1d4bba798417a532f08b5afb3b65458c6bb4a4b03c66e6; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| aeed9d74c7996d4edf95b795033b20d6def83e2e4aeb8378cc9fae65e9976be5 | baseline_historical_mean; seed —; fold 1; feature_set fs_all; config_signature dd9d92cc8699bcf2f2334e0bb114eb25af7d1e0a7984bf84a4eeec32b3d67097; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| af2ad1049c1c642298308124b8a3f53c0ed42e8db46be9320a1ef20e121a5ab7 | tft_quantile; seed 5; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| af912477dda2f0166460c832cb1d316d6dc23f0c9188b75bc6bb4d4a3e6ba450 | tft_quantile; seed 10; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| b01cb5be006f2826a30b9302f3f9c8cab647ece180db26cc1670c9aef6dba68b | tft_quantile; seed 7; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| b22d9e66183cb540cbc9f8f9e9d932bde41765e2ede2122f180bd09bda72ede5 | tft_quantile; seed 4; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| b703b27a7869c7ba4767db6fe1a7d3805c9196241c38baf3b2a8337437082bed | tft_quantile; seed 8; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| bb9f9cdac84e98ef3be87dc605f93f3679f9b9afe96010749599e736e14ec2ab | gbm_quantile; seed 0; fold 4; feature_set fs_all; config_signature b5880892d4c127312db3a917fd726da7aa47b0317bfc7ac1abe85e7f1e4d1323; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| bdab4044e0a4bddc6c7c9f76088ae95b995a2635b5bc06a8f188188229e094eb | tft_quantile; seed 4; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| bdec4236ba53cc962463457ea5c97df83a07e5459d47d001a3935e8411b1f939 | tft_quantile; seed 6; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| bea8f3791d16c4d2b4a04279d9824e717d159d70c3f437801024c6014a21c14d | tft_quantile; seed 8; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| c5974e5bdf99c121c5c8593bedf2014dbb8ae7d98f993bc8eedea9982835ea1c | baseline_historical_mean; seed —; fold 0; feature_set fs_all; config_signature dd9d92cc8699bcf2f2334e0bb114eb25af7d1e0a7984bf84a4eeec32b3d67097; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| c5f2f673e1cc398f74995fd6204f1241b9a66aeb2b3133f123b73210c2314c91 | baseline_zero_return; seed —; fold 0; feature_set fs_all; config_signature 48e4bab7b909c20aa6850fb27b4a7a61b3495ace4620f0708eb553dc128e3723; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| cc506528af8b53f53aa448b0219fc1fdc7f4fccf4db77b2e8de20e280d704799 | baseline_historical_quantiles; seed —; fold 1; feature_set fs_all; config_signature 6d302d9e5f8ae18d359cc22193ebef886d77d5f69df99da65657e6f1d28939a6; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| cd225a1a95bee746f24d8c6c467d48474d3890fa0e5e44260fd9d5020fc8d423 | baseline_zero_return; seed —; fold 1; feature_set fs_all; config_signature 48e4bab7b909c20aa6850fb27b4a7a61b3495ace4620f0708eb553dc128e3723; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| d0c1505b090286fa564c5c971f87bc6c1ecbae86edce361efda1e372cf4524e0 | tft_quantile; seed 3; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| d0d3d8c0369c7c28139f440b235c48d47c6d5fc8d0b0b17639511588994d6e75 | tft_quantile; seed 4; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| d1a3b34a43f6ff8d77f395c921caaca6f9f1ebcc7c6b855b487586a572880271 | tft_quantile; seed 8; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| d3f312820e97ca352385688bfbefbe40c11352b8c2edaef907fa93881de976c6 | tft_quantile; seed 2; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| d4ed74c8ff0877d72bd27e680dce5f8a162641fedc89343bb4ff29016c696d64 | tft_quantile; seed 7; fold 3; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 721b061b4596bb4d77af528bf4f1fbaa0e28288dd3bf937d922e69a978292209 |
| d58a4cfe09ddd867f0ee0c089693d55383f4744768f8d82d9256802573764887 | tft_quantile; seed 1; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| d9fc3d1aebc9ac012a7149e2c2017f62192dbcad6509b1861b3fccde151d33ec | baseline_ar1; seed —; fold 2; feature_set fs_all; config_signature 64da2ca20d4bf317cf6e02d009e8f5a957b7da965cfcd84adacb353a56f9ff12; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| db0fe0467260abc1375eabda7521b880abf82946a4a730fd2ab145d792082a16 | tft_quantile; seed 2; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| db16c03b821fd96dc5cf78157f2d41f0342dd658b2c50da69ec72985be7b1b10 | tft_quantile; seed 9; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| dc0b6d1ae7678c7b668ada3541402e4136df8c7b22c822ca85a2eb0965bc892c | tft_quantile; seed 5; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| e0e35d9545af3c33acb59880aeb4c027f8b5e5ea03370a49d57e0c31b68098a0 | tft_quantile; seed 6; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| e549820bad1e1454e29aa6391d2533a0dfeeeedb3514d8d854c1bc577ebee4f8 | baseline_historical_quantiles; seed —; fold 2; feature_set fs_all; config_signature 6d302d9e5f8ae18d359cc22193ebef886d77d5f69df99da65657e6f1d28939a6; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| e7493733e73660094aea3b6842df87e1277b725f4d9542fc4610b01d48a4c35a | tft_quantile; seed 6; fold 1; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ec6f00ad465e69f59d83d9a2029f3a48eec62f96301ea9c8275b78950e20ccd8 |
| e96a3c96cddb24d7c9d345940aedddddb6d8c48eb66dba559d538d18dabf6022 | tft_quantile; seed 8; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| e9958fc34ac10779d3e7683c05b87c8927b9e12002e5ec0e2cb1035d3713d15e | tft_quantile; seed 10; fold 0; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ca8897a2d7c26688c2ae8a5a5a83cead3b2be76727250903ae0da26f168edce5 |
| f11cdd23c09bdcd0787a280e7f7a8a5cba215e20cd35413e0aaec2c2664a84b8 | tft_quantile; seed 10; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| f57a7da08c47fdc2860c69921187d0b0f2c3d28ddac981c24690946c269e4560 | tft_quantile; seed 7; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| f65484d67b3290c92dbbaab2c599c63c753f28993a16d5686cc0d9f2ca8357df | tft_quantile; seed 9; fold 5; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint ad13ebc7dafd2fda7d7b8cf1cc56c52923e2dfb2db140737e1db2e91b1477647 |
| f68bf07d72e3f03fc35dbb6a4d5923551eaef0f9fdf7d7824a2d9da13d0e7757 | baseline_ewma_vol; seed —; fold 4; feature_set fs_all; config_signature c2c16ba068619c1a1e1d4bba798417a532f08b5afb3b65458c6bb4a4b03c66e6; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |
| f78a104dfa3a683136eeabbf8eec21c4b0fcd91dd8e6bacda50619dd9712b9da | tft_quantile; seed 8; fold 2; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 6460a39427aed208b051653bb6f984d9d09c4612bf8933fc0f21b72101a8513c |
| f95b2857537903f4eeffd7852b9d221e5ea4404577a53c0248764e54cd9f2fac | tft_quantile; seed 1; fold 4; feature_set fs_all; config_signature 57bba9a893e12d60df7db525e3bd8275da3fe5cbf0e960cd93f636824a005a72; split_fingerprint 7d62f474db1210e448e914bc1b8f675c06bfebc48fe8696177aab0e399068f4b |

## Cadeia do pré-registro

### r0

| campo | valor |
|---|---|
| preregistration_ref | aapl_confirmatory-r0-4526c437c296 |
| sha256 da revisão | 4526c437c2964eb5d38f634c4614074388ed4ce37c6f843c1780faa2ac8081b1 |
| tag | preregistration/aapl_confirmatory-r0-4526c437c296 |
| commit da âncora | 128d23eec95eea4f7ab183e075dfacac14985c66 |
| comentário de âncora | https://github.com/MarceloSanC/financial-forecasting/issues/127#issuecomment-5918567606 |
| instante do servidor | 2026-09-30T19:53:47+00:00 |

Fonte: [`config/preregistration/aapl_confirmatory-r0.toml`](../../config/preregistration/aapl_confirmatory-r0.toml)

### r1

| campo | valor |
|---|---|
| preregistration_ref | aapl_confirmatory-r1-bfa8028498ca |
| sha256 da revisão | bfa8028498ca0768bce8d9a5ae24af1d0ff7fb143216fd09639fa4de29a674bb |
| tag | preregistration/aapl_confirmatory-r1-bfa8028498ca |
| commit da âncora | 3b4285dec00c8f7b8f4bb8d14d767211e76eed21 |
| comentário de âncora | https://github.com/MarceloSanC/financial-forecasting/issues/129#issuecomment-6013351867 |
| instante do servidor | 2026-10-06T09:27:41+00:00 |
| emenda de | aapl_confirmatory-r0-4526c437c296 |
| blind_status | blinded |

Fonte: [`config/preregistration/aapl_confirmatory-r1.toml`](../../config/preregistration/aapl_confirmatory-r1.toml)

### r2

| campo | valor |
|---|---|
| preregistration_ref | aapl_confirmatory-r2-f32ef5ebbbb8 |
| sha256 da revisão | f32ef5ebbbb8e08a3bcc09c0cd2ea438be229cd20bffcaa03ff5bbc5b5b1d4a9 |
| tag | preregistration/aapl_confirmatory-r2-f32ef5ebbbb8 |
| commit da âncora | 25edda90eb19c30b2873d01b6edcae4e96b940d1 |
| comentário de âncora | https://github.com/MarceloSanC/financial-forecasting/issues/158#issuecomment-6258545893 |
| instante do servidor | 2026-10-19T02:45:31+00:00 |
| emenda de | aapl_confirmatory-r1-bfa8028498ca |
| blind_status | blinded |

Fonte: [`config/preregistration/aapl_confirmatory-r2.toml`](../../config/preregistration/aapl_confirmatory-r2.toml)

### r3

| campo | valor |
|---|---|
| preregistration_ref | aapl_confirmatory-r3-00fd83d9cd39 |
| sha256 da revisão | 00fd83d9cd3992b09a162e5e6fe87659d4468be2d73d4cefd54d57b4ac4d82fd |
| tag | preregistration/aapl_confirmatory-r3-00fd83d9cd39 |
| commit da âncora | ad6a4e0d3fef8a2cebf90fb4ef50fe7d8c598d16 |
| comentário de âncora | https://github.com/MarceloSanC/financial-forecasting/issues/186#issuecomment-6322547951 |
| instante do servidor | 2026-10-21T17:41:23+00:00 |
| emenda de | aapl_confirmatory-r2-f32ef5ebbbb8 |
| blind_status | blinded |
| revisão julgada | sim |

Fonte: [`config/preregistration/aapl_confirmatory-r3.toml`](../../config/preregistration/aapl_confirmatory-r3.toml)

## Computação pré-âncora já registrada

### Ressalva de ordem

| campo | valor |
|---|---|
| ressalva | a ordem provada é a do ADR 6.5.0003 item 4: a âncora precede a geração julgada; "no statement is made about computations before it" |

Fonte: [`docs/adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md`](../adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md)

### Computação das tabelas confirmatórias antes do pré-registro (6.4, Task 15)

| campo | valor |
|---|---|
| resumo | A medição da Task 15 da 6.4 rodou o RefreshGold até COMPLETED sobre uma cópia do cohort r0 antes do pré-registro, num container efêmero; foram impressos só status, contagens, durações e o resumo do realizado, nenhum valor de métrica, p-valor ou taxa. |

Fonte: [`docs/stages/6.4-gold-builders-and-quality-gates/technical.md#2026-09-29--finding-exposição-de-cegamento-b-ordem-na-medição-real-da-task-15--claude-opus-55`](../stages/6.4-gold-builders-and-quality-gates/technical.md#2026-09-29--finding-exposição-de-cegamento-b-ordem-na-medição-real-da-task-15--claude-opus-55)

### Decisão humana 6.5-P1: a computação fica como registrada

| campo | valor |
|---|---|
| resumo | r0 segue o cohort julgado, sem novo treino; nenhum artefato pode afirmar que nenhuma métrica foi calculada sobre r0; blinding_statement opcional no pré-registro (ADR 6.5.0010, P1). |

Fonte: [`docs/adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md#decision`](../adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md#decision)

### O que a prova de ordem cobre (ADR 6.5.0003 item 4)

| campo | valor |
|---|---|
| resumo | A ordem provada é âncora do cohort < âncora do pré-registro < primeiro refresh confirmatório (8.1), mais a 6.5 sem métrica sobre o cohort; no statement is made about computations before it. |

Fonte: [`docs/adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md#decision`](../adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md#decision)

## Declaração de cegamento

### Declaração de cegamento (transcrição)

| campo | valor |
|---|---|
| blinding_statement | As tabelas confirmatórias do cohort r0 foram calculadas uma vez num teste de software da Stage 6.4 (Task 15), num container descartado. Nenhum valor resultante foi lido. Nenhuma escolha deste plano usou informação de desempenho. |

Fonte: [`config/preregistration/aapl_confirmatory-r3.toml`](../../config/preregistration/aapl_confirmatory-r3.toml)

## Geração julgada preservada

### Cópia selada

| campo | valor |
|---|---|
| preregistration_ref | aapl_confirmatory-r3-00fd83d9cd39 |
| generation_digest | 96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539 |
| estado | COMPLETED |
| manifesto lido | AAPL/aapl_confirmatory-r0-665f45d9169a |
| academic_decision_ready | sim |
| motivos | — |
| commit da corrida (registrado no .judged.toml) | 060537fc7069b38a318bb5cf839d84b7767b1b4f |
| tag | confirmatory-run/aapl_confirmatory-r3-00fd83d9cd39 |
| comentário de atestação | https://github.com/MarceloSanC/financial-forecasting/issues/211#issuecomment-6362212743 |
| instante do comentário | 2026-10-23T09:51:53+00:00 |
| backup de entrada | data/backups/aapl-pre-8.1-20261023-084758 (e4c774570767c5679a11347beabd9ea872b53101acb8c77ada5a64bc2e50d5e6) |
| backup julgado | data/backups/judged-aapl_confirmatory-r3-00fd83d9cd39-20261023-084758 (ebaadfc4440b400dc9d1fe8c9eb6e42e73f3edb0659e429c5eb2aa151a6613f3) |

Fonte: [`config/preregistration/aapl_confirmatory-r3.judged.toml`](../../config/preregistration/aapl_confirmatory-r3.judged.toml)

## Ambiente

### Avaliação (corrida julgada)

| campo | valor |
|---|---|
| env.cpu_capability | AVX2 |
| env.cpu_count | 12 |
| env.image_id | sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45 |
| env.lib.arch | 8.0.0 |
| env.lib.duckdb | 1.5.4 |
| env.lib.mapie | 1.5.0 |
| env.lib.scikit-learn | 1.9.0 |
| env.lib.scipy | 1.18.0 |
| env.lib.scoringrules | 0.11.0 |
| env.lib.statsmodels | 0.15.0 |
| env.platform | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.41 |
| env.probe.cpu | x86_64/12 |
| env.probe.device | cpu |
| env.probe.exchange-calendars | 4.13.2 |
| env.probe.lightgbm | 4.7.0 |
| env.probe.lightning | 2.6.5 |
| env.probe.numpy | 2.5.0 |
| env.probe.optuna | 4.9.0 |
| env.probe.pandas | 2.3.3 |
| env.probe.pyarrow | 24.0.0 |
| env.probe.python | 3.12.13 |
| env.probe.pytorch-forecasting | 1.8.0 |
| env.probe.statsforecast | 2.1.1 |
| env.probe.torch | 2.13.0+cpu |
| env.probe.torch_threads | 6 |

### Treino confirmatório em CPU

| campo | valor |
|---|---|
| resumo | O cohort confirmatório AAPL foi treinado em CPU (decisão do passo 6 do runbook: n_trials = 60, seeds 1..10, CPU), na imagem de dev com torch 2.13.0+cpu; o ambiente registrado (versões, CPU, threads do torch) está no snapshot do cohort. |

Fonte: [`docs/runbooks/confirmatory-cohort-aapl.md#step-6--human-decisions-p-executed-for-real-task-33`](../runbooks/confirmatory-cohort-aapl.md#step-6--human-decisions-p-executed-for-real-task-33)

### Reprodução do cohort publicado

| campo | valor |
|---|---|
| resumo | Como reproduzir o cohort publicado e onde está o ambiente registrado (versões de bibliotecas, CPU, threads do torch). |

Fonte: [`docs/runbooks/confirmatory-cohort-aapl.md#reproduce-the-published-cohort`](../runbooks/confirmatory-cohort-aapl.md#reproduce-the-published-cohort)

### Ablação treinada em Linux com GPU (ROCm)

| campo | valor |
|---|---|
| resumo | O cohort de ablação (H3) foi treinado em Linux com GPU ROCm: o device e o torch_build entram no hash do spec da ablação e o snapshot ganha chaves de hardware observadas; os checkpoints confirmatórios seguem CPU (ADR 7.3.0004). |

Fonte: [`docs/adr/7_3_0004-device-per-trainer-instance-torch-build-declared.md#decision`](../adr/7_3_0004-device-per-trainer-instance-torch-build-declared.md#decision)

### code.src do HEAD difere do da corrida só por formatação

| campo | valor |
|---|---|
| resumo | Entre 060537fc (corrida julgada) e o HEAD, src/ mudou só por formatação do ruff e um trecho de docstring: o code.src difere, o comportamento não. A reprodução bit a bit rodou na árvore de 060537fc. |

Fonte: [`docs/stages/8.3-plots-and-final-report/concept.md#contexto`](../stages/8.3-plots-and-final-report/concept.md#contexto)

## Commits do código e árvore limpa

### Corrida julgada

| campo | valor |
|---|---|
| commit | 060537fc7069b38a318bb5cf839d84b7767b1b4f |
| início (persistido) | 2026-10-23T09:20:22.405228+00:00 |
| árvore limpa no commit do código | sim (code_dirty = false) |
| árvore limpa do pré-registro | sim (preregistration_dirty = false) |
| code.cohort_file | 6d7c8b82ef98cf27cabc985c53b710dbfba303ea |
| code.src | 4d2b2540a10f5cbb2f59164bba3262224d572d7b |
| code.uv_lock | 0f36050a0044db5f05ca9037e23c4425220cb82b |

### Como regenerar

| campo | valor |
|---|---|
| code.src | 9763b31699b981cd768d0cc48fe7ad174444ed02 |
| code.uv_lock | 0ff8a4dfe837fbb76c5d619b240f918e519c0dd7 |
| regra | regenerar em qualquer commit com code.src = 9763b31699b981cd768d0cc48fe7ad174444ed02 |
| comando | report-artifacts --data-root <data_root> --cohort <arquivo de cohort> --preregistration aapl_confirmatory --revision 3 --preregistration-ref aapl_confirmatory-r3-00fd83d9cd39 |

## Seeds de cada etapa aleatória

### Seeds

| campo | valor |
|---|---|
| treino: baseline_ar1 | sem seed |
| treino: baseline_ewma_vol | sem seed |
| treino: baseline_historical_mean | sem seed |
| treino: baseline_historical_quantiles | sem seed |
| treino: baseline_zero_return | sem seed |
| treino: gbm_quantile | 0 |
| treino: tft_quantile | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| MCS | 127 |
| Monte Carlo de Christoffersen | 128 |
| permutação de H3 | 130 |
| bootstrap de H3 | 129 |
| ablação de H3 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| referência (gold) | generation/MANIFEST.json parameters (MCS, Monte Carlo, H3) |
| referência (training) | cohort spec (code.cohort_file) |

## Figuras: fonte e reconstrução

### reliability_diagram

| campo | valor |
|---|---|
| arquivo | figures/reliability_diagram.pdf |
| data_digest | 92320bf22151cd08c7484466bccff854f7034333089de0e84d5f692c400f3a51 |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'path': 'verdict.horizons[].h1'}; campos lower_band, upper_band, passed, mean_observed |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'path': 'profile.horizons[].power'}; campos label, role, failure_probability |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'dgt_offset': None, 'dgt_step': None, 'includes_degenerate': False, 'level_high': None, 'model': 'tft_quantile', 'path': 'profile.horizons[].calibration_95', 'sample': 'model_full'}; campos mean_violations, mean_observed |
| fonte: gold_table gold_calibration_table | filtro {'band_level': 0.95, 'dgt_offset': None, 'dgt_step': None, 'includes_degenerate': False, 'level_high': None, 'model': 'tft_quantile', 'sample': 'model_full'}; campos violation_rate |
| fonte: gold_table gold_calibration_table | filtro {'band_level': 0.95, 'dgt_offset': None, 'dgt_step': None, 'includes_degenerate': False, 'level_high': None, 'models': 'comparators', 'sample': 'model_full'}; campos wilson_estimate, wilson_lower, wilson_upper |
| omissões declaradas | τ = 0,5 (sem linha de calibração); banda de Wilson do candidato nos níveis fora do gate e da média entre seeds (o gold só a tem por seed; a dispersão por seed é desenhada no lugar) |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

Fonte: [`docs/reports/figures/reliability_diagram.json`](figures/reliability_diagram.json)

### quantile_score_plot

| campo | valor |
|---|---|
| arquivo | figures/quantile_score_plot.pdf |
| data_digest | 1dee7acefecc1df244b5e7c55c1b32a5ef0e5f97eb5796cf7a49af866beff11e |
| fonte: gold_table gold_metrics_by_run | filtro {'level_high': None, 'metric': 'pinball', 'sample': 'common'}; campos value |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'metric': 'pinball', 'model': 'tft_quantile', 'path': 'profile.horizons[].descriptors', 'sample': 'common'}; campos mean, minimum, maximum |
| omissões declaradas | nenhuma |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

Fonte: [`docs/reports/figures/quantile_score_plot.json`](figures/quantile_score_plot.json)

### sharpness_diagram

| campo | valor |
|---|---|
| arquivo | figures/sharpness_diagram.pdf |
| data_digest | 9c3f327a5f93a0c9d2e6a29567da0655b552ed81250b261f01cd4cd25920ff06 |
| fonte: silver_table fact_oos_predictions | filtro {'split': 'test', 'value': 'value_guardrail'}; campos quantile_level, value_guardrail, target_timestamp_utc |
| fonte: realized realized | filtro {}; campos target_return |
| fonte: gold_table gold_metrics_by_run | filtro {'metric': 'mpiw', 'sample': 'model_full'}; campos value |
| omissões declaradas | nenhuma |
| modelos omitidos (sem picp/mpiw no gold) | baseline_zero_return, baseline_historical_mean |
| unidades do silver | 254 |

Fonte: [`docs/reports/figures/sharpness_diagram.json`](figures/sharpness_diagram.json)

### picp_mpiw_plot

| campo | valor |
|---|---|
| arquivo | figures/picp_mpiw_plot.pdf |
| data_digest | bcfd53ece66a8e9d28a148a5c260a8239bc72e1657d792c5ed1fe309409bedcd |
| omissões declaradas | nenhuma |
| modelos omitidos (sem picp/mpiw no gold) | baseline_zero_return, baseline_historical_mean |
| unidades do silver | 0 |

**fonte: gold_table gold_metrics_by_run:**

```text
filtro {'metric': 'picp|mpiw', 'sample': 'common'}; campos value
```

**fonte: document gold_model_comparison_confirmatory_scorecard.json:**

```text
filtro {'metric': 'picp|mpiw', 'model': 'tft_quantile', 'path': 'profile.horizons[].descriptors', 'sample': 'common'}; campos mean, minimum, maximum
```

Fonte: [`docs/reports/figures/picp_mpiw_plot.json`](figures/picp_mpiw_plot.json)

### dm_candidate_vs_comparators

| campo | valor |
|---|---|
| arquivo | figures/dm_candidate_vs_comparators.pdf |
| data_digest | 9d6d0dc210f0a770efc3bc3ac7a50915530862f4066cc293096c5cfed9c949a5 |
| fonte: gold_table gold_dm_results | filtro {'candidate': 'tft_quantile', 'variance_estimator': 'rectangular'}; campos p_value, adjusted_p_value, rejected |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'estimator': 'rectangular', 'path': 'profile.horizons[].dm'}; campos adjusted_p_value, rejected |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'path': 'verdict.horizons[].h1'}; campos passed |
| omissões declaradas | nenhuma |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

Fonte: [`docs/reports/figures/dm_candidate_vs_comparators.json`](figures/dm_candidate_vs_comparators.json)

### oos_fan_chart

| campo | valor |
|---|---|
| arquivo | figures/oos_fan_chart.pdf |
| data_digest | 88a6ede5a7e53ad7f129fc5e64f9fb6ad671d6474cd73ac71b9f447489a8c62d |
| fonte: silver_table fact_oos_predictions | filtro {'model': 'tft_quantile', 'seed': 1, 'split': 'test'}; campos quantile_level, value_guardrail, target_timestamp_utc |
| fonte: realized realized | filtro {}; campos target_return |
| fonte: silver_table dim_run | filtro {}; campos fold |
| omissões declaradas | nenhuma |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 20 |

Fonte: [`docs/reports/figures/oos_fan_chart.json`](figures/oos_fan_chart.json)

### loss_differential_acf

| campo | valor |
|---|---|
| arquivo | figures/loss_differential_acf.pdf |
| data_digest | 01443b683465d9360b5d32ac087b18d082ee9e530d73a5703ebbd7e751cf1b0a |
| fonte: gold_table gold_loss_differentials | filtro {'pairs': 'candidate x family comparator'}; campos differential, fold |
| fonte: gold_table gold_differential_acf | filtro {'pairs': 'candidate x family comparator'}; campos acf |
| omissões declaradas | faixa de confiança da ACF (±1,96/√n não persistida) |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

Fonte: [`docs/reports/figures/loss_differential_acf.json`](figures/loss_differential_acf.json)

### h3_family_importance

| campo | valor |
|---|---|
| arquivo | figures/h3_family_importance.pdf |
| data_digest | 29642f60010e8382042830d2970e4424d5d59460c76473ceecf71acbadcf016d |
| fonte: gold_table gold_h3_importance | filtro {}; campos importance, status, reason |
| fonte: gold_table gold_h3_shares | filtro {}; campos share_h1, share_h7, delta, lower, upper, status |
| fonte: gold_table gold_h3_reading | filtro {}; campos label, status, heterogeneous_permutation, heterogeneous_ablation, sustained, agreeing_families |
| omissões declaradas | intervalo bootstrap de I_f(h) e de s_f(h) (o gold só tem o de Δ_f) |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

Fonte: [`docs/reports/figures/h3_family_importance.json`](figures/h3_family_importance.json)

### vsn_weights

| campo | valor |
|---|---|
| arquivo | figures/vsn_weights.pdf |
| data_digest | 1574ad8ac24713c74c40f010ee85144d7c31eada8959c287b1d5a07f03f65bee |
| fonte: gold_table gold_h3_vsn | filtro {'kind': 'family'}; campos name, p10, p50, p90, label, status |
| omissões declaradas | nenhuma |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

Fonte: [`docs/reports/figures/vsn_weights.json`](figures/vsn_weights.json)

### native_vs_conformal

| campo | valor |
|---|---|
| arquivo | figures/native_vs_conformal.pdf |
| data_digest | c75ad2eabf561bcd55d6d90627836ec6ff5eda84a6487d3f9c153290edeeeb8a |
| fonte: gold_table gold_conformal_coverage | filtro {'band_level': 0.95}; campos coverage, mean_of_seed_coverages, n_evaluated, mpiw, wilson_lower, wilson_upper, label |
| fonte: gold_table gold_calibration_table | filtro {'band_level': 0.95, 'dgt_offset': None, 'includes_degenerate': False, 'model': 'tft_quantile', 'sample': 'model_full'}; campos n_observed, n_violations, wilson_lower, wilson_upper |
| fonte: document gold_model_comparison_confirmatory_scorecard.json | filtro {'dgt_offset': None, 'includes_degenerate': False, 'model': 'tft_quantile', 'path': 'profile.horizons[].calibration_95', 'sample': 'model_full'}; campos mean_violations, mean_observed |
| omissões declaradas | referência de dispersão Beta agregada (o gold só tem beta_mean/beta_sd por fold × seed × cauda; agregar ou tirar quantis seria cálculo novo); banda de Wilson do nativo na média entre seeds (só por seed no gold; os pontos por seed ficam como dispersão) |
| modelos omitidos (sem picp/mpiw no gold) | nenhum |
| unidades do silver | 0 |

**fonte: gold_table gold_metrics_by_run:**

```text
filtro {'metric': 'picp|mpiw', 'model': 'tft_quantile', 'sample': 'model_full'}; campos value
```

**fonte: document gold_model_comparison_confirmatory_scorecard.json:**

```text
filtro {'metric': 'picp|mpiw', 'model': 'tft_quantile', 'path': 'profile.horizons[].descriptors', 'sample': 'model_full'}; campos mean
```

Fonte: [`docs/reports/figures/native_vs_conformal.json`](figures/native_vs_conformal.json)

## Resultado da reprodução

### Identidade reproduzida

| campo | valor |
|---|---|
| generation_digest | 96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539 |
| result_digest | 7c7940d4f77ff772212d5ddc392ee46e5f46cebe06506c17a20885b7f0e31b7e |
| commit da corrida (registrado no .judged.toml) | 060537fc7069b38a318bb5cf839d84b7767b1b4f |
| imagem | sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45 |

Fonte: [`docs/reports/reproduction_audit.md#1-claim`](reproduction_audit.md#1-claim)

### Claim (a): reprodução bit a bit sem re-treino

**resumo:**

```text
No ambiente registrado da corrida e na árvore de 060537fc, silver -> gold -> scorecard refeito a partir dos dados persistidos reproduz a geração julgada bit a bit (19 tabelas gold e o scorecard). R1: 882 727 comparados, 0 diferentes, max |Δ| 0.0; R2: 288 671, 0, 0.0; R3: 1 856, 0, 0.0. Imagem sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45.
```

Fonte: [`docs/reports/reproduction_audit.md#1-claim`](reproduction_audit.md#1-claim)

### Identidade da reprodução

| campo | valor |
|---|---|
| resumo | preregistration_ref, partição, silver_content.digest e dataset_fingerprint iguais entre a geração julgada e a reproduzida; generation_digest 96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539. |

Fonte: [`docs/reports/reproduction_audit.md#2-identidade`](reproduction_audit.md#2-identidade)

### result_digest da reprodução

| campo | valor |
|---|---|
| resumo | result_digest julgado, reproduzido e esperado (input_read do ATTEMPTS.jsonl) iguais: 7c7940d4f77ff772212d5ddc392ee46e5f46cebe06506c17a20885b7f0e31b7e; audit-reproduction exit 0, bit_identical true. |

Fonte: [`docs/reports/reproduction_audit.md#3-result_digest`](reproduction_audit.md#3-result_digest)

### Comparação por classe e por tabela

| campo | valor |
|---|---|
| resumo | R1/R2/R3 por tabela gold, todas com chaves iguais e 0 diferentes; scorecard igual (66 117 folhas, 0 diferentes). |

Fonte: [`docs/reports/reproduction_audit.md#4-comparação-por-classe-e-por-tabela`](reproduction_audit.md#4-comparação-por-classe-e-por-tabela)

### Pré-voo da reprodução em 060537fc (E2)

| campo | valor |
|---|---|
| resumo | Saídas literais da pré-verificação da reprodução: árvore de 060537fc, ambiente igual ao da linha started da ref. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--measurement-e2--pré-voo-da-reprodução-em-060537fc--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--measurement-e2--pré-voo-da-reprodução-em-060537fc--claude-executor-das-etapas)

### Reprodução real e auditoria (E3)

| campo | valor |
|---|---|
| resumo | Saídas literais da reprodução real e do audit-reproduction. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--measurement-e3--reprodução-real-e-auditoria--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--measurement-e3--reprodução-real-e-auditoria--claude-executor-das-etapas)

## Registro de desvios do plano

### Errata O1 da 8.1: commit da corrida confirmatória

| campo | valor |
|---|---|
| resumo | A intenção 1 da Etapa R registra o HEAD d3b49909 (GATE2), mas a corrida rodou em 060537fc, o commit da própria intenção (filho de d3b49909, só §7). code.src e code.uv_lock são os mesmos; o commit do run_record.json e a tag apontam 060537fc. A identidade de código da geração julgada não muda. |

Fonte: [`docs/stages/8.1-confirmatory-run/technical.md#2026-10-23--finding-auditoria-da-stage--erratas-da-evidência-da-etapa-r-e-cobertura-por-arquivo--claude-auditoria-da-stage`](../stages/8.1-confirmatory-run/technical.md#2026-10-23--finding-auditoria-da-stage--erratas-da-evidência-da-etapa-r-e-cobertura-por-arquivo--claude-auditoria-da-stage)

### Errata O2 da 8.1: tentativas do run_record

| campo | valor |
|---|---|
| resumo | "run_record (2 tentativas listadas)" na evidência da Etapa R quer dizer 2 linhas (started e input_read) de 1 tentativa, como mostra o ATTEMPTS.jsonl. |

Fonte: [`docs/stages/8.1-confirmatory-run/technical.md#2026-10-23--finding-auditoria-da-stage--erratas-da-evidência-da-etapa-r-e-cobertura-por-arquivo--claude-auditoria-da-stage`](../stages/8.1-confirmatory-run/technical.md#2026-10-23--finding-auditoria-da-stage--erratas-da-evidência-da-etapa-r-e-cobertura-por-arquivo--claude-auditoria-da-stage)

### Reprodução, E2 item 7: redação do A7 para o parquet_gold_store.py

| campo | valor |
|---|---|
| resumo | Desvio de redação do critério A7 na pré-verificação da reprodução, registrado na Etapa E2. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-e2-item-7--redação-do-a7-para-o-parquet_gold_storepy--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-e2-item-7--redação-do-a7-para-o-parquet_gold_storepy--claude-executor-das-etapas)

### Reprodução: env-equal com --preregistration-ref obrigatória

| campo | valor |
|---|---|
| resumo | A conferência de ambiente (env-equal) passou a exigir --preregistration-ref para comparar com a linha started da ref certa; emenda do runbook das Etapas E2/E3. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-env-equal-com---preregistration-ref-obrigatória-emenda-do-runbook-e2e3--claude-executor`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-env-equal-com---preregistration-ref-obrigatória-emenda-do-runbook-e2e3--claude-executor)

### 5.5: sweep retomável por modelo, não por trial

| campo | valor |
|---|---|
| resumo | O estudo do Optuna vive em memória e o sweep só grava ao fim dos trials; uma queda no meio perde o estudo (o sweep do cohort foi refeito do zero com a mesma sampler_seed). Retomar trial a trial exigiria persistir o estudo; nenhuma Stage posterior tratou. |
| status | open |

Fonte: [`docs/stages/5.5-confirmatory-retrain/technical.md#2026-09-28--finding-task-34--sweep-interrompido-pelo-desligamento-do-host-não-retoma-no-meio-do-estudo--claude-opus-55`](../stages/5.5-confirmatory-retrain/technical.md#2026-09-28--finding-task-34--sweep-interrompido-pelo-desligamento-do-host-não-retoma-no-meio-do-estudo--claude-opus-55)

### 6.5: fronteira lower == nominal do WilsonBand sem teste

| campo | valor |
|---|---|
| resumo | Nenhum caso de tests/unit/features/evaluation/test_wilson_band.py tem um limite de Wilson exatamente igual ao nominal; a troca de <= por < no veredito sobrevive. A regra está certa (banda que toca o nominal contém); falta o teste no dono. |
| status | open |

Fonte: [`docs/stages/6.5-preregistration-and-scorecard/technical.md#2026-09-30--finding-checkpoint-c-bloco-1-a5-fronteira-lower--nominal-do-wilsonband-sem-teste-na-63--claude-opus-55`](../stages/6.5-preregistration-and-scorecard/technical.md#2026-09-30--finding-checkpoint-c-bloco-1-a5-fronteira-lower--nominal-do-wilsonband-sem-teste-na-63--claude-opus-55)

### 8.1: erro de mypy pré-existente em teste de integração

| campo | valor |
|---|---|
| resumo | Dos 3 erros da Task 02, o do contrato saiu com a issue #204 (mypy sobre tests/contract e tests/fakes); o de _cohort_factory.py não reaparece. Segue 1 erro attr-defined em tests/integration/features/evaluation/test_h3_refresh_memory.py, fora do escopo do mypy do make check (medido em 2026-10-24). |
| status | open |

Fonte: [`docs/stages/8.1-confirmatory-run/technical.md#2026-10-22--finding-task-02--erros-de-mypy-pré-existentes-em-tests--claude-sessão-windows`](../stages/8.1-confirmatory-run/technical.md#2026-10-22--finding-task-02--erros-de-mypy-pré-existentes-em-tests--claude-sessão-windows)

### 8.1: erros de mypy pré-existentes em test_refresh_gold_dtos.py

| campo | valor |
|---|---|
| resumo | tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py segue com 28 erros de mypy strict (call-arg, arg-type, attr-defined, unused-ignore); tests/unit fica fora do escopo do mypy do make check, então nenhum gate os cobra (medido em 2026-10-24). |
| status | open |

Fonte: [`docs/stages/8.1-confirmatory-run/technical.md#2026-10-22--finding-task-08--erros-de-mypy-pré-existentes-em-test_refresh_gold_dtospy--claude-sessão-windows`](../stages/8.1-confirmatory-run/technical.md#2026-10-22--finding-task-08--erros-de-mypy-pré-existentes-em-test_refresh_gold_dtospy--claude-sessão-windows)
