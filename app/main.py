import os,sqlite3,base64
from datetime import datetime
from fastapi import FastAPI,UploadFile,File
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB=os.path.join(ROOT,"chat.db")
API_KEY=os.getenv("OPENAI_API_KEY","")
MODEL=os.getenv("OPENAI_MODEL","gpt-5.6-luna")
SYSTEM_PROMPT=os.getenv("AI_SYSTEM_PROMPT","You are My AI, a helpful personal assistant. Be clear and friendly.")
ASSISTANT_NAME=os.getenv("ASSISTANT_NAME","My AI")
app=FastAPI(title="My AI API",version="10.0")
app.mount("/static",StaticFiles(directory=os.path.join(ROOT,"static")),name="static")

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,role TEXT,content TEXT,created_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,fact TEXT UNIQUE,created_at TEXT)")
 c.execute("CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT,filename TEXT,content TEXT,created_at TEXT)")
 c.commit();return c

class ChatRequest(BaseModel):
 message:str
 use_memory:bool=True
 web_search:bool=False
class MemoryRequest(BaseModel): fact:str

def demo_answer(m):
 return f"Demo mode received: {m}\n\nAdd OPENAI_API_KEY to .env for real AI."

def ai_client():
 from openai import OpenAI
 return OpenAI(api_key=API_KEY)

async def real_answer(message,history,memory,web_search=False):
 memory_text="\n".join("- "+x for x in memory)
 instructions=SYSTEM_PROMPT
 if memory_text: instructions += "\n\nLong-term user memory:\n"+memory_text
 items=[{"role":r,"content":c} for r,c in history[-12:]]
 items.append({"role":"user","content":message})
 kwargs={"model":MODEL,"instructions":instructions,"input":items}
 if web_search: kwargs["tools"]=[{"type":"web_search_preview"}]
 return ai_client().responses.create(**kwargs).output_text

@app.get("/")
async def home(): return FileResponse(os.path.join(ROOT,"static","index.html"))
@app.get("/api/health")
async def health(): return {"ok":True,"version":"10.0"}
@app.get("/api/status")
async def status(): return {"configured":bool(API_KEY),"model":MODEL if API_KEY else "demo","provider":"OpenAI Responses API" if API_KEY else "Demo","memory":True,"web_search":bool(API_KEY)}
@app.get("/api/settings")
async def settings(): return {"assistant_name":ASSISTANT_NAME,"version":"10.0","model":MODEL}

@app.get("/api/history")
async def history():
 c=db();rows=c.execute("SELECT role,content,created_at FROM messages ORDER BY id").fetchall();c.close()
 return {"messages":[dict(x) for x in rows]}

@app.get("/api/memory")
async def get_memory():
 c=db();rows=c.execute("SELECT id,fact,created_at FROM memories ORDER BY id").fetchall();c.close()
 return {"memories":[dict(x) for x in rows]}
@app.post("/api/memory")
async def add_memory(req:MemoryRequest):
 fact=req.fact.strip()
 if not fact:return JSONResponse({"error":"Memory cannot be empty."},status_code=400)
 c=db()
 try:c.execute("INSERT INTO memories(fact,created_at) VALUES(?,?)",(fact,datetime.utcnow().isoformat()));c.commit()
 except sqlite3.IntegrityError:pass
 c.close();return {"ok":True,"fact":fact}
@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id:int):
 c=db();c.execute("DELETE FROM memories WHERE id=?",(memory_id,));c.commit();c.close();return {"ok":True}
@app.delete("/api/memory")
async def clear_memory():
 c=db();c.execute("DELETE FROM memories");c.commit();c.close();return {"ok":True}

@app.get("/api/documents")
async def documents():
 c=db();rows=c.execute("SELECT id,filename,created_at FROM documents ORDER BY id DESC").fetchall();c.close()
 return {"documents":[dict(x) for x in rows]}
@app.delete("/api/documents/{document_id}")
async def delete_document(document_id:int):
 c=db();c.execute("DELETE FROM documents WHERE id=?",(document_id,));c.commit();c.close();return {"ok":True}

@app.post("/api/document")
async def document_upload(file:UploadFile=File(...)):
 data=await file.read()
 if len(data)>10*1024*1024:return {"ok":False,"error":"Maximum document size is 10 MB."}
 text=""
 try:
  if file.filename.lower().endswith(".pdf"):
   from pypdf import PdfReader
   import io
   reader=PdfReader(io.BytesIO(data))
   text="\n".join((p.extract_text() or "") for p in reader.pages)
  elif file.filename.lower().endswith((".txt",".md",".csv")):
   text=data.decode("utf-8",errors="ignore")
  else:return {"ok":False,"error":"Supported documents: PDF, TXT, MD and CSV."}
 except Exception as e:return {"ok":False,"error":f"Could not read document: {e}"}
 if not text.strip():return {"ok":False,"error":"No readable text was found."}
 c=db();c.execute("INSERT INTO documents(filename,content,created_at) VALUES(?,?,?)",(file.filename,text[:120000],datetime.utcnow().isoformat()));c.commit();c.close()
 return {"ok":True,"filename":file.filename,"characters":len(text)}

@app.post("/chat")
async def chat(req:ChatRequest):
 m=req.message.strip()
 if not m:return JSONResponse({"reply":"Please enter a message."},status_code=400)
 c=db()
 old=c.execute("SELECT role,content FROM messages ORDER BY id").fetchall()
 memories=c.execute("SELECT fact FROM memories ORDER BY id").fetchall()
 docs=c.execute("SELECT filename,content FROM documents ORDER BY id DESC LIMIT 5").fetchall()
 hist=[(x["role"],x["content"]) for x in old];facts=[x["fact"] for x in memories]
 if docs:
  m += "\n\nRelevant uploaded document content:\n"+"\n\n".join("["+x["filename"]+"]\n"+x["content"][:20000] for x in docs)
 try: reply=await real_answer(m,hist,facts,req.web_search) if API_KEY else demo_answer(req.message)
 except Exception as e: reply=f"AI connection error: {e}"
 now=datetime.utcnow().isoformat()
 c.execute("INSERT INTO messages(role,content,created_at) VALUES(?,?,?)",("user",req.message,now))
 c.execute("INSERT INTO messages(role,content,created_at) VALUES(?,?,?)",("assistant",reply,datetime.utcnow().isoformat()));c.commit();c.close()
 return {"reply":reply,"real_ai":bool(API_KEY),"web_search":req.web_search}

@app.post("/api/clear")
async def clear():
 c=db();c.execute("DELETE FROM messages");c.commit();c.close();return {"ok":True}
@app.get("/api/export")
async def export():
 c=db();rows=c.execute("SELECT role,content,created_at FROM messages ORDER BY id").fetchall();c.close()
 p=os.path.join(ROOT,"chat_export.txt")
 with open(p,"w",encoding="utf-8") as f:
  for x in rows:f.write(f"[{x['created_at']}] {x['role'].upper()}: {x['content']}\n\n")
 return FileResponse(p,filename="my_ai_chat.txt",media_type="text/plain")

@app.post("/api/image")
async def image_upload(file:UploadFile=File(...)):
 if file.content_type not in {"image/jpeg","image/png","image/webp","image/gif"}:return {"ok":False,"error":"Use JPG, PNG, WEBP or GIF."}
 data=await file.read()
 if len(data)>8*1024*1024:return {"ok":False,"error":"Maximum image size is 8 MB."}
 if not API_KEY:return {"ok":True,"filename":file.filename,"analysis":"Image received. Add OPENAI_API_KEY to .env to enable AI image understanding."}
 try:
  url=f"data:{file.content_type};base64,{base64.b64encode(data).decode()}"
  r=ai_client().responses.create(model=MODEL,instructions=SYSTEM_PROMPT,input=[{"role":"user","content":[{"type":"input_text","text":"Analyze this image and explain what you see clearly. Mention important visible details and any readable text."},{"type":"input_image","image_url":url}]}])
  return {"ok":True,"filename":file.filename,"analysis":r.output_text}
 except Exception as e:return {"ok":False,"error":f"Vision request failed: {e}"}
