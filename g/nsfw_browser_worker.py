"""
独立子进程：用 camoufox 浏览器过 Cloudflare 后在页面内启用 NSFW。
用法: python nsfw_browser_worker.py <sso> <sso_rw> [proxy]
输出: JSON {"ok": true/false, "error": "...", "status_code": ...}
"""
import sys
import json
import asyncio
import time

from camoufox.async_api import AsyncCamoufox


async def click_turnstile(page):
    """通过 page.frames 直接找到 Turnstile frame 并点击复选框"""
    # 策略1：通过 page.frames 直接访问 challenge frame（绕过 shadow DOM）
    for frame in page.frames:
        if "challenges.cloudflare.com" in frame.url or "turnstile" in frame.url:
            print(f"[nsfw-worker] 找到 challenge frame: {frame.url[:80]}", file=sys.stderr)
            checkbox_selectors = [
                'input[type="checkbox"]',
                '.cb-lb input',
                'label input',
                '.ctp-checkbox-label',
                '#challenge-stage input',
            ]
            for sel in checkbox_selectors:
                try:
                    loc = frame.locator(sel).first
                    await loc.click(timeout=3000)
                    print(f"[nsfw-worker] frame 内点击 {sel} 成功!", file=sys.stderr)
                    return True
                except Exception:
                    continue
            # 备用：在 frame 内用坐标点击（复选框通常在左上角区域）
            try:
                body = frame.locator('body')
                box = await body.bounding_box()
                if box:
                    click_x = box['x'] + 28
                    click_y = box['y'] + box['height'] / 2
                    await page.mouse.click(click_x, click_y)
                    print(f"[nsfw-worker] 坐标点击 frame body ({click_x:.0f}, {click_y:.0f})", file=sys.stderr)
                    return True
            except Exception as e:
                print(f"[nsfw-worker] 坐标点击失败: {e}", file=sys.stderr)

    # 策略2：尝试常规 DOM 查询
    for sel in ['.cf-turnstile', '[data-sitekey]']:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=3000)
                print(f"[nsfw-worker] DOM 点击 {sel} 成功", file=sys.stderr)
                return True
        except Exception:
            continue

    # 策略3：JS 点击
    try:
        await page.evaluate("document.querySelector('.cf-turnstile')?.click()")
        return True
    except Exception:
        pass

    return False


async def run(sso: str, sso_rw: str, proxy: str):
    result = {"ok": False, "error": None, "status_code": None}

    camoufox_inst = AsyncCamoufox(headless=True)
    browser = await camoufox_inst.start()

    try:
        ctx_opts = {}
        if proxy:
            ctx_opts["proxy"] = {"server": proxy}

        context = await browser.new_context(**ctx_opts)

        await context.add_cookies([
            {"name": "sso", "value": sso, "domain": ".grok.com", "path": "/"},
            {"name": "sso-rw", "value": sso_rw, "domain": ".grok.com", "path": "/"},
        ])

        page = await context.new_page()

        await page.add_init_script("""
        (function() {
            const orig = Element.prototype.attachShadow;
            Element.prototype.attachShadow = function(init) {
                const shadow = orig.call(this, init);
                if (init.mode === 'closed') window.__lastClosedShadowRoot = shadow;
                return shadow;
            };
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        })();
        """)

        print("[nsfw-worker] 正在打开 grok.com ...", file=sys.stderr)
        try:
            await page.goto("https://grok.com", wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"[nsfw-worker] goto 异常(可能正常): {e}", file=sys.stderr)

        # 等待 Cloudflare 挑战通过
        start = time.time()
        cf_passed = False
        check_count = 0
        while time.time() - start < 60:
            check_count += 1
            cookies = await context.cookies()
            cookie_names = [c["name"] for c in cookies]
            if any(c["name"] == "cf_clearance" for c in cookies):
                print("[nsfw-worker] 已获取 cf_clearance", file=sys.stderr)
                cf_passed = True
                break

            title = await page.title()
            url = page.url

            if check_count <= 3 or check_count % 10 == 0:
                print(f"[nsfw-worker] 第{check_count}次检查 | title={title[:40]} | url={url[:60]}", file=sys.stderr)

            if "just a moment" not in title.lower() and "checking" not in title.lower() and "grok" in url.lower():
                print(f"[nsfw-worker] 页面已加载: {title[:50]}", file=sys.stderr)
                cf_passed = True
                break

            # 每隔几秒尝试多策略点击 Turnstile
            if check_count >= 2 and check_count % 2 == 0:
                clicked = await click_turnstile(page)
                if not clicked and check_count <= 6:
                    print(f"[nsfw-worker] 第{check_count}次: 未能点击 Turnstile", file=sys.stderr)

            await asyncio.sleep(2)

        if not cf_passed:
            result["error"] = "Cloudflare 挑战超时 (60s)"
            print(json.dumps(result, ensure_ascii=False))
            await context.close()
            return

        await asyncio.sleep(2)

        # 在浏览器内发起 NSFW gRPC 请求
        print("[nsfw-worker] 发送 NSFW 启用请求...", file=sys.stderr)
        js_code = """
        async () => {
            const text = "always_show_nsfw_content";
            const encoded = new TextEncoder().encode(text);
            const prefix = new Uint8Array([
                0x0a, 0x02, 0x10, 0x01,
                0x12, 0x1a, 0x0a, 0x18
            ]);
            const payload = new Uint8Array(prefix.length + encoded.length);
            payload.set(prefix, 0);
            payload.set(encoded, prefix.length);

            const frame = new Uint8Array(5 + payload.length);
            frame[0] = 0x00;
            frame[1] = (payload.length >> 24) & 0xff;
            frame[2] = (payload.length >> 16) & 0xff;
            frame[3] = (payload.length >> 8) & 0xff;
            frame[4] = payload.length & 0xff;
            frame.set(payload, 5);

            try {
                const resp = await fetch(
                    "/auth_mgmt.AuthManagement/UpdateUserFeatureControls",
                    {
                        method: "POST",
                        headers: {
                            "content-type": "application/grpc-web+proto",
                            "x-grpc-web": "1",
                            "x-user-agent": "connect-es/2.1.1"
                        },
                        body: frame,
                        credentials: "include"
                    }
                );
                return { ok: resp.ok, status: resp.status, statusText: resp.statusText };
            } catch (e) {
                return { ok: false, error: e.message };
            }
        }
        """

        try:
            fetch_result = await page.evaluate(js_code)
            result["ok"] = fetch_result.get("ok", False)
            result["status_code"] = fetch_result.get("status")
            if not result["ok"]:
                result["error"] = fetch_result.get("error") or f"HTTP {fetch_result.get('status')} {fetch_result.get('statusText', '')}"
            print(f"[nsfw-worker] 请求结果: {fetch_result}", file=sys.stderr)
        except Exception as e:
            result["error"] = f"evaluate 失败: {e}"
            print(f"[nsfw-worker] evaluate 异常: {e}", file=sys.stderr)

        await context.close()

    except Exception as e:
        result["error"] = str(e)
        print(f"[nsfw-worker] 异常: {e}", file=sys.stderr)
    finally:
        try:
            await browser.close()
        except Exception:
            pass

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "用法: python nsfw_browser_worker.py <sso> <sso_rw> [proxy]"}))
        sys.exit(1)

    sso = sys.argv[1]
    sso_rw = sys.argv[2]
    proxy = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:7897"

    asyncio.run(run(sso, sso_rw, proxy))
