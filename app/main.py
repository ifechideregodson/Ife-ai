import os,sqlite3,base64,hashlib,hmac,secrets,io
from datetime import datetime
from fastapi import FastAPI,UploadFile,File,Request,Response
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); DB=os.path.join(ROOT,"chat.db")
API_KEY=os.getenv("OPENAI_API_KEY",""); MODEL=os.getenv("OPENAI_MODEL","gpt-5.6-luna")
SYSTEM_PROMPT=os.getenv("AI_SYSTEM_PROMPT","You are My AI, a helpful personal assistant. Be clear and friendly.")
ASSISTANT_NAME=os.getenv("ASSISTANT_NAME","My AI")
app=FastAPI(title="My AI API",version="12.0")
app.mount("/static",StaticFiles(directory=os.path.join(ROOT,"static")),name="static")

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,token_hash TEXT UNIQUE NOT NULL,created_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,created_at TEXT,updated_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id INTEGER,role TEXT,content TEXT,created_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,fact TEXT,created_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,filename TEXT,content TEXT,created_at TEXT)")
 for table,col in [("messages","conversation_id"),("memories","user_id"),("documents","user_id")]:
  cols=[r["name"] for r in c.execute("PRAGMA table_info("+table+")").fetchall()]
  if col not in cols:c.execute("ALTER TABLE "+table+" ADD COLUMN "+col+" INTEGER")
 c.commit()
 return c

def pwd_hash(password):
 salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,200000)
 return salt.hex()+":"+digest.hex()
def pwd_check(password,stored):
 try:
  s,d=stored.split(":"); got=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(s),200000).hex()
  return hmac.compare_digest(got,d)
 except: return False
def current_user(request):
 token=request.cookies.get("my_ai_session")
 if not token:return None
 h=hashlib.sha256(token.encode()).hexdigest(); c=db()
 u=c.execute("SELECT u.id,u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",(h,)).fetchone();c.close()
 return dict(u) if u else None
def require_user(request):
 u=current_user(request)
 if not u: raise PermissionError("Login required")
 return u
def new_session(response,user_id):
 token=secrets.token_urlsafe(32); c=db()
 c.execute("INSERT INTO sessions(user_id,token_hash,created_at) VALUES(?,?,?)",(user_id,hashlib.sha256(token.encode()).hexdigest(),datetime.utcnow().isoformat()));c.commit();c.close()
 response.set_cookie("my_ai_session",token,httponly=True,samesite="lax",secure=os.getenv("COOKIE_SECURE","0")=="1",max_age=60*60*24*30)
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
def demo_answer(m): return f"Demo mode received: {m}\n\nAdd OPENAI_API_KEY to .env for real AI."

@app.get("/")
async def home(): return FileResponse(os.path.join(ROOT,"static","index.html"))
@app.get("/api/health")
async def health(): return {"ok":True,"version":"12.0"}
@app.get("/api/status")
async def status(): return {"configured":bool(API_KEY),"model":MODEL if API_KEY else "demo","provider":"OpenAI Responses API" if API_KEY else "Demo","version":"12.0"}

@app.post("/api/auth/register")
async def register(req:AuthRequest,response:Response):
 username=req.username.strip()
 if len(username)<3 or len(username)>30 or len(req.password)<6:return JSONResponse({"error":"Username must be 3-30 characters and password at least 6 characters."},status_code=400)
 c=db()
 try:
  cur=c.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",(username,pwd_hash(req.password),datetime.utcnow().isoformat())); uid=cur.lastrowid
  c.execute("INSERT INTO conversations(user_id,title,created_at,updated_at) VALUES(?,?,?,?)",(uid,"New chat",datetime.utcnow().isoformat(),datetime.utcnow().isoformat()));c.commit()
 except sqlite3.IntegrityError:c.close();return JSONResponse({"error":"Username already exists."},status_code=409)
 c.close();new_session(response,uid);return {"ok":True,"username":username}
@app.post("/api/auth/login")
async def login(req:AuthRequest,response:Response):
 c=db();u=c.execute("SELECT id,username,password_hash FROM users WHERE username=?",(req.username.strip(),)).fetchone();c.close()
 if not u or not pwd_check(req.password,u["password_hash"]):return JSONResponse({"error":"Invalid username or password."},status_code=401)
 new_session(response,u["id"]);return {"ok":True,"username":u["username"]}
@app.post("/api/auth/logout")
async def logout(request:Request,response:Response):
 token=request.cookies.get("my_ai_session")
 if token:
  c=db();c.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),));c.commit();c.close()
 response.delete_cookie("my_ai_session");return {"ok":True}
@app.get("/api/auth/me")
async def me(request:Request):
 u=current_user(request);return {"logged_in":bool(u),"username":u["username"] if u else None}

@app.get("/api/conversations")
async def conversations(request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();rows=c.execute("SELECT id,title,created_at,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC",(u["id"],)).fetchall();c.close()
 return {"conversations":[dict(x) for x in rows]}
@app.post("/api/conversations")
async def create_conversation(request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();now=datetime.utcnow().isoformat();cur=c.execute("INSERT INTO conversations(user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)".replace("?,?,?,?,?","?,?,?,?"),(u["id"],"New chat",now,now));cid=cur.lastrowid;c.commit();c.close();return {"id":cid,"title":"New chat"}
@app.delete("/api/conversations/{cid}")
async def delete_conversation(cid:int,request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();c.execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE id=? AND user_id=?)",(cid,u["id"]));c.execute("DELETE FROM conversations WHERE id=? AND user_id=?",(cid,u["id"]));c.commit();c.close();return {"ok":True}

@app.get("/api/history")
async def history(request:Request,conversation_id:int|None=None):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db()
 if conversation_id is None:
  row=c.execute("SELECT id FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",(u["id"],)).fetchone();conversation_id=row["id"] if row else None
 rows=c.execute("SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id",(conversation_id,)).fetchall() if conversation_id else []
 c.close();return {"conversation_id":conversation_id,"messages":[dict(x) for x in rows]}

@app.post("/chat")
async def chat(req:ChatRequest,request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 m=req.message.strip()
 if not m:return JSONResponse({"reply":"Please enter a message."},status_code=400)
 c=db();cid=req.conversation_id
 if not cid:
  now=datetime.utcnow().isoformat();cur=c.execute("INSERT INTO conversations(user_id,title,created_at,updated_at) VALUES(?,?,?,?)",(u["id"],m[:45],now,now));cid=cur.lastrowid
 row=c.execute("SELECT id FROM conversations WHERE id=? AND user_id=?",(cid,u["id"])).fetchone()
 if not row:c.close();return JSONResponse({"error":"Conversation not found."},status_code=404)
 old=c.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id",(cid,)).fetchall()
 memories=c.execute("SELECT fact FROM memories WHERE user_id=? ORDER BY id",(u["id"],)).fetchall()
 docs=c.execute("SELECT filename,content FROM documents WHERE user_id=? ORDER BY id DESC LIMIT 5",(u["id"],)).fetchall()
 hist=[(x["role"],x["content"]) for x in old];facts=[x["fact"] for x in memories]
 prompt=m
 if docs:prompt+="\n\nRelevant uploaded document content:\n"+"\n\n".join("["+x["filename"]+"]\n"+x["content"][:20000] for x in docs)
 try:reply=await real_answer(prompt,hist,facts,req.web_search) if API_KEY else demo_answer(m)
 except Exception as e:reply=f"AI connection error: {e}"
 now=datetime.utcnow().isoformat();c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",(cid,"user",m,now));c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",(cid,"assistant",reply,datetime.utcnow().isoformat()));c.execute("UPDATE conversations SET updated_at=? WHERE id=?",(now,cid));c.commit();c.close()
 return {"reply":reply,"real_ai":bool(API_KEY),"conversation_id":cid}

@app.get("/api/memory")
async def get_memory(request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();rows=c.execute("SELECT id,fact,created_at FROM memories WHERE user_id=? ORDER BY id",(u["id"],)).fetchall();c.close();return {"memories":[dict(x) for x in rows]}
@app.post("/api/memory")
async def add_memory(req:MemoryRequest,request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 fact=req.fact.strip()
 if not fact:return JSONResponse({"error":"Memory cannot be empty."},status_code=400)
 c=db();c.execute("INSERT INTO memories(user_id,fact,created_at) VALUES(?,?,?)",(u["id"],fact,datetime.utcnow().isoformat()));c.commit();c.close();return {"ok":True}
@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id:int,request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();c.execute("DELETE FROM memories WHERE id=? AND user_id=?",(memory_id,u["id"]));c.commit();c.close();return {"ok":True}
@app.delete("/api/memory")
async def clear_memory(request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();c.execute("DELETE FROM memories WHERE user_id=?",(u["id"],));c.commit();c.close();return {"ok":True}

@app.get("/api/documents")
async def documents(request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();rows=c.execute("SELECT id,filename,created_at FROM documents WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall();c.close();return {"documents":[dict(x) for x in rows]}
@app.delete("/api/documents/{document_id}")
async def delete_document(document_id:int,request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();c.execute("DELETE FROM documents WHERE id=? AND user_id=?",(document_id,u["id"]));c.commit();c.close();return {"ok":True}
@app.post("/api/document")
async def document_upload(request:Request,file:UploadFile=File(...)):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
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
 c=db();c.execute("INSERT INTO documents(user_id,filename,content,created_at) VALUES(?,?,?,?)",(u["id"],file.filename,text[:120000],datetime.utcnow().isoformat()));c.commit();c.close();return {"ok":True,"filename":file.filename,"characters":len(text)}

@app.post("/api/image")
async def image_upload(request:Request,file:UploadFile=File(...)):
 try:require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 if file.content_type not in {"image/jpeg","image/png","image/webp","image/gif"}:return {"ok":False,"error":"Use JPG, PNG, WEBP or GIF."}
 data=await file.read()
 if len(data)>8*1024*1024:return {"ok":False,"error":"Maximum image size is 8 MB."}
 if not API_KEY:return {"ok":True,"filename":file.filename,"analysis":"Image received. Add OPENAI_API_KEY to .env to enable AI image understanding."}
 try:
  url=f"data:{file.content_type};base64,{base64.b64encode(data).decode()}"
  r=ai_client().responses.create(model=MODEL,instructions=SYSTEM_PROMPT,input=[{"role":"user","content":[{"type":"input_text","text":"Analyze this image and explain what you see clearly. Mention important visible details and any readable text."},{"type":"input_image","image_url":url}]}])
  return {"ok":True,"filename":file.filename,"analysis":r.output_text}
 except Exception as e:return {"ok":False,"error":f"Vision request failed: {e}"}

@app.get("/api/export")
async def export(request:Request):
 try:u=require_user(request)
 except PermissionError:return JSONResponse({"error":"Login required"},status_code=401)
 c=db();rows=c.execute("SELECT c.title,m.role,m.content,m.created_at FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.user_id=? ORDER BY m.id",(u["id"],)).fetchall();c.close()
 p=os.path.join(ROOT,"chat_export.txt")
 with open(p,"w",encoding="utf-8") as f:
  for x in rows:f.write(f"## {x['title']}\n[{x['created_at']}] {x['role'].upper()}: {x['content']}\n\n")
 return FileResponse(p,filename="my_ai_chat.txt",media_type="text/plain")
