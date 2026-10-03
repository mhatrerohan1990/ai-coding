from app import tokens


def test_secret_has_enough_entropy():
    assert len(tokens.new_secret()) >= 22  # >= 128 bits of base64url


def test_format_and_parse_roundtrip():
    invite_id, secret = tokens.new_invite_id(), tokens.new_secret()
    assert tokens.parse(tokens.format_token(invite_id, secret)) == (invite_id, secret)


def test_secrets_and_ids_are_unique():
    assert len({tokens.new_secret() for _ in range(100)}) == 100
    assert len({tokens.new_invite_id() for _ in range(100)}) == 100


def test_verify():
    secret = tokens.new_secret()
    stored = tokens.hash_secret(secret)
    assert tokens.verify(secret, stored)
    assert not tokens.verify(secret + "x", stored)


def test_parse_rejects_malformed():
    for bad in ["", "abc", ".secret", "id.", "a.b.c"]:
        assert tokens.parse(bad) is None
