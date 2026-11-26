"""vaughn-apt Spatial Home OS Server (Phases 1–5 Complete):
- Phase 1: Static 3D web apps + persistent Home Graph REST API (data/home_graph.json)
- Phase 2: Local filesystem folder browser & native launcher, live 3D Wall Art uploader,
           Drawer Photo capture + optional Gemini Vision auto-inventory
- Phase 3: Cyber-Physical Hardware Bridge (WLED Pick-to-Light, Moonraker/OctoPrint printers, smart lamps)
- Phase 4: Room-Aware Spatial Agent & BOM Feasibility Engine (offline + optional Gemini 2.5 Flash)
- Phase 5: Guests & Social Presence (server-side per-room privacy redaction, live 3D multiplayer
           avatar presence, lounge chat, synced Living Room TV co-watch, Front Door Comms Concierge)
"""
import base64
import json
import os
import re
import sys
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_DIR / "data" / "home_graph.json"
SHELF_PHOTOS_DIR = PROJECT_DIR / "data" / "shelf_photos"
CUSTOM_ART_DIR = PROJECT_DIR / "textures" / "custom"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

# Live in-memory Phase 5 Multiplayer Presence, Lounge Chat, Synced TV & Guest Permissions
PRESENCE: dict[str, dict] = {}
LOUNGE_CHAT: list[dict] = [
    {"id": 1, "sender": "Doorman Agent", "role": "agent", "text": "Welcome home! Invite guests to the Living Room with the Guest Invite button.", "ts": time.time()}
]
SHARED_TV: dict = {"title": "", "embed_url": "", "shared_by": "", "updated_at": 0.0}
GUEST_ROOM_ACCESS: dict = {"studio_unlocked": False}


def load_graph() -> dict:
    g = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    if "comms_inbox" not in g:
        g["comms_inbox"] = [
            {"id": "msg-1", "from": "Alex (VIP)", "channel": "SMS", "subject": "Coming over to jam at the MIDI desk?", "tier": "vip", "status": "living_room"},
            {"id": "msg-2", "from": "GitHub", "channel": "Email", "subject": "eyeoverthink/vaughn-apt push confirmed", "tier": "standard", "status": "entryway"},
            {"id": "msg-3", "from": "Promo Newsletter", "channel": "Email", "subject": "Flash sale on random cables", "tier": "muted", "status": "held_outside"},
        ]
    return g


def save_graph(data: dict) -> None:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def redact_graph_for_guest(graph: dict) -> dict:
    """Server-side privacy enforcement: strip private vault/studio nodes for Guests."""
    safe_nodes = []
    for n in graph.get("nodes", []):
        is_studio = n["id"].startswith("apt://studio/")
        if n.get("privacy") == "private" and not (is_studio and GUEST_ROOM_ACCESS.get("studio_unlocked")):
            safe_nodes.append({
                "id": n["id"],
                "room": n["room"],
                "label": f"{n['room']} (Private — Locked)",
                "position_threejs": n["position_threejs"],
                "privacy": "private",
                "locked": True,
                "category": "locked",
                "color": "#556275",
                "physical_items": [],
                "digital_files": [],
                "notes": "",
                "live_devices": [],
            })
        else:
            safe_nodes.append(n)
    return {
        "version": graph.get("version", "1.0"),
        "apartment": graph.get("apartment", "vaughn-apt"),
        "lighting_mood": graph.get("lighting_mood", "afternoon"),
        "custom_wall_art": graph.get("custom_wall_art", ""),
        "guest_redacted": True,
        "studio_unlocked": GUEST_ROOM_ACCESS.get("studio_unlocked", False),
        "nodes": safe_nodes,
    }


def find_node(graph: dict, node_id: str) -> dict | None:
    for n in graph.get("nodes", []):
        if n["id"] == node_id:
            return n
    return None


def find_best_node(nodes: list[dict], target_text: str) -> dict | None:
    q = target_text.lower().strip()
    tokens = [t for t in re.findall(r"[a-z0-9#]+", q) if len(t) > 1 or t.isdigit()]
    best, best_score = None, 0
    for node in nodes:
        hay = f"{node['id']} {node['room']} {node['label']} {node.get('category','')}".lower()
        score = 0
        if q in hay:
            score += 10
        for tok in tokens:
            if tok in hay:
                score += 3
            if tok in ("second", "2nd") and ("shelf-2" in hay or "#2" in hay):
                score += 8
            if tok in ("first", "top", "1st") and ("shelf-1" in hay or "#1" in hay):
                score += 8
            if tok in ("third", "bottom", "lower", "3rd") and ("shelf-3" in hay or "#3" in hay):
                score += 8
            if tok in ("extra", "bedroom", "office") and "studio" in hay:
                score += 4
        if score > best_score:
            best, best_score = node, score
    return best if best_score > 0 else None


def search_graph(graph: dict, query: str) -> list[dict]:
    q = query.lower().strip()
    tokens = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 1 or t.isdigit()]
    if not tokens:
        return []
    hits = []
    for node in graph.get("nodes", []):
        matched_items, matched_files = [], []
        score = 0
        node_text = f"{node['id']} {node['room']} {node['label']} {node.get('notes','')} {node.get('category','')}".lower()
        for tok in tokens:
            if tok in node_text:
                score += 2
        for item in node.get("physical_items", []):
            it_text = f"{item['name']} {' '.join(item.get('tags', []))}".lower()
            s = sum(4 for tok in tokens if tok in it_text)
            if s > 0:
                score += s
                matched_items.append(item)
        for fobj in node.get("digital_files", []):
            ft_text = f"{fobj['name']} {fobj.get('path','')} {fobj.get('type','')}".lower()
            s = sum(4 for tok in tokens if tok in ft_text)
            if s > 0:
                score += s
                matched_files.append(fobj)
        if score > 0:
            hits.append({
                "node_id": node["id"],
                "label": node["label"],
                "room": node["room"],
                "score": score,
                "matched_items": matched_items,
                "matched_files": matched_files,
            })
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits


def handle_nl_command(graph: dict, raw_cmd: str) -> dict:
    cmd = raw_cmd.strip()
    low = cmd.lower()

    m_file = re.match(r"^(?:save|pin|attach)\s+(?:file\s+)?(.+?)\s+(?:to|on|in|at)\s+(.+)$", cmd, re.I)
    if m_file:
        fname, loc_txt = m_file.group(1).strip().strip("'\""), m_file.group(2).strip()
        node = find_best_node(graph["nodes"], loc_txt)
        if node:
            node.setdefault("digital_files", []).append({
                "name": Path(fname).name if ("/" in fname or "\\" in fname) else fname,
                "path": fname,
                "type": "file",
            })
            save_graph(graph)
            return {"action": "added_file", "node_id": node["id"], "message": f"Saved '{fname}' to {node['label']} ({node['id']})", "graph": graph}

    m_item = re.match(r"^(?:add|put|store|move)\s+(.+?)\s+(?:to|on|in|into|at)\s+(.+)$", cmd, re.I)
    if m_item:
        item_raw, loc_txt = m_item.group(1).strip(), m_item.group(2).strip()
        qty = 1
        m_qty = re.search(r"\b(?:x|\*)(\d+)\b|\b(\d+)\s*x\b", item_raw, re.I)
        if m_qty:
            qty = int(m_qty.group(1) or m_qty.group(2))
            item_raw = re.sub(r"\b(?:x|\*)\d+\b|\b\d+\s*x\b", "", item_raw, flags=re.I).strip()
        node = find_best_node(graph["nodes"], loc_txt)
        if node:
            tags = [t for t in re.findall(r"[a-z0-9]+", item_raw.lower()) if len(t) > 2]
            node.setdefault("physical_items", []).append({"name": item_raw, "qty": qty, "tags": tags})
            save_graph(graph)
            return {"action": "added_item", "node_id": node["id"], "message": f"Stored '{item_raw}' (×{qty}) at {node['label']} ({node['id']})", "graph": graph}

    if low.startswith(("bom ", "build ", "do i have ", "parts for ")):
        cleaned = re.sub(r"^(?:bom|build|do i have|parts for)\s+", "", low)
        expansions = {
            "lamp": "esp32 led wled mosfet smart lamp",
            "plant": "arduino esp32 sensor dht22 breadboard",
            "robot": "arduino raspberry pi sensor l293d breadboard 3d printer",
            "fpga": "basys fpga circuit breadboard ic",
            "synth": "midi arduino music mixer audio",
            "printer": "3d printer filament nozzle",
            "camera": "raspberry pi esp32 sensor",
        }
        expanded = cleaned
        for k, v in expansions.items():
            if k in cleaned:
                expanded += " " + v
        hits = search_graph(graph, expanded)
        if hits:
            summary_lines = [f"{h['label']}: {', '.join(i['name'] for i in h['matched_items'][:3])}" for h in hits[:4] if h["matched_items"]]
            return {"action": "bom_result", "node_id": hits[0]["node_id"], "hits": hits, "message": "BOM Pick-List → " + (" | ".join(summary_lines) if summary_lines else "")}
        return {"action": "not_found", "hits": [], "message": f"No matching parts found for '{cmd}' yet."}

    cleaned_q = re.sub(r"^(?:where is|where are|find|locate|show|go to|open)\s+(?:my\s+)?", "", low)
    hits = search_graph(graph, cleaned_q)
    if hits:
        top = hits[0]
        return {"action": "search_hit", "node_id": top["node_id"], "hits": hits, "message": f"Found in {top['room']} → {top['label']} ({len(hits)} matching zone{'s' if len(hits)!=1 else ''})"}
    return {"action": "not_found", "hits": [], "message": f"Nothing matched '{cmd}'. Try 'put ESP32 x4 on studio shelf 2' or 'bom smart lamp'."}


def browse_local_folder(folder_str: str) -> dict:
    raw = (folder_str or "").strip()
    target = Path(raw) if raw else PROJECT_DIR
    if not target.is_absolute():
        target = (PROJECT_DIR / raw).resolve()
    if not target.exists() or not target.is_dir():
        return {"ok": False, "error": f"Folder not found: {target}", "entries": []}
    entries = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:80]:
            if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                continue
            try:
                size = entry.stat().st_size if entry.is_file() else 0
            except OSError:
                size = 0
            entries.append({"name": entry.name, "path": str(entry), "is_dir": entry.is_dir(), "size_kb": round(size / 1024, 1), "ext": entry.suffix.lower()})
    except PermissionError:
        return {"ok": False, "error": f"Permission denied reading {target}", "entries": []}
    return {"ok": True, "folder": str(target), "parent": str(target.parent), "entries": entries}


def analyze_drawer_photo_vision(b64_data: str, mime: str) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = "Identify all physical electronics, hardware components, tools, boards, sensors, or notable items in this shelf/drawer photo. Return ONLY a JSON array: [{\"name\": \"...\", \"qty\": 1, \"tags\": [\"...\"]}]."
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": b64_data}}]}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            txt = out["candidates"][0]["content"]["parts"][0]["text"]
            m = re.search(r"\[.*\]", txt, re.S)
            if m:
                parsed = json.loads(m.group(0))
                return [{"name": str(it.get("name", "Item")), "qty": max(1, int(it.get("qty", 1))), "tags": [str(t).lower() for t in it.get("tags", [])]} for it in parsed if isinstance(it, dict) and it.get("name")]
    except Exception:
        return []
    return []


def http_json(url: str, payload: dict | None = None, headers: dict | None = None, timeout: float = 2.5) -> dict:
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="ignore")
        return json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw}


def trigger_hardware_device(dev: dict, action: str = "pulse") -> dict:
    dtype = dev.get("type", "")
    ep = (dev.get("endpoint") or "").strip().rstrip("/")
    if not ep:
        return {"ok": True, "simulated": True, "message": f"Simulated {action} on '{dev.get('label', dtype)}' (set LAN IP/endpoint to fire real hardware!)"}
    try:
        if dtype == "wled_pick_to_light":
            seg_id = int(dev.get("segment_id", 0))
            http_json(f"{ep}/json/state", {"on": True, "bri": 220, "seg": [{"id": seg_id, "col": [[0, 235, 255]], "fx": 2 if action == "pulse" else 0}]})
            return {"ok": True, "simulated": False, "message": f"WLED Pick-to-Light fired on {ep} (segment {seg_id})!"}
        if dtype == "smart_lamp":
            on = action != "off"
            http_json(ep if ("/json" in ep or ep.endswith("/state")) else f"{ep}/json/state", {"on": on, "bri": 200})
            return {"ok": True, "simulated": False, "message": f"Smart Lamp '{dev.get('label')}' toggled ({'ON' if on else 'OFF'})!"}
        if dtype == "3d_printer":
            if "octoprint" in ep or dev.get("api_key"):
                data = http_json(f"{ep}/api/job", headers={"X-Api-Key": dev.get("api_key", "")})
                return {"ok": True, "simulated": False, "telemetry": data, "message": f"OctoPrint state: {data.get('state', 'online')}"}
            data = http_json(f"{ep}/printer/objects/query?heater_bed&extruder&print_stats&virtual_sdcard")
            return {"ok": True, "simulated": False, "telemetry": data, "message": f"Moonraker telemetry fetched from {ep}"}
        http_json(ep, {"action": action, "device": dev.get("label")})
        return {"ok": True, "simulated": False, "message": f"Webhook triggered on {ep}"}
    except Exception as exc:
        return {"ok": False, "simulated": False, "error": f"Device unreachable ({ep}): {exc}"}


def run_spatial_agent(graph: dict, message: str, current_node_id: str | None) -> dict:
    msg = message.strip()
    low = msg.lower()
    cur_node = find_node(graph, current_node_id) if current_node_id else None

    if re.match(r"^(?:add|put|store|move|save|pin|attach|bom|build|do i have|parts for|where is|where are|find|locate)\b", low):
        res = handle_nl_command(graph, msg)
        return {"reply": res["message"], "node_id": res.get("node_id"), "graph": res.get("graph"), "hits": res.get("hits", []), "engine": "local-spatial"}

    if any(k in low for k in ("summary", "inventory", "what do i own", "how many", "overview")):
        total_items = sum(sum(i.get("qty", 1) for i in n.get("physical_items", [])) for n in graph["nodes"])
        total_files = sum(len(n.get("digital_files", [])) for n in graph["nodes"])
        top_rooms = ", ".join(sorted({n["room"] for n in graph["nodes"]}))
        ctx = f" Currently focused on **{cur_node['label']}**." if cur_node else ""
        return {
            "reply": f"Your Home Graph tracks **{len(graph['nodes'])} spatial nodes** across {top_rooms}: **{total_items} physical parts/items** and **{total_files} digital files**.{ctx}",
            "node_id": cur_node["id"] if cur_node else None,
            "engine": "local-spatial",
        }

    if cur_node and any(k in low for k in ("here", "this shelf", "this room", "this desk", "what can i build")):
        atoms = ", ".join(f"{i['name']} (×{i.get('qty',1)})" for i in cur_node.get("physical_items", [])) or "none yet"
        bits = ", ".join(f["name"] for f in cur_node.get("digital_files", [])) or "none yet"
        return {
            "reply": f"At **{cur_node['label']}** (`{cur_node['id']}`):\n• **Physical (Atoms):** {atoms}\n• **Digital (Bits):** {bits}\n• **Notes:** {cur_node.get('notes','')}",
            "node_id": cur_node["id"],
            "engine": "local-spatial",
        }

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        compact_nodes = [{"id": n["id"], "room": n["room"], "label": n["label"], "items": [f"{i['name']} x{i.get('qty',1)}" for i in n.get("physical_items", [])], "files": [f["name"] for f in n.get("digital_files", [])]} for n in graph["nodes"]]
        sys_prompt = f"You are the Spatial Home OS Agent inside Vaughn's 3D apartment (vaughn-apt). Reference exact rooms, shelves, and apt:// URIs.\nCurrent node: {current_node_id}\nHome Graph: {json.dumps(compact_nodes)}\nUser: {msg}"
        try:
            out = http_json(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}", {"contents": [{"parts": [{"text": sys_prompt}]}]}, timeout=15)
            reply = out["candidates"][0]["content"]["parts"][0]["text"]
            m_uri = re.search(r"apt://[a-z0-9/_-]+", reply)
            return {"reply": reply, "node_id": m_uri.group(0) if m_uri else (cur_node["id"] if cur_node else None), "engine": "gemini-2.5-flash"}
        except Exception:
            pass

    hits = search_graph(graph, msg)
    if hits:
        top = hits[0]
        parts = ", ".join(i["name"] for i in top["matched_items"][:3])
        files = ", ".join(f["name"] for f in top["matched_files"][:3])
        detail = " | ".join(x for x in [f"Parts: {parts}" if parts else "", f"Files: {files}" if files else ""] if x)
        return {"reply": f"Check **{top['room']} → {top['label']}** (`{top['node_id']}`). {detail}", "node_id": top["node_id"], "hits": hits, "engine": "local-spatial"}
    return {"reply": "Try asking: `'where is my basys'`, `'bom smart lamp'`, `'put OLED display x3 on studio shelf 2'`, `'what is here?'`, or `'inventory summary'`.", "node_id": cur_node["id"] if cur_node else None, "engine": "local-spatial"}


def triage_incoming_message(sender: str, channel: str, subject: str) -> dict:
    """Doorman Concierge auto-triage: VIP -> living_room, Promo/Spam -> held_outside, else entryway."""
    low = f"{sender} {subject}".lower()
    if any(w in low for w in ("vip", "urgent", "jam", "visit", "friend", "coming over", "collab")):
        tier, status = "vip", "living_room"
    elif any(w in low for w in ("sale", "promo", "unsubscribe", "newsletter", "spam", "offer")):
        tier, status = "muted", "held_outside"
    else:
        tier, status = "standard", "entryway"
    return {
        "id": f"msg-{int(time.time()*1000) % 100000}",
        "from": sender,
        "channel": channel,
        "subject": subject,
        "tier": tier,
        "status": status,
    }


def prune_stale_presence() -> list[dict]:
    now = time.time()
    stale = [pid for pid, p in PRESENCE.items() if now - p["last_seen"] > 18.0]
    for pid in stale:
        PRESENCE.pop(pid, None)
    return list(PRESENCE.values())


class HomeOSHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

    def send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/api/graph":
            g = load_graph()
            if qs.get("guest", ["0"])[0] == "1":
                return self.send_json(redact_graph_for_guest(g))
            g["studio_unlocked"] = GUEST_ROOM_ACCESS.get("studio_unlocked", False)
            return self.send_json(g)
        if parsed.path == "/api/health":
            return self.send_json({"ok": True, "service": "vaughn-apt-home-os", "version": "phase-5-complete", "gemini_enabled": bool(os.environ.get("GEMINI_API_KEY"))})
        if parsed.path == "/api/fs/list":
            return self.send_json(browse_local_folder(qs.get("path", [""])[0]))
        if parsed.path == "/api/presence":
            return self.send_json({
                "visitors": prune_stale_presence(),
                "chat": LOUNGE_CHAT[-30:],
                "shared_tv": SHARED_TV,
                "studio_unlocked": GUEST_ROOM_ACCESS.get("studio_unlocked", False),
            })
        if parsed.path == "/api/inbox":
            g = load_graph()
            return self.send_json({"inbox": g.get("comms_inbox", [])})
        if parsed.path in ("/", "/web", "/web/"):
            self.send_response(302)
            self.send_header("Location", "/web/home_os.html")
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self.read_json()
        except Exception as exc:
            return self.send_json({"error": f"Invalid JSON: {exc}"}, 400)

        # Phase 5: Live Presence, Lounge Chat, Synced TV & Guest Permissions
        if parsed.path == "/api/presence/heartbeat":
            pid = str(body.get("id") or "anon")
            PRESENCE[pid] = {
                "id": pid,
                "name": (body.get("name") or "Guest")[:24],
                "role": "guest" if body.get("guest") else "owner",
                "pos": body.get("pos") or [-0.8, 1.1, -4.5],
                "room": body.get("room") or "Corner Living Room",
                "color": body.get("color") or ("#7ee787" if body.get("guest") else "#58d5ff"),
                "last_seen": time.time(),
            }
            return self.send_json({
                "ok": True,
                "visitors": prune_stale_presence(),
                "chat": LOUNGE_CHAT[-30:],
                "shared_tv": SHARED_TV,
                "studio_unlocked": GUEST_ROOM_ACCESS.get("studio_unlocked", False),
            })

        if parsed.path == "/api/chat":
            text = (body.get("text") or "").strip()[:280]
            if text:
                LOUNGE_CHAT.append({
                    "id": len(LOUNGE_CHAT) + 1,
                    "sender": (body.get("sender") or "Guest")[:24],
                    "role": body.get("role") or "guest",
                    "text": text,
                    "ts": time.time(),
                })
            return self.send_json({"ok": True, "chat": LOUNGE_CHAT[-30:]})

        if parsed.path == "/api/tv/sync":
            SHARED_TV["title"] = (body.get("title") or "Living Room TV")[:80]
            SHARED_TV["embed_url"] = (body.get("embed_url") or "").strip()
            SHARED_TV["shared_by"] = (body.get("shared_by") or "Vaughn")[:24]
            SHARED_TV["updated_at"] = time.time()
            return self.send_json({"ok": True, "shared_tv": SHARED_TV})

        if parsed.path == "/api/guest-access":
            GUEST_ROOM_ACCESS["studio_unlocked"] = bool(body.get("studio_unlocked", False))
            return self.send_json({"ok": True, "studio_unlocked": GUEST_ROOM_ACCESS["studio_unlocked"]})

        graph = load_graph()

        if parsed.path == "/api/inbox/add":
            item = triage_incoming_message(
                body.get("from", "Friend"),
                body.get("channel", "SMS"),
                body.get("subject", "Hey, are you home?"),
            )
            graph.setdefault("comms_inbox", []).insert(0, item)
            save_graph(graph)
            return self.send_json({"ok": True, "item": item, "inbox": graph["comms_inbox"]})

        if parsed.path == "/api/inbox/dismiss":
            mid = body.get("id")
            graph["comms_inbox"] = [m for m in graph.get("comms_inbox", []) if m.get("id") != mid]
            save_graph(graph)
            return self.send_json({"ok": True, "inbox": graph["comms_inbox"]})

        if parsed.path == "/api/command":
            return self.send_json(handle_nl_command(graph, body.get("command", "")))

        if parsed.path == "/api/agent":
            return self.send_json(run_spatial_agent(graph, body.get("message", ""), body.get("node_id")))

        if parsed.path == "/api/node/add-item":
            node = find_node(graph, body.get("node_id", ""))
            if not node:
                return self.send_json({"error": "Node not found"}, 404)
            name = (body.get("name") or "").strip()
            qty = max(1, int(body.get("qty") or 1))
            tags = [t.strip().lower() for t in (body.get("tags") or []) if t.strip()] or [t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) > 2]
            node.setdefault("physical_items", []).append({"name": name, "qty": qty, "tags": tags})
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph})

        if parsed.path == "/api/node/delete-item":
            node = find_node(graph, body.get("node_id", ""))
            idx = int(body.get("index", -1))
            if node and 0 <= idx < len(node.get("physical_items", [])):
                node["physical_items"].pop(idx)
                save_graph(graph)
                return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "Item not found"}, 404)

        if parsed.path == "/api/node/add-file":
            node = find_node(graph, body.get("node_id", ""))
            if not node:
                return self.send_json({"error": "Node not found"}, 404)
            name = (body.get("name") or "").strip()
            path = (body.get("path") or name).strip()
            node.setdefault("digital_files", []).append({"name": name, "path": path, "type": (body.get("type") or "file").strip()})
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph})

        if parsed.path == "/api/node/delete-file":
            node = find_node(graph, body.get("node_id", ""))
            idx = int(body.get("index", -1))
            if node and 0 <= idx < len(node.get("digital_files", [])):
                node["digital_files"].pop(idx)
                save_graph(graph)
                return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "File not found"}, 404)

        if parsed.path == "/api/node/notes":
            node = find_node(graph, body.get("node_id", ""))
            if not node:
                return self.send_json({"error": "Node not found"}, 404)
            node["notes"] = body.get("notes", "")
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph})

        if parsed.path == "/api/node/mount-folder":
            node = find_node(graph, body.get("node_id", ""))
            if not node:
                return self.send_json({"error": "Node not found"}, 404)
            node["mounted_folder"] = (body.get("folder") or "").strip()
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph, "listing": browse_local_folder(node["mounted_folder"])})

        if parsed.path == "/api/node/photo":
            node = find_node(graph, body.get("node_id", ""))
            if not node:
                return self.send_json({"error": "Node not found"}, 404)
            data_url = body.get("data_url", "")
            m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", data_url, re.S)
            if not m:
                return self.send_json({"error": "Invalid image data URL"}, 400)
            mime, b64 = m.group(1), m.group(2)
            ext = "png" if "png" in mime else "jpg"
            slug = re.sub(r"[^a-z0-9]+", "_", node["id"].lower()).strip("_")
            SHELF_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
            out_file = SHELF_PHOTOS_DIR / f"{slug}.{ext}"
            out_file.write_bytes(base64.b64decode(b64))
            rel = f"data/shelf_photos/{out_file.name}"
            node["photo"] = rel
            detected = analyze_drawer_photo_vision(b64, mime) if body.get("auto_detect", True) else []
            for it in detected:
                node.setdefault("physical_items", []).append(it)
            save_graph(graph)
            return self.send_json({"ok": True, "photo": rel, "detected": detected, "graph": graph})

        if parsed.path == "/api/wall-art":
            data_url = body.get("data_url", "")
            m = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", data_url, re.S)
            if not m:
                return self.send_json({"error": "Invalid image data URL"}, 400)
            mime, b64 = m.group(1), m.group(2)
            ext = "png" if "png" in mime else "jpg"
            CUSTOM_ART_DIR.mkdir(parents=True, exist_ok=True)
            out_file = CUSTOM_ART_DIR / f"dining_wall_art.{ext}"
            out_file.write_bytes(base64.b64decode(b64))
            rel = f"textures/custom/{out_file.name}"
            graph["custom_wall_art"] = rel
            save_graph(graph)
            return self.send_json({"ok": True, "path": rel, "graph": graph})

        if parsed.path == "/api/node/device":
            node = find_node(graph, body.get("node_id", ""))
            if not node:
                return self.send_json({"error": "Node not found"}, 404)
            node.setdefault("live_devices", []).append({
                "type": body.get("type", "wled_pick_to_light"),
                "label": (body.get("label") or "Hardware Device").strip(),
                "endpoint": (body.get("endpoint") or "").strip(),
                "segment_id": int(body.get("segment_id") or 0),
                "status": "ready",
            })
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph})

        if parsed.path == "/api/device/trigger":
            node = find_node(graph, body.get("node_id", ""))
            idx = int(body.get("index", 0))
            if not node or not (0 <= idx < len(node.get("live_devices", []))):
                return self.send_json({"error": "Device not found"}, 404)
            return self.send_json(trigger_hardware_device(node["live_devices"][idx], body.get("action", "pulse")))

        if parsed.path == "/api/mood":
            graph["lighting_mood"] = body.get("mood", "afternoon")
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph})

        if parsed.path == "/api/open-local":
            raw_p = (body.get("path") or "").strip()
            if raw_p.startswith(("http://", "https://")):
                return self.send_json({"ok": True, "url": raw_p})
            candidate = Path(raw_p)
            if not candidate.is_absolute():
                candidate = (PROJECT_DIR / raw_p).resolve()
            if candidate.exists():
                try:
                    os.startfile(str(candidate))
                    return self.send_json({"ok": True, "opened": str(candidate)})
                except Exception as exc:
                    return self.send_json({"ok": False, "error": str(exc)}, 500)
            return self.send_json({"ok": False, "error": f"Local path not found: {candidate}"}, 404)

        return self.send_json({"error": "Unknown API endpoint"}, 404)

    def log_message(self, fmt, *args):
        pass


def main():
    # Bind 0.0.0.0 so LAN guests on the same Wi-Fi can also join the Living Room!
    print(f"vaughn-apt Spatial Home OS Server (Phases 1-5 Complete) running on http://localhost:{PORT}/web/home_os.html")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), HomeOSHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
