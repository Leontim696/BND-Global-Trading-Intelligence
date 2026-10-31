# Matrice de integrare (generată de `scripts/arch_audit.py`)

Coloana „Producție” = rulat direct de un workflow sau script; „Rutină” = rulat de rutinele programate ale sesiunii; „Doar import” = folosit doar de alt modul; „Neconectat” = nu e apelat de nimic în afară de teste.

## Date de piață

| Modul | Folosit de | Producție | Teste |
|---|---|---|---|
| calendars | report_card | doar import | da |
| funding | – | **neconectat** | da |
| instruments | – | **neconectat** | da |
| intraday | – | **neconectat** | da |
| market_data | backtest_cli, backtester, council_context, council_daily, cross_sectional, intraday, paper_engine, paper_runner, portfolio, portfolio_walk_forward, regimes, report_card, robustness, rolls, signal_pipeline, strategies, walk_forward | doar import | da |
| quotes_snapshot | – | da (workflow/script) | da |
| rolls | – | **neconectat** | da |
| universe | backtest_cli, instruments, paper_runner, portfolio, portfolio_walk_forward, quotes_snapshot, report_card | doar import | da |

## Strategii și cercetare

| Modul | Folosit de | Producție | Teste |
|---|---|---|---|
| backtest_cli | paper_runner | da (workflow/script) | da |
| backtest_summary | – | da (workflow/script) | da |
| backtester | backtest_cli, portfolio, robustness, strategies, walk_forward | doar import | da |
| compare_wfo | – | **neconectat** | da |
| cross_sectional | backtest_cli, paper_runner | doar import | da |
| portfolio | backtest_cli, paper_runner, portfolio_walk_forward | doar import | da |
| portfolio_walk_forward | backtest_cli | doar import | da |
| quant_backtest | backtest_cli, market_data, quant_evaluation, quant_report | doar import | da |
| quant_evaluation | quant_report | doar import | da |
| quant_metrics | quant_report | doar import | da |
| quant_report | backtest_cli | doar import | da |
| regimes | backtest_cli | doar import | da |
| robustness | backtest_cli, paper_runner, portfolio, walk_forward | doar import | da |
| signal_pipeline | paper_runner | doar import | da |
| significance | backtest_cli | doar import | da |
| strategies | backtest_cli, council_context, paper_runner, portfolio_walk_forward, walk_forward | doar import | da |
| walk_forward | backtest_cli | doar import | da |

## Motor de trading virtual și risc

| Modul | Folosit de | Producție | Teste |
|---|---|---|---|
| audit_log | council_daily, paper_runner | doar import | da |
| paper_demo | – | **neconectat** | da |
| paper_engine | dashboard, health_check, paper_runner, report_card, scenarios, signal_pipeline | doar import | da |
| paper_runner | – | da (workflow/script) | da |
| risk_engine | backtest_cli, backtester, paper_demo, paper_engine, trade_coordinator | doar import | da |
| safety | paper_engine, paper_runner | doar import | da |
| scenarios | paper_runner, report_card | doar import | da |
| trade_coordinator | paper_demo | doar import | da |

## Consiliul AI

| Modul | Folosit de | Producție | Teste |
|---|---|---|---|
| council_context | council_daily | doar import | da |
| council_daily | – | da (workflow/script) | da |
| council_orchestrator | live_council_bridge | doar import | da |
| council_round | – | **neconectat** | da |
| council_runner | council_daily | doar import | da |
| crypto_signals | – | da (workflow/script) | da |
| debate_engine | paper_demo, trade_coordinator | doar import | da |
| decision_registry | council_daily, crypto_signals, dashboard | doar import | da |
| decision_rules | council_daily, decision_registry, signal_pipeline, trade_coordinator | doar import | da |
| fusion_council | ai_cache, ai_gateway, cost_storage, cost_tracker, council_daily, council_orchestrator, council_round, council_runner, debate_engine, decision_registry, decision_rules, live_council_bridge, local_ai, openrouter_adapter, paper_demo, signal_pipeline, trade_coordinator | doar import | da |
| live_council_bridge | – | **neconectat** | da |

## Furnizori AI și costuri

| Modul | Folosit de | Producție | Teste |
|---|---|---|---|
| ai_budgets | council_daily, orchestrator | doar import | da |
| ai_cache | cost_report, council_runner | doar import | da |
| ai_gateway | ai_cache, ai_smoke_test, code_review_loop, council_daily, council_round, council_runner, live_council_bridge, local_ai, openrouter_adapter, paper_demo | doar import | da |
| ai_smoke_test | – | **neconectat** | da |
| code_review_loop | – | **neconectat** | da |
| cost_report | – | **neconectat** | da |
| cost_storage | ai_budgets, ai_gateway | doar import | da |
| cost_tracker | ai_budgets, ai_gateway, cost_storage, council_daily, council_runner, openrouter_adapter | doar import | da |
| local_ai | – | **neconectat** | da |
| manual_live_review | – | da (workflow/script) | da |
| multi_ai_providers | ai_smoke_test, live_council_bridge | doar import | da |
| openrouter_adapter | council_daily, local_ai, multi_ai_providers | doar import | da |
| openrouter_models | council_daily | da (workflow/script) | da |
| orchestrator | – | **neconectat** | da |
| review_budget | – | **neconectat** | da |
| three_agents_live | – | da (workflow/script) | da |

## Rapoarte, monitorizare, aplicație

| Modul | Folosit de | Producție | Teste |
|---|---|---|---|
| dashboard | – | rutină | da |
| health_check | report_card | da (workflow/script) | da |
| notify | – | da (workflow/script) | da |
| report_card | quotes_snapshot | da (workflow/script) | da |
| report_html | – | rutină | da |

