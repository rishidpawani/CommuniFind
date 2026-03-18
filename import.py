import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from enum import Enum, auto
from PIL import Image, ImageTk
import math
import random
import os
import time
import io
import pandas as pd
import pymongo
import overpy
from geopy.distance import geodesic
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import warnings

# --- CONFIGURATION ---
warnings.filterwarnings("ignore") 
APP_TITLE = "CommuniFind (Offline Mode)"
WINDOW_SIZE = "1300x850"

# --- THEME & COLORS ---
COLOR_BG = "#E8F5E9"          # Light Green Background
COLOR_CARD = "#FFFFFF"        # White Card
COLOR_PRIMARY = "#2E7D32"     # Forest Green
COLOR_PRIMARY_HOVER = "#1B5E20" 
COLOR_SECONDARY = "#81C784"   # Light Green
COLOR_TEXT = "#1B5E20"        # Dark Green Text
COLOR_TEXT_LIGHT = "#546E7A"  # Grey Text
COLOR_MUTED = "#607D8B"       # Blue Grey
COLOR_ERROR = "#D32F2F"       
COLOR_WARN = "#F57F17"
COLOR_BORDER = "#A5D6A7"      
COLOR_SUCCESS = "#388E3C"

# Database Config
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "CommuniFindDB"

# Regions
MUMBAI_REGIONS = {
    "Colaba - Gateway": (18.9220, 72.8347),
    "Dadar - Shivaji Park": (19.0269, 72.8383),
    "Bandra - Bandstand": (19.0544, 72.8207),
    "Juhu - Beach Area": (19.0980, 72.8254),
    "Andheri - Station": (19.1197, 72.8464),
    "Borivali - National Park": (19.2294, 72.8642),
    "Navi Mumbai - Vashi": (19.0770, 72.9980),
    "Navi Mumbai - Nerul": (19.0330, 73.0297),
    "Navi Mumbai - Kharghar": (19.0298, 73.0726),
    "Panvel - City": (18.9894, 73.1175)
}

CATEGORY_EMOJIS = {
    "hospital": "🏥", "hotel": "🏨", "park": "🌳", 
    "museum": "🏛️", "shop": "🛒", "parking": "🅿️", "default": "📍"
}

SAFETY_TIPS = [
    "🚗 Safety: Always wear a seatbelt.",
    "💡 Tip: Use 'hospital' to find emergency care.",
    "🌍 Map: The map zooms automatically to your results!",
    "⭐ Pro Tip: Save your frequent locations."
]

# ==========================================
# PART 1: DATABASE SETUP
# ==========================================
def determine_category(tags_dict):
    tag_str = str(tags_dict).lower()
    if any(x in tag_str for x in ['hospital', 'clinic', 'pharmacy', 'doctor', 'police', 'fire']): return 'hospital'
    if any(x in tag_str for x in ['park', 'garden', 'playground', 'nature']): return 'park'
    if any(x in tag_str for x in ['museum', 'gallery', 'attraction', 'cinema', 'theatre']): return 'museum'
    if any(x in tag_str for x in ['hotel', 'guest_house', 'restaurant', 'cafe']): return 'hotel'
    if any(x in tag_str for x in ['mall', 'supermarket', 'department_store', 'shop']): return 'shop'
    if 'parking' in tag_str: return 'parking'
    return 'default'

def populate_images_db(db):
    col = db.category_images
    if not os.path.exists("assets"): return
    if col.count_documents({}) > 0: return 
    
    print(">>> Uploading images to Database...")
    categories = ["hospital", "hotel", "park", "museum", "shop", "parking", "default"]
    all_files = os.listdir("assets")
    for cat in categories:
        cat_files = [f for f in all_files if f.lower().startswith(cat) and f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if cat_files:
            binary_list = []
            for filename in cat_files:
                with open(os.path.join("assets", filename), "rb") as f:
                    binary_list.append(f.read())
            col.update_one({"_id": cat}, {"$set": {"image_data_list": binary_list}}, upsert=True)

def fetch_and_populate_db():
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        populate_images_db(db)
        
        collection = db.locations
        if collection.count_documents({}) > 500: return

        print("Fetching locations from OpenStreetMap...")
        collection.drop(); collection.create_index([("coordinates", "2dsphere")])
        api = overpy.Overpass(url="https://overpass.kumi.systems/api/interpreter")
        
        for region, coords in MUMBAI_REGIONS.items():
            print(f">>> Fetching: {region}")
            query = f"""[out:json][timeout:90];(node["amenity"](around:2500,{coords[0]},{coords[1]});node["shop"](around:2500,{coords[0]},{coords[1]});node["leisure"](around:2500,{coords[0]},{coords[1]});node["tourism"](around:2500,{coords[0]},{coords[1]}););out body;"""
            try:
                result = api.query(query)
                ops = []
                for node in result.nodes:
                    name = node.tags.get("name")
                    if not name: continue 
                    cat = determine_category(node.tags)
                    doc = {"name": name, "lat": float(node.lat), "lng": float(node.lon), "tags": str(node.tags), "category": cat, "desc": f"{name} in {region}", "region": region}
                    ops.append(pymongo.UpdateOne({"name": name}, {"$set": doc}, upsert=True))
                if ops: collection.bulk_write(ops)
            except: pass
            time.sleep(1)
    except: pass

# ==========================================
# PART 2: BACKEND LOGIC
# ==========================================
def get_bearing(lat1, lon1, lat2, lon2):
    d_lon = math.radians(lon2 - lon1); lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
    return dirs[round(((math.degrees(math.atan2(x, y)) + 360) % 360) / 45)]

class Backend:
    def __init__(self):
        self.current_user = None; self.image_cache = {}
        try:
            self.client = pymongo.MongoClient(MONGO_URI); self.db = self.client[DB_NAME]
            self.users_col = self.db["users"]; self.loc_col = self.db["locations"]; self.req_col = self.db["requests"]; self.img_col = self.db["category_images"]
            self.load_images_into_memory()
        except: pass
        if self.users_col is not None: self.init_db(); self.reload_data()

    def init_db(self):
        if self.users_col.count_documents({"_id": "admin"}) == 0:
            self.users_col.insert_one({"_id": "admin", "password": "admin", "name": "Administrator", "role": "admin", "lat": 19.0269, "lng": 72.8383, "favorites": []})

    def load_images_into_memory(self):
        for doc in self.img_col.find():
            cat = doc["_id"]; binary_list = doc.get("image_data_list", [])
            if binary_list:
                img_objects = []
                for b_data in binary_list:
                    try: img_objects.append(ctk.CTkImage(Image.open(io.BytesIO(b_data)), size=(80, 80)))
                    except: pass
                if img_objects: self.image_cache[cat] = img_objects

    def reload_data(self):
        loc_data = list(self.loc_col.find())
        self.df_locations = pd.DataFrame(loc_data) if loc_data else pd.DataFrame(columns=["name", "tags", "desc", "lat", "lng", "category"])
        self.requests = list(self.req_col.find())

    def login(self, u, p):
        user = self.users_col.find_one({"_id": u, "password": p})
        if user: self.current_user = u; self.reload_data(); return True, "Success"
        return False, "Invalid credentials"

    def register(self, u, p, name, lat, lng):
        if self.users_col.find_one({"_id": u}): return False, "Taken"
        self.users_col.insert_one({"_id": u, "password": p, "name": name, "favorites": [], "role": "user", "lat": float(lat), "lng": float(lng)})
        self.current_user = u; self.reload_data(); return True, "Success"

    def update_profile(self, name, password, lat, lng):
        self.users_col.update_one({"_id": self.current_user}, {"$set": {"name": name, "password": password, "lat": float(lat), "lng": float(lng)}})
        self.reload_data()

    def submit_request(self, req_type, details):
        self.req_col.insert_one({"user": self.current_user, "type": req_type, "details": details, "status": "pending"}); self.reload_data()

    def delete_user(self, u): self.users_col.delete_one({"_id": u}); self.reload_data()
    def delete_location(self, n): self.loc_col.delete_one({"name": n}); self.reload_data()
    def resolve_request(self, i, d):
        r = self.requests[i]; self.req_col.update_one({"_id": r["_id"]}, {"$set": {"status": d}})
        if d == "accepted": self.loc_col.insert_one({"name": r['details']['name'], "tags": r['details']['tags'], "desc": r['details']['desc'], "category": "default", "lat": float(r['details'].get('lat', 19.0)), "lng": float(r['details'].get('lng', 72.8))})
        self.reload_data()

    def search(self, query):
        if not self.current_user or self.df_locations.empty: return []
        u = self.users_col.find_one({"_id": self.current_user})
        u_lat = u.get("lat", 19.0); u_lng = u.get("lng", 72.8)
        if not query: matched_df = self.df_locations
        else:
            pat = '|'.join([t.strip().lower() for t in query.split(",")])
            mask = (self.df_locations['tags'].str.lower().str.contains(pat, na=False)) | \
                   (self.df_locations['name'].str.lower().str.contains(pat, na=False)) | \
                   (self.df_locations['category'].str.lower().str.contains(pat, na=False))
            matched_df = self.df_locations[mask]

        results = []
        for _, row in matched_df.iterrows():
            if abs(row['lat'] - u_lat) > 0.5 or abs(row['lng'] - u_lng) > 0.5: continue
            dist = geodesic((u_lat, u_lng), (row['lat'], row['lng'])).meters
            if dist > 50000: continue 
            results.append({
                "name": row['name'], "category": row.get('category', 'default'), "lat": row['lat'], "lng": row['lng'], 
                "dist": round(dist), "bearing": get_bearing(u_lat, u_lng, row['lat'], row['lng']), 
                "rel_x": (row['lng']-u_lng)*111000*math.cos(math.radians(u_lat)), "rel_y": (row['lat']-u_lat)*111000
            })
        results.sort(key=lambda k: k['dist'])
        return results

# ==========================================
# PART 3: FRONTEND UI (OPTIMIZED)
# ==========================================
class UIState(Enum):
    AUTH = auto(); TUTORIAL = auto(); HOME = auto(); RESULTS = auto()
    SETTINGS = auto(); ADD_LOCATION = auto(); UPDATE_LOCATION = auto(); ADMIN = auto(); ABOUT = auto()

class CommuniFind(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.backend = Backend()
        self.ui_state = None; self.results = []
        self.title(APP_TITLE); self.geometry(WINDOW_SIZE); ctk.set_appearance_mode("light")
        self.container = ctk.CTkFrame(self, fg_color=COLOR_BG); self.container.pack(fill="both", expand=True)
        try: 
            self.logo_large = ctk.CTkImage(Image.open("logo.png"), size=(150, 150))
            self.logo_small = ctk.CTkImage(Image.open("logo.png"), size=(40, 40))
        except: self.logo_large = None; self.logo_small = None
        self.set_state(UIState.AUTH)

    def clear(self):
        for w in self.container.winfo_children(): w.destroy()

    def set_state(self, s):
        self.ui_state = s; self.clear()
        if s == UIState.AUTH: self.build_auth_selection()
        elif s == UIState.HOME: self.build_home()
        elif s == UIState.RESULTS: self.build_results()
        elif s == UIState.ADMIN: self.build_admin()
        elif s == UIState.ADD_LOCATION: self.build_add_location()
        elif s == UIState.SETTINGS: self.build_settings()
        elif s == UIState.TUTORIAL: self.build_tutorial()
        elif s == UIState.ABOUT: self.build_about()

    def get_db_image(self, category, place_name):
        images = self.backend.image_cache.get(category) or self.backend.image_cache.get("default")
        if not images: return None
        return images[sum(ord(c) for c in place_name) % len(images)]

    def build_topbar(self, back=False):
        bar = ctk.CTkFrame(self.container, height=70, fg_color=COLOR_CARD); bar.pack(fill="x", padx=15, pady=10)
        left = ctk.CTkFrame(bar, fg_color="transparent"); left.pack(side="left", padx=10)
        if back: ctk.CTkButton(left, text="⬅", width=40, fg_color="transparent", text_color=COLOR_TEXT, hover_color=COLOR_BG, command=lambda: self.set_state(UIState.HOME)).pack(side="left", padx=5)
        if self.logo_small: ctk.CTkLabel(left, image=self.logo_small, text="").pack(side="left", padx=5)
        ctk.CTkLabel(left, text=APP_TITLE, font=("Segoe UI", 20, "bold"), text_color=COLOR_PRIMARY).pack(side="left")
        ctk.CTkButton(bar, text="Logout", width=80, fg_color=COLOR_ERROR, command=lambda: self.set_state(UIState.AUTH)).pack(side="right", padx=10)
        if self.backend.current_user: ctk.CTkButton(bar, text="⚙", width=40, fg_color="transparent", text_color=COLOR_MUTED, hover_color=COLOR_BG, command=lambda: self.set_state(UIState.SETTINGS)).pack(side="right")

    def build_auth_selection(self):
        box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        box.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(padx=80, pady=60)
        if self.logo_large: ctk.CTkLabel(inner, image=self.logo_large, text="").pack(pady=10)
        ctk.CTkLabel(inner, text="CommuniFind", font=("Segoe UI", 32, "bold"), text_color=COLOR_PRIMARY).pack()
        ctk.CTkLabel(inner, text="Offline Local Discovery", font=("Segoe UI", 16), text_color=COLOR_MUTED).pack(pady=(0, 20))
        ctk.CTkButton(inner, text="Login", width=250, height=45, fg_color=COLOR_PRIMARY, command=self.build_login).pack(pady=10)
        ctk.CTkButton(inner, text="Create Account", width=250, height=45, fg_color="transparent", border_width=2, border_color=COLOR_PRIMARY, text_color=COLOR_PRIMARY, command=self.build_register).pack(pady=10)
        ctk.CTkButton(inner, text="How does it work?", fg_color="transparent", text_color=COLOR_MUTED, hover_color=COLOR_BG, command=self.open_help_modal).pack(pady=5)

    def build_login(self):
        self.clear(); box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD, corner_radius=20); box.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(padx=60, pady=50)
        ctk.CTkLabel(inner, text="Welcome Back", font=("Segoe UI", 24, "bold"), text_color=COLOR_TEXT).pack(pady=20)
        u = ctk.CTkEntry(inner, placeholder_text="Username", width=280, height=40); u.pack(pady=10)
        p = ctk.CTkEntry(inner, placeholder_text="Password", show="*", width=280, height=40); p.pack(pady=10)
        def do_login():
            if self.backend.login(u.get(), p.get())[0]: self.set_state(UIState.ADMIN if self.backend.users_col.find_one({"_id": self.backend.current_user})['role'] == 'admin' else UIState.HOME)
            else: messagebox.showerror("Error", "Invalid Credentials")
        ctk.CTkButton(inner, text="Sign In", width=280, height=45, fg_color=COLOR_PRIMARY, command=do_login).pack(pady=20)
        ctk.CTkButton(inner, text="Back", fg_color="transparent", text_color=COLOR_MUTED, command=lambda: self.set_state(UIState.AUTH)).pack()

    def build_register(self):
        self.clear(); box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD, corner_radius=20); box.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(padx=60, pady=40)
        ctk.CTkLabel(inner, text="New Account", font=("Segoe UI", 24, "bold"), text_color=COLOR_TEXT).pack(pady=20)
        rn = ctk.CTkEntry(inner, placeholder_text="Full Name", width=280); rn.pack(pady=5)
        ru = ctk.CTkEntry(inner, placeholder_text="Username", width=280); ru.pack(pady=5)
        rp = ctk.CTkEntry(inner, placeholder_text="Password", show="*", width=280); rp.pack(pady=5)
        ctk.CTkLabel(inner, text="Select Hub:", text_color=COLOR_MUTED).pack(pady=(10,0), anchor="w")
        loc = ctk.CTkOptionMenu(inner, values=list(MUMBAI_REGIONS.keys()), width=280); loc.pack(pady=5)
        def do_reg():
            if self.backend.register(ru.get(), rp.get(), rn.get(), MUMBAI_REGIONS[loc.get()][0], MUMBAI_REGIONS[loc.get()][1])[0]: self.set_state(UIState.TUTORIAL)
            else: messagebox.showerror("Error", "Username taken")
        ctk.CTkButton(inner, text="Sign Up", width=280, height=45, fg_color=COLOR_PRIMARY, command=do_reg).pack(pady=20)
        ctk.CTkButton(inner, text="Back", fg_color="transparent", text_color=COLOR_MUTED, command=lambda: self.set_state(UIState.AUTH)).pack()

    def build_home(self):
        self.build_topbar()
        center = ctk.CTkFrame(self.container, fg_color="transparent"); center.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(center, text="Find nearby...", font=("Segoe UI", 36, "bold"), text_color=COLOR_TEXT).pack(pady=10)
        chips = ctk.CTkFrame(center, fg_color="transparent"); chips.pack(pady=10)
        for tag in ["Hospital", "Park", "Mall", "Museum", "Parking"]:
            ctk.CTkButton(chips, text=tag, width=80, height=30, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER, text_color=COLOR_TEXT, hover_color=COLOR_SECONDARY, command=lambda t=tag: self.do_search(t)).pack(side="left", padx=5)
        self.search_entry = ctk.CTkEntry(center, width=600, height=60, placeholder_text="Search (e.g., wifi, toilet, library)...", corner_radius=30, border_width=2, border_color=COLOR_PRIMARY, font=("Segoe UI", 16))
        self.search_entry.pack(pady=30)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        ctk.CTkButton(center, text="🔍 Find Places", command=self.do_search, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, width=200, height=50, corner_radius=25, font=("Segoe UI", 16, "bold")).pack()
        ctk.CTkLabel(center, text=f"💡 Tip: {random.choice(SAFETY_TIPS)}", font=("Segoe UI", 12, "italic"), text_color=COLOR_MUTED).pack(pady=30)
        if self.backend.current_user:
            u_data = self.backend.users_col.find_one({"_id": self.backend.current_user})
            if u_data and u_data.get("role") == "admin":
                 ctk.CTkButton(center, text="Admin Panel", fg_color="transparent", border_width=1, border_color=COLOR_MUTED, text_color=COLOR_MUTED, command=lambda: self.set_state(UIState.ADMIN)).pack(pady=10)

    def do_search(self, query=None):
        q = query if query else self.search_entry.get().strip()
        if not q: return
        self.results = self.backend.search(q); self.set_state(UIState.RESULTS)

    def build_results(self):
        self.build_topbar(back=True)
        split = ctk.CTkFrame(self.container, fg_color="transparent"); split.pack(fill="both", expand=True, padx=20, pady=10)
        left = ctk.CTkScrollableFrame(split, width=450, fg_color="transparent"); left.pack(side="left", fill="both", padx=10)
        right = ctk.CTkFrame(split, fg_color="white", corner_radius=15); right.pack(side="right", fill="both", expand=True)
        
        if not self.results: ctk.CTkLabel(left, text="No places found nearby.", font=("Arial", 16)).pack(pady=50); return

        display_results = self.results[:30] # Limit to 30
        if len(self.results) > 30: ctk.CTkLabel(left, text=f"Top 30 of {len(self.results)} results shown", text_color=COLOR_WARN).pack(pady=5)

        fig = Figure(figsize=(5, 4), dpi=100); ax = fig.add_subplot(111); ax.set_facecolor("#FAFAFA")
        canvas = FigureCanvasTkAgg(fig, master=right); canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        def draw_map(focus_idx=None):
            ax.clear(); ax.scatter([0], [0], color=COLOR_PRIMARY, s=150, marker="^", label="You", zorder=10)
            ax.text(0, -50, "YOU", ha='center', va='top', fontsize=10, fontweight='bold', color=COLOR_PRIMARY)
            all_x = [r['rel_x'] for r in display_results]; all_y = [r['rel_y'] for r in display_results]
            ax.scatter(all_x, all_y, color=COLOR_MUTED, alpha=0.3, s=30, zorder=5)
            if focus_idx is None:
                if all_x:
                    padding = max(500, max(max(all_x)-min(all_x), max(all_y)-min(all_y)) * 0.1)
                    ax.set_xlim(min(all_x+[0])-padding, max(all_x+[0])+padding)
                    ax.set_ylim(min(all_y+[0])-padding, max(all_y+[0])+padding)
            else:
                target = display_results[focus_idx]; tx, ty = target['rel_x'], target['rel_y']
                ax.plot([0, tx], [0, ty], color=COLOR_WARN, linewidth=2, linestyle="--", zorder=8)
                ax.scatter([tx], [ty], color=COLOR_WARN, s=150, edgecolor='black', zorder=11, marker='*')
                ax.text(tx/2, ty/2, f"{target['dist']}m", ha='center', va='center', fontsize=9, fontweight='bold', color='white', bbox=dict(facecolor=COLOR_WARN, edgecolor='none', alpha=0.8))
                margin = max(abs(tx), abs(ty)) * 0.3 + 200
                ax.set_xlim(min(0, tx)-margin, max(0, tx)+margin); ax.set_ylim(min(0, ty)-margin, max(0, ty)+margin)
            ax.grid(True, linestyle=":", alpha=0.6); canvas.draw()

        draw_map(None)

        for i, res in enumerate(display_results):
            card = ctk.CTkFrame(left, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER)
            card.pack(fill="x", pady=8)
            img = self.get_db_image(res['category'], res['name'])
            if img: ctk.CTkLabel(card, image=img, text="").pack(side="left", padx=15, pady=15)
            info = ctk.CTkFrame(card, fg_color="transparent"); info.pack(side="left", padx=5)
            icon = CATEGORY_EMOJIS.get(res['category'], "📍")
            safe_name = ''.join([c for c in res['name'] if ord(c) < 128])[:25]
            ctk.CTkLabel(info, text=f"{icon} {safe_name}", font=("Segoe UI", 15, "bold"), text_color=COLOR_TEXT).pack(anchor="w")
            ctk.CTkLabel(info, text=f"{res['dist']}m • {res['category'].title()}", text_color=COLOR_MUTED, font=("Segoe UI", 12)).pack(anchor="w")
            ctk.CTkButton(card, text="📍 Locate", width=80, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, corner_radius=20, command=lambda idx=i: draw_map(idx)).pack(side="right", padx=15)

    def build_admin(self):
        self.backend.reload_data(); self.build_topbar(back=True)
        tabs = ctk.CTkTabview(self.container); tabs.pack(fill="both", expand=True, padx=20, pady=20)
        tabs.add("Requests"); tabs.add("Users"); tabs.add("Locations")
        
        # --- FIXED ADMIN PANEL (LIMIT TO 50) ---
        r_frame = ctk.CTkScrollableFrame(tabs.tab("Requests"), fg_color="transparent"); r_frame.pack(fill="both", expand=True)
        for idx, req in enumerate(self.backend.requests):
            if req['status'] == 'pending':
                card = ctk.CTkFrame(r_frame, fg_color=COLOR_CARD); card.pack(fill="x", pady=5)
                ctk.CTkLabel(card, text=f"{req['details']['name']}", text_color="black").pack(side="left", padx=10)
                ctk.CTkButton(card, text="✔", width=40, fg_color=COLOR_SUCCESS, command=lambda: [self.backend.resolve_request(idx, "accepted"), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
                ctk.CTkButton(card, text="❌", width=40, fg_color=COLOR_ERROR, command=lambda: [self.backend.resolve_request(idx, "declined"), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
        
        u_frame = ctk.CTkScrollableFrame(tabs.tab("Users"), fg_color="transparent"); u_frame.pack(fill="both", expand=True)
        # Limit users to first 50 to prevent freezing
        for u in list(self.backend.users_col.find().limit(50)):
            card = ctk.CTkFrame(u_frame, fg_color=COLOR_CARD); card.pack(fill="x", pady=5)
            ctk.CTkLabel(card, text=f"{u['_id']} ({u['role']})", text_color="black").pack(side="left", padx=10)
            if u['role'] != 'admin': ctk.CTkButton(card, text="🗑", width=40, fg_color=COLOR_ERROR, command=lambda n=u['_id']: [self.backend.delete_user(n), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
        
        l_frame = ctk.CTkScrollableFrame(tabs.tab("Locations"), fg_color="transparent"); l_frame.pack(fill="both", expand=True)
        # Limit locations to first 50
        locs_subset = self.backend.df_locations.head(50)
        for _, l in locs_subset.iterrows():
            card = ctk.CTkFrame(l_frame, fg_color=COLOR_CARD); card.pack(fill="x", pady=2)
            safe_l = ''.join([c for c in l['name'] if ord(c) < 128])
            ctk.CTkLabel(card, text=safe_l, text_color="black").pack(side="left", padx=10)
            ctk.CTkButton(card, text="🗑", width=40, fg_color=COLOR_ERROR, command=lambda n=l['name']: [self.backend.delete_location(n), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
        
        if len(self.backend.df_locations) > 50:
            ctk.CTkLabel(l_frame, text="...Showing first 50 locations only...", text_color="gray").pack(pady=10)

    def build_settings(self):
        self.build_topbar(back=True)
        box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD); box.place(relx=0.5, rely=0.5, anchor="center")
        u_data = self.backend.users_col.find_one({"_id": self.backend.current_user})
        e_name = ctk.CTkEntry(box); e_name.insert(0, u_data.get("name", "")); e_name.pack(pady=5)
        e_pass = ctk.CTkEntry(box); e_pass.insert(0, u_data.get("password", "")); e_pass.pack(pady=5)
        loc = ctk.CTkOptionMenu(box, values=list(MUMBAI_REGIONS.keys())); loc.pack(pady=5)
        def save():
            lat, lng = MUMBAI_REGIONS[loc.get()]
            self.backend.update_profile(e_name.get(), e_pass.get(), lat, lng); self.set_state(UIState.HOME)
        ctk.CTkButton(box, text="Save", command=save, fg_color=COLOR_PRIMARY).pack(pady=20)

    def build_add_location(self):
        self.build_topbar(back=True)
        box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD); box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text="Suggest New Place", font=("Segoe UI", 20, "bold")).pack(pady=20)
        e_name = ctk.CTkEntry(box, placeholder_text="Name"); e_name.pack(pady=5)
        e_tags = ctk.CTkEntry(box, placeholder_text="Tags"); e_tags.pack(pady=5)
        e_desc = ctk.CTkTextbox(box, height=80); e_desc.pack(pady=5)
        def sub():
            self.backend.submit_request("new_place", {"name": e_name.get(), "tags": e_tags.get(), "desc": e_desc.get("0.0", "end")})
            messagebox.showinfo("Sent", "Request sent."); self.set_state(UIState.HOME)
        ctk.CTkButton(box, text="Submit", command=sub, fg_color=COLOR_PRIMARY).pack(pady=20)

    def open_help_modal(self):
        top = ctk.CTkToplevel(self); top.geometry("400x350"); top.title("Help"); top.attributes('-topmost', True)
        ctk.CTkLabel(top, text="How to use CommuniFind 🛠️", font=("Segoe UI", 20, "bold"), text_color=COLOR_PRIMARY).pack(pady=20)
        ctk.CTkLabel(top, text="1. Login or Register to get started.\n\n2. Type tags like 'wifi', 'toilet', or 'park'.\n\n3. Click 'Locate' to see the path on the map.", font=("Segoe UI", 14), justify="left").pack(padx=20)
        ctk.CTkButton(top, text="Got it!", fg_color=COLOR_PRIMARY, command=top.destroy).pack(pady=30)

    def build_tutorial(self): self.build_home()
    def build_about(self): 
        box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD, corner_radius=15); box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text="About CommuniFind", font=("Segoe UI", 20, "bold"), text_color=COLOR_PRIMARY).pack(pady=(30, 10))
        ctk.CTkLabel(box, text="Offline Discovery Tool\nVersion 1.0.0", font=("Segoe UI", 14)).pack(padx=40, pady=10)
        ctk.CTkButton(box, text="Back", command=lambda: self.set_state(UIState.AUTH), fg_color=COLOR_MUTED).pack(pady=30)
    def build_update_location(self): pass

if __name__ == "__main__":
    fetch_and_populate_db() 
    app = CommuniFind()
    app.mainloop()
