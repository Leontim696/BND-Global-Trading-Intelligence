# Lista manuală de walleturi

Pune adresele (Solana) în `wallete.json`, de exemplu:

```json
[{"wallet": "ADRESA_BASE58", "label": "notiță proprie"}]
```

Adresele invalide se ignoră. Colectorul rulează zilnic (`.github/workflows/smart-money.yml`), salvează statistici și
filtrele pe ramura `smart-money` și **nu ia nicio decizie**. Etichetarea `tipar_insider` e un tipar de comportament,
nu o dovadă.
