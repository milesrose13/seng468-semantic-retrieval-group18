from sqlalchemy import Column, Integer, String

from ..database import Base

# This code is based on https://fastapi.tiangolo.com/tutorial/sql-databases/
# Syntax understanding from Gemini and https://docs.sqlalchemy.org/en/20/core/type_basics.html
# For Mapping https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html
# Remove this after but make sure to make note for Report


class User(Base):
    __tablename__ = "users"

    # The primary key which is the unique id for each user in da DB
    id = Column(Integer, primary_key=True, index=True)

    # username
    username = Column(String, unique=True, index=True, nullable=False)

    hashed_password = Column(String, nullable=False)
