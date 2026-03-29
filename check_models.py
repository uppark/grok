import asyncio, json, random, sys

SSO = sys.argv[1] if len(sys.argv) > 1 else ""
if not SSO:
    SSO = input("SSO Token: ").strip()

async def check_models():
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(headless=False, proxy={"server": "http://127.0.0.1:7897"}) as browser:
        ctx = await browser.new_context()
        await ctx.add_cookies([
            {"name": "sso", "value": SSO, "domain": ".grok.com", "path": "/"},
            {"name": "sso-rw", "value": SSO, "domain": ".grok.com", "path": "/"},
        ])
        page = await ctx.new_page()

        resp = await page.goto("https://grok.com/", timeout=30000)
        status = resp.status if resp else "N/A"
        print(f"initial load: status={status}")

        for i in range(30):
            await asyncio.sleep(2)
            try:
                title = await page.title()
            except:
                title = "(error)"
            url = page.url
            print(f"[{i}] title={title} | url={url[:80]}")

            if "moment" not in title.lower() and "just" not in title.lower():
                print("CF passed!")
                break

            for frame in page.frames:
                if "challenges.cloudflare" in (frame.url or ""):
                    try:
                        box = await frame.locator("body").bounding_box()
                        if box:
                            x = box["x"] + random.randint(20, int(box["width"]) - 20)
                            y = box["y"] + random.randint(20, int(box["height"]) - 20)
                            await page.mouse.click(x, y)
                            print(f"  clicked CF frame at ({x},{y})")
                    except:
                        pass

        await asyncio.sleep(2)

        print("\n" + "=" * 50)
        print("Querying account info & models...")
        print("=" * 50)

        # 1. 获取用户信息
        try:
            r = await page.evaluate("""async () => {
                try {
                    const r = await fetch('/rest/app-chat/conversations', {
                        method: 'GET',
                        headers: {'Content-Type': 'application/json'}
                    });
                    return {status: r.status, data: await r.json()};
                } catch(e) { return {error: e.message}; }
            }""")
            print("\n--- /conversations ---")
            data = r.get("data", {})
            if isinstance(data, dict):
                print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
            else:
                print(f"status={r.get('status')}, type={type(data).__name__}")
        except Exception as e:
            print(f"error: {e}")

        # 2. 创建新对话（触发模型检测）
        try:
            r = await page.evaluate("""async () => {
                try {
                    const r = await fetch('/rest/app-chat/conversations/new', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({temporary: true})
                    });
                    return {status: r.status, data: await r.json()};
                } catch(e) { return {error: e.message}; }
            }""")
            print("\n--- /conversations/new ---")
            print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
        except Exception as e:
            print(f"error: {e}")

        # 3. 遍历尝试不同 modelSlug
        models = [
            "grok-3", "grok-3-mini", "grok-2", "grok-3-reasoning",
            "grok3", "grok2", "grok-latest", "default",
        ]
        print("\n--- Rate Limits per model ---")
        for model in models:
            try:
                r = await page.evaluate(
                    """async (m) => {
                    try {
                        const r = await fetch('/rest/rate-limits', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({requestKind: 'DEFAULT', modelSlug: m})
                        });
                        const d = await r.json();
                        return {s: r.status, d: d};
                    } catch(e) { return {e: e.message}; }
                }""",
                    model,
                )
                s = r.get("s", "?")
                d = r.get("d", {})
                msg = d.get("message", "") if isinstance(d, dict) else str(d)[:100]
                remaining = d.get("remainingQueries", "?") if isinstance(d, dict) else "?"
                print(f"  {model:20s} | status={s} | remaining={remaining} | {msg}")
            except Exception as e:
                print(f"  {model:20s} | error: {e}")

        # 4. 获取页面实际加载的模型数据（通过window对象）
        try:
            r = await page.evaluate("""() => {
                const data = {};
                data.nextData = window.__NEXT_DATA__ ? Object.keys(window.__NEXT_DATA__) : null;
                data.buildId = window.__NEXT_DATA__?.buildId;
                data.props = window.__NEXT_DATA__?.props?.pageProps ? Object.keys(window.__NEXT_DATA__.props.pageProps) : null;
                return data;
            }""")
            print("\n--- Page __NEXT_DATA__ ---")
            print(json.dumps(r, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"NEXT_DATA error: {e}")

        # 5. 尝试发一条消息看看
        try:
            r = await page.evaluate("""async () => {
                try {
                    const r = await fetch('/rest/app-chat/conversations/new', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({temporary: true})
                    });
                    const conv = await r.json();
                    if (!conv.conversationId) return {error: 'no conversationId', conv: conv};
                    
                    const r2 = await fetch('/rest/app-chat/conversations/' + conv.conversationId + '/responses', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            message: 'Hi, what model are you? Reply in one line.',
                            modelSlug: conv.modelSlug || 'grok-3',
                            parentResponseId: conv.parentResponseId || '',
                            isReasoning: false,
                            temporary: true
                        })
                    });
                    const text = await r2.text();
                    return {status: r2.status, convId: conv.conversationId, modelSlug: conv.modelSlug, response: text.substring(0, 500)};
                } catch(e) { return {error: e.message}; }
            }""")
            print("\n--- Test Message ---")
            print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
        except Exception as e:
            print(f"msg error: {e}")

        await ctx.close()


asyncio.run(check_models())
