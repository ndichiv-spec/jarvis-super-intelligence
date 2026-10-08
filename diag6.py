import inspect
from jarvis_backend.routers import system as s
src = inspect.getsource(s)
for i, l in enumerate(src.split("\n"), 1):
    if ("@router" in l) or ("async def " in l) or ("Depends" in l):
        print(f"{i:5d}| {l}")
