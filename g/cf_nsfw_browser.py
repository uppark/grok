"""
通过子进程调用 camoufox 浏览器绕过 Cloudflare 启用 NSFW。
避免主进程 asyncio 事件循环冲突。
"""
import json
import os
import subprocess
import sys

PROXY_SERVER = "http://127.0.0.1:7897"
WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "nsfw_browser_worker.py")


def enable_nsfw_via_browser(
    sso: str,
    sso_rw: str,
    proxy: str = PROXY_SERVER,
    timeout: int = 120,
) -> dict:
    """用子进程启动浏览器来启用 NSFW，返回 {"ok": bool, "error": str|None}。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-u", WORKER_SCRIPT, sso, sso_rw, proxy],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )

        if proc.stderr:
            for line in proc.stderr.strip().splitlines():
                print(f"  {line}")

        stdout = proc.stdout.strip()
        if not stdout:
            return {"ok": False, "error": f"子进程无输出, exit={proc.returncode}"}

        last_line = stdout.splitlines()[-1]
        return json.loads(last_line)

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"子进程超时 ({timeout}s)"}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON 解析失败: {e}, raw={stdout[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
