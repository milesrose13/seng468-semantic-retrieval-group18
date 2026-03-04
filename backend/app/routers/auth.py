import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db  # import the database.py
from ..models.user import User
from ..utils import create_access_token

# Notes for documentation, what I'm using to dev:
# Password hashing and security with FastAPI
# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
# FastAPI (SQL Relational Databases)
# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-hero
# More stuff I read for Bigger Apps from FASTAPI
# https://fastapi.tiangolo.com/tutorial/bigger-applications/


password_hash = PasswordHash.recommended()
#For security against timing from FASTAPI doc
DUMMY_HASH = password_hash.hash("dummy")


class CreateUser(BaseModel):
    username: str
    password: str
    
class SignupResponse(BaseModel):
    message: str  # User Created Successfully
    user_id: int | str  # STR for UUID or int

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password):
    return password_hash.hash(password)

def get_user(db: Session, username: str):
    existing_user = db.query(User).filter(User.username == username).first()
    if not existing_user:
        return False
    return existing_user
    
def authenticate_user(db: Session,username:str,password:str):
    user = get_user(db, username)
    if not user:
        verify_password(password,DUMMY_HASH)
        return False
    if not verify_password(password,user.hashed_password):
        return False
    return user

app = FastAPI()

#Post /auth/signup 
@app.post("/auth/signup")
async def signup(user_in: CreateUser, db: Session = Depends(get_db)):  # noqa: B008, claude told me to add this
    # TODO: Write code to check if user is already in database
    existing_user = db.query(User).filter(User.username == user_in.username).first()
    if existing_user:
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail="Username Already Exists"
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


#This portion was created using https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
#Post /auth/login

@app.post("/auth/login")
async def login(user_in: CreateUser, db: Session = Depends(get_db)): #noqa: B008
    #TODO: Request "username", "Password"
    #TODO: Response 200 OK token and user_id
    #TODO: Error 401 Unauthorized "error: Invald Credentials"
    return 