# Getting Started - MemoLibDev

> Agent de code local, gratuit, qui refuse de modifier sans accord.

## Prerequis

- Python 3.11+
- Git
- Ollama : https://ollama.com/download
- Un modele : qwen2.5-coder:7b

## Installation

```powershell
git clone <url> MemoLibDev
cd MemoLibDev\v3
```

## CLI - 4 modes

- READ_ONLY : analyse pure
- PROPOSE : diff propose, aucune ecriture
- SANDBOX : apply sur copie
- SUPERVISED_APPLY : apply apres approbation

## Exemple

```powershell
$env:MEMOLIBDEV_TARGET = "C:\chemin\projet"
python memolibdev_cli.py --mission "Renomme hello en greet" --mode PROPOSE --model qwen2.5-coder:7b
```

## Securite

- Aucune ecriture sans approbation humaine
- Rollback automatique si verification echoue
- Trace chainee (hash precedent)
- Fail-closed : refuse d agir en cas de doute

## Philosophie

Il refuse de mentir sur ce qu il fait.
