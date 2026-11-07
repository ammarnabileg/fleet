"""Email through the SMTP server set up in the control panel (the company's own mailbox or any SMTP service).

Sending is done by a background job from a queue table (integrations.email_outbox), never inside a request: a slow
or refusing mail server never slows a page, and a message waits until the server accepts it.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

TIMEOUT = 20


class MailError(Exception):
    """The SMTP server could not be reached or refused (the message is safe to show an administrator)."""


class SmtpMailer:
    def __init__(
        self,
        host: str,
        port: int,
        security: str,
        username: str | None,
        password: str | None,
        from_address: str,
        from_name: str | None = None,
    ) -> None:
        self.host, self.port, self.security = host, port, security
        self.username, self.password = username, password
        self.sender = formataddr((from_name or "", from_address))
        self.from_address = from_address

    def _connect(self) -> smtplib.SMTP:
        context = ssl.create_default_context()
        try:
            if self.security == "ssl":
                smtp: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=TIMEOUT, context=context)
            else:
                smtp = smtplib.SMTP(self.host, self.port, timeout=TIMEOUT)
                if self.security == "starttls":
                    smtp.starttls(context=context)
            if self.username:
                smtp.login(self.username, self.password or "")
            return smtp
        except (smtplib.SMTPException, OSError) as exc:
            raise MailError(f"{exc.__class__.__name__}: {exc}"[:300]) from None

    def check(self) -> None:
        """Connects and signs in, sending nothing."""
        smtp = self._connect()
        try:
            smtp.noop()
        finally:
            smtp.quit()

    def send(self, to: list[str], subject: str, body: str, reply_to: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, ", ".join(to), subject
        msg["Message-ID"] = make_msgid(domain=self.from_address.split("@")[-1])
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        smtp = self._connect()
        try:
            smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise MailError(f"{exc.__class__.__name__}: {exc}"[:300]) from None
        finally:
            try:
                smtp.quit()
            except (smtplib.SMTPException, OSError):
                pass
