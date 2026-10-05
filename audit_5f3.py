from decision_agent import inspect_repository
from decision_selector import select_relevant_files

REQUEST = "Auditer l authentification Clerk OAuth middleware et isolation tenant de MemoLib"

files = inspect_repository()
selection = select_relevant_files(files, REQUEST)

print("=" * 70)
print("MEMOLIBDEV — 5F.3 CONTEXT AUDIT")
print("=" * 70)
print(f"Repository : {len(files)}")
print(f"Candidats  : {selection['candidate_count']}")
print(f"Selection  : {len(selection['selected'])}")
print(f"Total chars: {selection['context_chars']}")
print()

for i, item in enumerate(selection["selected"], 1):
    content = item.get("content", "")
    print(f"{i:02d} | {len(content):7d} chars | {item['path']}")
