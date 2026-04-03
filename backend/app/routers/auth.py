import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi import APIRouter, Depends, status
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

#Improvement to auth.py performance:
#Concurrency and async/wait in FastAPI
# https://fastapi.tiangolo.com/async/
#The changes:
# Before: when user logged in or signed up the pwd hashing blcoked the server
# After: the server can handle other requests while the pwd hashing is being done

#create the thread pool executor
executor = ThreadPoolExecutor()

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
    user_id: str


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

#Async definitions:
async def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        await verify_password_async(password, DUMMY_HASH)
        return False
    if not await verify_password_async(password, user.hashed_password):
        return False
    return user

async def hash_password_async(password: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, get_password_hash, password)

async def verify_password_async(plain: str, hashed_password: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, verify_password, plain, hashed_password)

router = APIRouter()


# Post /auth/signup
@router.post("/auth/signup")
async def signup(user_in: CreateUser, db: Session = Depends(get_db)):  # noqa: B008, claude told me to add this
    # TODO: Write code to check if user is already in database
    existing_user = get_user(db, user_in.username)
    if existing_user:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "Username already exists"},
        )

    # After checking if the username isnt a duplicate then I can hash the password they put in
    hashed_pass = await hash_password_async(user_in.password)

    # Then can create the new User
    new_user = User(username=user_in.username, hashed_password=hashed_pass)
    # Add to the user database and commit it
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Response (200 OK) From Project Description
    return {"message": "User Created Successfully", "user_id": new_user.id}


# This portion was created using https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
# Post /auth/login


@router.post("/auth/login")
async def login(user_in: CreateUser, db: Session = Depends(get_db)):  # noqa: B008
    user = await authenticate_user(db, user_in.username, user_in.password)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Invalid credentials"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_in.username}, expires_delta=access_token_expires
    )
    return Token(token=access_token, token_type="bearer", user_id=str(user.id))
