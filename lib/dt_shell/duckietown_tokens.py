import json
import os
from typing import cast

import base58

from ecdsa import BadSignatureError, SigningKey, VerifyingKey, NIST192p


class DuckietownToken:
    VERSION = "dt1"

    def __init__(self, payload, signature):
        self.payload = payload
        self.signature = signature

    def as_string(self):
        payload_58 = base58.b58encode(self.payload).decode("utf-8")
        signature_58 = base58.b58encode(self.signature).decode("utf-8")
        return "%s-%s-%s" % (DuckietownToken.VERSION, payload_58, signature_58)

    @staticmethod
    def from_string(s):
        p = s.split("-")
        if len(p) != 3:
            raise ValueError(p)
        if p[0] != DuckietownToken.VERSION:
            raise ValueError(p[0])
        payload_base58 = p[1]
        signature_base58 = p[2]
        payload = base58.b58decode(payload_base58)
        signature = base58.b58decode(signature_base58)
        return DuckietownToken(payload, signature)


private = "key1.pem"
public = "key1-pub.pem"
curve = NIST192p


def get_signing_key() -> SigningKey:
    if not os.path.exists(private):
        print("Creating private key %r" % private)
        sk0 = SigningKey.generate(curve=curve)
        with open(private, "w") as f:
            f.write(sk0.to_pem())

        vk = sk0.get_verifying_key()
        with open(public, "w") as f:
            f.write(vk.to_pem())

    with open(private) as f:
        pem = f.read()
    sk = SigningKey.from_pem(pem)
    return cast(SigningKey, sk)


def get_verify_key():
    key1 = """-----BEGIN PUBLIC KEY-----
MEkwEwYHKoZIzj0CAQYIKoZIzj0DAQEDMgAEQr/8RJmJZT+Bh1YMb1aqc2ao5teE
ixOeCMGTO79Dbvw5dGmHJLYyNPwnKkWayyJS
-----END PUBLIC KEY-----"""
    return VerifyingKey.from_pem(key1)


def create_signed_token(payload):
    sk = get_signing_key()

    def entropy(numbytes):
        s = b"duckietown is a place of relaxed introspection"
        return s[:numbytes]

    signature = sk.sign(payload, entropy=entropy)
    return DuckietownToken(payload, signature)


def verify_token(token):
    vk = get_verify_key()
    return vk.verify(token.signature, token.payload)


class InvalidToken(Exception):
    pass


def get_id_from_token(s):
    """
    Returns a numeric ID from the token, or raises InvalidToken.

    """
    try:
        token = DuckietownToken.from_string(s)
    except ValueError:
        msg = "Invalid token format %r." % s
        raise InvalidToken(msg)
    try:
        data = json.loads(token.payload)
        uid = data["uid"]
        return uid
    except ValueError:
        raise InvalidToken()


SAMPLE_TOKEN = (
    "dt1-9Hfd69b5ythetkCiNG12pKDrL987sLJT6KejWP2Eo5QQ"
    "-43dzqWFnWd8KBa1yev1g3UKnzVxZkkTbfWWn6of92V5Bf8qGV24rZHe6r7sueJNtWF"
)
SAMPLE_TOKEN_UID = -1
SAMPLE_TOKEN_EXP = "2018-10-20"


def tests_private():
    payload = json.dumps({"uid": SAMPLE_TOKEN_UID, "exp": SAMPLE_TOKEN_EXP})
    # generate a token
    token = create_signed_token(payload)
    s = token.as_string()
    print(s)
    assert s == SAMPLE_TOKEN
    token2 = token.from_string(s)

    assert verify_token(token2)


def test1():
    token = DuckietownToken.from_string(SAMPLE_TOKEN)
    assert verify_token(token)
    data = json.loads(token.payload)
    print(data)
    assert data["uid"] == SAMPLE_TOKEN_UID
    assert data["exp"] == SAMPLE_TOKEN_EXP

    seq = SAMPLE_TOKEN[6:8]
    msg_bad = SAMPLE_TOKEN.replace(seq, "XY")
    token = DuckietownToken.from_string(msg_bad)
    try:
        verify_token(token)
    except BadSignatureError:
        pass
    else:
        raise Exception(token)

    assert SAMPLE_TOKEN_UID == get_id_from_token(SAMPLE_TOKEN)

    try:
        get_id_from_token(msg_bad)
    except InvalidToken:
        pass
    else:
        raise Exception()


if __name__ == "__main__":
    if os.path.exists(private):
        tests_private()
    test1()
