"""
Silverwing Sandbox - safe Python execution.

Executes untrusted code in an isolated subprocess using:
  * an AST allowlist (import/attribute/module restrictions),
  * restricted builtins,
  * a wall-clock timeout,
  * no filesystem/network/session access (guarded at the language level).

This is a software sandbox (defense in depth against accidental misuse and
common escapes); it is not a hardened OS-level isolation boundary (no
container/runtime isolation). Treat it accordingly.
"""

import ast
import builtins
import io
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict

# AST node types allowed in sandboxed code.
ALLOWED_AST = {
    ast.Module, ast.Expr, ast.Constant, ast.Name, ast.Load,
    ast.Store, ast.Del, ast.Attribute, ast.Subscript, ast.List, ast.Tuple,
    ast.Set, ast.Dict, ast.Call, ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In,
    ast.NotIn, ast.Is, ast.IsNot, ast.Not, ast.And, ast.Or, ast.Add, ast.Sub,
    ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
    ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For, ast.While, ast.If,
    ast.Pass, ast.Break, ast.Continue, ast.Return, ast.FunctionDef,
    ast.arguments, ast.arg, ast.Return, ast.IfExp, ast.Slice,
    ast.Import, ast.ImportFrom, ast.alias, ast.Try, ast.ExceptHandler,
    ast.Raise, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.Lambda, ast.Starred, ast.NamedExpr, ast.AsyncFunctionDef, ast.Await, ast.AsyncFor,
}

# Modules/attributes that are always blocked regardless of depth.
BLOCKLIST_KEYWORDS = (
    "system", "popen", "subprocess", "fork", "exec", "eval", "globals", "locals",
    "open", "compile", "execfile", "breakpoint", "memoryview", "input",
    "getattr", "setattr", "delattr", "vars", "help",
)
SAFE_BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "chr",
    "classmethod", "complex", "dict", "dir", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "hasattr", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min",
    "next", "object", "oct", "ord", "pow", "range", "repr", "reversed", "round",
    "set", "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple",
    "type", "zip", "print", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "StopIteration", "ZeroDivisionError", "RuntimeError",
}


class SandboxViolation(Exception):
    pass


def _check_node(node, col_offset=0):
    if col_offset > 40000:
        raise SandboxViolation("Node budget exceeded")
    if type(node) not in ALLOWED_AST:
        raise SandboxViolation(f"Unsupported syntax: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _check_node(child, col_offset + 1)


def _check_import(node):
    if isinstance(node, ast.Import):
        for alias in node.names:
            if not (alias.name == "_sandbox_helpers" or alias.name.startswith("_sandbox_helpers.")):
                raise SandboxViolation(f"Import not allowed: {alias.name}")
    elif isinstance(node, ast.ImportFrom):
        if node.module != "_sandbox_helpers":
            raise SandboxViolation(f"Import not allowed: from {node.module}")
        for alias in node.names:
            if alias.name not in SAFE_BUILTINS and alias.name != "SandboxViolation":
                raise SandboxViolation(f"Import not allowed: {alias.name}")


def _check_name(node):
    # block access to module-global machinery
    if node.id in BLOCKLIST_KEYWORDS:
        raise SandboxViolation(f"Blocked identifier: {node.id}")


class _SandboxVisitor(ast.NodeVisitor):
    def visit_Import(self, node):
        _check_import(node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        _check_import(node)
        self.generic_visit(node)

    def visit_Name(self, node):
        _check_name(node)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        # Walk the attribute chain and block dangerous names at any depth.
        chain = []
        cur = node
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            chain.append(cur.id)
        for part in chain:
            if part in BLOCKLIST_KEYWORDS:
                raise SandboxViolation(f"Blocked attribute: {part}")
        self.generic_visit(node)


def validate(code: str) -> None:
    """Validate and rewrite untrusted code. Raises SandboxViolation."""
    tree = ast.parse(code, mode="exec")
    _check_node(tree)
    ast.fix_missing_locations(tree)
    visitor = _SandboxVisitor()
    visitor.visit(tree)
    return tree


def _runner_source() -> str:
    return r"""
import sys, builtins, time
import json
from io import StringIO

SAFE = {
    "abs","all","any","ascii","bin","bool","bytearray","bytes","chr","classmethod",
    "complex","dict","dir","divmod","enumerate","filter","float","format","frozenset",
    "hasattr","hash","hex","id","int","isinstance","issubclass","iter","len","list",
    "map","max","min","next","object","oct","ord","pow","range","repr","reversed",
    "round","set","slice","sorted","staticmethod","str","sum","super","tuple","type","zip",
    "print", "Exception","ValueError","TypeError","KeyError","IndexError","StopIteration",
    "ZeroDivisionError","RuntimeError","True","False","None",
}
class SandboxViolation(Exception): pass

class _SafeNamespace(dict):
    def __getitem__(self, key):
        if key in SAFE or key in self:
            return dict.__getitem__(self, key)
        if key in ("os", "sys", "subprocess", "builtins", "io", "re", "socket", "shutil", "pathlib", "tempfile", "ctypes", "multiprocessing", "threading"):
            raise SandboxViolation(f"Blocked name: {key}")
        return dict.__getitem__(self, key)
    def get(self, key, default=None):
        if key in self:
            return dict.get(self, key, default)
        if key not in SAFE and key not in ("os", "sys", "subprocess", "builtins", "io", "re", "socket", "shutil", "pathlib", "tempfile", "ctypes"):
            return default
        raise SandboxViolation(f"Blocked name: {key}")

def sandbox_lock_import(*a, **k):
    raise SandboxViolation("Import is not allowed in sandbox")
_orig_getattr = getattr
_orig_compile = compile
_orig_exec = exec
builtins.__import__ = sandbox_lock_import
builtins.eval = lambda *a, **k: (_ for _ in ()).throw(SandboxViolation("eval blocked"))
builtins.exec = lambda *a, **k: (_ for _ in ()).throw(SandboxViolation("exec blocked"))
builtins.getattr = lambda *a, **k: (_ for _ in ()).throw(SandboxViolation("getattr blocked"))
builtins.compile = lambda *a, **k: (_ for _ in ()).throw(SandboxViolation("compile blocked"))

code = sys.stdin.read()
out, err = StringIO(), StringIO()
old_out, old_err, old_stdout, old_stderr = sys.stdout, sys.stderr, None, None
sys.stdout, sys.stderr = out, err
result = {"ok": True, "stdout": "", "stderr": "", "error": None, "time": 0.0}
start = time.time()
try:
    safe_builtins = {k: _orig_getattr(builtins, k) for k in SAFE if hasattr(builtins, k)}
    ns = _SafeNamespace(dict(safe_builtins))
    ns["__builtins__"] = safe_builtins
    # 'print' must target the captured stdout
    ns["print"] = print
    _orig_exec(_orig_compile(code, "<sandbox>", "exec"), ns, ns)
except SandboxViolation as e:
    result["ok"] = False; result["error"] = "violation: %s" % e
except SystemExit:
    result["ok"] = False; result["error"] = "SandboxViolation: SystemExit is not allowed"
except BaseException as e:
    result["ok"] = False; result["error"] = "%s: %s" % (type(e).__name__, e)
finally:
    sys.stdout, sys.stderr = old_out, old_err
result["time"] = round(time.time() - start, 4)
result["stdout"] = out.getvalue()[-4000:]
result["stderr"] = err.getvalue()[-2000:]
print(json.dumps(result))
sys.stdout.flush()
"""


def _kill_tree(pid):
    """Best-effort recursive kill of a process and its children."""
    try:
        import psutil
    except Exception:
        return False
    try:
        p = psutil.Process(pid)
        for child in p.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        p.kill()
        return True
    except Exception:
        return False


def run_code(code: str, timeout: float = 5.0, max_memory_mb: int = 128,
             memory_interval: float = 0.1) -> Dict[str, Any]:
    """Execute untrusted Python code in an isolated subprocess.

    Returns a dict with keys: ok, stdout, stderr, error, time, signal.
    """
    validate(code)  # pre-flight AST checks in the parent process
    runner = sys.executable
    start = time.time()
    result = {"ok": True, "stdout": "", "stderr": "", "error": None, "time": 0.0, "signal": None}
    try:
        import psutil  # memory enforcement backend (not available everywhere)
    except Exception:
        psutil = None
    _mem_flag = psutil is not None and max_memory_mb > 0
    result["memory_enforced"] = _mem_flag
    proc = None
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}

    def _finish_common() -> None:
        result["time"] = round(time.time() - start, 4)

    def _apply_parsed(parsed: Dict[str, Any]) -> None:
        # The runner's payload must not wipe policy metadata on the result dict.
        result.update(parsed)
        result["memory_enforced"] = _mem_flag

    if psutil is None:
        # Minimal path: no memory enforcement available on this interpreter.
        try:
            proc = subprocess.run(
                [runner, "-c", _runner_source()],
                input=code.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env=env,
            )
            if proc.returncode == 0:
                payload = (proc.stdout or b"").decode("utf-8", "replace")
                idx = payload.rfind("{")
                if idx != -1:
                    try:
                        _apply_parsed(json.loads(payload[idx:]))
                    except Exception:
                        _apply_parsed({"ok": True, "stdout": payload, "stderr": (proc.stderr or b"").decode("utf-8", "replace")})
                        result["error"] = "unparseable runner output"
                else:
                    _apply_parsed({"ok": True, "stdout": payload, "stderr": (proc.stderr or b"").decode("utf-8", "replace")})
                    result["error"] = "empty runner output"
            else:
                result["ok"] = False
                result["signal"] = proc.returncode
                stderr = (proc.stderr or b"").decode("utf-8", "replace")
                idx = stderr.rfind("{")
                if idx != -1:
                    try:
                        recovered = json.loads(stderr[idx:])
                        if isinstance(recovered, dict):
                            _apply_parsed(recovered)
                            _finish_common()
                            return result
                    except Exception:
                        pass
                result["error"] = f"process exit code {proc.returncode}: {stderr[-2000:]}"
        except subprocess.TimeoutExpired:
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            result["ok"] = False
            result["error"] = f"Timeout after {timeout}s"
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
        _finish_common()
        return result

    # Path with memory enforcement: Popen + RSS monitor thread.
    limit_bytes = int(max_memory_mb * 1_000_000)
    oom = {"killed": False}
    stop = threading.Event()

    def _monitor(pid: int) -> None:
        try:
            p = psutil.Process(pid)
        except Exception:
            return
        while not stop.wait(memory_interval):
            try:
                total = p.memory_info().rss
                for child in p.children(recursive=True):
                    try:
                        total += child.memory_info().rss
                    except Exception:
                        pass
            except Exception:
                return
            if total > limit_bytes:
                oom["killed"] = True
                _kill_tree(pid)
                return

    try:
        proc = subprocess.Popen(
            [runner, "-c", _runner_source()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        monitor = threading.Thread(target=_monitor, args=(proc.pid,), daemon=True)
        monitor.start()
        try:
            out, err = proc.communicate(input=code.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            oom["killed"] = True  # reuse kill path (signal reports timeout below)
            _kill_tree(proc.pid)
            try:
                out, err = proc.communicate()
            except Exception:
                out, err = b"", b""
            result["ok"] = False
            result["error"] = f"Timeout after {timeout}s"
            result["signal"] = "timeout"
        finally:
            stop.set()
            monitor.join(timeout=1.0)

        if oom["killed"] and result["ok"]:
            if result["error"] == f"Timeout after {timeout}s":
                pass
            elif not result["error"]:
                result["ok"] = False
                result["error"] = f"Memory limit exceeded (>= {max_memory_mb}MB)"
                result["signal"] = "killed"
                _finish_common()
                return result

        if proc.returncode == 0 and not (oom["killed"] and "Timeout" not in (result["error"] or "")):
            payload = (out or b"").decode("utf-8", "replace")
            idx = payload.rfind("{")
            if idx != -1 and "Memory limit" not in (result["error"] or ""):
                try:
                    _apply_parsed(json.loads(payload[idx:]))
                except Exception:
                    _apply_parsed({"ok": True, "stdout": payload, "stderr": (err or b"").decode("utf-8", "replace")})
            else:
                result["ok"] = True
                result["stdout"] = payload
                result["stderr"] = (err or b"").decode("utf-8", "replace")
        elif result["ok"]:
            result["ok"] = False
            if not result["error"]:
                stderr = (err or b"").decode("utf-8", "replace")
                idx = stderr.rfind("{")
                if idx != -1:
                    try:
                        recovered = json.loads(stderr[idx:])
                        if isinstance(recovered, dict):
                            _apply_parsed(recovered)
                            _finish_common()
                            return result
                    except Exception:
                        pass
                result["error"] = f"process exit code {proc.returncode}: {stderr[-2000:]}"
                result["signal"] = proc.returncode
    except Exception as e:  # noqa: BLE001
        result["ok"] = False
        result["error"] = str(e)
    _finish_common()
    return result