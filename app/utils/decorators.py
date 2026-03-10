from flask_login import current_user, login_required
from flask import abort


def role_required(role):
    def decorator(func):
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator
