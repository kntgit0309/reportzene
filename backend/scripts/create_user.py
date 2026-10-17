"""Create or reset a user.

  PYTHONPATH=. uv run python scripts/create_user.py EMAIL NAME CODE [member|admin]
      asks the password interactively (never pass it on the command line)
  PYTHONPATH=. uv run python scripts/create_user.py EMAIL NAME CODE admin --password-file PATH
      generates a random password and writes it to PATH (chmod 600), for a first deploy over SSH
"""
import getpass
import os
import secrets
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models import User
from app.services.naming import clean_code

MIN_PASSWORD = 8


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    email, name, code = argv[1].strip().lower(), argv[2], clean_code(argv[3], 16)
    role = argv[4] if len(argv) > 4 and not argv[4].startswith("--") else "admin"
    if role not in ("member", "admin"):
        print("Role phải là member hoặc admin")
        return 2
    if "--password-file" in argv:
        path = argv[argv.index("--password-file") + 1]
        password = secrets.token_urlsafe(12)
        with open(path, "w") as fh:
            fh.write(password + "\n")
        os.chmod(path, 0o600)
    else:
        password = getpass.getpass("Mật khẩu: ")
    if len(password) < MIN_PASSWORD:
        print(f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự")
        return 2
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(User(email=email, name=name, code=code, role=role, password_hash=hash_password(password)))
        else:
            user.name, user.code, user.role, user.password_hash, user.is_active = name, code, role, hash_password(password), True
        db.commit()
    print(f"OK: {email} ({role}, mã {code})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
