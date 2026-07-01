# -*- coding: utf-8 -*-
"""邮件发送服务。"""
import asyncio
import html
import socket
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings
from app.utils.exceptions import AppException


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


def _send_message(message: EmailMessage) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        raise AppException("邮件服务未配置", status_code=500)

    smtp = None
    try:
        if settings.SMTP_USE_SSL:
            smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        else:
            smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
        smtp.send_message(message)
    except (OSError, smtplib.SMTPException, socket.timeout) as exc:
        raise AppException(
            "邮件发送失败，请检查 SMTP_HOST / SMTP_PORT / SMTP_USE_TLS / SMTP_USE_SSL 配置",
            status_code=502,
        ) from exc
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except smtplib.SMTPException:
                pass


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    """发送找回密码邮件。"""
    if not _smtp_configured():
        raise AppException("邮件服务未配置", status_code=500)

    safe_url = html.escape(reset_url, quote=True)
    message = EmailMessage()
    message["Subject"] = "重置你的 EMIYA 密码"
    message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL or ""))
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "你正在重置 EMIYA 账号密码。",
                "",
                "请在 30 分钟内打开下面的链接完成重置：",
                reset_url,
                "",
                "如果这不是你本人操作，可以忽略这封邮件。",
            ]
        )
    )
    message.add_alternative(
        f"""
        <html>
          <body>
            <p>你正在重置 EMIYA 账号密码。</p>
            <p><a href="{safe_url}">点击这里重置密码</a></p>
            <p>此链接 30 分钟内有效，且只能使用一次。</p>
            <p>如果这不是你本人操作，可以忽略这封邮件。</p>
          </body>
        </html>
        """,
        subtype="html",
    )

    await asyncio.to_thread(_send_message, message)
