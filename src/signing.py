"""Is this download really from Project Moon Pi? Every release's downloads are signed on the developer's own computer
with a private key that never leaves it (tools/sign_release.py, OpenSSH's "ssh-keygen -Y sign"); each copy of the
app carries the matching public key below. Before an update is installed, its file is checked against its signature
(<file>.sig, published beside it): if anyone else changed or replaced it, even on GitHub, the check fails and the
update isn't used.

Ed25519 (RFC 8032) is checked here in plain Python, so nothing extra needs installing. The same file is in SkyScope
and US Train Tracker. Designed and Created by Project Moon Pi.
"""
import base64
import hashlib

# the release key's public half (the private half: ~/CLAUDE CODE PROJECTS/pmp-release-key, never in a repo)
PUBLIC_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIMii+JaPFjkK9U2XF7AXPzBZZNfUngchSNTVqcprBEpJ"
NAMESPACE = "projectmoonpi-update"


class BadSignature(Exception):
    pass


# --- Ed25519 signature check (RFC 8032, section 5.1.7) -------------------------------------
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _x(y, sign):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P:
        x = x * _I % _P
    if (x * x - xx) % _P:
        raise BadSignature("not a point on the curve")
    if x == 0 and sign:
        raise BadSignature("not a point on the curve")
    return _P - x if (x & 1) != sign else x


def _point(b: bytes):
    if len(b) != 32:
        raise BadSignature("wrong length")
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P:
        raise BadSignature("not a point on the curve")
    x = _x(y, b[31] >> 7)
    return (x, y, 1, x * y % _P)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % _P
    B = (y1 + x1) * (y2 + x2) % _P
    C = 2 * t1 * t2 * _D % _P
    D = 2 * z1 * z2 % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


_BY = 4 * pow(5, _P - 2, _P) % _P
_B = (_x(_BY, 0), _BY, 1, _x(_BY, 0) * _BY % _P)


def ed25519_ok(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64 or len(public) != 32:
        return False
    try:
        R, A = _point(signature[:32]), _point(public)
    except BadSignature:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    left, right = _mul(s, _B), _add(R, _mul(h, A))
    return (left[0] * right[2] - right[0] * left[2]) % _P == 0 and (left[1] * right[2] - right[1] * left[2]) % _P == 0


# --- OpenSSH signatures (ssh-keygen -Y sign: the "SSHSIG" format) -------------------------------
def _strings(blob: bytes):
    """The length-prefixed fields of an SSH blob."""
    out, i = [], 0
    while i < len(blob):
        if i + 4 > len(blob):
            raise BadSignature("damaged signature")
        n = int.from_bytes(blob[i:i + 4], "big")
        if i + 4 + n > len(blob):
            raise BadSignature("damaged signature")
        out.append(blob[i + 4:i + 4 + n])
        i += 4 + n
    return out


def _s(b: bytes) -> bytes:
    return len(b).to_bytes(4, "big") + b


def check_file(path: str, signature_text: str) -> None:
    """Raises BadSignature unless the file at path is signed with the release key (for NAMESPACE)."""
    lines = [ln.strip() for ln in signature_text.strip().splitlines()]
    if not lines or lines[0] != "-----BEGIN SSH SIGNATURE-----" or lines[-1] != "-----END SSH SIGNATURE-----":
        raise BadSignature("not a signature file")
    try:
        blob = base64.b64decode("".join(lines[1:-1]), validate=True)
    except ValueError:
        raise BadSignature("damaged signature") from None
    if blob[:6] != b"SSHSIG" or int.from_bytes(blob[6:10], "big") != 1:
        raise BadSignature("not a signature this app knows")
    public_blob, namespace, _reserved, hash_name, sig_blob = _strings(blob[10:])
    ours = base64.b64decode(PUBLIC_KEY)
    if public_blob != ours:
        raise BadSignature("signed by someone else's key")
    if namespace != NAMESPACE.encode():
        raise BadSignature("a signature for something else")
    if hash_name not in (b"sha512", b"sha256"):
        raise BadSignature("not a signature this app knows")
    kind, sig = _strings(sig_blob)
    if kind != b"ssh-ed25519":
        raise BadSignature("not a signature this app knows")
    h = hashlib.new(hash_name.decode())
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    signed = b"SSHSIG" + _s(namespace) + _s(_reserved) + _s(hash_name) + _s(h.digest())
    key = _strings(ours)[1]
    if not ed25519_ok(key, signed, sig):
        raise BadSignature("the file was changed after it was signed")
