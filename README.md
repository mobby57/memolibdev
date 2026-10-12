# MemoLibDev v3

Outil d'analyse et de modification assistee par IA pour depots de code,
avec confinement, validation humaine et sandbox.

**Promesse** : MemoLibDev analyse votre code, propose des modifications,
mais n'ecrit jamais sans autorisation humaine explicite et verifiable.

## Installation

    git clone https://github.com/mobby57/memolibdev.git
    cd memolibdev/v3
    python -m pip install pytest pytest-timeout

## Configuration

    $env:MEMOLIBDEV_TARGET = "C:\Users\moros\Desktop\memolib"

## Usage

    python memolibdev_cli.py --mission "Analyse le fichier src/lib/ai-isolation.ts" --mode READ_ONLY --model qwen2.5-coder:7b

## Modes

| Mode | Effet |
|---|---|
| READ_ONLY | Analyse, aucun changement (defaut) |
| PROPOSE | Genere une proposition de patch |
| SANDBOX | Applique dans un sandbox isole |
| SUPERVISED_APPLY | Applique dans la cible avec approbation |

## Tests

    python -m pytest -q
    python check_fixes.py
    python doctor.py

## Documentation

- ARCHITECTURE.md
- GETTING_STARTED.md
- CHANGELOG.md

## Garanties

| Garantie | Preuve |
|---|---|
| Aucune ecriture sans approbation | e2e_smoke_test_v3.py |
| Binding cryptographique | coder_authorization.canonical_diff_bytes |
| Sandbox isole | controlled_coder.verify_patch_in_sandbox |
| Fail-closed | REQUIRE_DIFF_BINDING = True |