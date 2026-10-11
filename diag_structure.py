import os, sys
os.environ["MEMOLIBDEV_TARGET"] = r"C:\Users\moros\Desktop\memolib"
sys.path.insert(0, ".")

from project_target import resolve_target
import context.context_builder as cb
import dataclasses

target = resolve_target()
insp = cb.inspect_target(target, max_files=100)
f = insp.files[0]

print("=" * 60)
print(f" Type        : {type(f).__module__}.{type(f).__name__}")
print(f" is_dataclass: {dataclasses.is_dataclass(f)}")
print(f" frozen      : {getattr(type(f), '__dataclass_params__', None) is not None and type(f).__dataclass_params__.frozen}")
print(f" Fields      : {list(vars(f).keys())}")
print()
print(" Sample values:")
for k, v in vars(f).items():
    s = str(v)[:80].replace("\n", "\\n")
    print(f"   {k} = {s}")
print("=" * 60)

# Test dataclasses.replace
try:
    new_f = dataclasses.replace(f, path="src/lib/ai-isolation.ts")
    print("[OK] dataclasses.replace fonctionne")
    print(f"     new path: {new_f.path}")
except Exception as e:
    print(f"[KO] dataclasses.replace echoue : {e}")
