# Architecture - MemoLibDev

## Pipeline

```
Mission -> Contexte -> LLM -> Validation
       -> Apply -> Verify -> Rollback si echec
```

## Composants cles

- project_target.py : resout la cible Git
- context_builder.py : construit le contexte
- ollama_provider.py : appelle Ollama
- llm_planner.py : valide la sortie LLM
- code_adapter.py : traduit intent en diff
- coder_authorization.py : verifie HumanApproval
- d59_controlled_apply.py : SEUL module qui ecrit
- agent_loop.py : orchestre le cycle

## Invariants

1. LLM != autorite
2. Fail-closed
3. Pas de fallback silencieux
4. Trace chainee
5. Manifeste runtime
6. Rollback automatique
7. Binding cryptographique
