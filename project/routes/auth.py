from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import DBIntegrityError, get_db
from ..utils import (
    _send_email_notification,
    _send_sms_to_parent,
    _student_row_by_login,
    login_required,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/test-notification", methods=["GET", "POST"])
@login_required(["warden", "principal"])
def test_notification():
    result = None
    if request.method == "POST":
        test_email = (request.form.get("email") or "").strip()
        test_mobile = (request.form.get("mobile") or "").strip()
        student_name = (request.form.get("student_name") or "Student").strip()

        email_body = (
            f"Dear {student_name},\n\n"
            "Your leave is accepted. (Test notification)\n\n"
            "Regards,\nHostel Administration"
        )
        sms_text = f"Dear Parent, your child {student_name} leave is approved. (Test)"

        email_ok, email_msg = _send_email_notification(test_email, "Leave Approved - Test", email_body)
        sms_ok, sms_msg = _send_sms_to_parent(test_mobile, sms_text)
        result = {"email_ok": email_ok, "email_msg": email_msg, "sms_ok": sms_ok, "sms_msg": sms_msg}
        flash(f"Test result: email={'yes' if email_ok else 'no'}, sms={'yes' if sms_ok else 'no'}")

    return render_template("test_notification.html", result=result)


@auth_bp.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        selected_role = (request.form.get("role") or "").strip().lower()
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if selected_role not in {"student", "caretaker", "warden", "principal", "admin"}:
            flash("Please select a valid role.")
            return render_template("login.html")

        conn = get_db()
        cur = conn.cursor()

        # Student login (reg_no or email)
        if selected_role == "student":
            student = _student_row_by_login(cur, username)
            if not student:
                conn.close()
                flash("Invalid student credentials.")
                return render_template("login.html")
            stored = student["password_hash"]
            fallback_passwords = {student["reg_no"], student["email"] or ""}
            if not stored:
                # first-time fallback password = reg_no or email
                if password in fallback_passwords:
                    cur.execute(
                        "UPDATE students SET password_hash=? WHERE id=?",
                        (generate_password_hash(password), student["id"]),
                    )
                    conn.commit()
                else:
                    conn.close()
                    flash("Invalid student credentials.")
                    return render_template("login.html")
            elif not (check_password_hash(stored, password) or password in fallback_passwords):
                conn.close()
                flash("Invalid student credentials.")
                return render_template("login.html")

            session["user"] = student["reg_no"]
            session["reg_no"] = student["reg_no"]
            session["role"] = "student"
            conn.close()
            return redirect(url_for("student.student_dashboard"))

        # Staff login
        cur.execute("SELECT * FROM staff_users WHERE username=?", (username,))
        staff = cur.fetchone()
        # Keep username lookup case-insensitive for convenience.
        if not staff:
            cur.execute("SELECT * FROM staff_users WHERE LOWER(username)=LOWER(?)", (username,))
            staff = cur.fetchone()

        staff_role = (staff["role"] or "").lower() if staff else ""
        staff_password = (staff["password_hash"] or "") if staff else ""
        staff_auth_ok = False

        if staff:
            if staff_password:
                try:
                    staff_auth_ok = check_password_hash(staff_password, password)
                except ValueError:
                    staff_auth_ok = False

        if staff and staff_role == selected_role and staff_auth_ok:
            session["user"] = staff["username"]
            session["username"] = staff["username"]
            session["role"] = staff_role
            conn.close()
            if staff_role == "caretaker":
                return redirect(url_for("caretaker.caretaker_dashboard"))
            if staff_role == "warden":
                return redirect(url_for("warden.warden_leaves"))
            if staff_role == "principal":
                return redirect(url_for("principal.principal_leaves"))
            if staff_role == "admin":
                return redirect(url_for("admin.admin_tools"))

        conn.close()
        flash("Invalid credentials for selected role.")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.home"))


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    allowed_roles = {"caretaker", "warden", "principal", "admin"}
    if request.method == "POST":
        role = (request.form.get("role") or "").strip().lower()
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if role not in allowed_roles:
            flash("Please select a valid staff role.")
            return render_template("staff_signup.html")
        if not username:
            flash("Username is required.")
            return render_template("staff_signup.html")
        if len(password) < 4:
            flash("Password must be at least 4 characters.")
            return render_template("staff_signup.html")
        if password != confirm_password:
            flash("Password and confirm password do not match.")
            return render_template("staff_signup.html")

        conn = None
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM staff_users WHERE LOWER(username)=LOWER(?)", (username,))
            exists = cur.fetchone()
            if exists:
                flash("Username already exists. Please choose another one.")
                return render_template("staff_signup.html")

            cur.execute(
                "INSERT INTO staff_users(username, password_hash, role) VALUES(?,?,?)",
                (username, generate_password_hash(password), role),
            )
            conn.commit()
            flash("Signup successful. Please login with your new credentials.")
            return redirect(url_for("auth.home"))
        except DBIntegrityError:
            flash("Username already exists. Please choose another one.")
            return render_template("staff_signup.html")
        except Exception:
            flash("Signup is temporarily unavailable. Please contact admin.")
            return render_template("staff_signup.html")
        finally:
            if conn:
                conn.close()

    return render_template("staff_signup.html")

