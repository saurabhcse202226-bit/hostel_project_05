from typing import Any

from flask import Blueprint, flash, render_template, request, session

from ..database import get_db
from ..utils import _csv_response, _dict_count, _log_audit, login_required

warden_bp = Blueprint("warden", __name__)


@warden_bp.route("/warden/complaints", methods=["GET", "POST"])
@login_required(["warden"])
def warden_complaints():
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
            "forward": "Forwarded to Principal",
        }
        new_status = status_map.get(action, "Pending")
        assigned_to = "principal" if action == "forward" else "warden"
        cur.execute(
            """
            UPDATE complaints
            SET status=?, resolution=?, resolved_by=?, assigned_to=?
            WHERE id=? AND assigned_to='warden' AND status='Pending'
            """,
            (new_status, resolution, session["user"], assigned_to, complaint_id),
        )
        if cur.rowcount:
            conn.commit()
            _log_audit(cur, "update", "complaint", complaint_id, f"status={new_status}, assigned_to={assigned_to}")
            conn.commit()
            flash("Complaint updated.")
        else:
            flash("Complaint already processed once. Further changes are blocked.")

    cur.execute(
        """
        SELECT c.*, s.name as student_name
        FROM complaints c
        LEFT JOIN students s ON s.reg_no=c.reg_no
        WHERE c.assigned_to='warden' OR c.status='Forwarded to Principal'
        ORDER BY c.id DESC
        """
    )
    complaints = cur.fetchall()
    stats = {
        "total": _dict_count(cur, "SELECT COUNT(*) FROM complaints"),
        "pending": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE assigned_to='warden' AND status='Pending'"),
        "resolved": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE resolved_by='warden' AND status='Resolved'"),
        "rejected": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE resolved_by='warden' AND status='Rejected'"),
    }
    conn.close()
    return render_template("complaints_manage.html", complaints=complaints, stats=stats, role="warden")


@warden_bp.route("/warden/students")
@login_required(["warden"])
def warden_students():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE is_deleted=0 ORDER BY id DESC")
    students = cur.fetchall()
    conn.close()
    return render_template("students_list.html", data=students, role="warden")


@warden_bp.route("/warden/leaves", methods=["GET", "POST"])
@login_required(["warden"])
def warden_leaves():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        leave_id = int(request.form.get("leave_id") or "0")
        action = request.form.get("action") or ""
        remark = (request.form.get("remark") or "").strip() or None
        new_status = "Approved" if action == "approve" else "Rejected"
        cur.execute(
            "UPDATE leaves SET warden_status=?, warden_remark=? WHERE id=? AND warden_status='Pending'",
            (new_status, remark, leave_id),
        )
        if cur.rowcount:
            conn.commit()
            _log_audit(cur, "update", "leave", leave_id, f"warden_status={new_status}")
            conn.commit()
            flash(f"Leave {new_status.lower()}.")
        else:
            flash("Leave decision already taken once. Further changes are blocked.")

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
        "pending": _dict_count(cur, "SELECT COUNT(*) FROM leaves WHERE warden_status='Pending'"),
        "approved": _dict_count(cur, "SELECT COUNT(*) FROM leaves WHERE warden_status='Approved'"),
        "rejected": _dict_count(cur, "SELECT COUNT(*) FROM leaves WHERE warden_status='Rejected'"),
    }
    conn.close()
    return render_template("leaves_manage.html", leaves=leaves, role="warden", stats=stats)


@warden_bp.route("/warden/leaves/export")
@login_required(["warden"])
def warden_leaves_export():
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
        SELECT l.id, l.reg_no, COALESCE(s.name, ''), l.from_date, l.to_date, l.total_days, l.reason, l.warden_status, COALESCE(l.warden_remark, ''), l.principal_status
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
        "warden_leave_report.csv",
        ["ID", "RegNo", "StudentName", "FromDate", "ToDate", "TotalDays", "Reason", "WardenStatus", "WardenRemark", "PrincipalStatus"],
        rows,
    )

