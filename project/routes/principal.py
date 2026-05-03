from typing import Any

from flask import Blueprint, flash, render_template, request, session

from ..database import get_db
from ..utils import _csv_response, _dict_count, _log_audit, _notify_leave_approved, login_required

principal_bp = Blueprint("principal", __name__)


@principal_bp.route("/principal/complaints", methods=["GET", "POST"])
@login_required(["principal"])
def principal_complaints():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        complaint_id = int(request.form.get("complaint_id") or "0")
        action = request.form.get("action") or "pending"
        resolution = (request.form.get("resolution") or "").strip() or None
        status_map = {
            "pending": "Pending",
            "resolved": "Resolved",
            "rejected": "Rejected",
        }
        new_status = status_map.get(action, "Pending")
        cur.execute(
            """
            UPDATE complaints
            SET status=?, resolution=?, resolved_by=?, assigned_to=?
            WHERE id=? AND assigned_to='principal' AND (status='Pending' OR status='Forwarded to Principal')
            """,
            (new_status, resolution, session["user"], "principal", complaint_id),
        )
        if cur.rowcount:
            conn.commit()
            _log_audit(cur, "update", "complaint", complaint_id, f"status={new_status}")
            conn.commit()
            flash("Complaint updated.")
        else:
            flash("Complaint already processed once. Further changes are blocked.")

    cur.execute(
        """
        SELECT c.*, s.name as student_name
        FROM complaints c
        LEFT JOIN students s ON s.reg_no=c.reg_no
        WHERE c.assigned_to='principal' OR c.status='Forwarded to Principal'
        ORDER BY c.id DESC
        """
    )
    complaints = cur.fetchall()
    stats = {
        "total": _dict_count(
            cur,
            "SELECT COUNT(*) FROM complaints WHERE assigned_to='principal' OR status='Forwarded to Principal'",
        ),
        "pending": _dict_count(
            cur,
            "SELECT COUNT(*) FROM complaints WHERE (assigned_to='principal' OR status='Forwarded to Principal') AND status='Pending'",
        ),
        "resolved": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE resolved_by='principal' AND status='Resolved'"),
        "rejected": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE resolved_by='principal' AND status='Rejected'"),
    }
    conn.close()
    return render_template("complaints_manage.html", complaints=complaints, stats=stats, role="principal")


@principal_bp.route("/principal/students")
@login_required(["principal"])
def principal_students():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE is_deleted=0 ORDER BY id DESC")
    students = cur.fetchall()
    conn.close()
    return render_template("students_list.html", data=students, role="principal")


@principal_bp.route("/principal/leaves", methods=["GET", "POST"])
@login_required(["principal"])
def principal_leaves():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        leave_id = int(request.form.get("leave_id") or "0")
        action = request.form.get("action") or ""
        remark = (request.form.get("remark") or "").strip() or None
        new_status = "Approved" if action == "approve" else "Rejected"
        cur.execute(
            "UPDATE leaves SET principal_status=?, principal_remark=? WHERE id=? AND principal_status='Pending' AND warden_status='Approved'",
            (new_status, remark, leave_id),
        )
        if not cur.rowcount:
            flash("Leave decision already taken once. Further changes are blocked.")
        else:
            conn.commit()
            _log_audit(cur, "update", "leave", leave_id, f"principal_status={new_status}")
            conn.commit()
            if new_status == "Approved":
                email_ok, email_msg, sms_ok, sms_msg = _notify_leave_approved(cur, leave_id)
                _log_audit(
                    cur,
                    "notify",
                    "leave",
                    leave_id,
                    f"email={email_ok} ({email_msg}); sms={sms_ok} ({sms_msg})",
                )
                conn.commit()
                flash(f"Leave approved. Email: {'sent' if email_ok else 'failed'}.")
                if not email_ok:
                    flash(email_msg)
                if not sms_ok:
                    flash("SMS provider currently unavailable, but leave approval is completed.", "warning")
            else:
                flash(f"Leave {new_status.lower()}.")

    cur.execute(
        """
        SELECT l.*, s.name as student_name, s.room_no, s.year
        FROM leaves l
        LEFT JOIN students s ON s.reg_no=l.reg_no
        ORDER BY l.id DESC
        """
    )
    leaves = cur.fetchall()
    stats = {
        "total": _dict_count(cur, "SELECT COUNT(*) FROM leaves"),
        "pending": _dict_count(
            cur,
            "SELECT COUNT(*) FROM leaves WHERE warden_status='Approved' AND principal_status='Pending'",
        ),
        "approved": _dict_count(cur, "SELECT COUNT(*) FROM leaves WHERE principal_status='Approved'"),
        "rejected": _dict_count(cur, "SELECT COUNT(*) FROM leaves WHERE principal_status='Rejected'"),
    }
    conn.close()
    return render_template("leaves_manage.html", leaves=leaves, role="principal", stats=stats)


@principal_bp.route("/principal/leaves/export")
@login_required(["principal"])
def principal_leaves_export():
    conn = get_db()
    cur = conn.cursor()
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    where = ""
    params: list[Any] = []
    if start and end:
        where = "WHERE date(l.from_date) >= date(?) AND date(l.to_date) <= date(?)"
        params = [start, end]
    cur.execute(
        f"""
        SELECT l.id, l.reg_no, COALESCE(s.name, ''), l.from_date, l.to_date, l.total_days, l.reason, l.warden_status, l.principal_status, COALESCE(l.principal_remark, '')
        FROM leaves l
        LEFT JOIN students s ON s.reg_no=l.reg_no
        {where}
        ORDER BY l.id DESC
        """,
        params,
    )
    rows = [list(r) for r in cur.fetchall()]
    conn.close()
    return _csv_response(
        "principal_leave_report.csv",
        ["ID", "RegNo", "StudentName", "FromDate", "ToDate", "TotalDays", "Reason", "WardenStatus", "PrincipalStatus", "PrincipalRemark"],
        rows,
    )

