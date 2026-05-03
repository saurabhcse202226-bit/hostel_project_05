from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from ..database import db
from ..models import AuditLog, StaffUser, Student
from ..utils import login_required

admin_bp = Blueprint("admin", __name__)

_DB_ROW_LIMIT = 100


def _list_db_tables() -> tuple[list[str], str | None]:
    insp = inspect(db.engine)
    dialect = db.engine.dialect.name
    schema: str | None = None
    if dialect == "postgresql":
        schema = "public"
        raw = insp.get_table_names(schema=schema)
    elif dialect == "sqlite":
        raw = [
            name
            for name in insp.get_table_names()
            if not name.startswith("sqlite_")
        ]
    else:
        raw = insp.get_table_names()
    names = sorted(set(raw))
    return names, schema


def _quote_table_for_select(table_name: str, schema: str | None) -> str:
    prep = db.engine.dialect.identifier_preparer
    q = prep.quote(table_name)
    if schema:
        q = f"{prep.quote(schema)}.{q}"
    return q


@admin_bp.route("/admin", methods=["GET", "POST"])
@login_required(["admin"])
def admin_tools():
    if request.method == "POST":
        action = request.form.get("action", "").strip()

        try:
            if action == "reset_student_password":
                reg_no = request.form.get("reg_no", "").strip()

                if not reg_no:
                    flash("Reg No is required.", "error")
                else:
                    student = Student.query.filter_by(reg_no=reg_no).first()

                    if student:
                        student.password_hash = generate_password_hash(reg_no)

                        db.session.add(AuditLog(
                            actor_role="admin",
                            actor_user="admin",
                            action="reset_password",
                            entity="student",
                            entity_id=reg_no,
                            details="Password reset to Reg No"
                        ))

                        db.session.commit()
                        flash("Student password reset successfully.", "success")
                    else:
                        flash("Student not found.", "error")

            elif action == "reset_staff_password":
                username = request.form.get("username", "").strip()
                new_password = request.form.get("new_password", "").strip()

                if not username or not new_password:
                    flash("Username and new password are required.", "error")
                else:
                    staff = StaffUser.query.filter_by(username=username).first()

                    if staff:
                        staff.password_hash = generate_password_hash(new_password)

                        db.session.add(AuditLog(
                            actor_role="admin",
                            actor_user="admin",
                            action="reset_password",
                            entity="staff",
                            entity_id=username,
                            details="Staff password updated"
                        ))

                        db.session.commit()
                        flash("Staff password updated successfully.", "success")
                    else:
                        flash("Staff not found.", "error")

        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "error")

    audit_logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(50).all()

    return render_template("admin_tools.html", audit_logs=audit_logs)


@admin_bp.route("/admin/backup")
@login_required(["admin"])
def admin_backup():
    flash("Backup via file is disabled on PostgreSQL.", "warning")
    return redirect(url_for("admin.admin_tools"))


@admin_bp.route("/admin/restore", methods=["POST"])
@login_required(["admin"])
def admin_restore():
    try:
        db.session.add(AuditLog(
            actor_role="admin",
            actor_user="admin",
            action="restore",
            entity="database",
            entity_id="postgres",
            details="restore_attempt_blocked"
        ))
        db.session.commit()

        flash("Restore via .db file is disabled. Use PostgreSQL tools.", "warning")

    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")

    return redirect(url_for("admin.admin_tools"))


@admin_bp.route("/admin/db-view")
@login_required(["admin"])
def admin_db_view():
    tables, schema = _list_db_tables()
    requested = (request.args.get("table") or "").strip()
    selected_table = requested if requested in tables else (tables[0] if tables else "")

    columns: list[str] = []
    rows: list[dict] = []
    viewer_error = None

    if selected_table:
        try:
            fq = _quote_table_for_select(selected_table, schema)
            stmt = text(f"SELECT * FROM {fq} LIMIT {_DB_ROW_LIMIT}")
            with db.engine.connect() as conn:
                result = conn.execute(stmt)
                columns = list(result.keys())
                rows = [dict(row) for row in result.mappings().all()]
        except Exception as e:
            viewer_error = str(e)

    return render_template(
        "admin_db_view.html",
        selected_table=selected_table,
        columns=columns,
        rows=rows,
        tables=tables,
        viewer_error=viewer_error,
        row_limit=_DB_ROW_LIMIT,
    )