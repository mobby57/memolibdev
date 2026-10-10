# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/moros/MemoLibDev/v3/memolibdev_gui_v4.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/moros/MemoLibDev/v3/memolibdev_cli.py', '.'), ('C:/Users/moros/MemoLibDev/v3/verify_project.py', '.'), ('C:/Users/moros/MemoLibDev/v3/create_parser.py', '.'), ('C:/Users/moros/MemoLibDev/v3/create_target.py', '.'), ('C:/Users/moros/MemoLibDev/v3/create_apply.py', '.'), ('C:/Users/moros/MemoLibDev/v3/create_authorization.py', '.'), ('C:/Users/moros/MemoLibDev/v3/create_proof.py', '.'), ('C:/Users/moros/MemoLibDev/v3/create_cli.py', '.'), ('C:/Users/moros/MemoLibDev/v3/project_target.py', '.'), ('C:/Users/moros/MemoLibDev/v3/coder_authorization.py', '.'), ('C:/Users/moros/MemoLibDev/v3/d59_controlled_apply.py', '.'), ('C:/Users/moros/MemoLibDev/v3/code_adapter.py', '.'), ('C:/Users/moros/MemoLibDev/v3/file_target.py', '.'), ('C:/Users/moros/MemoLibDev/v3/humanize.py', '.'), ('C:/Users/moros/MemoLibDev/v3/human_states.py', '.'), ('C:/Users/moros/MemoLibDev/v3/agent_loop.py', '.'), ('C:/Users/moros/MemoLibDev/v3/analysis_builder.py', '.'), ('C:/Users/moros/MemoLibDev/v3/confidence_engine.py', '.'), ('C:/Users/moros/MemoLibDev/v3/proposal.py', '.'), ('C:/Users/moros/MemoLibDev/v3/controlled_coder.py', '.'), ('C:/Users/moros/MemoLibDev/v3/evidence_gate.py', '.'), ('C:/Users/moros/MemoLibDev/v3/mission_intent.py', '.'), ('C:/Users/moros/MemoLibDev/v3/api_facade.py', '.'), ('C:/Users/moros/MemoLibDev/v3/llm', 'llm'), ('C:/Users/moros/MemoLibDev/v3/context', 'context')],
    hiddenimports=['customtkinter', 'llm.ollama_provider', 'llm.llm_planner', 'llm.ai_provider', 'context.context_builder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MemoLibDev',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
