from datetime import timedelta

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

# from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db  # import the database.py
from ..models.user import User
from ..utils import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token

# Notes for documentation, what I'm using to dev:
# Password hashing and security with FastAPI
# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
# FastAPI (SQL Relational Databases)
# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-hero
# More stuff I read for Bigger Apps from FASTAPI
# https://fastapi.tiangolo.com/tutorial/bigger-applications/


password_hash = PasswordHash.recommended()
# For security against timing from FASTAPI doc
DUMMY_HASH = password_hash.hash("dummy")

# Class declerations


class CreateUser(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    token: str
    token_type: str
    user_id: str | int


# for now keep it out
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Helper funcs


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password):
    return password_hash.hash(password)


def get_user(db: Session, username: str):
    existing_user = db.query(User).filter(User.username == username).first()
    if not existing_user:
        return False
    return existing_user


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


app = FastAPI()


# Post /auth/signup
@app.post("/auth/signup")
async def signup(user_in: CreateUser, db: Session = Depends(get_db)):  # noqa: B008, claude told me to add this
    # TODO: Write code to check if user is already in database
    existing_user = get_user(db, user_in.username)
    if existing_user:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "Username already exists"},
        )

    # After checking if the username isnt a duplicate then I can hash the password they put in
    hashed_pass = get_password_hash(user_in.password)

    # Then can create the new User
    new_user = User(username=user_in.username, hashed_password=hashed_pass)
    # Add to the user, no idea if this is correct right now, TODO Look more into
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Response (200 OK) From Project Description
    return {"message": "User Created Successfully", "user_id": new_user.id}


# This portion was created using https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
# Post /auth/login


@app.post("/auth/login")
async def login(user_in: CreateUser, db: Session = Depends(get_db)):  # noqa: B008
    user = authenticate_user(db, user_in.username, user_in.password)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Invalid credentials"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_in.username}, expires_delta=access_token_expires
    )
    return Token(token=access_token, token_type="bearer", user_id=user.id)
