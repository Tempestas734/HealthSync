# health_api

Projet Django pour la gestion de sante.

## Lancement local

Sous Windows, double-clique sur `runserver.bat` ou execute:

```powershell
.\runserver.bat
```

Le script utilise `.health\Scripts\python.exe` si disponible, sinon il retombe sur `py` puis `python`.
Il lance une commande Django dediee `runserver_nodb` qui saute la verification de migrations au demarrage, pour eviter un echec immediat quand la base distante n'est pas joignable.

## Preparation GitHub

Le projet est pret pour GitHub avec:

- un `.gitignore` pour exclure l'environnement virtuel, `.env`, la base SQLite et les caches Python
- un `requirements.txt` a installer sur une autre machine
- un fichier `.env.example` comme modele de configuration

## Commandes Git utiles

```powershell
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<ton-user>/<ton-repo>.git
git push -u origin main
```
