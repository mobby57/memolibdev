# Cible de MemoLibDev v3

## Depot cible unique

`C:\Users\moros\Desktop\memolib`

- Remote : https://github.com/mobby57/memoLib.git
- Branche : `fix/clerk-signup-m1` (dev en cours)

## Historique

Un 2e clone existait sur `C:\Users\moros\memoLib` (branche `main`).
Supprime le <date> pour eviter la confusion.

Pour revenir sur main, faire dans `Desktop\memolib` :

    git checkout main

Pour creer une vue d'une autre branche sans dupliquer le clone :

    git worktree add ..\memolib-<branche> <branche>

## Scripts v3

Tous pointent vers `Desktop\memolib` :
- `conftest.py` : DEFAULT_TARGET
- `post_ci.py` : ROOT
- Variable `MEMOLIBDEV_TARGET` (a definir pour les scripts standalone)
