"""freemail 命令行查询脚本."""
import argparse
import json
import sys
from typing import Any

from g.email_service import EmailService


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def dump_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def print_mailboxes(mailboxes: list[dict[str, Any]]) -> None:
    if not mailboxes:
        print("没有查到邮箱。")
        return

    for mailbox in mailboxes:
        print(f"邮箱: {mailbox.get('address', '-')}")
        print(f"ID: {mailbox.get('id', '-')}")
        print(f"创建时间: {mailbox.get('created_at', '-')}")
        print(f"可登录: {bool(mailbox.get('can_login', 0))}")
        print(f"收藏: {bool(mailbox.get('is_favorite', 0))}")
        print(f"转发到: {mailbox.get('forward_to') or '-'}")
        print("-" * 60)


def print_emails(emails: list[dict[str, Any]]) -> None:
    if not emails:
        print("这个邮箱里还没有邮件。")
        return

    for email in emails:
        print(f"邮件ID: {email.get('id', '-')}")
        print(f"发件人: {email.get('sender', '-')}")
        print(f"主题: {email.get('subject', '-')}")
        print(f"接收时间: {email.get('received_at', '-')}")
        print(f"验证码: {email.get('verification_code') or '-'}")
        print(f"预览: {email.get('preview') or '-'}")
        print("-" * 60)


def print_email_detail(email: dict[str, Any] | None) -> None:
    if not email:
        print("没有查到邮件详情。")
        return

    print(f"邮件ID: {email.get('id', '-')}")
    print(f"发件人: {email.get('sender', '-')}")
    print(f"收件人: {email.get('to_addrs', '-')}")
    print(f"主题: {email.get('subject', '-')}")
    print(f"接收时间: {email.get('received_at', '-')}")
    print(f"验证码: {email.get('verification_code') or '-'}")
    print("纯文本内容:")
    print(email.get("content") or "(空)")
    print()
    print("HTML 内容:")
    print(email.get("html_content") or "(空)")
    download_url = email.get("download")
    if download_url:
        print()
        print(f"原始邮件下载路径: {download_url}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="查询 freemail 邮箱、邮件列表和邮件正文。",
    )
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--json",
        action="store_true",
        help="原样输出 JSON。",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        parents=[common_parser],
        help="生成一个新邮箱",
    )
    generate_parser.add_argument("--length", type=int, default=None, help="本地名前缀长度")
    generate_parser.add_argument(
        "--domain-index",
        type=int,
        default=None,
        help="域名索引，从 0 开始",
    )

    mailboxes_parser = subparsers.add_parser(
        "mailboxes",
        parents=[common_parser],
        help="获取邮箱列表",
    )
    mailboxes_parser.add_argument("--limit", type=int, default=100, help="返回数量")
    mailboxes_parser.add_argument("--offset", type=int, default=0, help="偏移量")
    mailboxes_parser.add_argument("--domain", default=None, help="按域名过滤")

    emails_parser = subparsers.add_parser(
        "emails",
        parents=[common_parser],
        help="获取某个邮箱的邮件列表",
    )
    emails_parser.add_argument("--mailbox", required=True, help="邮箱地址")
    emails_parser.add_argument("--limit", type=int, default=20, help="返回数量")

    email_parser = subparsers.add_parser(
        "email",
        parents=[common_parser],
        help="按邮件 ID 获取正文",
    )
    email_parser.add_argument("--id", required=True, type=int, help="邮件 ID")

    latest_parser = subparsers.add_parser(
        "latest",
        parents=[common_parser],
        help="获取某个邮箱最新一封邮件的正文",
    )
    latest_parser.add_argument("--mailbox", required=True, help="邮箱地址")
    latest_parser.add_argument("--limit", type=int, default=20, help="最多查询多少封")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    service = EmailService()

    try:
        if args.command == "generate":
            result = service.generate_email(
                length=args.length,
                domain_index=args.domain_index,
            )
            if args.json:
                dump_json(result)
            else:
                print(f"新邮箱: {result.get('email', '-')}")
                print(f"过期时间戳: {result.get('expires', '-')}")
            return 0

        if args.command == "mailboxes":
            result = service.list_mailboxes(
                limit=args.limit,
                offset=args.offset,
                domain=args.domain,
            )
            if args.json:
                dump_json(result)
            else:
                print_mailboxes(result)
            return 0

        if args.command == "emails":
            result = service.list_emails(
                mailbox=args.mailbox,
                limit=args.limit,
            )
            if args.json:
                dump_json(result)
            else:
                print_emails(result)
            return 0

        if args.command == "email":
            result = service.get_email_detail(args.id)
            if args.json:
                dump_json(result)
            else:
                print_email_detail(result)
            return 0

        if args.command == "latest":
            result = service.get_latest_email_detail(
                mailbox=args.mailbox,
                limit=args.limit,
            )
            if args.json:
                dump_json(result)
            else:
                print_email_detail(result)
            return 0
    except Exception as exc:
        print(f"执行失败: {exc}")
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
