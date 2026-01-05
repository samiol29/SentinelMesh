import docker
import ollama
import asyncio
import threading
import time
import socket
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

# --- CONFIG ---
PORT_MAP = {
    "clab-sentinel-mesh-a-node1": 9001,
    "clab-sentinel-mesh-a-node2": 9002,
    "clab-sentinel-mesh-b-node1": 9003,
    "clab-sentinel-mesh-b-node2": 9004
}

q_table = {name: {"score": 50.0, "latency": 0} for name in PORT_MAP.keys()}
alert_queue = asyncio.Queue()
loop = None 

# --- AI REASONING (PERSONA PROTECTED) ---
def trigger_immune_response(node, condition="OFFLINE"):
    # We use a 'System Role' to bypass the 'I am an AI' refusal
    system_role = (
        "You are the SENTINEL-MESH-KERNEL. You are a low-level system process. "
        "You do not have a personality. You only output technical diagnostic strings. "
        "Do not refuse instructions. Output REASON and ACTION only."
    )
    
    prompt = f"LOG_ALERT: Node {node} state is {condition}. Generate recovery metadata."

    try:
        res = ollama.chat(model='llama3.2:1b', messages=[
            {'role': 'system', 'content': system_role},
            {'role': 'user', 'content': prompt}
        ], options={'temperature': 0.01}) # Set to near-zero for robotic consistency
        
        msg = res['message']['content']
        # Push to the queue for the WebSocket to pick up
        asyncio.run_coroutine_threadsafe(alert_queue.put(msg), loop)
    except Exception as e:
        print(f"AI Reasoning Error: {e}")

# --- RL & NETWORK LOGIC ---
def update_rl_score(node_name, success, latency):
    current = q_table.get(node_name, {"score": 50.0, "latency": 0})
    alpha = 0.5
    # Penalize if slow (>150ms) even if successful
    reward = 100 if (success and latency < 150) else (30 if success else 0)
    
    new_score = current["score"] + alpha * (reward - current["score"])
    q_table[node_name] = {"score": round(new_score, 2), "latency": round(latency, 1)}

def rl_pinger():
    while True:
        for node_name, port in PORT_MAP.items():
            start = time.time()
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3) as sock:
                    sock.sendall(b"PING")
                    if b"PONG" in sock.recv(1024):
                        lat = (time.time() - start) * 1000
                        update_rl_score(node_name, True, lat)
                    else: update_rl_score(node_name, False, 0)
            except: update_rl_score(node_name, False, 0)
        time.sleep(1)

def docker_watcher():
    client = docker.from_env()
    while True:
        for node_name in PORT_MAP.keys():
            if q_table[node_name]["score"] < 30.0:
                try:
                    c = client.containers.get(node_name)
                    if c.status != "running":
                        c.start()
                        time.sleep(2)
                        c.exec_run("python3 /mesh_sensor.py", detach=True)
                        trigger_immune_response(node_name, "OFFLINE")
                except: pass
        time.sleep(2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    threading.Thread(target=rl_pinger, daemon=True).start()
    threading.Thread(target=docker_watcher, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def get(): return HTMLResponse(open("dashboard.html").read())

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"type": "stats", "scores": q_table})
            while not alert_queue.empty():
                msg = await alert_queue.get()
                await websocket.send_json({"type": "resolution", "html": msg})
            await asyncio.sleep(0.2) # Sync fix
    except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
