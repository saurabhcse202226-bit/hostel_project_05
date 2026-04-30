"""Application SQLAlchemy models.

Importing this module registers all model metadata on the shared `db` instance.
"""

from sqlalchemy import UniqueConstraint

from .database import db


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text)
    reg_no = db.Column(db.Text, unique=True)
    branch = db.Column(db.Text)
    year = db.Column(db.Text)
    room_no = db.Column(db.Text)
    bed_no = db.Column(db.Text)
    mobile = db.Column(db.Text)
    email = db.Column(db.Text)
    allot_date = db.Column(db.Text)
    remark = db.Column(db.Text)
    image = db.Column(db.Text)
    address = db.Column(db.Text)
    father_name = db.Column(db.Text)
    father_mobile = db.Column(db.Text)
    fee_status = db.Column(db.Text, default="Pending", server_default="Pending")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
    password_hash = db.Column(db.Text)
    is_deleted = db.Column(db.Integer, default=0, server_default="0")
    is_active = db.Column(db.Integer, default=1, server_default="1")
    aadhar_no = db.Column(db.Text)
    blood_group = db.Column(db.Text)
    mess_id = db.Column(db.Integer)


class StaffUser(db.Model):
    __tablename__ = "staff_users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.Text, unique=True)
    password_hash = db.Column(db.Text)
    role = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class Leave(db.Model):
    __tablename__ = "leaves"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reg_no = db.Column(db.Text)
    reason = db.Column(db.Text)
    from_date = db.Column(db.Text)
    to_date = db.Column(db.Text)
    total_days = db.Column(db.Integer)
    proof = db.Column(db.Text)
    warden_status = db.Column(db.Text)
    principal_status = db.Column(db.Text)
    warden_remark = db.Column(db.Text)
    principal_remark = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class Complaint(db.Model):
    __tablename__ = "complaints"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reg_no = db.Column(db.Text)
    complaint = db.Column(db.Text)
    media = db.Column(db.Text)
    status = db.Column(db.Text)
    resolution = db.Column(db.Text)
    resolved_by = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
    assigned_to = db.Column(db.Text, default="warden", server_default="warden")


class Notice(db.Model):
    __tablename__ = "notices"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.Text)
    message = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
    posted_by = db.Column(db.Text)
    attachment = db.Column(db.Text)


class Room(db.Model):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("block_name", "floor_no", "room_no", name="uq_rooms_block_floor_room"),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    block_name = db.Column(db.Text)
    floor_no = db.Column(db.Text)
    room_no = db.Column(db.Text)
    total_beds = db.Column(db.Integer, default=4, server_default="4")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class MessBill(db.Model):
    __tablename__ = "mess_bills"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer)
    month = db.Column(db.Text)
    amount = db.Column(db.Float)
    status = db.Column(db.Text, default="Pending", server_default="Pending")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class StudentMonthlyCharge(db.Model):
    __tablename__ = "student_monthly_charges"
    __table_args__ = (UniqueConstraint("student_id", "month", name="uq_student_monthly_charges_student_month"),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Text, nullable=False)
    hostel_maintenance = db.Column(db.Float, default=0, server_default="0")
    mess_charge = db.Column(db.Float, default=0, server_default="0")
    fine = db.Column(db.Float, default=0, server_default="0")
    total = db.Column(db.Float, default=0, server_default="0")
    status = db.Column(db.Text, default="Pending", server_default="Pending")
    note = db.Column(db.Text)
    source_file = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
    concession = db.Column(db.Float, default=0, server_default="0")


class HostelFee(db.Model):
    __tablename__ = "hostel_fees"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fee_type = db.Column(db.Text, unique=True)
    amount = db.Column(db.Float)
    description = db.Column(db.Text)
    is_active = db.Column(db.Integer, default=1, server_default="1")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class Visitor(db.Model):
    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_reg = db.Column(db.Text)
    visitor_name = db.Column(db.Text)
    relation = db.Column(db.Text)
    mobile = db.Column(db.Text)
    visit_date = db.Column(db.Text)
    check_in = db.Column(db.Text)
    check_out = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class Maintenance(db.Model):
    __tablename__ = "maintenance"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_reg = db.Column(db.Text)
    issue = db.Column(db.Text)
    location = db.Column(db.Text)
    priority = db.Column(db.Text, default="Normal", server_default="Normal")
    status = db.Column(db.Text, default="Pending", server_default="Pending")
    remark = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.Text)
    content = db.Column(db.Text)
    priority = db.Column(db.Text, default="Normal", server_default="Normal")
    target_audience = db.Column(db.Text, default="All", server_default="All")
    posted_by = db.Column(db.Text)
    is_active = db.Column(db.Integer, default=1, server_default="1")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class RoomInspection(db.Model):
    __tablename__ = "room_inspection"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    room_id = db.Column(db.Integer)
    inspection_date = db.Column(db.Text)
    cleanliness_score = db.Column(db.Integer)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class HostelRule(db.Model):
    __tablename__ = "hostel_rules"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rule_text = db.Column(db.Text)
    category = db.Column(db.Text)
    is_active = db.Column(db.Integer, default=1, server_default="1")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
    posted_by = db.Column(db.Text)


class GateLog(db.Model):
    __tablename__ = "gate_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_reg = db.Column(db.Text)
    entry_time = db.Column(db.Text)
    exit_time = db.Column(db.Text)
    is_late = db.Column(db.Integer, default=0, server_default="0")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class Mess(db.Model):
    __tablename__ = "mess"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mess_name = db.Column(db.Text, unique=True)
    location = db.Column(db.Text)
    contact_person = db.Column(db.Text)
    contact_mobile = db.Column(db.Text)
    monthly_fee = db.Column(db.Float, default=0, server_default="0")
    capacity = db.Column(db.Integer, default=100, server_default="100")
    status = db.Column(db.Text, default="Active", server_default="Active")
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class StaffMember(db.Model):
    __tablename__ = "staff_members"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False)
    mobile = db.Column(db.Text)
    email = db.Column(db.Text)
    address = db.Column(db.Text)
    aadhar_no = db.Column(db.Text)
    blood_group = db.Column(db.Text)
    joining_date = db.Column(db.Text)
    status = db.Column(db.Text, default="Active", server_default="Active")
    managed_by = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    actor_role = db.Column(db.Text)
    actor_user = db.Column(db.Text)
    action = db.Column(db.Text)
    entity = db.Column(db.Text)
    entity_id = db.Column(db.Text)
    details = db.Column(db.Text)
    created_at = db.Column(db.Text, server_default=db.text("CURRENT_TIMESTAMP"))
