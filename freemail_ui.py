"""freemail 简单桌面 UI."""
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable, Optional

from g.email_service import EmailService


class FreemailUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Freemail 简单 UI")
        self.geometry("1480x860")
        self.minsize(1180, 700)

        self.service = EmailService()
        self.mailboxes: list[dict[str, Any]] = []
        self.emails: list[dict[str, Any]] = []
        self.selected_mailbox: Optional[str] = None
        self.selected_email_id: Optional[int] = None
        self.pending_mailbox_to_select: Optional[str] = None

        self.status_var = tk.StringVar(value="就绪")
        self.mailbox_limit_var = tk.IntVar(value=50)
        self.email_limit_var = tk.IntVar(value=20)
        self.current_mailbox_var = tk.StringVar(value="")
        self.subject_var = tk.StringVar(value="-")
        self.sender_var = tk.StringVar(value="-")
        self.to_var = tk.StringVar(value="-")
        self.time_var = tk.StringVar(value="-")
        self.code_var = tk.StringVar(value="-")

        self._build_style()
        self._build_ui()
        self.after(200, self.refresh_mailboxes)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("MetaName.TLabel", foreground="#666666")
        style.configure("MetaValue.TLabel", font=("Consolas", 10))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="生成邮箱", command=self.generate_mailbox).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="刷新邮箱", command=self.refresh_mailboxes).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Label(toolbar, text="邮箱数量").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Spinbox(
            toolbar,
            from_=1,
            to=500,
            width=6,
            textvariable=self.mailbox_limit_var,
        ).pack(side=tk.LEFT)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12
        )

        ttk.Button(toolbar, text="刷新邮件", command=self.refresh_emails).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="最新邮件", command=self.load_latest_email).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Label(toolbar, text="邮件数量").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Spinbox(
            toolbar,
            from_=1,
            to=50,
            width=6,
            textvariable=self.email_limit_var,
        ).pack(side=tk.LEFT)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12
        )

        ttk.Button(toolbar, text="复制邮箱", command=self.copy_selected_mailbox).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="复制验证码", command=self.copy_verification_code).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        ttk.Label(toolbar, textvariable=self.current_mailbox_var).pack(
            side=tk.RIGHT, padx=(12, 0)
        )

        main = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        mailbox_frame = ttk.Frame(main, padding=8)
        email_frame = ttk.Frame(main, padding=8)
        detail_frame = ttk.Frame(main, padding=8)
        main.add(mailbox_frame, weight=3)
        main.add(email_frame, weight=4)
        main.add(detail_frame, weight=6)

        self._build_mailbox_panel(mailbox_frame)
        self._build_email_panel(email_frame)
        self._build_detail_panel(detail_frame)

        status = ttk.Label(
            root,
            textvariable=self.status_var,
            anchor="w",
            relief=tk.SUNKEN,
            padding=(8, 6),
        )
        status.pack(fill=tk.X, pady=(10, 0))

    def _build_mailbox_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="邮箱列表", style="Title.TLabel").pack(anchor="w")

        columns = ("address", "created_at")
        self.mailbox_tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            height=20,
        )
        self.mailbox_tree.heading("address", text="邮箱")
        self.mailbox_tree.heading("created_at", text="创建时间")
        self.mailbox_tree.column("address", width=240, anchor="w")
        self.mailbox_tree.column("created_at", width=140, anchor="w")
        self.mailbox_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.mailbox_tree.bind("<<TreeviewSelect>>", self.on_mailbox_select)

        scrollbar = ttk.Scrollbar(
            self.mailbox_tree, orient=tk.VERTICAL, command=self.mailbox_tree.yview
        )
        self.mailbox_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_email_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="邮件列表", style="Title.TLabel").pack(anchor="w")

        columns = ("id", "sender", "subject", "time", "code")
        self.email_tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            height=20,
        )
        self.email_tree.heading("id", text="ID")
        self.email_tree.heading("sender", text="发件人")
        self.email_tree.heading("subject", text="主题")
        self.email_tree.heading("time", text="接收时间")
        self.email_tree.heading("code", text="验证码")

        self.email_tree.column("id", width=70, anchor="center")
        self.email_tree.column("sender", width=150, anchor="w")
        self.email_tree.column("subject", width=240, anchor="w")
        self.email_tree.column("time", width=140, anchor="w")
        self.email_tree.column("code", width=90, anchor="center")
        self.email_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.email_tree.bind("<<TreeviewSelect>>", self.on_email_select)

        scrollbar = ttk.Scrollbar(
            self.email_tree, orient=tk.VERTICAL, command=self.email_tree.yview
        )
        self.email_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_detail_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="邮件正文", style="Title.TLabel").pack(anchor="w")

        meta = ttk.Frame(parent)
        meta.pack(fill=tk.X, pady=(8, 10))
        meta.columnconfigure(1, weight=1)

        self._meta_row(meta, 0, "主题", self.subject_var)
        self._meta_row(meta, 1, "发件人", self.sender_var)
        self._meta_row(meta, 2, "收件人", self.to_var)
        self._meta_row(meta, 3, "时间", self.time_var)
        self._meta_row(meta, 4, "验证码", self.code_var)

        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        text_tab = ttk.Frame(notebook)
        html_tab = ttk.Frame(notebook)
        notebook.add(text_tab, text="纯文本")
        notebook.add(html_tab, text="HTML")

        self.text_content = ScrolledText(
            text_tab,
            wrap=tk.WORD,
            font=("Consolas", 10),
        )
        self.text_content.pack(fill=tk.BOTH, expand=True)

        self.html_content = ScrolledText(
            html_tab,
            wrap=tk.WORD,
            font=("Consolas", 10),
        )
        self.html_content.pack(fill=tk.BOTH, expand=True)

    def _meta_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=f"{label}:", style="MetaName.TLabel").grid(
            row=row, column=0, sticky="nw", padx=(0, 8), pady=2
        )
        ttk.Label(parent, textvariable=variable, style="MetaValue.TLabel").grid(
            row=row, column=1, sticky="nw", pady=2
        )

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def run_task(
        self,
        action: Callable[[], Any],
        *,
        success_message: Optional[str] = None,
        loading_message: str = "处理中...",
        callback: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self.set_status(loading_message)

        def worker() -> None:
            try:
                result = action()
            except Exception as exc:
                self.after(0, lambda: self._handle_task_error(exc))
                return

            def finish() -> None:
                if callback:
                    callback(result)
                self.set_status(success_message or "完成")

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_task_error(self, exc: Exception) -> None:
        self.set_status("执行失败")
        messagebox.showerror("错误", str(exc))

    def populate_mailboxes(self, mailboxes: list[dict[str, Any]]) -> None:
        self.mailboxes = mailboxes
        self.mailbox_tree.delete(*self.mailbox_tree.get_children())

        for mailbox in mailboxes:
            item_id = str(mailbox.get("id", mailbox.get("address", "")))
            self.mailbox_tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(
                    mailbox.get("address", ""),
                    mailbox.get("created_at", ""),
                ),
            )

        if self.pending_mailbox_to_select:
            self.select_mailbox_by_address(self.pending_mailbox_to_select)
            self.pending_mailbox_to_select = None
            return

        if self.selected_mailbox:
            self.select_mailbox_by_address(self.selected_mailbox)

    def populate_emails(self, emails: list[dict[str, Any]]) -> None:
        self.emails = emails
        self.email_tree.delete(*self.email_tree.get_children())

        for email in emails:
            email_id = email.get("id")
            if email_id is None:
                continue
            self.email_tree.insert(
                "",
                tk.END,
                iid=str(email_id),
                values=(
                    email_id,
                    email.get("sender", ""),
                    email.get("subject", ""),
                    email.get("received_at", ""),
                    email.get("verification_code") or "",
                ),
            )

        if emails:
            first_id = str(emails[0].get("id"))
            if first_id:
                self.email_tree.selection_set(first_id)
                self.email_tree.focus(first_id)
                self.load_email_detail(int(first_id))
        else:
            self.clear_email_detail()

    def show_email_detail(self, detail: Optional[dict[str, Any]]) -> None:
        if not detail:
            self.clear_email_detail()
            return

        self.subject_var.set(detail.get("subject") or "-")
        self.sender_var.set(detail.get("sender") or "-")
        self.to_var.set(detail.get("to_addrs") or "-")
        self.time_var.set(detail.get("received_at") or "-")
        self.code_var.set(detail.get("verification_code") or "-")

        self._set_text_widget(self.text_content, detail.get("content") or "")
        self._set_text_widget(self.html_content, detail.get("html_content") or "")

    def _set_text_widget(self, widget: ScrolledText, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content or "(空)")
        widget.configure(state=tk.DISABLED)

    def clear_email_detail(self) -> None:
        self.selected_email_id = None
        self.subject_var.set("-")
        self.sender_var.set("-")
        self.to_var.set("-")
        self.time_var.set("-")
        self.code_var.set("-")
        self._set_text_widget(self.text_content, "")
        self._set_text_widget(self.html_content, "")

    def refresh_mailboxes(self) -> None:
        limit = self.mailbox_limit_var.get()
        self.run_task(
            lambda: self.service.list_mailboxes(limit=limit),
            loading_message="正在获取邮箱列表...",
            success_message="邮箱列表已更新",
            callback=self.populate_mailboxes,
        )

    def generate_mailbox(self) -> None:
        def on_done(result: dict[str, Any]) -> None:
            email = result.get("email")
            if email:
                self.pending_mailbox_to_select = email
            self.refresh_mailboxes()

        self.run_task(
            self.service.generate_email,
            loading_message="正在生成邮箱...",
            success_message="邮箱已生成",
            callback=on_done,
        )

    def refresh_emails(self) -> None:
        if not self.selected_mailbox:
            messagebox.showinfo("提示", "请先在左侧选择一个邮箱。")
            return

        mailbox = self.selected_mailbox
        limit = self.email_limit_var.get()
        self.run_task(
            lambda: self.service.list_emails(mailbox=mailbox, limit=limit),
            loading_message=f"正在获取 {mailbox} 的邮件列表...",
            success_message="邮件列表已更新",
            callback=self.populate_emails,
        )

    def load_latest_email(self) -> None:
        if not self.selected_mailbox:
            messagebox.showinfo("提示", "请先在左侧选择一个邮箱。")
            return

        mailbox = self.selected_mailbox
        limit = self.email_limit_var.get()

        def on_done(detail: Optional[dict[str, Any]]) -> None:
            self.show_email_detail(detail)
            if detail and detail.get("id") is not None:
                email_id = str(detail["id"])
                if self.email_tree.exists(email_id):
                    self.email_tree.selection_set(email_id)
                    self.email_tree.focus(email_id)

        self.run_task(
            lambda: self.service.get_latest_email_detail(mailbox=mailbox, limit=limit),
            loading_message=f"正在获取 {mailbox} 的最新邮件...",
            success_message="最新邮件已加载",
            callback=on_done,
        )

    def load_email_detail(self, email_id: int) -> None:
        self.selected_email_id = email_id
        self.run_task(
            lambda: self.service.get_email_detail(email_id),
            loading_message=f"正在获取邮件 {email_id} 的正文...",
            success_message="邮件正文已加载",
            callback=self.show_email_detail,
        )

    def select_mailbox_by_address(self, address: str) -> None:
        for item_id in self.mailbox_tree.get_children():
            values = self.mailbox_tree.item(item_id, "values")
            if values and values[0] == address:
                self.mailbox_tree.selection_set(item_id)
                self.mailbox_tree.focus(item_id)
                self.mailbox_tree.see(item_id)
                self.on_mailbox_select()
                break

    def on_mailbox_select(self, _event: Optional[tk.Event] = None) -> None:
        selection = self.mailbox_tree.selection()
        if not selection:
            return

        values = self.mailbox_tree.item(selection[0], "values")
        if not values:
            return

        self.selected_mailbox = str(values[0])
        self.current_mailbox_var.set(f"当前邮箱: {self.selected_mailbox}")
        self.refresh_emails()

    def on_email_select(self, _event: Optional[tk.Event] = None) -> None:
        selection = self.email_tree.selection()
        if not selection:
            return

        try:
            email_id = int(selection[0])
        except ValueError:
            return
        self.load_email_detail(email_id)

    def copy_selected_mailbox(self) -> None:
        if not self.selected_mailbox:
            messagebox.showinfo("提示", "请先选择一个邮箱。")
            return
        self.clipboard_clear()
        self.clipboard_append(self.selected_mailbox)
        self.set_status(f"已复制邮箱: {self.selected_mailbox}")

    def copy_verification_code(self) -> None:
        code = self.code_var.get().strip()
        if not code or code == "-":
            messagebox.showinfo("提示", "当前邮件没有验证码。")
            return
        self.clipboard_clear()
        self.clipboard_append(code.replace("-", ""))
        self.set_status(f"已复制验证码: {code}")


def main() -> int:
    app = FreemailUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
