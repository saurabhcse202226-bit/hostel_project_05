import csv
import io
import os
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Iterable

from flask import current_app, make_response, redirect, session, url_for
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from .config import FAST2SMS_API_KEY, SMTP_FROM, SMTP_HOST, SMTP_PASS, SMTP_PORT, SMTP_USER


def login_required(roles: Iterable[str] | None = None):
    """
    Flask decorator for role-based auth.

    Note: blueprint endpoints ke hisaab se `auth.home` ko redirect kiya ja raha hai.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "role" not in session:
                return redirect(url_for("auth.home"))
            if roles is not None and session.get("role") not in set(roles):
                return redirect(url_for("auth.home"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def _save_upload(file, allowed_ext: set[str]) -> str | None:
    if not file or not getattr(file, "filename", ""):
        return None
    filename = secure_filename(file.filename)
    if "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_ext:
        return None
    stamped = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    out_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stamped)
    file.save(out_path)
    return stamped


def _student_row_by_reg(cur, reg_no: str):
    cur.execute("SELECT * FROM students WHERE reg_no=? AND is_deleted=0 AND is_active=1", (reg_no,))
    return cur.fetchone()


def _student_row_by_login(cur, login_id: str):
    cur.execute(
        """
        SELECT * FROM students
        WHERE (reg_no=? OR email=?)
          AND is_deleted=0
          AND is_active=1
        """,
        (login_id, login_id),
    )
    return cur.fetchone()


def _dict_count(cur, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float((value or "").strip() if isinstance(value, str) else value)
    except (TypeError, ValueError):
        return default


def _csv_response(filename: str, headers: list[str], rows: list[list[Any]]):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    response = make_response(stream.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _log_audit(cur, action: str, entity: str, entity_id: Any = "", details: str = "") -> None:
    role = session.get("role")
    user = session.get("user")
    cur.execute(
        "INSERT INTO audit_logs(actor_role, actor_user, action, entity, entity_id, details) VALUES(?,?,?,?,?,?)",
        (role, user, action, entity, str(entity_id or ""), (details or "")[:500]),
    )


def _send_email_notification(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    if not to_email:
        return (False, "missing student email")

    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and SMTP_FROM):
        return (False, "SMTP credentials not configured")

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())

        return (True, "Email sent successfully")
    except Exception as e:
        # Don't raise from helper; UI expects a (ok, msg).
        print("EMAIL ERROR:", e)
        return (False, f"email error: {e}")


def _send_sms_to_parent(mobile: str, message: str) -> tuple[bool, str]:
    raw = (mobile or "").strip()
    digits = "".join([c for c in raw if c.isdigit()])
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        return (False, "invalid parent mobile (need 10 digits)")
    if not FAST2SMS_API_KEY:
        return (False, "FAST2SMS_API_KEY not configured")

    try:
        payload = urllib.parse.urlencode({"route": "q", "message": message, "numbers": digits}).encode()
        req = urllib.request.Request(
            "https://www.fast2sms.com/dev/bulkV2",
            data=payload,
            headers={"authorization": FAST2SMS_API_KEY, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "ignore")
            if resp.status == 200:
                return (True, "sent")
            return (False, f"sms http {resp.status}: {body[:200]}")
    except Exception as e:
        return (False, f"sms error: {type(e).__name__}: {e}")


def _notify_leave_approved(cur, leave_id: int) -> tuple[bool, str, bool, str]:
    cur.execute(
        """
        SELECT l.id, l.from_date, l.to_date, l.total_days, s.name, s.reg_no, s.email, s.father_mobile
        FROM leaves l
        LEFT JOIN students s ON s.reg_no=l.reg_no
        WHERE l.id=?
        """,
        (leave_id,),
    )
    row = cur.fetchone()
    if not row:
        return (False, "leave not found", False, "leave not found")

    student_name = row["name"] or "Student"
    email_text = (
        f"Dear {student_name},\n\n"
        f"Your leave application (ID: {row['id']}) is accepted.\n"
        f"From: {row['from_date']}  To: {row['to_date']}  Days: {row['total_days']}\n\n"
        "Regards,\nHostel Administration"
    )
    sms_text = (
        f"Dear Parent, your child {student_name} (Reg: {row['reg_no']}) leave is approved "
        f"from {row['from_date']} to {row['to_date']}."
    )
    email_ok, email_msg = _send_email_notification(row["email"] or "", "Leave Approved", email_text)
    sms_ok, sms_msg = _send_sms_to_parent((row["father_mobile"] or "").strip(), sms_text)
    return (email_ok, email_msg, sms_ok, sms_msg)

