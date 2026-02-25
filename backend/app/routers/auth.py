from fastapi import Depends, FastAPI, HTTPException, status
from pwdlib import PasswordHash
from pydantic import BaseModel


class User(BaseModel):
    username: str

class UserInDB(User):
    hashed_password: str

app = FastAPI()
