# Instrumente pentru fiecare piață

Generat cu `python -m src.bnd.instruments`. Nu e o recomandare de produs sau broker.

| Piață | Clasă | Activ / ETF din teste | Futures echivalent | CFD tipic | Marjă minimă (ESMA) | Cost pe tranzacție (comision + alunecare) |
|---|---|---|---|---|---:|---:|
| GOLD | commodity | GLD | GC (COMEX) | XAUUSD | 5.00% | 0.040% |
| SILVER | commodity | SLV | SI (COMEX) | XAGUSD | 10.00% | 0.040% |
| CRUDE_OIL | commodity | USO | CL (NYMEX) | USOIL / WTI | 10.00% | 0.040% |
| NATURAL_GAS | commodity | UNG | NG (NYMEX) | NATGAS | 10.00% | 0.040% |
| COPPER | commodity | CPER | HG (COMEX) | COPPER | 10.00% | 0.040% |
| AGRICULTURE | commodity | DBA | ZC / ZW / ZS (CBOT) | – | 10.00% | 0.040% |
| BROAD_COMMODITIES | commodity | DBC | – | – | 10.00% | 0.040% |
| SP500 | index | SPY | ES (CME) | US500 | 5.00% | 0.015% |
| NASDAQ100 | index | QQQ | NQ (CME) | US100 | 5.00% | 0.015% |
| GERMANY | index | EWG | FDAX (Eurex) | GER40 | 5.00% | 0.015% |
| JAPAN | index | EWJ | NK (CME) | JP225 | 5.00% | 0.015% |
| UK | index | EWU | Z (ICE) | UK100 | 5.00% | 0.015% |
| EMERGING | index | EEM | MES (CME, indice MSCI EM) | – | 10.00% | 0.015% |
| US10Y_NOTE | bond | IEF | ZN (CBOT) | US10Y | 20.00% | 0.015% |
| US20Y_BOND | bond | TLT | ZB (CBOT) | US30Y | 20.00% | 0.015% |
| EURUSD | forex | EUR/USD spot | 6E (CME) | EURUSD | 3.33% | 0.007% |
| GBPUSD | forex | GBP/USD spot | 6B (CME) | GBPUSD | 3.33% | 0.007% |
| USDJPY | forex | USD/JPY spot | 6J (CME, invers) | USDJPY | 3.33% | 0.007% |
| AUDUSD | forex | AUD/USD spot | 6A (CME) | AUDUSD | 5.00% | 0.007% |
| USDCHF | forex | USD/CHF spot | 6S (CME, invers) | USDCHF | 3.33% | 0.007% |
| USDCAD | forex | USD/CAD spot | 6C (CME, invers) | USDCAD | 3.33% | 0.007% |
| BITCOIN | crypto | BTC spot (sau un ETF spot pe Bitcoin) | BTC (CME) | BTCUSD | 50.00% | 0.150% |
| ETHEREUM | crypto | ETH spot (sau un ETF spot pe Ethereum) | ETH (CME) | ETHUSD | 50.00% | 0.150% |
| CORN | commodity | – | ZC (CBOT) | CORN | 10.00% | 0.070% |
| WHEAT | commodity | – | ZW (CBOT) | WHEAT | 10.00% | 0.070% |
| SOYBEANS | commodity | – | ZS (CBOT) | SOYBEAN | 10.00% | 0.070% |
| DAX | index | EWG | FDAX (Eurex) | GER40 | 5.00% | 0.030% |
| NIKKEI | index | EWJ | NK (CME) | JP225 | 5.00% | 0.030% |
| FTSE100 | index | EWU | Z (ICE) | UK100 | 5.00% | 0.030% |
| AAPL | stock | AAPL | – | AAPL (CFD pe acțiune) | 20.00% | 0.050% |
| MSFT | stock | MSFT | – | MSFT (CFD pe acțiune) | 20.00% | 0.050% |
| NVDA | stock | NVDA | – | NVDA (CFD pe acțiune) | 20.00% | 0.050% |
| GOOGL | stock | GOOGL | – | GOOGL (CFD pe acțiune) | 20.00% | 0.050% |
| AMZN | stock | AMZN | – | AMZN (CFD pe acțiune) | 20.00% | 0.050% |
| WMT | stock | WMT | – | WMT (CFD pe acțiune) | 20.00% | 0.050% |
| KO | stock | KO | – | KO (CFD pe acțiune) | 20.00% | 0.050% |
| PG | stock | PG | – | PG (CFD pe acțiune) | 20.00% | 0.050% |
| JNJ | stock | JNJ | – | JNJ (CFD pe acțiune) | 20.00% | 0.050% |
| UNH | stock | UNH | – | UNH (CFD pe acțiune) | 20.00% | 0.050% |
| XOM | stock | XOM | – | XOM (CFD pe acțiune) | 20.00% | 0.050% |
| CVX | stock | CVX | – | CVX (CFD pe acțiune) | 20.00% | 0.050% |
| JPM | stock | JPM | – | JPM (CFD pe acțiune) | 20.00% | 0.050% |
| GS | stock | GS | – | GS (CFD pe acțiune) | 20.00% | 0.050% |
| CAT | stock | CAT | – | CAT (CFD pe acțiune) | 20.00% | 0.050% |
| BA | stock | BA | – | BA (CFD pe acțiune) | 20.00% | 0.050% |
| SOLANA | crypto | SOL spot | SOL (CME) | SOLUSD | 50.00% | 0.150% |
| BNB | crypto | BNB spot | – | BNBUSD | 50.00% | 0.150% |
| XRP | crypto | XRP spot | XRP (CME) | XRPUSD | 50.00% | 0.150% |
