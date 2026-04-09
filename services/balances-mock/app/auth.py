import os

import dotenv
import requests
from jose import jwt
from jose.exceptions import JWTError

dotenv.load_dotenv()

KEYCLOAK_JWKS_URL = os.getenv('JWKS_URL')
ISSUER = os.getenv('ISSUER_URL')
# AUDIENCE = os.getenv("AUDIENCE")

jwks = requests.get(KEYCLOAK_JWKS_URL).json()


def get_public_key(token):
    headers = jwt.get_unverified_header(token)
    kid = headers['kid']

    for key in jwks['keys']:
        if key['kid'] == kid:
            return key
    raise Exception('Public key not found')


def verify_token(token: str):
    try:
        key = get_public_key(token)
        payload = jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            issuer=ISSUER,
            options={'verify_aud': False}
            # audience=AUDIENCE,
        )
        return payload
    except JWTError as e:
        raise Exception(f'Invalid token: {str(e)}')
