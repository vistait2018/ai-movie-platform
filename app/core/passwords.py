from pwdlib import PasswordHash

_passwords = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return _passwords.verify(password, encoded)
