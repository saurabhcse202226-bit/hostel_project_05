from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import db
from ..models import StaffUser, Student
from ..utils import (
    _send_email_notification,
    _send_sms_to_parent,
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
        custom_message = (request.form.get("message") or "").strip()
        student_name = "Student"

        email_body = (
            f"Dear {student_name},\n\n"
            "Your leave is accepted. (Test notification)\n\n"
            "Regards,\nHostel Administration"
        )
        sms_text = custom_message or f"Dear Parent, your child {student_name} leave is approved. (Test)"

        email_ok, email_msg = _send_email_notification(test_email, "Leave Approved - Test", email_body)
        sms_ok, sms_msg = _send_sms_to_parent(test_mobile, sms_text)

        result = {"email_ok": email_ok, "email_msg": email_msg, "sms_ok": sms_ok, "sms_msg": sms_msg}
        flash(f"Test result: email={'yes' if email_ok else 'no'}, sms={'yes' if sms_ok else 'no'}")
        if not sms_ok:
            flash("SMS provider currently unavailable. This does not affect core leave flow.", "warning")

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

        # ================= STUDENT LOGIN =================
        if selected_role == "student":
            student = Student.query.filter(
                (Student.reg_no == username) | (Student.email == username)
            ).first()

            if not student:
                flash("Invalid student credentials.")
                return render_template("login.html")

            stored = student.password_hash
            fallback_passwords = {student.reg_no, student.email or ""}

            if not stored:
                if password in fallback_passwords:
                    student.password_hash = generate_password_hash(password)
                    db.session.commit()
                else:
                    flash("Invalid student credentials.")
                    return render_template("login.html")

            elif not (check_password_hash(stored, password) or password in fallback_passwords):
                flash("Invalid student credentials.")
                return render_template("login.html")

            session["user"] = student.reg_no
            session["reg_no"] = student.reg_no
            session["role"] = "student"

            return redirect(url_for("student.student_dashboard"))

        # ================= STAFF LOGIN =================
        staff = StaffUser.query.filter(
            (StaffUser.username == username)
        ).first()

        if not staff:
            staff = StaffUser.query.filter(
                db.func.lower(StaffUser.username) == username.lower()
            ).first()

        if staff:
            staff_role = (staff.role or "").lower()
            staff_password = staff.password_hash or ""

            staff_auth_ok = False
            if staff_password:
                try:
                    staff_auth_ok = check_password_hash(staff_password, password)
                except ValueError:
                    staff_auth_ok = False

            if staff_role == selected_role and staff_auth_ok:
                session["user"] = staff.username
                session["username"] = staff.username
                session["role"] = staff_role

                if staff_role == "caretaker":
                    return redirect(url_for("caretaker.caretaker_dashboard"))
                if staff_role == "warden":
                    return redirect(url_for("warden.warden_leaves"))
                if staff_role == "principal":
                    return redirect(url_for("principal.principal_leaves"))
                if staff_role == "admin":
                    return redirect(url_for("admin.admin_tools"))

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

        existing = StaffUser.query.filter(
            db.func.lower(StaffUser.username) == username.lower()
        ).first()

        if existing:
            flash("Username already exists.")
            return render_template("staff_signup.html")

        try:
            new_user = StaffUser(
                username=username,
                password_hash=generate_password_hash(password),
                role=role,
            )
            db.session.add(new_user)
            db.session.commit()

            flash("Signup successful. Please login.")
            return redirect(url_for("auth.home"))

        except Exception:
            db.session.rollback()
            flash("Signup failed. Try again.")

    return render_template("staff_signup.html")


@auth_bp.route("/staff/forgot-password", methods=["GET", "POST"])
def staff_forgot_password():
    allowed_roles = {"caretaker", "warden", "principal", "admin"}

    if request.method == "POST":
        role = (request.form.get("role") or "").strip().lower()
        username = (request.form.get("username") or "").strip()
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if role not in allowed_roles:
            flash("Please select a valid staff role.")
            return render_template("staff_forgot_password.html")

        if not username:
            flash("Username is required.")
            return render_template("staff_forgot_password.html")

        if len(new_password) < 4:
            flash("New password must be at least 4 characters.")
            return render_template("staff_forgot_password.html")

        if new_password != confirm_password:
            flash("New password and confirm password do not match.")
            return render_template("staff_forgot_password.html")

        staff = StaffUser.query.filter(
            db.func.lower(StaffUser.username) == username.lower()
        ).first()
        if not staff:
            flash("Staff user not found.")
            return render_template("staff_forgot_password.html")

        if (staff.role or "").strip().lower() != role:
            flash("Selected role does not match this username.")
            return render_template("staff_forgot_password.html")

        try:
            staff.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash("Password reset successful. Please login.")
            return redirect(url_for("auth.home"))
        except Exception:
            db.session.rollback()
            flash("Password reset failed. Try again.")

    return render_template("staff_forgot_password.html")