from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from ..database import db
from ..models import AuditLog, StaffUser, Student
from ..utils import login_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin", methods=["GET", "POST"])
@login_required(["admin"])
def admin_tools():
    if request.method == "POST":
        action = request.form.get("action") or ""

        if action == "reset_student_password":
            reg_no = (request.form.get("reg_no") or "").strip()

            if not reg_no:
                flash("Reg No is required.")
            else:
                student = Student.query.filter_by(reg_no=reg_no).first()

                if student:
                    student.password_hash = generate_password_hash(reg_no)
                    db.session.commit()

                    db.session.add(
                        AuditLog(
                            actor_role="admin",
                            actor_user="admin",
                            action="reset_password",
                            entity="student",
                            entity_id=reg_no,
                            details="",
                        )
                    )
                    db.session.commit()

                    flash("Student password reset to Reg No.")
                else:
                    flash("Student not found.")

        elif action == "reset_staff_password":
            username = (request.form.get("username") or "").strip()
            new_password = (request.form.get("new_password") or "").strip()

            if not username or not new_password:
                flash("Username and new password are required.")
            else:
                staff = StaffUser.query.filter_by(username=username).first()

                if staff:
                    staff.password_hash = generate_password_hash(new_password)
                    db.session.commit()

                    db.session.add(
                        AuditLog(
                            actor_role="admin",
                            actor_user="admin",
                            action="reset_password",
                            entity="staff",
                            entity_id=username,
                            details="",
                        )
                    )
                    db.session.commit()

                    flash("Staff password updated.")
                else:
                    flash("Staff not found.")

    audit_logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(50).all()

    return render_template("admin_tools.html", audit_logs=audit_logs)


@admin_bp.route("/admin/backup")
@login_required(["admin"])
def admin_backup():
    flash("Backup via file is disabled on PostgreSQL.")
    return redirect(url_for("admin.admin_tools"))


@admin_bp.route("/admin/restore", methods=["POST"])
@login_required(["admin"])
def admin_restore():
    db.session.add(
        AuditLog(
            actor_role="admin",
            actor_user="admin",
            action="restore",
            entity="database",
            entity_id="postgres",
            details="restore_attempt_blocked",
        )
    )
    db.session.commit()

    flash("Restore via .db file is disabled. Use PostgreSQL tools.")
    return redirect(url_for("admin.admin_tools"))


@admin_bp.route("/admin/db-view")
@login_required(["admin"])
def admin_db_view():
    # Simple version (no raw SQL)
    tables = [
        "students",
        "staff_users",
        "audit_logs",
    ]

    selected_table = request.args.get("table") or "students"

    data = []
    if selected_table == "students":
        data = Student.query.limit(100).all()
    elif selected_table == "staff_users":
        data = StaffUser.query.limit(100).all()
    elif selected_table == "audit_logs":
        data = AuditLog.query.order_by(AuditLog.id.desc()).limit(100).all()

    return render_template(
        "admin_db_view.html",
        selected_table=selected_table,
        rows=data,
        tables=tables,
    )