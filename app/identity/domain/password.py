import hashlib
import hmac
import secrets

# 시연용 보안 수준: 16 MiB, 수십 ms. 파라미터가 저장 문자열에 들어 있어
# 나중에 올려도 옛 해시가 검증된다
_N, _R, _P = 2**14, 8, 1
_SALT_BYTES, _HASH_BYTES = 16, 32
_MAXMEM = 256 * 1024 * 1024
# 저장값에서 읽은 파라미터가 터무니없이 크지 않게 하는 범위
_N_EXPONENTS = range(4, 17)
_R_RANGE, _P_RANGE = range(1, 17), range(1, 5)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=_MAXMEM
    )


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = secrets.token_bytes(_SALT_BYTES) if salt is None else salt
    digest = _scrypt(password, salt, _N, _R, _P, _HASH_BYTES)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """저장값과 맞는지. 형식이 틀린 값(잠금 해시 '!' 등)은 예외 없이 불일치다."""
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        n, r, p = int(n), int(r), int(p)
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if (
            scheme != "scrypt"
            or n not in {2**e for e in _N_EXPONENTS}
            or r not in _R_RANGE
            or p not in _P_RANGE
            or not salt
            or not expected
        ):
            return False
        actual = _scrypt(password, salt, n, r, p, len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)
