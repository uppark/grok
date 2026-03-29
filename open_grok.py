"""打开浏览器并用 SSO cookie 登录 grok.com"""
import sys
import asyncio
from patchright.async_api import async_playwright


async def main():
    sso = input("请输入 SSO Token: ").strip()
    if not sso:
        print("SSO Token 不能为空")
        return

    print(f"使用 SSO: {sso[:30]}...")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=["--start-maximized"],
    )
    context = await browser.new_context(
        no_viewport=True,
        proxy={"server": "http://127.0.0.1:7897"},
    )

    await context.add_cookies([
        {"name": "sso", "value": sso, "domain": ".grok.com", "path": "/"},
        {"name": "sso-rw", "value": sso, "domain": ".grok.com", "path": "/"},
    ])

    page = await context.new_page()
    await page.goto("https://grok.com", wait_until="domcontentloaded", timeout=60000)
    print("已打开 grok.com，浏览器将保持打开。")
    print("按 Enter 键退出程序并关闭浏览器...")

    await asyncio.get_event_loop().run_in_executor(None, input)

    try:
        await context.close()
        await browser.close()
        await pw.stop()
    except Exception:
        pass


asyncio.run(main())
