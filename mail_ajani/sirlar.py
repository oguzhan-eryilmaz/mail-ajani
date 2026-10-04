import keyring
import keyring.errors

from .config import KEYRING_SERVICE


def get_secret(name: str) -> str | None:
    return keyring.get_password(KEYRING_SERVICE, name)


def set_secret(name: str, value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, name, value)


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass
