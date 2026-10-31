# Conturile virtuale

Trei portofolii separate, fără capital comun (detalii în `docs/AUDIT_P0.md`, secțiunea A3). Se compară prin randament în procente, nu prin valoare absolută: contul „Reguli” e în unități etichetate EUR (prețuri în USD, fără conversie), celelalte două în USD (10.000 € ≈ 11.183 $ la 1,1183, folosit o singură dată la creare).

Verificarea contabilă independentă: `python -m src.bnd.reconcile --state paper.sqlite` (cod de ieșire 0 = corect).
