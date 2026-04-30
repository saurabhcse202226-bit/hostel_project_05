from importlib import import_module
from importlib.metadata import version as package_version


REQUIRED_PACKAGES = {
    "flask": "Flask",
    "flask_sqlalchemy": "Flask-SQLAlchemy",
    "psycopg2": "psycopg2-binary",
    "dotenv": "python-dotenv",
    "gunicorn": "gunicorn",
    "openpyxl": "openpyxl",
}


def main() -> None:
    print("Package health check:\n")
    missing = []

    for module_name, package_name in REQUIRED_PACKAGES.items():
        try:
            import_module(module_name)
            print(f"[OK] {package_name} ({module_name}) version: {package_version(package_name)}")
        except Exception:
            missing.append(package_name)
            print(f"[MISSING] {package_name} ({module_name})")

    if missing:
        print("\nInstall missing packages with:")
        print("pip install -r requirements.txt")
    else:
        print("\nAll required packages are installed.")


if __name__ == "__main__":
    main()
