from flask import Flask

from .routes.admin import admin_bp
from .routes.auth import auth_bp
from .routes.caretaker import caretaker_bp
from .routes.principal import principal_bp
from .routes.student import student_bp
from .routes.warden import warden_bp


def register_routes(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(caretaker_bp)
    app.register_blueprint(warden_bp)
    app.register_blueprint(principal_bp)
    app.register_blueprint(admin_bp)


def register_legacy_endpoint_aliases(app: Flask) -> None:
    # Backward-compatible endpoint aliases for templates that still use
    # unqualified endpoint names instead of blueprint-qualified names.
    legacy_endpoints = {
        "student_dashboard": "student.student_dashboard",
        "caretaker_dashboard": "caretaker.caretaker_dashboard",
        "caretaker_rooms": "caretaker.caretaker_rooms",
        "room_students": "caretaker.room_students",
        "floors_visual": "caretaker.floors_visual",
        "rooms_visual": "caretaker.rooms_visual",
        "edit_student": "caretaker.edit_student",
        "delete_student": "caretaker.delete_student",
        "trash": "caretaker.trash",
        "restore": "caretaker.restore",
        "trash_delete": "caretaker.trash_delete",
        "caretaker_complaints": "caretaker.caretaker_complaints",
        "caretaker_complaints_export": "caretaker.caretaker_complaints_export",
        "notices": "caretaker.notices",
        "notices_manage": "caretaker.notices_manage",
        "notice_delete": "caretaker.notice_delete",
        "staff_manage": "caretaker.staff_manage",
        "staff_delete": "caretaker.staff_delete",
        "mess_manage": "caretaker.mess_manage",
        "mess_delete": "caretaker.mess_delete",
        "mess_bills": "caretaker.mess_bills",
        "hostel_fees": "caretaker.hostel_fees",
        "hostel_visitors": "caretaker.hostel_visitors",
        "maintenance_requests": "caretaker.maintenance_requests",
        "hostel_rules": "caretaker.hostel_rules",
        "gate_log": "caretaker.gate_log",
        "hostel_analytics": "caretaker.hostel_analytics",
        "warden_complaints": "warden.warden_complaints",
        "warden_students": "warden.warden_students",
        "warden_leaves": "warden.warden_leaves",
        "warden_leaves_export": "warden.warden_leaves_export",
        "principal_complaints": "principal.principal_complaints",
        "principal_students": "principal.principal_students",
        "principal_leaves": "principal.principal_leaves",
        "principal_leaves_export": "principal.principal_leaves_export",
        "admin_tools": "admin.admin_tools",
        "admin_db_view": "admin.admin_db_view",
        "admin_backup": "admin.admin_backup",
        "admin_restore": "admin.admin_restore",
        "logout": "auth.logout",
    }
    rules_by_endpoint = {rule.endpoint: rule for rule in app.url_map.iter_rules()}
    for alias, actual in legacy_endpoints.items():
        if alias in app.view_functions or actual not in app.view_functions:
            continue
        actual_rule = rules_by_endpoint.get(actual)
        if not actual_rule:
            continue
        methods = sorted(m for m in actual_rule.methods if m not in {"HEAD", "OPTIONS"})
        app.add_url_rule(actual_rule.rule, endpoint=alias, view_func=app.view_functions[actual], methods=methods)

