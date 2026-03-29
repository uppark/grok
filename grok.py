import os, json, random, string, time, re, struct, logging
import threading
import concurrent.futures
from datetime import datetime
from urllib.parse import urljoin, urlparse
from curl_cffi import requests
from bs4 import BeautifulSoup

from g import EmailService, TurnstileService, UserAgreementService, NsfwSettingsService, enable_nsfw_via_browser

# 基础配置
site_url = "https://accounts.x.ai"
DEFAULT_IMPERSONATE = "chrome120"
CHROME_PROFILES = [
    {"impersonate": "chrome110", "version": "110.0.0.0", "brand": "chrome"},
    {"impersonate": "chrome119", "version": "119.0.0.0", "brand": "chrome"},
    {"impersonate": "chrome120", "version": "120.0.0.0", "brand": "chrome"},
    {"impersonate": "edge99", "version": "99.0.1150.36", "brand": "edge"},
    {"impersonate": "edge101", "version": "101.0.1210.47", "brand": "edge"},
]
def get_random_chrome_profile():
    profile = random.choice(CHROME_PROFILES)
    if profile.get("brand") == "edge":
        chrome_major = profile["version"].split(".")[0]
        chrome_version = f"{chrome_major}.0.0.0"
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Safari/537.36 Edg/{profile['version']}"
        )
    else:
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{profile['version']} Safari/537.36"
        )
    return profile["impersonate"], ua
PROXIES = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897"
}

# 动态获取的全局变量
config = {
    "site_key": "0x4AAAAAAAhr9JGVDZbrZOo0",
    "action_id": None,
    "state_tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fsign-up%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
}

post_lock = threading.Lock()
file_lock = threading.Lock()
success_count = 0
start_time = time.time()
target_count = 100
stop_event = threading.Event()
output_file = None
accounts_file = None
log_file = None
logger = None

def setup_logger(log_path):
    """配置同时输出到控制台和文件的日志"""
    global logger
    logger = logging.getLogger("grok")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

def log(msg):
    if logger:
        logger.info(msg)
    else:
        print(msg)

def save_account(account_info):
    """追加一条账号记录到 JSON Lines 文件（调用方需持有 file_lock）"""
    with open(accounts_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(account_info, ensure_ascii=False) + "\n")

def generate_random_name() -> str:
    length = random.randint(4, 6)
    return random.choice(string.ascii_uppercase) + ''.join(random.choice(string.ascii_lowercase) for _ in range(length - 1))

def generate_random_string(length: int = 15) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def encode_grpc_message(field_id, string_value):
    key = (field_id << 3) | 2
    value_bytes = string_value.encode('utf-8')
    length = len(value_bytes)
    payload = struct.pack('B', key) + struct.pack('B', length) + value_bytes
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def encode_grpc_message_verify(email, code):
    p1 = struct.pack('B', (1 << 3) | 2) + struct.pack('B', len(email)) + email.encode('utf-8')
    p2 = struct.pack('B', (2 << 3) | 2) + struct.pack('B', len(code)) + code.encode('utf-8')
    payload = p1 + p2
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def send_email_code_grpc(session, email):
    url = f"{site_url}/auth_mgmt.AuthManagement/CreateEmailValidationCode"
    data = encode_grpc_message(1, email)
    headers = {"content-type": "application/grpc-web+proto", "x-grpc-web": "1", "x-user-agent": "connect-es/2.1.1", "origin": site_url, "referer": f"{site_url}/sign-up?redirect=grok-com"}
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        if res.status_code != 200:
            log(f"[-] {email} 发送验证码失败: HTTP {res.status_code} | {res.text[:100]}")
        return res.status_code == 200
    except Exception as e:
        log(f"[-] {email} 发送验证码异常: {e}")
        return False

def verify_email_code_grpc(session, email, code):
    url = f"{site_url}/auth_mgmt.AuthManagement/VerifyEmailValidationCode"
    data = encode_grpc_message_verify(email, code)
    headers = {"content-type": "application/grpc-web+proto", "x-grpc-web": "1", "x-user-agent": "connect-es/2.1.1", "origin": site_url, "referer": f"{site_url}/sign-up?redirect=grok-com"}
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        return res.status_code == 200
    except Exception as e:
        log(f"[-] {email} 验证验证码异常: {e}")
        return False

def register_single_thread():
    time.sleep(random.uniform(0, 5))
    thread_id = threading.get_ident() % 10000
    
    try:
        email_service = EmailService()
        turnstile_service = TurnstileService()
        user_agreement_service = UserAgreementService()
        nsfw_service = NsfwSettingsService()
    except Exception as e:
        log(f"[-] [T{thread_id}] 服务初始化失败: {e}")
        return
    
    final_action_id = config["action_id"]
    if not final_action_id:
        log(f"[-] [T{thread_id}] 线程退出：缺少 Action ID")
        return
    
    while True:
        try:
            if stop_event.is_set():
                return
            impersonate_fingerprint, account_user_agent = get_random_chrome_profile()
            with requests.Session(impersonate=impersonate_fingerprint, proxies=PROXIES) as session:
                try: session.get(site_url, timeout=10)
                except: pass

                password = generate_random_string()
                given_name = generate_random_name()
                family_name = generate_random_name()
                
                try:
                    jwt, email = email_service.create_email()
                except Exception as e:
                    log(f"[-] [T{thread_id}] 邮箱服务异常: {e}")
                    jwt, email = None, None

                if not email:
                    time.sleep(5); continue

                if stop_event.is_set():
                    if email:
                        email_service.delete_email(email)
                    return
                
                reg_start = time.time()
                log(f"[*] [T{thread_id}] 开始注册: {email}")

                if not send_email_code_grpc(session, email):
                    log(f"[-] [T{thread_id}] {email} 发送验证码失败")
                    email_service.delete_email(email)
                    time.sleep(5); continue

                log(f"[*] [T{thread_id}] {email} 验证码已发送，等待接收...")
                verify_code = email_service.fetch_verification_code(email)
                if not verify_code:
                    log(f"[-] [T{thread_id}] {email} 未收到验证码，跳过")
                    email_service.delete_email(email)
                    continue

                log(f"[*] [T{thread_id}] {email} 验证码: {verify_code}")
                if not verify_email_code_grpc(session, email, verify_code):
                    log(f"[-] [T{thread_id}] {email} 验证码验证失败")
                    email_service.delete_email(email)
                    continue
                
                for attempt in range(3):
                    if stop_event.is_set():
                        email_service.delete_email(email)
                        return
                    task_id = turnstile_service.create_task(site_url, config["site_key"])
                    token = turnstile_service.get_response(task_id)
                    
                    if not token or token == "CAPTCHA_FAIL":
                        log(f"[-] [T{thread_id}] {email} Turnstile 失败 ({attempt+1}/3)")
                        continue
                    
                    log(f"[*] [T{thread_id}] {email} Turnstile OK, 提交注册...")

                    headers = {
                        "user-agent": account_user_agent, "accept": "text/x-component", "content-type": "text/plain;charset=UTF-8",
                        "origin": site_url, "referer": f"{site_url}/sign-up", "cookie": f"__cf_bm={session.cookies.get('__cf_bm','')}",
                        "next-router-state-tree": config["state_tree"], "next-action": final_action_id
                    }
                    payload = [{
                        "emailValidationCode": verify_code,
                        "createUserAndSessionRequest": {
                            "email": email, "givenName": given_name, "familyName": family_name,
                            "clearTextPassword": password, "tosAcceptedVersion": "$undefined"
                        },
                        "turnstileToken": token, "promptOnDuplicateEmail": True
                    }]
                    
                    with post_lock:
                        res = session.post(f"{site_url}/sign-up", json=payload, headers=headers)
                    
                    log(f"[d] [T{thread_id}] {email} 注册响应: HTTP {res.status_code}, len={len(res.text)}")
                    
                    if res.status_code == 200:
                        match = re.search(r'(https://[^" \s]+set-cookie\?q=[^:" \s]+)1:', res.text)
                        if not match:
                            log(f"[-] [T{thread_id}] {email} 注册失败: 未找到 set-cookie URL")
                            email_service.delete_email(email)
                            break
                        if match:
                            verify_url = match.group(1)
                            log(f"[*] [T{thread_id}] {email} 访问 set-cookie URL...")
                            session.get(verify_url, allow_redirects=True)
                            sso = session.cookies.get("sso")
                            sso_rw = session.cookies.get("sso-rw")
                            if not sso:
                                log(f"[-] [T{thread_id}] {email} 未获取到 SSO cookie")
                                email_service.delete_email(email)
                                break

                            log(f"[+] [T{thread_id}] {email} SSO获取成功!")

                            tos_ok = False
                            log(f"[*] [T{thread_id}] {email} 接受TOS...")
                            try:
                                tos_result = user_agreement_service.accept_tos_version(
                                    sso=sso, sso_rw=sso_rw or "",
                                    impersonate=impersonate_fingerprint,
                                    user_agent=account_user_agent,
                                )
                                tos_ok = tos_result.get("ok", False)
                                if not tos_ok:
                                    log(f"[!] [T{thread_id}] {email} TOS接受失败(账号仍有效)")
                            except Exception as e:
                                log(f"[!] [T{thread_id}] {email} TOS异常: {e}")

                            nsfw_ok = False
                            nsfw_method = "none"
                            log(f"[*] [T{thread_id}] {email} 启用NSFW...")
                            try:
                                nsfw_result = nsfw_service.enable_nsfw(
                                    sso=sso, sso_rw=sso_rw or "",
                                    impersonate=impersonate_fingerprint,
                                    user_agent=account_user_agent,
                                )
                                if nsfw_result.get("ok"):
                                    nsfw_ok = True
                                    nsfw_method = "direct"
                                else:
                                    log(f"[!] [T{thread_id}] {email} NSFW直连失败({nsfw_result.get('error')}), 留到最后批量处理")
                            except Exception as e:
                                log(f"[!] [T{thread_id}] {email} NSFW异常: {e}")

                            reg_duration = round(time.time() - reg_start, 1)
                            account_info = {
                                "index": None,
                                "email": email,
                                "password": password,
                                "given_name": given_name,
                                "family_name": family_name,
                                "sso": sso,
                                "sso_rw": sso_rw or "",
                                "tos_accepted": tos_ok,
                                "nsfw_enabled": nsfw_ok,
                                "nsfw_method": nsfw_method,
                                "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "duration_sec": reg_duration,
                            }

                            with file_lock:
                                global success_count
                                if success_count >= target_count:
                                    if not stop_event.is_set():
                                        stop_event.set()
                                    break
                                success_count += 1
                                account_info["index"] = success_count
                                with open(output_file, "a") as f:
                                    f.write(sso + "\n")
                                save_account(account_info)
                                avg = (time.time() - start_time) / success_count
                                log(f"[+] [{success_count}/{target_count}] {email} | 密码:{password} | NSFW:{nsfw_ok} | {reg_duration}s | 均{avg:.1f}s/个")
                                if success_count >= target_count and not stop_event.is_set():
                                    stop_event.set()
                            break

                    time.sleep(3)
                else:
                    log(f"[-] [T{thread_id}] {email} 重试3次均失败")
                    email_service.delete_email(email)
                    time.sleep(5)

        except Exception as e:
            log(f"[-] [T{thread_id}] 异常: {str(e)[:80]}")
            time.sleep(5)

def print_summary():
    """读取账号文件并打印汇总"""
    if not accounts_file or not os.path.exists(accounts_file):
        return
    accounts = []
    with open(accounts_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                accounts.append(json.loads(line))
    
    total = len(accounts)
    if total == 0:
        log("=" * 60)
        log("注册完成，无成功账号")
        return

    nsfw_ok = sum(1 for a in accounts if a.get("nsfw_enabled"))
    tos_ok = sum(1 for a in accounts if a.get("tos_accepted"))
    avg_dur = sum(a.get("duration_sec", 0) for a in accounts) / total
    elapsed = time.time() - start_time

    log("=" * 60)
    log(f"注册完成汇总")
    log(f"=" * 60)
    log(f"  成功注册: {total} 个")
    log(f"  TOS已接受: {tos_ok}/{total}")
    log(f"  NSFW已启用: {nsfw_ok}/{total}")
    log(f"  平均耗时: {avg_dur:.1f}s/个")
    log(f"  总耗时: {elapsed:.0f}s ({elapsed/60:.1f}分钟)")
    log(f"  SSO文件: {output_file}")
    log(f"  账号详情: {accounts_file}")
    log(f"  日志文件: {log_file}")
    log(f"=" * 60)

    import csv as csv_mod
    csv_file = accounts_file.replace(".jsonl", ".csv")
    fields = ["index", "email", "password", "family_name", "given_name",
              "sso", "sso_rw", "nsfw_enabled", "nsfw_method", "tos_accepted",
              "registered_at", "duration_sec"]
    headers = ["序号", "邮箱", "密码", "姓", "名",
               "SSO", "SSO-RW", "NSFW", "NSFW方式", "TOS",
               "注册时间", "耗时(秒)"]
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv_mod.writer(f)
        writer.writerow(headers)
        for a in accounts:
            writer.writerow([a.get(k, "") for k in fields])
    log(f"  CSV汇总: {csv_file}")


def main():
    global target_count, output_file, accounts_file, log_file

    import sys
    if len(sys.argv) >= 3:
        t = int(sys.argv[1])
        total = int(sys.argv[2])
    else:
        try:
            t = int(input("\n并发数 (默认8): ").strip() or 8)
        except: t = 8
        try:
            total = int(input("注册数量 (默认100): ").strip() or 100)
        except: total = 100

    target_count = max(1, total)

    os.makedirs("keys", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"keys/grok_{timestamp}_{target_count}.txt"
    accounts_file = f"keys/grok_{timestamp}_{target_count}_accounts.jsonl"
    log_file = f"logs/grok_{timestamp}_{target_count}.log"

    setup_logger(log_file)

    log("=" * 60)
    log("Grok 注册机")
    log("=" * 60)
    log(f"  目标数量: {target_count}")
    log(f"  并发线程: {t}")
    log(f"  SSO输出:  {output_file}")
    log(f"  账号详情: {accounts_file}")
    log(f"  运行日志: {log_file}")
    log("=" * 60)

    log("[*] 正在初始化...")
    start_url = f"{site_url}/sign-up"
    with requests.Session(impersonate=DEFAULT_IMPERSONATE) as s:
        try:
            html = s.get(start_url).text
            key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
            if key_match: config["site_key"] = key_match.group(1)
            tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
            if tree_match: config["state_tree"] = tree_match.group(1)
            soup = BeautifulSoup(html, 'html.parser')
            js_urls = [urljoin(start_url, script['src']) for script in soup.find_all('script', src=True) if '_next/static' in script['src']]
            for js_url in js_urls:
                js_content = s.get(js_url).text
                match = re.search(r'7f[a-fA-F0-9]{40}', js_content)
                if match:
                    config["action_id"] = match.group(0)
                    log(f"[+] Action ID: {config['action_id']}")
                    break
        except Exception as e:
            log(f"[-] 初始化扫描失败: {e}")
            return

    if not config["action_id"]:
        log("[-] 错误: 未找到 Action ID")
        return

    log(f"[*] 启动 {t} 个线程，开始注册...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=t) as executor:
        futures = [executor.submit(register_single_thread) for _ in range(t)]
        concurrent.futures.wait(futures)

    # 未成功启用 NSFW 的账号做二次验证
    if accounts_file and os.path.exists(accounts_file):
        need_nsfw = []
        with open(accounts_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    a = json.loads(line)
                    if not a.get("nsfw_enabled"):
                        need_nsfw.append(a)
        if need_nsfw:
            log(f"\n[*] {len(need_nsfw)} 个账号 NSFW 未启用，开始二次验证...")
            for a in need_nsfw:
                result = enable_nsfw_via_browser(a["sso"], a.get("sso_rw", ""))
                if result.get("ok"):
                    log(f"[+] NSFW二次启用成功: {a['email']}")
                    a["nsfw_enabled"] = True
                    a["nsfw_method"] = "browser_retry"
                else:
                    log(f"[!] NSFW二次启用失败: {a['email']} | {result.get('error')}")
            all_accounts = []
            with open(accounts_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_accounts.append(json.loads(line))
            nsfw_map = {a["email"]: a for a in need_nsfw}
            for i, acc in enumerate(all_accounts):
                if acc["email"] in nsfw_map:
                    all_accounts[i] = nsfw_map[acc["email"]]
            with open(accounts_file, "w", encoding="utf-8") as f:
                for acc in all_accounts:
                    f.write(json.dumps(acc, ensure_ascii=False) + "\n")

    print_summary()

if __name__ == "__main__":
    main()