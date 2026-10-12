# Demarrage rapide

## 1. Prerequis

- Python 3.11+
- Git
- (Optionnel) Ollama

## 2. Installation

    git clone https://github.com/mobby57/memolibdev.git
    cd memolibdev/v3
    python -m pip install pytest pytest-timeout

## 3. Configuration

    $env:MEMOLIBDEV_TARGET = "C:\Users\moros\Desktop\memolib"

Pour rendre permanent :

    Add-Content $PROFILE "`n`$env:MEMOLIBDEV_TARGET = 'C:\Users\moros\Desktop\memolib'"

## 4. Verification

    python doctor.py
    python -m pytest -q
    python check_fixes.py

## 5. Premiere mission

    python memolibdev_cli.py --mission "Analyse le fichier src/lib/ai-isolation.ts" --mode READ_ONLY --model qwen2.5-coder:7b

## 6. Depannage

Ollama non disponible :

    python -c "from ollama_helpers import ollama_available; print(ollama_available())"

Tests bloquent :

    python find_blocker.py

Diagnostic complet :

    python doctor.py