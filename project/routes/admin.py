from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from ..database import DB_PATH, get_db
from ..utils import _log_audit, login_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin", methods=["GET", "POST"])
@login_required(["admin"])
def admin_tools():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action") or ""
        if action == "reset_student_password":
            reg_no = (request.form.get("reg_no") or "").strip()
            if not reg_no:
                flash("Reg No is required.")
            else:
                cur.execute(
                    "UPDATE students SET password_hash=? WHERE reg_no=?",
                    (generate_password_hash(reg_no), reg_no),
                )
                conn.commit()
                _log_audit(cur, "reset_password", "student", reg_no, "")
                conn.commit()
                flash("Student password reset to Reg No.")

        elif action == "reset_staff_password":
            username = (request.form.get("username") or "").strip()
            new_password = (request.form.get("new_password") or "").strip()
            if not username or not new_password:
                flash("Username and new password are required.")
            else:
                cur.execute(
                    "UPDATE staff_users SET password_hash=? WHERE username=?",
                    (generate_password_hash(new_password), username),
                )
                conn.commit()
                _log_audit(cur, "reset_password", "staff", username, "")
                conn.commit()
                flash("Staff password updated.")

    cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50")
    audit_logs = cur.fetchall()
    conn.close()
    return render_template("admin_tools.html", audit_logs=audit_logs, db_path=DB_PATH)


@admin_bp.route("/admin/backup")
@login_required(["admin"])
def admin_backup():
    flash("File backup is disabled on PostgreSQL. Use Supabase backups/export instead.")
    return redirect(url_for("admin.admin_tools"))


@admin_bp.route("/admin/restore", methods=["POST"])
@login_required(["admin"])
def admin_restore():
    conn = get_db()
    cur = conn.cursor()
    _log_audit(cur, "restore", "database", "postgres", "restore_attempt_blocked_for_postgres")
    conn.commit()
    conn.close()
    flash("DB restore via .db file is disabled on PostgreSQL. Use SQL dump/restore tools.")
    return redirect(url_for("admin.admin_tools"))


@admin_bp.route("/admin/db-view")
@login_required(["admin"])
def admin_db_view():
    selected_table = (request.args.get("table") or "").strip()
    limit_raw = (request.args.get("limit") or "100").strip()
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 100
    limit = max(10, min(limit, 500))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT table_name AS name
        FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE'
        ORDER BY table_name
        """
    )
    table_names = [row["name"] for row in cur.fetchall()]

    table_stats = []
    for table_name in table_names:
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        table_stats.append({"name": table_name, "count": count})

    columns: list[str] = []
    rows = []
    if selected_table in table_names:
        cur.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (selected_table,),
        )
        columns = [col["name"] for col in cur.fetchall()]
        cur.execute(f"SELECT * FROM {selected_table} ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    elif not selected_table and table_names:
        selected_table = table_names[0]
        cur.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (selected_table,),
        )
        columns = [col["name"] for col in cur.fetchall()]
        cur.execute(f"SELECT * FROM {selected_table} ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall()

    conn.close()
    return render_template(
        "admin_db_view.html",
        table_stats=table_stats,
        selected_table=selected_table,
        columns=columns,
        rows=rows,
        limit=limit,
        db_path=DB_PATH,
    )

