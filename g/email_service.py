"""邮箱服务类 - 适配 freemail API."""
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


class EmailService:
    def __init__(
        self,
        worker_domain: Optional[str] = None,
        freemail_token: Optional[str] = None,
        timeout: int = 10,
    ):
        load_dotenv()
        self.worker_domain = worker_domain or os.getenv("WORKER_DOMAIN")
        self.freemail_token = freemail_token or os.getenv("FREEMAIL_TOKEN")
        if not all([self.worker_domain, self.freemail_token]):
            raise ValueError("Missing: WORKER_DOMAIN or FREEMAIL_TOKEN")
        self.base_url = f"https://{self.worker_domain}".rstrip("/")
        self.headers = {"Authorization": f"Bearer {self.freemail_token}"}
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = dict(self.headers)
        extra_headers = kwargs.pop("headers", None)
        if extra_headers:
            headers.update(extra_headers)

        timeout = kwargs.pop("timeout", self.timeout)
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=timeout,
            **kwargs,
        )

        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise RuntimeError(
                f"{method} {path} failed: {response.status_code} - {detail}"
            )

        if not response.content:
            return None

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        try:
            return response.json()
        except ValueError:
            return response.text

    def generate_email(
        self,
        length: Optional[int] = None,
        domain_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if length is not None:
            params["length"] = length
        if domain_index is not None:
            params["domainIndex"] = domain_index
        return self._request("GET", "/api/generate", params=params)

    def create_email(self):
        """创建临时邮箱 GET /api/generate."""
        try:
            result = self.generate_email()
            email = result.get("email")
            return email, email  # 兼容原接口 (jwt, email)
        except Exception as exc:
            print(f"[-] 创建邮箱失败: {exc}")
            return None, None

    def list_mailboxes(
        self,
        limit: int = 100,
        offset: int = 0,
        domain: Optional[str] = None,
        favorite: Optional[bool] = None,
        forward: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if domain:
            params["domain"] = domain
        if favorite is not None:
            params["favorite"] = str(favorite).lower()
        if forward is not None:
            params["forward"] = str(forward).lower()

        data = self._request("GET", "/api/mailboxes", params=params)
        if isinstance(data, dict):
            return data.get("list", [])
        return data if isinstance(data, list) else []

    def list_emails(self, mailbox: str, limit: int = 20) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            "/api/emails",
            params={"mailbox": mailbox, "limit": limit},
        )
        if isinstance(data, dict):
            return data.get("value", [])
        return data if isinstance(data, list) else []

    def get_email_detail(self, email_id: int) -> Dict[str, Any]:
        data = self._request("GET", f"/api/email/{email_id}")
        return data if isinstance(data, dict) else {}

    def get_latest_email_detail(
        self,
        mailbox: str,
        limit: int = 20,
    ) -> Optional[Dict[str, Any]]:
        emails = self.list_emails(mailbox=mailbox, limit=limit)
        if not emails:
            return None
        latest_id = emails[0].get("id")
        if latest_id is None:
            return None
        return self.get_email_detail(int(latest_id))

    def fetch_verification_code(self, email, max_attempts=60):
        """轮询获取验证码 GET /api/emails?mailbox=xxx.

        Grok 验证码格式: XXX-XXX (字母数字混合), 在邮件主题开头, 提交时去掉横杠
        """
        for _ in range(max_attempts):
            try:
                emails_list = self.list_emails(email, limit=20)
                if emails_list:
                    first = emails_list[0]
                    code = first.get("verification_code")
                    if code:
                        return str(code).replace("-", "")
                    subject = first.get("subject", "")
                    match = re.match(
                        r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s",
                        subject,
                        re.IGNORECASE,
                    )
                    if match:
                        return match.group(1).replace("-", "")
            except Exception:
                pass
            time.sleep(1)
        return None

    def delete_email(self, address):
        """删除邮箱 DELETE /api/mailboxes?address=xxx."""
        try:
            result = self._request(
                "DELETE",
                "/api/mailboxes",
                params={"address": address},
            )
            return bool(result and result.get("success"))
        except Exception:
            return False
