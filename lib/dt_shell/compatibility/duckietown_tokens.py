from dt_authentication import DuckietownToken


def get_id_from_token(s):
    return DuckietownToken.from_string(s).uid
