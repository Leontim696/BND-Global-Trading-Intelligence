# Conturile virtuale

Trei portofolii separate, fără capital comun (detalii în `docs/AUDIT_P0.md`, secțiunea A3). Se compară prin randament în procente, nu prin valoare absolută: toate trei sunt acum etichetate USD, iar prețurile sunt în USD, fără conversie. Contul „Reguli” are 10.000 USD (a fost etichetat EUR până pe 31.10.2026, schimbare de etichetă auditată, fără conversie), celelalte două 11.183 USD (10.000 € la 1,1183 la creare).

Verificarea contabilă independentă: `python -m src.bnd.reconcile --state paper.sqlite` (cod de ieșire 0 = corect).
