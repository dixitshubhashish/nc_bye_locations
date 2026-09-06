import os

local_dir = r"e:\Personal\nc_bye_locations_local"

for fname in ["DATAFLOW.md", "README.md", "IMPLEMENTATION_PLAN.md", "WALKTHROUGH.md"]:
    p = os.path.join(local_dir, fname)
    if os.path.exists(p):
        print(f"=== {fname} exists (size: {os.path.getsize(p)}) ===")
    else:
        print(f"=== {fname} MISSING ===")

