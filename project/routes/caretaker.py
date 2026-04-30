import csv
import io
from datetime import datetime
from typing import Any

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from ..database import DBIntegrityError, get_db
from ..utils import _csv_response, _dict_count, _log_audit, _save_upload, _to_float, login_required

caretaker_bp = Blueprint("caretaker", __name__)


@caretaker_bp.route("/caretaker", methods=["GET", "POST"])
@login_required(["caretaker"])
def caretaker_dashboard():
    conn = get_db()
    cur = conn.cursor()
    msg = ""

    if request.method == "POST":
        # Add student
        reg_no = (request.form.get("reg_no") or "").strip()
        name = (request.form.get("name") or "").strip()
        room_id = (request.form.get("room_id") or "").strip()
        bed_no = (request.form.get("bed_no") or "").strip()
        if not reg_no or not name:
            flash("Name and Reg No are required.")
            return redirect(url_for("caretaker.caretaker_dashboard"))
        if not room_id or not bed_no:
            flash("Room and Bed No are required.")
            return redirect(url_for("caretaker.caretaker_dashboard"))

        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        selected_room = cur.fetchone()
        if not selected_room:
            flash("Please select a valid room.")
            conn.close()
            return redirect(url_for("caretaker.caretaker_dashboard"))

        room_label = f"{selected_room['block_name']}-{selected_room['floor_no']}-{selected_room['room_no']}"
        cur.execute("SELECT COUNT(*) FROM students WHERE room_no=? AND is_deleted=0", (room_label,))
        occupied = int(cur.fetchone()[0])
        if occupied >= int(selected_room["total_beds"]):
            flash("Selected room is full.")
            conn.close()
            return redirect(url_for("caretaker.caretaker_dashboard"))

        cur.execute("SELECT 1 FROM students WHERE room_no=? AND bed_no=? AND is_deleted=0", (room_label, bed_no))
        if cur.fetchone():
            flash("This bed number is already occupied in selected room.")
            conn.close()
            return redirect(url_for("caretaker.caretaker_dashboard"))

        filename = _save_upload(request.files.get("image"), {"png", "jpg", "jpeg"})
        password_hash = generate_password_hash(reg_no)  # default password = reg_no

        data: tuple[Any, ...] = (
            name,
            reg_no,
            request.form.get("branch"),
            request.form.get("year"),
            room_label,
            bed_no,
            request.form.get("mobile"),
            request.form.get("email"),
            request.form.get("allot_date"),
            request.form.get("remark"),
            filename,
            request.form.get("address"),
            request.form.get("father_name"),
            request.form.get("father_mobile"),
            request.form.get("fee_status") or "Pending",
            password_hash,
            request.form.get("aadhar_no"),
            request.form.get("blood_group"),
            request.form.get("mess_id") or None,
        )

        try:
            cur.execute(
                """
                INSERT INTO students(name, reg_no, branch, year, room_no, bed_no, mobile, email, allot_date, remark, image, address, father_name, father_mobile, fee_status, password_hash, aadhar_no, blood_group, mess_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                data,
            )
            conn.commit()
            msg = "Student added."
            _log_audit(cur, "create", "student", reg_no, f"room={room_label}, bed={bed_no}")
            conn.commit()
        except DBIntegrityError:
            flash("Reg No already exists.")

    # Filters
    q = (request.args.get("q") or "").strip()
    year = (request.args.get("year") or "").strip()
    room = (request.args.get("room") or "").strip()
    fee = (request.args.get("fee") or "").strip()

    sql = "SELECT * FROM students WHERE is_deleted=0"
    params: list[Any] = []
    if q:
        sql += " AND (name LIKE ? OR reg_no LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if year:
        sql += " AND year=?"
        params.append(year)
    if room:
        sql += " AND room_no=?"
        params.append(room)
    if fee:
        sql += " AND fee_status=?"
        params.append(fee)
    sql += " ORDER BY id DESC"

    cur.execute(sql, params)
    data = cur.fetchall()

    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        """
        SELECT l.*,
               s.name as student_name,
               s.room_no as student_room
        FROM leaves l
        LEFT JOIN students s ON s.reg_no=l.reg_no
        WHERE l.principal_status='Approved'
          AND l.from_date <= ?
          AND l.to_date >= ?
          AND (s.is_deleted=0 OR s.is_deleted IS NULL)
        ORDER BY l.from_date DESC
        """,
        (today, today),
    )
    current_leaves = cur.fetchall()

    cur.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM students s WHERE s.room_no=(r.block_name || '-' || r.floor_no || '-' || r.room_no) AND s.is_deleted=0) as occupied_beds
        FROM rooms r
        ORDER BY r.block_name, r.floor_no, r.room_no
        """,
    )
    all_rooms = cur.fetchall()
    available_rooms = [r for r in all_rooms if int(r["occupied_beds"]) < int(r["total_beds"])]

    # Get all mess
    cur.execute("SELECT * FROM mess WHERE status='Active' ORDER BY mess_name")
    all_mess = cur.fetchall()

    stats = {
        "total_students": _dict_count(cur, "SELECT COUNT(*) FROM students WHERE is_deleted=0"),
        "fee_pending": _dict_count(cur, "SELECT COUNT(*) FROM students WHERE is_deleted=0 AND fee_status='Pending'"),
        "complaints_pending": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE status='Pending'"),
        "leaves_pending": _dict_count(
            cur,
            "SELECT COUNT(*) FROM leaves WHERE warden_status='Pending' OR (warden_status='Approved' AND principal_status='Pending')",
        ),
    }

    conn.close()
    return render_template(
        "caretaker.caretaker_dashboard.html",
        data=data,
        msg=msg,
        stats=stats,
        available_rooms=available_rooms,
        current_leaves=current_leaves,
        all_rooms=all_rooms,
        all_mess=all_mess,
    )


@caretaker_bp.route("/caretaker/rooms", methods=["GET", "POST"])
@login_required(["caretaker"])
def caretaker_rooms():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        block_name = (request.form.get("block_name") or "").strip().upper()
        floor_no = (request.form.get("floor_no") or "").strip()
        room_no = (request.form.get("room_no") or "").strip()
        total_beds = int((request.form.get("total_beds") or "4").strip())

        if not block_name or not floor_no or not room_no:
            flash("Block, floor and room are required.")
            conn.close()
            return redirect(url_for("caretaker.caretaker_rooms"))
        if total_beds < 1 or total_beds > 10:
            flash("Total beds must be between 1 and 10.")
            conn.close()
            return redirect(url_for("caretaker.caretaker_rooms"))

        try:
            cur.execute(
                "INSERT INTO rooms(block_name, floor_no, room_no, total_beds) VALUES(?,?,?,?)",
                (block_name, floor_no, room_no, total_beds),
            )
            conn.commit()
            flash("Room added successfully.")
            _log_audit(cur, "create", "room", f"{block_name}-{floor_no}-{room_no}", f"beds={total_beds}")
            conn.commit()
        except DBIntegrityError:
            flash("This room already exists.")

    cur.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM students s WHERE s.room_no=(r.block_name || '-' || r.floor_no || '-' || r.room_no) AND s.is_deleted=0) as occupied_beds
        FROM rooms r
        ORDER BY r.block_name, r.floor_no, r.room_no
        """
    )
    rooms = cur.fetchall()
    conn.close()
    return render_template("rooms_manage.html", rooms=rooms)


@caretaker_bp.route("/caretaker/rooms/<int:room_id>/students")
@login_required(["caretaker", "warden", "principal"])
def room_students(room_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
    room = cur.fetchone()
    if not room:
        conn.close()
        flash("Room not found.")
        return redirect(url_for("caretaker.caretaker_rooms"))
    room_label = f"{room['block_name']}-{room['floor_no']}-{room['room_no']}"
    cur.execute("SELECT * FROM students WHERE room_no=? AND is_deleted=0 ORDER BY bed_no, name", (room_label,))
    students = cur.fetchall()
    conn.close()
    return render_template("room_detail.html", room=room, room_label=room_label, students=students)


@caretaker_bp.route("/rooms/visual")
@login_required(["caretaker", "warden", "principal"])
def floors_visual():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT floor_no FROM rooms ORDER BY floor_no")
    floors = [r["floor_no"] for r in cur.fetchall()]
    conn.close()
    return render_template("floor.html", floors=floors)


@caretaker_bp.route("/rooms/visual/<floor_no>")
@login_required(["caretaker", "warden", "principal"])
def rooms_visual(floor_no: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM students s WHERE s.room_no=(r.block_name || '-' || r.floor_no || '-' || r.room_no) AND s.is_deleted=0) as occupied_beds
        FROM rooms r
        WHERE r.floor_no=?
        ORDER BY r.block_name, r.room_no
        """,
        (floor_no,),
    )
    rooms = cur.fetchall()
    conn.close()
    return render_template("room.html", rooms=rooms, floor=floor_no)


@caretaker_bp.route("/edit/<int:student_id>", methods=["GET", "POST"])
@login_required(["caretaker"])
def edit_student(student_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id=? AND is_deleted=0", (student_id,))
    s = cur.fetchone()
    if not s:
        conn.close()
        flash("Student not found.")
        return redirect(url_for("caretaker.caretaker_dashboard"))

    cur.execute(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM students s WHERE s.room_no=(r.block_name || '-' || r.floor_no || '-' || r.room_no) AND s.is_deleted=0) as occupied_beds
        FROM rooms r
        ORDER BY r.block_name, r.floor_no, r.room_no
        """
    )
    all_rooms = cur.fetchall()

    if request.method == "POST":
        room_id = (request.form.get("room_id") or "").strip()
        bed_no = (request.form.get("bed_no") or "").strip()
        if not room_id or not bed_no:
            conn.close()
            flash("Room and Bed No are required.")
            return redirect(url_for("caretaker.edit_student", student_id=student_id))

        cur.execute("SELECT * FROM rooms WHERE id=?", (room_id,))
        selected_room = cur.fetchone()
        if not selected_room:
            conn.close()
            flash("Please select a valid admin-created room.")
            return redirect(url_for("caretaker.edit_student", student_id=student_id))

        room_label = f"{selected_room['block_name']}-{selected_room['floor_no']}-{selected_room['room_no']}"
        cur.execute(
            "SELECT COUNT(*) FROM students WHERE room_no=? AND is_deleted=0 AND id<>?",
            (room_label, student_id),
        )
        occupied_excluding_self = int(cur.fetchone()[0])
        if occupied_excluding_self >= int(selected_room["total_beds"]):
            conn.close()
            flash("Selected room is full.")
            return redirect(url_for("caretaker.edit_student", student_id=student_id))

        cur.execute(
            "SELECT 1 FROM students WHERE room_no=? AND bed_no=? AND is_deleted=0 AND id<>?",
            (room_label, bed_no, student_id),
        )
        if cur.fetchone():
            conn.close()
            flash("This bed number is already occupied in selected room.")
            return redirect(url_for("caretaker.edit_student", student_id=student_id))

        cur.execute(
            """
            UPDATE students
            SET name=?, branch=?, year=?, room_no=?, bed_no=?, mobile=?, email=?, remark=?, address=?, father_name=?, father_mobile=?, fee_status=?
            WHERE id=?
            """,
            (
                request.form.get("name"),
                request.form.get("branch"),
                request.form.get("year"),
                room_label,
                bed_no,
                request.form.get("mobile"),
                request.form.get("email"),
                request.form.get("remark"),
                request.form.get("address"),
                request.form.get("father_name"),
                request.form.get("father_mobile"),
                request.form.get("fee_status") or s["fee_status"],
                student_id,
            ),
        )
        conn.commit()
        _log_audit(cur, "update", "student", s["reg_no"], f"room={room_label}, bed={bed_no}")
        conn.commit()
        conn.close()
        flash("Student updated.")
        return redirect(url_for("caretaker.caretaker_dashboard"))

    conn.close()
    return render_template("edit.html", s=s, all_rooms=all_rooms)


@caretaker_bp.route("/delete/<int:student_id>")
@login_required(["caretaker"])
def delete_student(student_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT reg_no FROM students WHERE id=?", (student_id,))
    r = cur.fetchone()
    cur.execute("UPDATE students SET is_deleted=1 WHERE id=?", (student_id,))
    conn.commit()
    _log_audit(cur, "delete", "student", (r["reg_no"] if r else student_id), "soft-delete")
    conn.commit()
    conn.close()
    flash("Moved to trash.")
    return redirect(url_for("caretaker.caretaker_dashboard"))


@caretaker_bp.route("/trash")
@login_required(["caretaker"])
def trash():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE is_deleted=1 ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template("trash.html", data=data)


@caretaker_bp.route("/restore/<int:student_id>")
@login_required(["caretaker"])
def restore(student_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT reg_no FROM students WHERE id=?", (student_id,))
    r = cur.fetchone()
    cur.execute("UPDATE students SET is_deleted=0 WHERE id=?", (student_id,))
    conn.commit()
    _log_audit(cur, "restore", "student", (r["reg_no"] if r else student_id), "")
    conn.commit()
    conn.close()
    flash("Restored.")
    return redirect(url_for("caretaker.trash"))


@caretaker_bp.route("/trash/delete/<int:student_id>")
@login_required(["caretaker"])
def trash_delete(student_id: int):
    """Permanently delete a soft-deleted student."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT reg_no, is_deleted FROM students WHERE id=?", (student_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        flash("Student not found.")
        return redirect(url_for("caretaker.trash"))
    if int(row["is_deleted"] or 0) != 1:
        conn.close()
        flash("Only trash records can be permanently deleted.")
        return redirect(url_for("caretaker.trash"))

    cur.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    _log_audit(cur, "delete_permanent", "student", (row["reg_no"] or student_id), "hard-delete from trash")
    conn.commit()
    conn.close()
    flash("Permanently deleted.")
    return redirect(url_for("caretaker.trash"))


@caretaker_bp.route("/caretaker/complaints", methods=["GET", "POST"])
@login_required(["caretaker"])
def caretaker_complaints():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        complaint_id = int(request.form.get("complaint_id") or "0")
        status = request.form.get("status") or "Pending"
        resolution = (request.form.get("resolution") or "").strip() or None
        cur.execute(
            "UPDATE complaints SET status=?, resolution=?, resolved_by=? WHERE id=?",
            (status, resolution, session["user"], complaint_id),
        )
        conn.commit()
        flash("Complaint updated.")

    cur.execute(
        """
        SELECT c.*, s.name as student_name
        FROM complaints c
        LEFT JOIN students s ON s.reg_no=c.reg_no
        ORDER BY c.id DESC
        """
    )
    complaints = cur.fetchall()
    stats = {
        "total": _dict_count(cur, "SELECT COUNT(*) FROM complaints"),
        "pending": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE status='Pending'"),
        "resolved": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE status='Resolved'"),
        "rejected": _dict_count(cur, "SELECT COUNT(*) FROM complaints WHERE status='Rejected'"),
    }
    conn.close()
    return render_template("complaints_manage.html", complaints=complaints, stats=stats, role="caretaker")


@caretaker_bp.route("/caretaker/complaints/export")
@login_required(["caretaker"])
def caretaker_complaints_export():
    conn = get_db()
    cur = conn.cursor()
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    where = ""
    params: list[Any] = []
    if start and end:
        where = "WHERE date(c.created_at) BETWEEN date(?) AND date(?)"
        params = [start, end]
    cur.execute(
        f"""
        SELECT c.id, c.reg_no, COALESCE(s.name, ''), c.status, c.complaint, COALESCE(c.resolution, ''), COALESCE(c.resolved_by, ''), COALESCE(c.created_at, '')
        FROM complaints c
        LEFT JOIN students s ON s.reg_no=c.reg_no
        {where}
        ORDER BY c.id DESC
        """,
        params,
    )
    rows = [list(r) for r in cur.fetchall()]
    conn.close()
    return _csv_response(
        "complaints_report.csv",
        ["ID", "RegNo", "StudentName", "Status", "Complaint", "Resolution", "ResolvedBy", "CreatedAt"],
        rows,
    )


# ---------------- NOTICES ----------------
@caretaker_bp.route("/notices")
@login_required(["student", "warden", "principal", "caretaker"])
def notices():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notices ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template("notice.html", data=data)


@caretaker_bp.route("/notices/manage", methods=["GET", "POST"])
@login_required(["warden", "principal"])
def notices_manage():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        message = (request.form.get("message") or "").strip()
        attachment = _save_upload(
            request.files.get("attachment"),
            {"pdf", "doc", "docx", "png", "jpg", "jpeg", "xlsx", "xls", "txt"},
        )
        if title and message:
            cur.execute(
                "INSERT INTO notices(title, message, posted_by, attachment) VALUES(?,?,?,?)",
                (title, message, session.get("role"), attachment),
            )
            conn.commit()
            _log_audit(cur, "create", "notice", cur.lastrowid, f"attachment={bool(attachment)}")
            conn.commit()
            flash("Notice posted.")
        else:
            flash("Title and message are required.")

    cur.execute("SELECT * FROM notices ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template("notices_manage.html", data=data)


@caretaker_bp.route("/notices/manage/delete/<int:notice_id>")
@login_required(["warden", "principal"])
def notice_delete(notice_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM notices WHERE id=?", (notice_id,))
    conn.commit()
    _log_audit(cur, "delete", "notice", notice_id, "")
    conn.commit()
    conn.close()
    flash("Notice deleted.")
    return redirect(url_for("caretaker.notices_manage"))


# ────────────── STAFF MODULE (Caretaker & Admin) ──────────────
@caretaker_bp.route("/staff/manage", methods=["GET", "POST"])
@login_required(roles=["caretaker", "admin"])
def staff_manage():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name")
            role = request.form.get("role")
            mobile = request.form.get("mobile")
            email = request.form.get("email")
            address = request.form.get("address")
            aadhar_no = request.form.get("aadhar_no")
            blood_group = request.form.get("blood_group")
            joining_date = request.form.get("joining_date")

            try:
                cur.execute(
                    """INSERT INTO staff_members(name, role, mobile, email, address, aadhar_no, blood_group, joining_date, managed_by)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (name, role, mobile, email, address, aadhar_no, blood_group, joining_date, session.get("username")),
                )
                _log_audit(cur, "create", "staff_member", "", f"Added {name} as {role}")
                conn.commit()
                flash("Staff member added successfully!")
            except Exception as e:
                flash(f"Error: {e}")

        elif action == "update":
            staff_id = request.form.get("staff_id")
            status = request.form.get("status")
            cur.execute("UPDATE staff_members SET status=? WHERE id=?", (status, staff_id))
            _log_audit(cur, "update", "staff_member", staff_id, f"Status changed to {status}")
            conn.commit()
            flash("Staff member updated!")

    cur.execute(
        "SELECT * FROM staff_members WHERE managed_by=? OR managed_by IS NULL ORDER BY created_at DESC",
        (session.get("username"),),
    )
    staff = cur.fetchall()
    conn.close()

    stats = {
        "total": len(staff),
        "active": sum(1 for s in staff if s["status"] == "Active"),
        "inactive": sum(1 for s in staff if s["status"] == "Inactive"),
    }

    return render_template("staff_manage.html", staff=staff, stats=stats)


@caretaker_bp.route("/staff/manage/delete/<int:staff_id>")
@login_required(roles=["caretaker", "admin"])
def staff_delete(staff_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM staff_members WHERE id=?", (staff_id,))
    _log_audit(cur, "delete", "staff_member", staff_id, "Deleted")
    conn.commit()
    conn.close()
    flash("Staff member removed!")
    return redirect(url_for("caretaker.staff_manage"))


# ────────────── MESS MODULE (Caretaker & Warden) ──────────────
@caretaker_bp.route("/mess/manage", methods=["GET", "POST"])
@login_required(roles=["caretaker", "warden"])
def mess_manage():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            mess_name = request.form.get("mess_name")
            location = request.form.get("location")
            contact_person = request.form.get("contact_person")
            contact_mobile = request.form.get("contact_mobile")
            monthly_fee = request.form.get("monthly_fee", 0)
            capacity = request.form.get("capacity", 100)

            try:
                cur.execute(
                    """INSERT INTO mess(mess_name, location, contact_person, contact_mobile, monthly_fee, capacity)
                       VALUES(?,?,?,?,?,?)""",
                    (mess_name, location, contact_person, contact_mobile, float(monthly_fee), int(capacity)),
                )
                _log_audit(cur, "create", "mess", "", f"Added mess: {mess_name}")
                conn.commit()
                flash("Mess added successfully!")
            except Exception as e:
                flash(f"Error: {e}")

        elif action == "update":
            mess_id = request.form.get("mess_id")
            status = request.form.get("status")
            monthly_fee = request.form.get("monthly_fee")
            cur.execute(
                "UPDATE mess SET status=?, monthly_fee=? WHERE id=?",
                (status, float(monthly_fee), mess_id),
            )
            _log_audit(cur, "update", "mess", mess_id, f"Status: {status}, Fee: {monthly_fee}")
            conn.commit()
            flash("Mess updated!")

    cur.execute("SELECT * FROM mess ORDER BY created_at DESC")
    mess_list = cur.fetchall()
    # Convert DB rows to mutable dicts to append computed fields safely.
    mess_data = [dict(m) for m in mess_list]

    # Get mess statistics
    for m in mess_data:
        cur.execute(
            "SELECT COUNT(*) as count FROM students WHERE mess_id=? AND is_deleted=0",
            (m["id"],),
        )
        m["enrolled_students"] = cur.fetchone()["count"]

    conn.close()

    stats = {
        "total_mess": len(mess_data),
        "active": sum(1 for m in mess_data if m["status"] == "Active"),
    }

    return render_template("mess_manage.html", mess_list=mess_data, stats=stats)


@caretaker_bp.route("/mess/manage/delete/<int:mess_id>")
@login_required(roles=["caretaker"])
def mess_delete(mess_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM mess WHERE id=?", (mess_id,))
    _log_audit(cur, "delete", "mess", mess_id, "Deleted")
    conn.commit()
    conn.close()
    flash("Mess deleted!")
    return redirect(url_for("caretaker.mess_manage"))


# ────────────── MESS BILL / HOSTEL CHARGES ──────────────
@caretaker_bp.route("/mess/bills", methods=["GET", "POST"])
@login_required(roles=["student", "caretaker", "warden", "principal"])
def mess_bills():
    """Monthly per-student charges: hostel+maintenance, mess and fine."""
    conn = get_db()
    cur = conn.cursor()
    selected_month = (request.args.get("month") or "").strip() or datetime.now().strftime("%Y-%m")

    if request.method == "POST":
        action = request.form.get("action")
        role = session.get("role")

        if action == "update_charge":
            if role != "warden":
                flash("Only warden can edit monthly charges.")
                conn.close()
                return redirect(url_for("caretaker.mess_bills", month=selected_month))

            student_id = int(request.form.get("student_id") or "0")
            month = (request.form.get("month") or "").strip() or selected_month
            hostel_maintenance = _to_float(request.form.get("hostel_maintenance"), 0.0)
            mess_charge = _to_float(request.form.get("mess_charge"), 0.0)
            fine = _to_float(request.form.get("fine"), 0.0)
            concession = _to_float(request.form.get("concession"), 0.0)
            status = (request.form.get("status") or "Pending").strip() or "Pending"
            note = (request.form.get("note") or "").strip() or None
            total = max(hostel_maintenance + mess_charge + fine - concession, 0.0)
            if student_id and month:
                cur.execute(
                    """
                    INSERT INTO student_monthly_charges(student_id, month, hostel_maintenance, mess_charge, fine, concession, total, status, note)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(student_id, month) DO UPDATE SET
                        hostel_maintenance=excluded.hostel_maintenance,
                        mess_charge=excluded.mess_charge,
                        fine=excluded.fine,
                        concession=excluded.concession,
                        total=excluded.total,
                        status=excluded.status,
                        note=excluded.note,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (student_id, month, hostel_maintenance, mess_charge, fine, concession, total, status, note),
                )
                conn.commit()
                flash("Monthly charge updated.")

        elif action == "bulk_upload":
            # Bulk upload original app.py me tha. Here we keep it simple:
            flash("Bulk upload is not enabled in this modular build.")

        elif action == "apply_month_defaults":
            if role != "warden":
                flash("Only warden can apply month-wise charges.")
                conn.close()
                return redirect(url_for("caretaker.mess_bills", month=selected_month))

            month = (request.form.get("month") or "").strip() or selected_month
            hostel_maintenance = _to_float(request.form.get("hostel_maintenance_default"), 0.0)
            mess_charge_raw = (request.form.get("mess_charge_default") or "").strip()
            use_custom_mess_charge = bool(mess_charge_raw)
            custom_mess_charge = _to_float(mess_charge_raw, 0.0)
            fine = _to_float(request.form.get("fine_default"), 0.0)
            concession = _to_float(request.form.get("concession_default"), 0.0)
            status = (request.form.get("status_default") or "Pending").strip() or "Pending"
            note = (request.form.get("note_default") or "").strip() or None
            overwrite_existing = (request.form.get("overwrite_existing") or "") == "1"

            cur.execute(
                """
                SELECT s.id, COALESCE(m.monthly_fee, 0) as default_mess_fee
                FROM students s
                LEFT JOIN mess m ON s.mess_id=m.id
                WHERE s.is_deleted=0 AND s.is_active=1
                """
            )
            active_students = cur.fetchall()

            cur.execute("SELECT student_id FROM student_monthly_charges WHERE month=?", (month,))
            existing_for_month = {row["student_id"] for row in cur.fetchall()}

            updated_count = 0
            skipped_count = 0
            for student in active_students:
                student_id = int(student["id"])
                if (student_id in existing_for_month) and not overwrite_existing:
                    skipped_count += 1
                    continue

                mess_charge = custom_mess_charge if use_custom_mess_charge else _to_float(student["default_mess_fee"], 0.0)
                total = max(hostel_maintenance + mess_charge + fine - concession, 0.0)
                cur.execute(
                    """
                    INSERT INTO student_monthly_charges(student_id, month, hostel_maintenance, mess_charge, fine, concession, total, status, note)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(student_id, month) DO UPDATE SET
                        hostel_maintenance=excluded.hostel_maintenance,
                        mess_charge=excluded.mess_charge,
                        fine=excluded.fine,
                        concession=excluded.concession,
                        total=excluded.total,
                        status=excluded.status,
                        note=excluded.note,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (student_id, month, hostel_maintenance, mess_charge, fine, concession, total, status, note),
                )
                updated_count += 1

            conn.commit()
            selected_month = month
            flash(f"Month-wise charges applied. Updated: {updated_count}, Skipped: {skipped_count}.")

        conn.close()
        return redirect(url_for("caretaker.mess_bills", month=selected_month))

    # GET: build student list and charges for the month
    role = session.get("role")
    if role == "student":
        cur.execute(
            """
            SELECT s.id, s.name, s.reg_no, s.room_no, s.mess_id, m.mess_name, COALESCE(m.monthly_fee, 0) as default_mess_fee
            FROM students s
            LEFT JOIN mess m ON s.mess_id=m.id
            WHERE s.is_deleted=0 AND s.is_active=1 AND s.reg_no=?
            ORDER BY s.name
            """,
            (session.get("user"),),
        )
    else:
        cur.execute(
            """
            SELECT s.id, s.name, s.reg_no, s.room_no, s.mess_id, m.mess_name, COALESCE(m.monthly_fee, 0) as default_mess_fee
            FROM students s
            LEFT JOIN mess m ON s.mess_id=m.id
            WHERE s.is_deleted=0 AND s.is_active=1
            ORDER BY s.name
            """,
        )

    students = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """
        SELECT student_id, hostel_maintenance, mess_charge, fine, concession, total, status, note
        FROM student_monthly_charges
        WHERE month=?
        """,
        (selected_month,),
    )
    charge_map = {r["student_id"]: dict(r) for r in cur.fetchall()}

    total_due = 0.0
    paid_count = 0
    for s in students:
        c = charge_map.get(s["id"], {})
        hm = _to_float(c.get("hostel_maintenance"), 0.0)
        mess_charge = _to_float(c.get("mess_charge"), _to_float(s.get("default_mess_fee"), 0.0))
        fine = _to_float(c.get("fine"), 0.0)
        concession = _to_float(c.get("concession"), 0.0)
        total = _to_float(c.get("total"), max(hm + mess_charge + fine - concession, 0.0))
        status = c.get("status") or "Pending"
        s["hostel_maintenance"] = hm
        s["mess_charge"] = mess_charge
        s["fine"] = fine
        s["concession"] = concession
        s["total"] = total
        s["bill_status"] = status
        s["note"] = c.get("note") or ""
        total_due += total
        if str(status).lower() == "paid":
            paid_count += 1

    stats = {
        "student_count": len(students),
        "paid_count": paid_count,
        "pending_count": max(len(students) - paid_count, 0),
        "total_due": round(total_due, 2),
    }

    conn.close()
    return render_template("mess_bills.html", students=students, selected_month=selected_month, stats=stats)


# ────────────── HOSTEL FEES / CHARGES ──────────────
@caretaker_bp.route("/hostel/fees", methods=["GET", "POST"])
@login_required(roles=["caretaker", "warden", "principal"])
def hostel_fees():
    """Manage hostel room charges and other fees."""
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        if session.get("role") != "warden":
            flash("Only warden can edit fee master.")
            conn.close()
            return redirect(url_for("caretaker.hostel_fees"))
        action = request.form.get("action")
        if action == "add":
            fee_type = request.form.get("fee_type")
            amount = request.form.get("amount")
            description = request.form.get("description")
            if fee_type and amount:
                cur.execute(
                    """
                    INSERT INTO hostel_fees(fee_type, amount, description)
                    VALUES(?,?,?)
                    """,
                    (fee_type, float(amount), description),
                )
                conn.commit()
                flash("Fee added!")

    cur.execute("SELECT * FROM hostel_fees WHERE is_active=1 ORDER BY fee_type")
    fees = cur.fetchall()
    conn.close()
    return render_template("hostel_fees.html", fees=fees)


# ────────────── VISITOR MANAGEMENT ──────────────
@caretaker_bp.route("/hostel/visitors", methods=["GET", "POST"])
@login_required(roles=["student", "caretaker", "warden", "principal"])
def hostel_visitors():
    """Track hostel visitors."""
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        if session.get("role") not in {"caretaker", "warden"}:
            flash("Only caretaker/warden can log visitors.")
            conn.close()
            return redirect(url_for("caretaker.hostel_visitors"))

        action = request.form.get("action")
        if action == "add":
            student_reg = request.form.get("student_reg")
            visitor_name = request.form.get("visitor_name")
            relation = request.form.get("relation")
            mobile = request.form.get("mobile")
            visit_date = request.form.get("visit_date")
            check_in = request.form.get("check_in")
            check_out = request.form.get("check_out")

            try:
                cur.execute(
                    """
                    INSERT INTO visitors(student_reg, visitor_name, relation, mobile, visit_date, check_in, check_out)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (student_reg, visitor_name, relation, mobile, visit_date, check_in, check_out),
                )
                conn.commit()
                flash("Visitor record added!")
            except Exception as e:
                flash(f"Error: {e}")

    if session.get("role") == "student":
        cur.execute(
            """
            SELECT * FROM visitors
            WHERE student_reg=?
            ORDER BY visit_date DESC, check_in DESC
            LIMIT 100
            """,
            (session.get("user"),),
        )
    else:
        cur.execute(
            """
            SELECT * FROM visitors
            ORDER BY visit_date DESC, check_in DESC
            LIMIT 100
            """
        )

    visitors = cur.fetchall()
    conn.close()
    return render_template("visitors.html", visitors=visitors)


# ────────────── MAINTENANCE REQUESTS ──────────────
@caretaker_bp.route("/hostel/maintenance", methods=["GET", "POST"])
@login_required(roles=["student", "caretaker", "warden", "principal"])
def maintenance_requests():
    """Report and track maintenance issues with controlled status flow."""
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        role = session.get("role")

        if action == "add" and role in ["student", "caretaker"]:
            if role == "student":
                student_reg = session.get("user")
            else:
                student_reg = request.form.get("student_reg", "").strip() or "Caretaker"

            issue = request.form.get("issue")
            location = request.form.get("location")
            priority = request.form.get("priority", "Normal")

            try:
                cur.execute(
                    """
                    INSERT INTO maintenance(student_reg, issue, location, priority, status)
                    VALUES(?,?,?,?,?)
                    """,
                    (student_reg, issue, location, priority, "Raised"),
                )
                conn.commit()
                flash("Maintenance request submitted!")
            except Exception as e:
                flash(f"Error: {e}")

        elif action == "update" and role == "warden":
            maint_id = request.form.get("maint_id")
            status = request.form.get("status")
            remark = request.form.get("remark")
            allowed = {"Under Process", "Forwarded"}
            if status not in allowed:
                flash("Warden can only set Under Process or Forwarded.")
            else:
                cur.execute(
                    """
                    UPDATE maintenance SET status=?, remark=? WHERE id=?
                    """,
                    (status, remark, maint_id),
                )
                conn.commit()
                flash("Request updated!")

        elif action == "update" and role == "principal":
            maint_id = request.form.get("maint_id")
            status = request.form.get("status")
            remark = request.form.get("remark")
            allowed = {"Under Process", "Forwarded", "Resolved"}
            if status not in allowed:
                flash("Invalid status update.")
            else:
                cur.execute(
                    """
                    UPDATE maintenance SET status=?, remark=? WHERE id=?
                    """,
                    (status, remark, maint_id),
                )
                conn.commit()
                flash("Request updated!")

    cur.execute("SELECT * FROM maintenance ORDER BY created_at DESC LIMIT 100")
    requests = cur.fetchall()
    conn.close()
    return render_template("maintenance.html", requests=requests)


# ────────────── HOSTEL RULES & REGULATIONS ──────────────
@caretaker_bp.route("/hostel/rules", methods=["GET", "POST"])
@login_required(roles=["student", "caretaker", "warden", "principal"])
def hostel_rules():
    """Manage hostel rules and regulations."""
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add" and session.get("role") in ["warden", "principal"]:
            rule = request.form.get("rule")
            category = request.form.get("category")
            try:
                cur.execute(
                    """
                    INSERT INTO hostel_rules(rule_text, category, posted_by)
                    VALUES(?,?,?)
                    """,
                    (rule, category, session.get("role")),
                )
                conn.commit()
                flash("Rule added!")
            except Exception as e:
                flash(f"Error: {e}")

    cur.execute("SELECT * FROM hostel_rules WHERE is_active=1 ORDER BY category")
    rules = cur.fetchall()
    conn.close()
    return render_template("hostel_rules.html", rules=rules)


# ────────────── LATE ENTRY / EXIT LOG ──────────────
@caretaker_bp.route("/hostel/gate-log", methods=["GET", "POST"])
@login_required(roles=["student", "caretaker", "warden", "principal"])
def gate_log():
    """Track gate entry/exit (late + normal)."""
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        if session.get("role") not in {"caretaker", "warden"}:
            flash("Only caretaker/warden can log gate entries.")
            conn.close()
            return redirect(url_for("caretaker.gate_log"))

        student_reg = request.form.get("student_reg")
        entry_time = request.form.get("entry_time")
        exit_time = request.form.get("exit_time")
        is_late = request.form.get("is_late") == "1"

        try:
            cur.execute(
                """
                INSERT INTO gate_log(student_reg, entry_time, exit_time, is_late)
                VALUES(?,?,?,?)
                """,
                (student_reg, entry_time, exit_time, is_late),
            )
            conn.commit()
            flash("Gate log entry added!")
        except Exception as e:
            flash(f"Error: {e}")

    where = ""
    params: list[Any] = []
    if session.get("role") == "student":
        where = "WHERE gl.student_reg=?"
        params = [session.get("user")]

    cur.execute(
        f"""
        SELECT gl.*, s.name, s.room_no
        FROM gate_log gl
        LEFT JOIN students s ON gl.student_reg = s.reg_no
        {where}
        ORDER BY gl.created_at DESC
        LIMIT 200
        """,
        params,
    )
    rows = cur.fetchall()
    late_entries = [r for r in rows if int(r["is_late"] or 0) == 1]
    normal_entries = [r for r in rows if int(r["is_late"] or 0) == 0]

    conn.close()
    return render_template("gate_log.html", late_entries=late_entries, normal_entries=normal_entries)


# ────────────── HOSTEL REPORT / ANALYTICS ──────────────
@caretaker_bp.route("/hostel/dashboard-analytics")
@login_required(roles=["principal", "caretaker", "admin"])
def hostel_analytics():
    """Comprehensive hostel analytics dashboard."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN fee_status='Paid' THEN 1 ELSE 0 END) as fee_paid,
            SUM(CASE WHEN fee_status='Pending' THEN 1 ELSE 0 END) as fee_pending
        FROM students WHERE is_deleted=0
        """
    )
    student_stats = cur.fetchone()

    cur.execute(
        """
        SELECT
            COUNT(*) as total_rooms,
            SUM(total_beds) as total_beds,
            (SELECT COUNT(*) FROM students WHERE is_deleted=0) as occupied_beds
        FROM rooms
        """
    )
    room_stats = cur.fetchone()

    cur.execute("SELECT COUNT(*) as total_mess FROM mess WHERE status='Active'")
    mess_row = cur.fetchone()

    cur.execute("SELECT status, COUNT(*) as count FROM complaints GROUP BY status")
    complaint_stats = {row["status"]: row["count"] for row in cur.fetchall()}

    cur.execute("SELECT status, COUNT(*) as count FROM maintenance GROUP BY status")
    maintenance_stats = {row["status"]: row["count"] for row in cur.fetchall()}

    conn.close()
    return render_template(
        "hostel_analytics.html",
        student_stats=student_stats,
        room_stats=room_stats,
        mess_count=mess_row["total_mess"] if mess_row else 0,
        complaint_stats=complaint_stats,
        maintenance_stats=maintenance_stats,
    )

