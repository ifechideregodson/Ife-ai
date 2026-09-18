import os,base64,hashlib,hmac,secrets,io
from datetime import datetime
from fastapi import FastAPI,UploadFile,File,Request,Response
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import select,delete,desc
from sqlalchemy.exc import IntegrityError
from .database import SessionLocal,User,SessionToken,Conversation,Message,Memory,Document
load_dotenv()

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY=os.getenv("OPENAI_API_KEY",""); MODEL=os.getenv("OPENAI_MODEL","gpt-5.6-luna")
SYSTEM_PROMPT=os.getenv("AI_SYSTEM_PROMPT","You are My AI, a helpful personal assistant. Be clear and friendly.")
ASSISTANT_NAME=os.getenv("ASSISTANT_NAME","My AI")
app=FastAPI(title="My AI API",version="13.0")
app.mount("/static",StaticFiles(directory=os.path.join(ROOT,"static")),name="static")

def now(): return datetime.utcnow()
def pwd_hash(password):
    salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,200000)
    return salt.hex()+":"+digest.hex()
def pwd_check(password,stored):
    try:
        s,d=stored.split(":"); got=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(s),200000).hex()
        return hmac.compare_digest(got,d)
    except Exception:return False
def current_user(request):
    token=request.cookies.get("my_ai_session")
    if not token:return None
    with SessionLocal() as db:
        h=hashlib.sha256(token.encode()).hexdigest()
        s=db.scalar(select(SessionToken).where(SessionToken.token_hash==h))
        if not s:return None
        u=db.get(User,s.user_id)
        return {"id":u.id,"username":u.username} if u else None
def new_session(response,user_id):
    token=secrets.token_urlsafe(32)
    with SessionLocal() as db:
        db.add(SessionToken(user_id=user_id,token_hash=hashlib.sha256(token.encode()).hexdigest(),created_at=now()));db.commit()
    response.set_cookie("my_ai_session",token,httponly=True,samesite="lax",secure=os.getenv("COOKIE_SECURE","0")=="1",max_age=60*60*24*30)
def auth_error(): return JSONResponse({"error":"Login required"},status_code=401)

class AuthRequest(BaseModel): username:str; password:str
class ChatRequest(BaseModel): message:str; conversation_id:int|None=None; use_memory:bool=True; web_search:bool=False
class MemoryRequest(BaseModel): fact:str

def ai_client():
    from openai import OpenAI
    return OpenAI(api_key=API_KEY)
async def real_answer(message,history,memory,web_search=False):
    ins=SYSTEM_PROMPT
    if memory: ins+="\n\nLong-term user memory:\n"+"\n".join("- "+x for x in memory)
    items=[{"role":r,"content":c} for r,c in history[-12:]]+[{"role":"user","content":message}]
    kw={"model":MODEL,"instructions":ins,"input":items}
    if web_search: kw["tools"]=[{"type":"web_search_preview"}]
    return ai_client().responses.create(**kw).output_text
def demo_answer(m): return f"Demo mode received: {m}\n\nAdd OPENAI_API_KEY to enable real AI."

@app.get("/")
async def home(): return FileResponse(os.path.join(ROOT,"static","index.html"))
@app.get("/api/health")
async def health(): return {"ok":True,"version":"13.0","database":"postgres" if os.getenv("DATABASE_URL") else "sqlite"}
@app.get("/api/status")
async def status(): return {"configured":bool(API_KEY),"model":MODEL if API_KEY else "demo","provider":"OpenAI Responses API" if API_KEY else "Demo","database":"postgres" if os.getenv("DATABASE_URL") else "sqlite","version":"13.0"}

@app.post("/api/auth/register")
async def register(req:AuthRequest,response:Response):
    username=req.username.strip()
    if len(username)<3 or len(username)>30 or len(req.password)<6:return JSONResponse({"error":"Username must be 3-30 characters and password at least 6 characters."},status_code=400)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username==username)): return JSONResponse({"error":"Username already exists."},status_code=409)
        u=User(username=username,password_hash=pwd_hash(req.password),created_at=now());db.add(u);db.flush()
        db.add(Conversation(user_id=u.id,title="New chat",created_at=now(),updated_at=now()));db.commit();uid=u.id
    new_session(response,uid);return {"ok":True,"username":username}

@app.post("/api/auth/login")
async def login(req:AuthRequest,response:Response):
    with SessionLocal() as db:u=db.scalar(select(User).where(User.username==req.username.strip()))
    if not u or not pwd_check(req.password,u.password_hash):return JSONResponse({"error":"Invalid username or password."},status_code=401)
    new_session(response,u.id);return {"ok":True,"username":u.username}

@app.post("/api/auth/logout")
async def logout(request:Request,response:Response):
    token=request.cookies.get("my_ai_session")
    if token:
        with SessionLocal() as db:
            db.execute(delete(SessionToken).where(SessionToken.token_hash==hashlib.sha256(token.encode()).hexdigest()));db.commit()
    response.delete_cookie("my_ai_session");return {"ok":True}
@app.get("/api/auth/me")
async def me(request:Request):
    u=current_user(request);return {"logged_in":bool(u),"username":u["username"] if u else None}

@app.get("/api/conversations")
async def conversations(request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:
        rows=db.scalars(select(Conversation).where(Conversation.user_id==u["id"]).order_by(desc(Conversation.updated_at))).all()
        return {"conversations":[{"id":x.id,"title":x.title,"created_at":x.created_at,"updated_at":x.updated_at} for x in rows]}
@app.post("/api/conversations")
async def create_conversation(request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:
        x=Conversation(user_id=u["id"],title="New chat",created_at=now(),updated_at=now());db.add(x);db.commit();db.refresh(x);return {"id":x.id,"title":x.title}
@app.delete("/api/conversations/{cid}")
async def delete_conversation(cid:int,request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:
        c=db.scalar(select(Conversation).where(Conversation.id==cid,Conversation.user_id==u["id"]))
        if c:
            db.execute(delete(Message).where(Message.conversation_id==cid));db.delete(c);db.commit()
    return {"ok":True}

@app.get("/api/history")
async def history(request:Request,conversation_id:int|None=None):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:
        if conversation_id is None:
            c=db.scalar(select(Conversation).where(Conversation.user_id==u["id"]).order_by(desc(Conversation.updated_at)))
            conversation_id=c.id if c else None
        rows=db.scalars(select(Message).where(Message.conversation_id==conversation_id).order_by(Message.id)).all() if conversation_id else []
        return {"conversation_id":conversation_id,"messages":[{"role":x.role,"content":x.content,"created_at":x.created_at} for x in rows]}

@app.post("/chat")
async def chat(req:ChatRequest,request:Request):
    u=current_user(request)
    if not u:return auth_error()
    m=req.message.strip()
    if not m:return JSONResponse({"reply":"Please enter a message."},status_code=400)
    with SessionLocal() as db:
        cid=req.conversation_id
        c=db.scalar(select(Conversation).where(Conversation.id==cid,Conversation.user_id==u["id"])) if cid else None
        if not c:
            c=Conversation(user_id=u["id"],title=m[:45],created_at=now(),updated_at=now());db.add(c);db.flush();cid=c.id
        old=db.scalars(select(Message).where(Message.conversation_id==cid).order_by(Message.id)).all()
        facts=db.scalars(select(Memory).where(Memory.user_id==u["id"]).order_by(Memory.id)).all()
        docs=db.scalars(select(Document).where(Document.user_id==u["id"]).order_by(desc(Document.id)).limit(5)).all()
        hist=[(x.role,x.content) for x in old]; memory=[x.fact for x in facts]
        prompt=m
        if docs:prompt+="\n\nRelevant uploaded document content:\n"+"\n\n".join("["+x.filename+"]\n"+x.content[:20000] for x in docs)
    try:reply=await real_answer(prompt,hist,memory,req.web_search) if API_KEY else demo_answer(m)
    except Exception as e:reply=f"AI connection error: {e}"
    with SessionLocal() as db:
        c=db.get(Conversation,cid)
        if c:
            t=now();db.add(Message(conversation_id=cid,role="user",content=m,created_at=t));db.add(Message(conversation_id=cid,role="assistant",content=reply,created_at=now()))
            c.updated_at=t;db.commit()
    return {"reply":reply,"real_ai":bool(API_KEY),"conversation_id":cid}

@app.get("/api/memory")
async def get_memory(request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db: rows=db.scalars(select(Memory).where(Memory.user_id==u["id"]).order_by(Memory.id)).all()
    return {"memories":[{"id":x.id,"fact":x.fact,"created_at":x.created_at} for x in rows]}
@app.post("/api/memory")
async def add_memory(req:MemoryRequest,request:Request):
    u=current_user(request)
    if not u:return auth_error()
    fact=req.fact.strip()
    if not fact:return JSONResponse({"error":"Memory cannot be empty."},status_code=400)
    with SessionLocal() as db:db.add(Memory(user_id=u["id"],fact=fact,created_at=now()));db.commit()
    return {"ok":True}
@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id:int,request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:db.execute(delete(Memory).where(Memory.id==memory_id,Memory.user_id==u["id"]));db.commit()
    return {"ok":True}
@app.delete("/api/memory")
async def clear_memory(request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:db.execute(delete(Memory).where(Memory.user_id==u["id"]));db.commit()
    return {"ok":True}

@app.get("/api/documents")
async def documents(request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:rows=db.scalars(select(Document).where(Document.user_id==u["id"]).order_by(desc(Document.id))).all()
    return {"documents":[{"id":x.id,"filename":x.filename,"created_at":x.created_at} for x in rows]}
@app.delete("/api/documents/{document_id}")
async def delete_document(document_id:int,request:Request):
    u=current_user(request)
    if not u:return auth_error()
    with SessionLocal() as db:db.execute(delete(Document).where(Document.id==document_id,Document.user_id==u["id"]));db.commit()
    return {"ok":True}
@app.post("/api/document")
async def document_upload(request:Request,file:UploadFile=File(...)):
    u=current_user(request)
    if not u:return auth_error()
    data=await file.read()
    if len(data)>10*1024*1024:return {"ok":False,"error":"Maximum document size is 10 MB."}
    try:
        if file.filename.lower().endswith(".pdf"):
            from pypdf import PdfReader
            text="\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        elif file.filename.lower().endswith((".txt",".md",".csv")):text=data.decode("utf-8",errors="ignore")
        else:return {"ok":False,"error":"Supported documents: PDF, TXT, MD and CSV."}
    except Exception as e:return {"ok":False,"error":f"Could not read document: {e}"}
    if not text.strip():return {"ok":False,"error":"No readable text was found."}
    with SessionLocal() as db:db.add(Document(user_id=u["id"],filename=file.filename,content=text[:120000],created_at=now()));db.commit()
    return {"ok":True,"filename":file.filename,"characters":len(text)}

@app.post("/api/image")
async def image_upload(request:Request,file:UploadFile=File(...)):
    if not current_user(request):return auth_error()
    if file.content_type not in {"image/jpeg","image/png","image/webp","image/gif"}:return {"ok":False,"error":"Use JPG, PNG, WEBP or GIF."}
    data=await file.read()
    if len(data)>8*1024*1024:return {"ok":False,"error":"Maximum image size is 8 MB."}
    if not API_KEY:return {"ok":True,"filename":file.filename,"analysis":"Image received. Add OPENAI_API_KEY to enable AI image understanding."}
    try:
        url=f"data:{file.content_type};base64,{base64.b64encode(data).decode()}"
        r=ai_client().responses.create(model=MODEL,instructions=SYSTEM_PROMPT,input=[{"role":"user","content":[{"type":"input_text","text":"Analyze this image and explain what you see clearly. Mention important visible details and any readable text."},{"type":"input_image","image_url":url}]}])
        return {"ok":True,"filename":file.filename,"analysis":r.output_text}
    except Exception as e:return {"ok":False,"error":f"Vision request failed: {e}"}

@app.get("/api/export")
async def export(request:Request):
    u=current_user(request)
    if not u:return auth_error()
    p=os.path.join(ROOT,"chat_export.txt")
    with SessionLocal() as db:
        rows=db.execute(select(Conversation.title,Message.role,Message.content,Message.created_at).join(Message,Message.conversation_id==Conversation.id).where(Conversation.user_id==u["id"]).order_by(Message.id)).all()
    with open(p,"w",encoding="utf-8") as f:
        for title,role,content,created in rows:f.write(f"## {title}\n[{created}] {role.upper()}: {content}\n\n")
    return FileResponse(p,filename="my_ai_chat.txt",media_type="text/plain")
