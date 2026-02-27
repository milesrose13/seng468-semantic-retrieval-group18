from fastapi import Depends, FastAPI
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db  #import the database.py
from ..models.user import User

#Notes for documentation, what I'm using to dev:
#Password hashing and security with FastAPI
# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords
#FastAPI (SQL Relational Databases)
# https://fastapi.tiangolo.com/tutorial/sql-databases/#create-a-hero
# More stuff I read for Bigger Apps from FASTAPI
#https://fastapi.tiangolo.com/tutorial/bigger-applications/


password_hash = PasswordHash.recommended()

class CreateUser(BaseModel):
    username: str
    password: str

class SignupResponse(BaseModel):
    message : str #User Created Successfully
    user_id : int | str # STR for UUID or int
    
app = FastAPI()

@app.post("/auth/signup")
async def signup(user_in: CreateUser, db: Session = Depends(get_db)): # noqa: B008, claude told me to add this
    #TODO: Write code to check if user is already in database
    #existing_user = db.query(User).filter(User.username == user_in.username).first()
    #if exisiting_user:
    # throw the HTTPException TODO: Look into throwing HTTPExcetpion
    
    #After checking if the username isnt a duplicate then I can hash the password they put in
    hashed_pass = password_hash.hash(user_in.password)
    
    #Then can create the new User
    new_user = User(
        username = user_in.username,
        hashed_password = hashed_pass
    )
    #Add to the user, no idea if this is correct right now, TODO Look more into
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Response (200 OK) From Project Description
    return {
        "message" : "User Created Successfully",
        "user_id" : new_user.id
    }
    
    
    
        
            