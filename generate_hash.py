# generate_hash.py — StroyBase (dev utility)
from app.extensions import bcrypt

password = input("Введите пароль: ")
hash = bcrypt.generate_password_hash(password).decode('utf-8')
print(f"Хэш: {hash}")