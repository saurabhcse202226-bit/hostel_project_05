from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import get_db
from ..utils import _save_upload, _student_row_by_reg, login_required

student_bp = Blueprint("student", __name__)


@student_bp.route("/student", methods=["GET", "POST"])
@login_required(["student"])
def student_dashboard():
    reg_no = session["user"]
    msg = ""

    conn = get_db()
    cur = conn.cursor()
    student = _student_row_by_reg(cur, reg_no)
    if not student:
        conn.close()
        session.clear()
        return redirect(url_for("auth.home"))

    # Apply leave
    if request.method == "POST" and request.form.get("type") == "leave":
        reason = (request.form.get("reason") or "").strip()
        from_date = request.form.get("from") or ""
        to_date = request.form.get("to") or ""
        try:
            d1 = datetime.strptime(from_date, "%Y-%m-%d")
            d2 = datetime.strptime(to_date, "%Y-%m-%d")
            if d2 < d1:
                raise ValueError("to_date before from_date")
            total_days = (d2 - d1).days + 1
        except Exception:
            conn.close()
            flash("Please provide valid From/To dates.")
            return redirect(url_for("student.student_dashboard"))

        proof_name = _save_upload(request.files.get("proof"), {"png", "jpg", "jpeg", "pdf"})

        cur.execute(
            """
            INSERT INTO leaves(reg_no, reason, from_date, to_date, total_days, proof, warden_status, principal_status, warden_remark, principal_remark)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (reg_no, reason, from_date, to_date, total_days, proof_name, "Pending", "Pending", None, None),
        )
        conn.commit()
        msg = "Leave applied."

    # Submit complaint
    if request.method == "POST" and request.form.get("type") == "comp":
        complaint = (request.form.get("msg") or "").strip()
        media_name = _save_upload(
            request.files.get("media"),
            {"png", "jpg", "jpeg", "mp4", "webm", "mp3", "wav", "aac", "m4a", "pdf"},
        )
        cur.execute(
            "INSERT INTO complaints(reg_no, complaint, media, status, resolution, resolved_by, assigned_to) VALUES(?,?,?,?,?,?,?)",
            (reg_no, complaint, media_name, "Pending", None, None, "warden"),
        )
        conn.commit()
        msg = "Complaint submitted."

    # Change student password
    if request.method == "POST" and request.form.get("type") == "pwd":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        fallback_passwords = {student["reg_no"], student["email"] or ""}

        if new_password != confirm_password:
            conn.close()
            flash("New password and confirm password do not match.")
            return redirect(url_for("student.student_dashboard"))
        if len(new_password) < 6:
            conn.close()
            flash("New password must be at least 6 characters.")
            return redirect(url_for("student.student_dashboard"))

        current_ok = False
        if student["password_hash"] and check_password_hash(student["password_hash"], current_password):
            current_ok = True
        if current_password in fallback_passwords:
            current_ok = True

        if not current_ok:
            conn.close()
            flash("Current password is incorrect.")
            return redirect(url_for("student.student_dashboard"))

        cur.execute(
            "UPDATE students SET password_hash=? WHERE id=?",
            (generate_password_hash(new_password), student["id"]),
        )
        conn.commit()
        msg = "Password updated successfully."

    cur.execute("SELECT fee_status FROM students WHERE reg_no=?", (reg_no,))
    fee_status = (cur.fetchone() or {"fee_status": "Pending"})["fee_status"]

    cur.execute(
        "SELECT * FROM leaves WHERE reg_no=? ORDER BY id DESC LIMIT 10",
        (reg_no,),
    )
    leaves = cur.fetchall()

    cur.execute(
        "SELECT * FROM complaints WHERE reg_no=? ORDER BY id DESC LIMIT 10",
        (reg_no,),
    )
    complaints = cur.fetchall()

    cur.execute("SELECT * FROM notices ORDER BY id DESC LIMIT 5")
    latest_notices = cur.fetchall()

    conn.close()
    return render_template(
        "student.html",
        student=student,
        fee_status=fee_status,
        msg=msg,
        leaves=leaves,
        complaints=complaints,
        latest_notices=latest_notices,
    )

