import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.engine import make_url

DATABASE_URL=os.getenv("DATABASE_URL","").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL="postgresql+psycopg://"+DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL="postgresql+psycopg://"+DATABASE_URL[len("postgresql://"):]
if not DATABASE_URL:
    root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATABASE_URL="sqlite:///"+os.path.join(root,"chat.db")

connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {}
engine=create_engine(DATABASE_URL,connect_args=connect_args,pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autocommit=False,autoflush=False)
Base=declarative_base()

class User(Base):
    __tablename__="users"
    id=Column(Integer,primary_key=True)
    username=Column(String(30),unique=True,nullable=False,index=True)
    password_hash=Column(String(300),nullable=False)
    created_at=Column(DateTime)

class SessionToken(Base):
    __tablename__="sessions"
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=False,index=True)
    token_hash=Column(String(64),unique=True,nullable=False,index=True)
    created_at=Column(DateTime)

class Conversation(Base):
    __tablename__="conversations"
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=False,index=True)
    title=Column(String(200),nullable=False)
    created_at=Column(DateTime)
    updated_at=Column(DateTime,index=True)

class Message(Base):
    __tablename__="messages"
    id=Column(Integer,primary_key=True)
    conversation_id=Column(Integer,ForeignKey("conversations.id"),index=True)
    role=Column(String(30),nullable=False)
    content=Column(Text,nullable=False)
    created_at=Column(DateTime)

class Memory(Base):
    __tablename__="memories"
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=False,index=True)
    fact=Column(Text,nullable=False)
    created_at=Column(DateTime)

class Document(Base):
    __tablename__="documents"
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=False,index=True)
    filename=Column(String(255),nullable=False)
    content=Column(Text,nullable=False)
    created_at=Column(DateTime)

Base.metadata.create_all(engine)

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
