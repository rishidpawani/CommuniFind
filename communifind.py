import customtkinter as ctk
import tkinter as tk
from enum import Enum, auto
from PIL import Image, ImageTk, ImageOps, ImageDraw
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
import datetime

# --- CONFIGURATION ---
warnings.filterwarnings("ignore") 
APP_TITLE = "CommuniFind (Offline Mode)"
WINDOW_SIZE = "1300x850"

# --- THEME & COLORS ---
COLOR_BG = "#E8F5E9"          # Light Green Background
COLOR_CARD = "#FFFFFF"        # White Card
COLOR_PRIMARY = "#2E7D32"     # Forest Green (Normal)
COLOR_PRIMARY_HOVER = "#1976D2" # Blue Hover Effect
COLOR_SECONDARY = "#81C784"   # Light Green
COLOR_TEXT = "#1B5E20"        # Dark Green Text
COLOR_TEXT_LIGHT = "#546E7A"  # Grey Text
COLOR_MUTED = "#607D8B"       # Blue Grey
COLOR_ERROR = "#D32F2F"       # Red
COLOR_WARN = "#F57F17"        # Orange
COLOR_BORDER = "#A5D6A7"      
COLOR_ACCENT = "#C8E6C9"      
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
    "Ghatkopar - Metro": (19.0860, 72.9090),
    "Mulund - West": (19.1726, 72.9425),
    "Thane - City": (19.2183, 72.9781),
    "Powai - Lake": (19.1176, 72.9060),
    "Navi Mumbai - Vashi": (19.0770, 72.9980),
    "Navi Mumbai - Nerul": (19.0330, 73.0297),
    "Navi Mumbai - Kharghar": (19.0298, 73.0726),
    "Panvel - City": (18.9894, 73.1175),
    "Dombivli - Station": (19.2183, 73.0868),
    "Kalyan - Junction": (19.2403, 73.1305)
}

CATEGORY_EMOJIS = {
    "hospital": "🏥", "hotel": "🏨", "park": "🌳", "entertainment": "🎬",
    "museum": "🏛️", "shop": "🛒", "parking": "🅿️", "default": "📍"
}

SAFETY_TIPS = [
    "🚗 Safety: Always wear a seatbelt.",
    "💡 Tip: Use 'hospital' to find emergency care.",
    "🌍 Map: The map zooms automatically to your results!",
    "⭐ Pro Tip: Save your frequent locations.",
    "🚶 Walking: Use zebra crossings and look right-left-right.",
    "🏍️ Bike: Always wear a helmet, even for short rides."
]

# ==========================================
# PART 1: DATABASE SETUP
# ==========================================
def determine_category(tags_dict):
    tag_str = str(tags_dict).lower()
    if 'parking' in tag_str: return 'parking'
    if any(x in tag_str for x in ['cinema', 'theatre', 'movie', 'multiplex', 'entertainment']): return 'entertainment'
    if any(x in tag_str for x in ['hospital', 'clinic', 'pharmacy', 'doctor', 'police', 'fire']): return 'hospital'
    if any(x in tag_str for x in ['park', 'garden', 'playground', 'nature']): return 'park'
    if any(x in tag_str for x in ['museum', 'gallery', 'attraction', 'historic', 'art']): return 'museum'
    if any(x in tag_str for x in ['hotel', 'guest_house', 'restaurant', 'cafe']): return 'hotel' 
    if any(x in tag_str for x in ['mall', 'supermarket', 'department_store', 'shop']): return 'shop'
    return 'default'

def populate_images_db(db):
    col = db.category_images
    if not os.path.exists("assets"): return
    if col.count_documents({}) > 0: return 
    print(">>> Uploading images to Database...")
    categories = ["hospital", "hotel", "park", "museum", "shop", "parking", "default", "entertainment"]
    all_files = os.listdir("assets")
    for cat in categories:
        search_cat = "museum" if cat == "entertainment" else cat 
        cat_files = [f for f in all_files if f.lower().startswith(search_cat) and f.lower().endswith(('.jpg', '.jpeg', '.png'))]
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
            query = f"""[out:json][timeout:90];(node["amenity"](around:2500,{coords[0]},{coords[1]});node["shop"](around:2500,{coords[0]},{coords[1]});node["leisure"](around:2500,{coords[0]},{coords[1]});node["tourism"](around:2500,{coords[0]},{coords[1]}););out body;"""
            try:
                result = api.query(query)
                ops = []
                for node in result.nodes:
                    name = node.tags.get("name")
                    if not name: continue 
                    cat = determine_category(node.tags)
                    doc = {"name": name, "lat": float(node.lat), "lng": float(node.lon), "tags": str(node.tags), "category": cat, "desc": f"{name} is a local {cat} in {region}.", "region": region}
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
            self.reviews_col = self.db["reviews"]
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
                    try: 
                        pil_img = Image.open(io.BytesIO(b_data))
                        mask = Image.new("L", pil_img.size, 0)
                        draw = ImageDraw.Draw(mask)
                        draw.ellipse((0, 0) + pil_img.size, fill=255)
                        rounded_img = ImageOps.fit(pil_img, mask.size, centering=(0.5, 0.5))
                        rounded_img.putalpha(mask)
                        img_objects.append(ctk.CTkImage(rounded_img, size=(80, 80)))
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

    def add_review(self, loc_name, review_text):
        self.reviews_col.insert_one({"location": loc_name, "user": self.current_user, "text": review_text, "date": datetime.datetime.now().strftime("%Y-%m-%d")})

    def get_reviews(self, loc_name):
        return list(self.reviews_col.find({"location": loc_name}).sort("date", -1))

    def toggle_favorite(self, loc_name):
        u = self.users_col.find_one({"_id": self.current_user})
        favs = u.get("favorites", [])
        if loc_name in favs: favs.remove(loc_name)
        else: favs.append(loc_name)
        self.users_col.update_one({"_id": self.current_user}, {"$set": {"favorites": favs}})
        return loc_name in favs

    def is_favorite(self, loc_name):
        u = self.users_col.find_one({"_id": self.current_user})
        return loc_name in u.get("favorites", [])

    def search(self, query):
        if not self.current_user or self.df_locations.empty: return []
        u = self.users_col.find_one({"_id": self.current_user})
        u_lat = u.get("lat", 19.0); u_lng = u.get("lng", 72.8)
        
        q = query.lower().strip() if query else ""
        matched_df = self.df_locations

        if query == "FAVORITES_ONLY":
            favs = u.get("favorites", [])
            matched_df = self.df_locations[self.df_locations['name'].isin(favs)]
        elif q == 'park':
            matched_df = self.df_locations[self.df_locations['category'] == 'park']
        elif q == 'parking':
            matched_df = self.df_locations[self.df_locations['category'] == 'parking']
        elif q:
            pat = '|'.join([t.strip() for t in q.split(",")])
            mask = (self.df_locations['tags'].str.lower().str.contains(pat, na=False)) | \
                   (self.df_locations['name'].str.lower().str.contains(pat, na=False)) | \
                   (self.df_locations['category'].str.lower().str.contains(pat, na=False))
            matched_df = self.df_locations[mask]

        results = []
        for _, row in matched_df.iterrows():
            if abs(row['lat'] - u_lat) > 0.2 or abs(row['lng'] - u_lng) > 0.2: continue 
            dist = geodesic((u_lat, u_lng), (row['lat'], row['lng'])).meters
            if dist > 10000: continue 
            results.append({
                "name": row['name'], "category": row.get('category', 'default'), "lat": row['lat'], "lng": row['lng'], 
                "dist": round(dist), "bearing": get_bearing(u_lat, u_lng, row['lat'], row['lng']), 
                "rel_x": (row['lng']-u_lng)*111000*math.cos(math.radians(u_lat)), "rel_y": (row['lat']-u_lat)*111000,
                "desc": row.get('desc', "No description available.")
            })
        results.sort(key=lambda k: k['dist'])
        return results

# ==========================================
# PART 3: FRONTEND UI
# ==========================================
class UIState(Enum):
    AUTH = auto(); LOGIN = auto(); REGISTER = auto(); HOME = auto(); RESULTS = auto()
    SETTINGS = auto(); ADD_LOCATION = auto(); UPDATE_LOCATION = auto(); ADMIN = auto(); ABOUT = auto(); TUTORIAL = auto()

class CommuniFind(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.backend = Backend()
        self.ui_state = None; self.results = []
        self.history_stack = []
        self.title(APP_TITLE); self.geometry(WINDOW_SIZE); ctk.set_appearance_mode("light")
        self.container = ctk.CTkFrame(self, fg_color=COLOR_BG); self.container.pack(fill="both", expand=True)
        try: 
            self.logo_large = ctk.CTkImage(Image.open("logo.png"), size=(180, 180))
            self.logo_small = ctk.CTkImage(Image.open("logo.png"), size=(60, 60))
        except: self.logo_large = None; self.logo_small = None
        self.set_state(UIState.AUTH)

    # --- HELPER FUNCTIONS ---
    def clear(self):
        for w in self.container.winfo_children(): w.destroy()

    def set_state(self, s, push_history=True):
        if push_history and self.ui_state and self.ui_state != s:
            self.history_stack.append(self.ui_state)
        self.clear()
        self.ui_state = s
        if s == UIState.AUTH: self.build_auth_selection()
        elif s == UIState.LOGIN: self.build_login()
        elif s == UIState.REGISTER: self.build_register()
        elif s == UIState.HOME: self.build_home()
        elif s == UIState.RESULTS: self.build_results()
        elif s == UIState.ADMIN: self.build_admin()
        elif s == UIState.ADD_LOCATION: self.build_add_location()
        elif s == UIState.SETTINGS: self.build_settings()
        elif s == UIState.TUTORIAL: self.build_tutorial()
        elif s == UIState.ABOUT: self.build_about()

    def go_back(self):
        if self.history_stack:
            prev = self.history_stack.pop()
            self.set_state(prev, push_history=False)
        else:
            self.set_state(UIState.AUTH, push_history=False)

    def show_custom_popup(self, title, msg, is_confirm=False, on_yes=None):
        top = ctk.CTkToplevel(self)
        top.geometry("420x220")
        top.title(title)
        top.attributes('-topmost', True)
        x = self.winfo_x() + (self.winfo_width() // 2) - 210
        y = self.winfo_y() + (self.winfo_height() // 2) - 110
        top.geometry(f"+{x}+{y}")
        
        bg = ctk.CTkFrame(top, fg_color=COLOR_CARD, border_width=2, border_color=COLOR_PRIMARY)
        bg.pack(fill="both", expand=True, padx=2, pady=2)
        ctk.CTkLabel(bg, text=title, font=("Segoe UI", 18, "bold"), text_color=COLOR_PRIMARY).pack(pady=(20, 5))
        ctk.CTkLabel(bg, text=msg, font=("Segoe UI", 14), text_color=COLOR_TEXT, wraplength=380).pack(pady=10)
        btn_frame = ctk.CTkFrame(bg, fg_color="transparent"); btn_frame.pack(pady=20)
        
        if is_confirm:
            ctk.CTkButton(btn_frame, text="Yes", fg_color=COLOR_ERROR, hover_color="#C62828", corner_radius=20, width=100, command=lambda: [top.destroy(), on_yes()]).pack(side="left", padx=10)
            ctk.CTkButton(btn_frame, text="Cancel", fg_color=COLOR_MUTED, hover_color=COLOR_PRIMARY_HOVER, corner_radius=20, width=100, command=top.destroy).pack(side="left", padx=10)
        else:
            ctk.CTkButton(btn_frame, text="OK", fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, corner_radius=20, width=100, command=top.destroy).pack()

    def logout_confirm(self):
        def perform_logout():
            self.history_stack = []
            self.backend.current_user = None
            self.set_state(UIState.AUTH, push_history=False)
        self.show_custom_popup("Logout", "Are you sure you want to log out?", is_confirm=True, on_yes=perform_logout)

    def get_db_image(self, category, place_name):
        images = self.backend.image_cache.get(category) or self.backend.image_cache.get("default")
        if not images: return None
        return images[sum(ord(c) for c in place_name) % len(images)]

    def open_help_modal(self):
        self.show_custom_popup("Help", "1. Login or Register.\n2. Search Tags (park, wifi).\n3. Click 📍 to Locate on Map.")

    # --- UI SCREENS ---
    def build_topbar(self, back=False):
        bar = ctk.CTkFrame(self.container, height=80, fg_color=COLOR_CARD); bar.pack(fill="x", padx=15, pady=10)
        left = ctk.CTkFrame(bar, fg_color="transparent"); left.pack(side="left", padx=10)
        if back: ctk.CTkButton(left, text="⬅", width=40, fg_color="transparent", text_color=COLOR_TEXT, hover_color=COLOR_BG, corner_radius=20, command=self.go_back).pack(side="left", padx=5)
        if self.logo_small: ctk.CTkLabel(left, image=self.logo_small, text="").pack(side="left", padx=5)
        
        ctk.CTkButton(bar, text="Logout", width=80, fg_color=COLOR_ERROR, hover_color="#B71C1C", corner_radius=25, command=self.logout_confirm).pack(side="right", padx=10)
        if self.backend.current_user: ctk.CTkButton(bar, text="⚙", width=40, fg_color="transparent", text_color=COLOR_MUTED, hover_color=COLOR_BG, corner_radius=20, command=lambda: self.set_state(UIState.SETTINGS)).pack(side="right")

    def build_auth_selection(self):
        bg = ctk.CTkFrame(self.container, fg_color=COLOR_BG); bg.pack(fill="both", expand=True)
        # **LEFT SIDE PANEL**
        side = ctk.CTkFrame(bg, fg_color=COLOR_PRIMARY, width=350, corner_radius=0); side.pack(side="left", fill="y")
        if self.logo_large: ctk.CTkLabel(side, image=self.logo_large, text="").place(relx=0.5, rely=0.4, anchor="center")
        ctk.CTkLabel(side, text="CommuniFind", font=("Segoe UI", 32, "bold"), text_color="white").place(relx=0.5, rely=0.6, anchor="center")
        ctk.CTkLabel(side, text="Offline Local Discovery", font=("Segoe UI", 16), text_color="#E8F5E9").place(relx=0.5, rely=0.65, anchor="center")

        # **RIGHT SIDE (BUTTONS)**
        right = ctk.CTkFrame(bg, fg_color="transparent"); right.pack(side="right", expand=True, fill="both")
        inner = ctk.CTkFrame(right, fg_color=COLOR_CARD, corner_radius=25); inner.place(relx=0.5, rely=0.5, anchor="center")
        content = ctk.CTkFrame(inner, fg_color="transparent"); content.pack(padx=60, pady=60)
        
        ctk.CTkLabel(content, text="Get Started", font=("Segoe UI", 28, "bold"), text_color=COLOR_TEXT).pack(pady=(0, 30))
        ctk.CTkButton(content, text="Login", width=250, height=50, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, font=("Segoe UI", 16, "bold"), corner_radius=25, command=lambda: self.set_state(UIState.LOGIN)).pack(pady=10)
        ctk.CTkButton(content, text="Create Account", width=250, height=50, fg_color="transparent", border_width=2, border_color=COLOR_PRIMARY, text_color=COLOR_PRIMARY, hover_color="#E3F2FD", font=("Segoe UI", 16, "bold"), corner_radius=25, command=lambda: self.set_state(UIState.REGISTER)).pack(pady=10)
        ctk.CTkButton(content, text="How does it work?", fg_color="transparent", text_color=COLOR_MUTED, hover_color=COLOR_BG, command=self.open_help_modal).pack(pady=5)
        ctk.CTkButton(content, text="About Us", fg_color="transparent", text_color=COLOR_MUTED, hover_color=COLOR_BG, command=lambda: self.set_state(UIState.ABOUT)).pack(pady=5)

    def build_login(self):
        self.build_form_screen("Welcome Back", "Login to continue", is_register=False)

    def build_register(self):
        self.build_form_screen("Create Account", "Join the community", is_register=True)

    def build_form_screen(self, title, subtitle, is_register):
        bg = ctk.CTkFrame(self.container, fg_color=COLOR_BG); bg.pack(fill="both", expand=True)
        # **LEFT SIDE PANEL**
        side = ctk.CTkFrame(bg, fg_color=COLOR_PRIMARY, width=350, corner_radius=0); side.pack(side="left", fill="y")
        if self.logo_large: ctk.CTkLabel(side, image=self.logo_large, text="").place(relx=0.5, rely=0.5, anchor="center")

        # **FORM CARD**
        card = ctk.CTkFrame(bg, fg_color=COLOR_CARD, corner_radius=25); card.place(relx=0.6, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(card, fg_color="transparent"); inner.pack(padx=60, pady=50)
        ctk.CTkLabel(inner, text=title, font=("Segoe UI", 28, "bold"), text_color=COLOR_TEXT).pack(pady=(0, 5))
        ctk.CTkLabel(inner, text=subtitle, font=("Segoe UI", 14), text_color=COLOR_MUTED).pack(pady=(0, 25))
        
        rn_entry = None
        if is_register: rn_entry = ctk.CTkEntry(inner, placeholder_text="Full Name", width=280, height=45, corner_radius=15); rn_entry.pack(pady=8)
        u_entry = ctk.CTkEntry(inner, placeholder_text="Username", width=280, height=45, corner_radius=15); u_entry.pack(pady=8)
        
        # **CENTERED ICON IN BUTTON**
        p_frame = ctk.CTkFrame(inner, fg_color="transparent"); p_frame.pack(pady=8)
        p_entry = ctk.CTkEntry(p_frame, placeholder_text="Password", show="*", width=235, height=45, corner_radius=15)
        p_entry.pack(side="left")
        def toggle():
            state = p_entry.cget("show")
            p_entry.configure(show="" if state=="*" else "*")
            btn_eye.configure(text="🔒" if state=="*" else "👁")
        btn_eye = ctk.CTkButton(p_frame, text="👁", width=45, height=45, fg_color=COLOR_ACCENT, text_color=COLOR_PRIMARY, hover_color=COLOR_SECONDARY, corner_radius=15, command=toggle)
        btn_eye.pack(side="left", padx=5)

        loc_menu = None
        if is_register:
            ctk.CTkLabel(inner, text="Select Hub:", text_color=COLOR_MUTED, font=("Arial", 12)).pack(anchor="w", pady=(5,0))
            loc_menu = ctk.CTkOptionMenu(inner, values=list(MUMBAI_REGIONS.keys()), width=280, height=40, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, corner_radius=15); loc_menu.pack(pady=5)
        def action():
            if is_register:
                if not rn_entry.get() or not u_entry.get() or not p_entry.get(): self.show_custom_popup("Error", "All fields are required!"); return
                if self.backend.register(u_entry.get(), p_entry.get(), rn_entry.get(), MUMBAI_REGIONS[loc_menu.get()][0], MUMBAI_REGIONS[loc_menu.get()][1])[0]: self.set_state(UIState.TUTORIAL)
                else: self.show_custom_popup("Error", "Username already exists")
            else:
                if not u_entry.get() or not p_entry.get(): self.show_custom_popup("Error", "All fields are required!"); return
                if self.backend.login(u_entry.get(), p_entry.get())[0]: self.set_state(UIState.ADMIN if self.backend.users_col.find_one({"_id": self.backend.current_user})['role'] == 'admin' else UIState.HOME)
                else: self.show_custom_popup("Error", "Invalid Credentials")
        btn_text = "Create Account" if is_register else "Sign In"
        ctk.CTkButton(inner, text=btn_text, width=280, height=50, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, font=("Segoe UI", 16, "bold"), corner_radius=25, command=action).pack(pady=20)
        ctk.CTkButton(inner, text="Back", fg_color="transparent", text_color=COLOR_MUTED, hover_color=COLOR_BG, command=self.go_back).pack()

    def build_home(self):
        self.build_topbar()
        hero = ctk.CTkFrame(self.container, fg_color=COLOR_ACCENT, height=120, corner_radius=0); hero.pack(fill="x")
        ctk.CTkLabel(hero, text="What are you looking for?", font=("Segoe UI", 32, "bold"), text_color=COLOR_PRIMARY).place(relx=0.5, rely=0.5, anchor="center")
        center = ctk.CTkFrame(self.container, fg_color="transparent"); center.pack(pady=40)
        chips = ctk.CTkFrame(center, fg_color="transparent"); chips.pack(pady=10)
        for tag in ["Hospital", "Park", "Mall", "Cinema", "Parking"]:
            ctk.CTkButton(chips, text=tag, width=90, height=35, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER, text_color=COLOR_TEXT, hover_color=COLOR_SECONDARY, corner_radius=20, command=lambda t=tag: self.do_search(t)).pack(side="left", padx=5)
        ctk.CTkButton(chips, text="❤ Favorites", width=90, height=35, fg_color=COLOR_SECONDARY, text_color="white", hover_color=COLOR_PRIMARY, corner_radius=20, command=lambda: self.do_search("FAVORITES_ONLY")).pack(side="left", padx=5)
        self.search_entry = ctk.CTkEntry(center, width=600, height=60, placeholder_text="Search tags (e.g., wifi, toilet, library)...", corner_radius=30, border_width=2, border_color=COLOR_PRIMARY, font=("Segoe UI", 16))
        self.search_entry.pack(pady=30)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        ctk.CTkButton(center, text="🔍 Search Now", command=self.do_search, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, width=220, height=55, corner_radius=27, font=("Segoe UI", 18, "bold")).pack()
        ctk.CTkLabel(center, text=f"💡 Tip: {random.choice(SAFETY_TIPS)}", font=("Segoe UI", 12, "italic"), text_color=COLOR_MUTED).pack(pady=30)
        if self.backend.current_user:
            u_data = self.backend.users_col.find_one({"_id": self.backend.current_user})
            if u_data and u_data.get("role") == "admin":
                 ctk.CTkButton(center, text="Admin Panel", fg_color="transparent", border_width=1, border_color=COLOR_MUTED, text_color=COLOR_MUTED, command=lambda: self.set_state(UIState.ADMIN)).pack(pady=10)

    def do_search(self, query=None):
        q = query if query else self.search_entry.get().strip()
        if not q: return
        self.results = self.backend.search(q); self.set_state(UIState.RESULTS)

    def open_details(self, result):
        top = ctk.CTkToplevel(self); top.geometry("600x600"); top.title(result['name']); top.attributes('-topmost', True)
        img = self.get_db_image(result['category'], result['name'])
        if img: ctk.CTkLabel(top, image=img, text="").pack(pady=10)
        ctk.CTkLabel(top, text=result['name'], font=("Nirmala UI", 22, "bold")).pack() 
        ctk.CTkLabel(top, text=f"{result['category'].title()} • {result['dist']}m away", text_color=COLOR_MUTED).pack()
        is_fav = self.backend.is_favorite(result['name'])
        btn_text = "💔 Unfavorite" if is_fav else "❤ Favorite"
        btn_col = COLOR_ERROR if is_fav else COLOR_SECONDARY
        def toggle_fav(): self.backend.toggle_favorite(result['name']); top.destroy(); self.open_details(result) 
        ctk.CTkButton(top, text=btn_text, fg_color=btn_col, hover_color=COLOR_PRIMARY_HOVER, height=30, corner_radius=15, command=toggle_fav).pack(pady=5)
        ctk.CTkLabel(top, text=result.get("desc", ""), wraplength=550, font=("Nirmala UI", 12)).pack(pady=10)
        ctk.CTkLabel(top, text="Reviews", font=("Segoe UI", 16, "bold")).pack(pady=(10, 5))
        rev_scroll = ctk.CTkScrollableFrame(top, height=200, fg_color="transparent"); rev_scroll.pack(fill="x", padx=20)
        reviews = self.backend.get_reviews(result['name'])
        if not reviews: ctk.CTkLabel(rev_scroll, text="No reviews yet.", text_color="gray").pack(pady=20)
        else:
            for r in reviews:
                f = ctk.CTkFrame(rev_scroll, fg_color=COLOR_CARD); f.pack(fill="x", pady=2)
                ctk.CTkLabel(f, text=f"{r['user']} ({r['date']})", font=("Arial", 10, "bold")).pack(anchor="w", padx=5)
                ctk.CTkLabel(f, text=r['text']).pack(anchor="w", padx=5)
        input_frame = ctk.CTkFrame(top); input_frame.pack(fill="x", padx=20, pady=10)
        e_rev = ctk.CTkEntry(input_frame, placeholder_text="Write a review..."); e_rev.pack(side="left", fill="x", expand=True, padx=5)
        def post():
            if not e_rev.get(): return
            self.backend.add_review(result['name'], e_rev.get()); top.destroy(); self.open_details(result)
            self.show_custom_popup("Success", "Review posted!")
        ctk.CTkButton(input_frame, text="Post", width=60, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, corner_radius=15, command=post).pack(side="right", padx=5)

    def build_results(self):
        self.build_topbar(back=True)
        split = ctk.CTkFrame(self.container, fg_color="transparent"); split.pack(fill="both", expand=True, padx=20, pady=10)
        left_side = ctk.CTkFrame(split, fg_color="transparent"); left_side.pack(side="left", fill="both", padx=10)
        u = self.backend.users_col.find_one({"_id": self.backend.current_user})
        nearest_reg = "Unknown"; min_d = float('inf')
        for name, coords in MUMBAI_REGIONS.items():
            d = abs(coords[0]-u['lat']) + abs(coords[1]-u['lng'])
            if d < min_d: min_d = d; nearest_reg = name
        ctk.CTkLabel(left_side, text=f"Searching near: {nearest_reg}", font=("Segoe UI", 14, "bold"), text_color=COLOR_PRIMARY).pack(pady=5, anchor="w")
        left_scroll = ctk.CTkScrollableFrame(left_side, width=450, fg_color="transparent"); left_scroll.pack(fill="both", expand=True)
        # **FIXED: SOLID BUTTON STYLE**
        ctk.CTkButton(left_side, text="Can't find it? Add Missing Place", fg_color=COLOR_CARD, border_width=2, border_color=COLOR_PRIMARY, text_color=COLOR_PRIMARY, hover_color="#E3F2FD", corner_radius=20, height=40, command=lambda: self.set_state(UIState.ADD_LOCATION)).pack(pady=10)
        right = ctk.CTkFrame(split, fg_color="white", corner_radius=15); right.pack(side="right", fill="both", expand=True)
        if not self.results: ctk.CTkLabel(left_scroll, text="No places found nearby (10km).", font=("Arial", 16)).pack(pady=50); return
        display_results = self.results[:50]
        if len(self.results) > 50: ctk.CTkLabel(left_scroll, text=f"Showing top 50 closest", text_color=COLOR_WARN).pack(pady=5)
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
                    ax.set_xlim(min(all_x+[0])-padding, max(all_x+[0])+padding); ax.set_ylim(min(all_y+[0])-padding, max(all_y+[0])+padding)
            else:
                target = display_results[focus_idx]; tx, ty = target['rel_x'], target['rel_y']
                ax.plot([0, tx], [0, ty], color=COLOR_WARN, linewidth=2, linestyle="--", zorder=8)
                ax.scatter([tx], [ty], color=COLOR_WARN, s=150, edgecolor='black', zorder=11, marker='*')
                # **FIXED: TEXT ON TOP OF LINE**
                ax.text(tx/2, ty/2, f"{target['dist']}m", ha='center', va='center', fontsize=9, fontweight='bold', color='white', bbox=dict(facecolor=COLOR_WARN, edgecolor='none', alpha=1.0, boxstyle='round,pad=0.3'), zorder=20)
                margin = max(abs(tx), abs(ty)) * 0.3 + 200
                ax.set_xlim(min(0, tx)-margin, max(0, tx)+margin); ax.set_ylim(min(0, ty)-margin, max(0, ty)+margin)
            ax.grid(True, linestyle=":", alpha=0.6); canvas.draw()
        draw_map(None)
        for i, res in enumerate(display_results):
            card = ctk.CTkFrame(left_scroll, fg_color=COLOR_CARD, corner_radius=15, border_width=1, border_color=COLOR_BORDER)
            card.pack(fill="x", pady=8)
            img = self.get_db_image(res['category'], res['name'])
            if img: ctk.CTkLabel(card, image=img, text="").pack(side="left", padx=15, pady=15)
            info = ctk.CTkFrame(card, fg_color="transparent"); info.pack(side="left", padx=5)
            icon = CATEGORY_EMOJIS.get(res['category'], "📍")
            safe_name = ''.join([c for c in res['name'] if ord(c) < 128])[:25]
            if not safe_name: safe_name = res['name'][:25]
            ctk.CTkLabel(info, text=f"{icon} {safe_name}", font=("Nirmala UI", 15, "bold"), text_color=COLOR_TEXT).pack(anchor="w")
            ctk.CTkLabel(info, text=f"{res['dist']}m • {res['category'].title()}", text_color=COLOR_MUTED, font=("Segoe UI", 12)).pack(anchor="w")
            btn_frame = ctk.CTkFrame(card, fg_color="transparent"); btn_frame.pack(side="right", padx=10)
            ctk.CTkButton(btn_frame, text="ℹ Info", width=60, fg_color=COLOR_SECONDARY, text_color="black", height=25, corner_radius=15, hover_color="#66BB6A", command=lambda r=res: self.open_details(r)).pack(pady=2)
            ctk.CTkButton(btn_frame, text="📍 Map", width=60, fg_color=COLOR_PRIMARY, height=25, corner_radius=15, hover_color=COLOR_PRIMARY_HOVER, command=lambda idx=i: draw_map(idx)).pack(pady=2)

    def build_admin(self):
        self.backend.reload_data(); self.build_topbar(back=True)
        tabs = ctk.CTkTabview(self.container); tabs.pack(fill="both", expand=True, padx=20, pady=20)
        tabs.add("Requests"); tabs.add("Users"); tabs.add("Locations")
        r_frame = ctk.CTkScrollableFrame(tabs.tab("Requests"), fg_color="transparent"); r_frame.pack(fill="both", expand=True)
        if not self.backend.requests: ctk.CTkLabel(r_frame, text="No pending requests", text_color=COLOR_MUTED).pack(pady=20)
        for idx, req in enumerate(self.backend.requests):
            if req['status'] == 'pending':
                card = ctk.CTkFrame(r_frame, fg_color=COLOR_CARD); card.pack(fill="x", pady=5)
                # **FIXED: VISIBLE ADMIN DETAILS**
                info = ctk.CTkFrame(card, fg_color="transparent"); info.pack(side="left", fill="x", expand=True, padx=10)
                ctk.CTkLabel(info, text=req['details']['name'], font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x")
                ctk.CTkLabel(info, text=f"Type: {req['details']['tags']} | By: {req['user']}", text_color=COLOR_MUTED, anchor="w").pack(fill="x")
                ctk.CTkLabel(info, text=req['details']['desc'][:60]+"...", text_color="gray", font=("Arial", 10), anchor="w").pack(fill="x")
                ctk.CTkButton(card, text="✔", width=40, fg_color=COLOR_SUCCESS, corner_radius=15, command=lambda i=idx: [self.backend.resolve_request(i, "accepted"), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
                ctk.CTkButton(card, text="❌", width=40, fg_color=COLOR_ERROR, corner_radius=15, command=lambda i=idx: [self.backend.resolve_request(i, "declined"), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
        
        u_frame = ctk.CTkScrollableFrame(tabs.tab("Users"), fg_color="transparent"); u_frame.pack(fill="both", expand=True)
        for u in list(self.backend.users_col.find().limit(50)):
            card = ctk.CTkFrame(u_frame, fg_color=COLOR_CARD); card.pack(fill="x", pady=5)
            ctk.CTkLabel(card, text=f"{u['_id']} ({u['role']})", text_color="black").pack(side="left", padx=10)
            if u['role'] != 'admin': ctk.CTkButton(card, text="🗑", width=40, fg_color=COLOR_ERROR, corner_radius=15, command=lambda n=u['_id']: [self.backend.delete_user(n), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)
        l_frame = ctk.CTkScrollableFrame(tabs.tab("Locations"), fg_color="transparent"); l_frame.pack(fill="both", expand=True)
        for _, l in self.backend.df_locations.head(50).iterrows():
            card = ctk.CTkFrame(l_frame, fg_color=COLOR_CARD); card.pack(fill="x", pady=2)
            safe_l = ''.join([c for c in l['name'] if ord(c) < 128])
            if not safe_l: safe_l = l['name'][:20]
            ctk.CTkLabel(card, text=safe_l, text_color="black").pack(side="left", padx=10)
            ctk.CTkButton(card, text="🗑", width=40, fg_color=COLOR_ERROR, corner_radius=15, command=lambda n=l['name']: [self.backend.delete_location(n), self.set_state(UIState.ADMIN)]).pack(side="right", padx=5)

    def build_settings(self):
        self.build_topbar(back=True)
        bg = ctk.CTkFrame(self.container, fg_color=COLOR_BG); bg.pack(fill="both", expand=True)
        box = ctk.CTkFrame(bg, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        box.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(padx=60, pady=40)
        ctk.CTkLabel(inner, text="Settings", font=("Segoe UI", 24, "bold"), text_color=COLOR_TEXT).pack(pady=(0, 20))
        u_data = self.backend.users_col.find_one({"_id": self.backend.current_user})
        ctk.CTkLabel(inner, text="Update Name", anchor="w", text_color=COLOR_MUTED).pack(fill="x")
        e_name = ctk.CTkEntry(inner, width=280); e_name.insert(0, u_data.get("name", "")); e_name.pack(pady=(0, 10))
        
        ctk.CTkLabel(inner, text="Update Password", anchor="w", text_color=COLOR_MUTED).pack(fill="x")
        p_frame = ctk.CTkFrame(inner, fg_color="transparent"); p_frame.pack(pady=(0, 10))
        e_pass = ctk.CTkEntry(p_frame, width=220, show="*"); e_pass.insert(0, u_data.get("password", ""))
        e_pass.pack(side="left")
        def toggle_pw():
            state = e_pass.cget("show")
            e_pass.configure(show="" if state=="*" else "*")
            btn_eye.configure(text="🔒" if state=="*" else "👁")
        btn_eye = ctk.CTkButton(p_frame, text="👁", width=40, height=30, fg_color=COLOR_SECONDARY, hover_color=COLOR_PRIMARY_HOVER, corner_radius=10, command=toggle_pw)
        btn_eye.pack(side="left", padx=5)

        ctk.CTkLabel(inner, text="Move Base Location", anchor="w", text_color=COLOR_MUTED).pack(fill="x")
        loc = ctk.CTkOptionMenu(inner, values=list(MUMBAI_REGIONS.keys()), width=280, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, text_color="white"); loc.pack(pady=(0, 20))
        def save():
            lat, lng = MUMBAI_REGIONS[loc.get()]
            self.backend.update_profile(e_name.get(), e_pass.get(), lat, lng); 
            self.backend.reload_data() # **FIXED: INSTANT REFRESH**
            self.show_custom_popup("Success", "Profile Updated! Location changed.")
        ctk.CTkButton(inner, text="Save Changes", width=280, height=45, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, corner_radius=25, command=save).pack()

    def build_add_location(self):
        self.build_topbar(back=True)
        bg = ctk.CTkFrame(self.container, fg_color=COLOR_BG); bg.pack(fill="both", expand=True)
        box = ctk.CTkFrame(bg, fg_color=COLOR_CARD, corner_radius=20, border_width=1, border_color=COLOR_BORDER)
        box.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(padx=60, pady=40)
        ctk.CTkLabel(inner, text="Suggest a Place", font=("Segoe UI", 24, "bold"), text_color=COLOR_TEXT).pack(pady=(0, 10))
        ctk.CTkLabel(inner, text="Help us improve the map!", text_color=COLOR_MUTED).pack(pady=(0, 20))
        
        e_name = ctk.CTkEntry(inner, placeholder_text="Place Name", width=280); e_name.pack(pady=5)
        e_tags = ctk.CTkEntry(inner, placeholder_text="Category (e.g. park, cafe)", width=280); e_tags.pack(pady=5)
        e_desc = ctk.CTkTextbox(inner, height=80, width=280, border_color=COLOR_BORDER, border_width=2); e_desc.insert("0.0", "Description..."); e_desc.pack(pady=5)
        
        ctk.CTkLabel(inner, text="Nearest Hub (Approx. Location):", text_color=COLOR_MUTED, font=("Segoe UI", 12)).pack(pady=(10, 0), anchor="w")
        loc_var = ctk.StringVar(value=list(MUMBAI_REGIONS.keys())[0])
        loc_menu = ctk.CTkOptionMenu(inner, values=list(MUMBAI_REGIONS.keys()), variable=loc_var, width=280, fg_color=COLOR_SECONDARY, button_color=COLOR_PRIMARY, text_color="white")
        loc_menu.pack(pady=5)

        def sub():
            if not e_name.get() or not e_tags.get():
                self.show_custom_popup("Error", "Name and Category required!")
                return
            
            region = loc_var.get()
            lat, lng = MUMBAI_REGIONS[region]
            lat += random.uniform(-0.002, 0.002)
            lng += random.uniform(-0.002, 0.002)
            self.backend.submit_request("new_place", {
                "name": e_name.get(), 
                "tags": e_tags.get(), 
                "desc": e_desc.get("0.0", "end"),
                "lat": lat,
                "lng": lng
            })
            self.show_custom_popup("Sent", "Thanks! An admin will review this."); self.set_state(UIState.HOME)
        ctk.CTkButton(inner, text="Submit Suggestion", width=280, height=45, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, corner_radius=25, command=sub).pack(pady=20)

    # --- TUTORIAL PAGE ADDED HERE ---
    def build_tutorial(self):
        self.build_topbar(back=False)
        bg = ctk.CTkFrame(self.container, fg_color=COLOR_BG); bg.pack(fill="both", expand=True)
        box = ctk.CTkFrame(bg, fg_color=COLOR_CARD, corner_radius=25); box.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(box, fg_color="transparent"); inner.pack(padx=60, pady=40)
        
        ctk.CTkLabel(inner, text="Welcome to CommuniFind! 🎉", font=("Segoe UI", 24, "bold"), text_color=COLOR_PRIMARY).pack(pady=(0, 20))
        
        steps = [
            "1. 🔍 Search for amenities like 'wifi', 'park', or 'hospital'.",
            "2. 📍 Click 'Map' to see the distance and direction.",
            "3. ❤ Save your favorite spots for quick access.",
            "4. ➕ Add new places if they are missing from the map."
        ]
        
        for step in steps:
            ctk.CTkLabel(inner, text=step, font=("Segoe UI", 14), text_color=COLOR_TEXT, anchor="w").pack(fill="x", pady=5)
            
        ctk.CTkButton(inner, text="Start Exploring", width=250, height=50, fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, font=("Segoe UI", 16, "bold"), corner_radius=25, command=lambda: self.set_state(UIState.HOME)).pack(pady=30)

    def build_about(self): 
        box = ctk.CTkFrame(self.container, fg_color=COLOR_CARD, corner_radius=15); box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text="About CommuniFind", font=("Segoe UI", 24, "bold"), text_color=COLOR_PRIMARY).pack(pady=(30, 10))
        desc = "CommuniFind is an offline-first hyper-local discovery tool.\nDesigned to help communities find essential amenities\nlike hospitals, parks, and shops without internet.\n\nBuilt with ❤ for Mumbai."
        ctk.CTkLabel(box, text=desc, font=("Segoe UI", 14), text_color=COLOR_TEXT, justify="center").pack(padx=40, pady=20)
        ctk.CTkButton(box, text="Back", command=self.go_back, fg_color=COLOR_MUTED, hover_color=COLOR_PRIMARY_HOVER, corner_radius=25).pack(pady=30)
    def build_update_location(self): pass

if __name__ == "__main__":
    fetch_and_populate_db() 
    app = CommuniFind()
    app.mainloop()
