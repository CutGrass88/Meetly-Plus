import customtkinter as ctk
from tkinter import ttk, messagebox
import tkintermapview as tkm
import csv
import os
import threading
from PIL import Image
from modules import backend

# ---------- APP CONFIG ----------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------- MAIN WINDOW ----------
app = ctk.CTk()
app.title("Meetly+")
app.geometry("1200x850")
app.minsize(1080, 600)

# ---------- GRID CONFIGURATION ----------
app.grid_columnconfigure(0, weight=1)   # left
app.grid_columnconfigure(1, weight=3)   # right
app.grid_rowconfigure(0, weight=0)      # title
app.grid_rowconfigure(1, weight=1)      # table
app.grid_rowconfigure(2, weight=2)      # map

# ---------- TITLE ----------
logo_image = None
try:
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
    logo_path = os.path.join(assets_dir, "logo.png")
    if os.path.exists(logo_path):
        # Resize to a reasonable display size while preserving aspect
        pil_logo = Image.open(logo_path)
        logo_width, logo_height = pil_logo.size
        max_width = 300
        if logo_width > max_width:
            scale = max_width / logo_width
            logo_size = (int(logo_width * scale), int(logo_height * scale))
        else:
            logo_size = (logo_width, logo_height)
        logo_image = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=logo_size)
except Exception:
    logo_image = None

if logo_image:
    title = ctk.CTkLabel(app, text="", image=logo_image)
    title.image = logo_image  # keep reference
else:
    title = ctk.CTkLabel(app, text="Meetly+", font=ctk.CTkFont(size=32, weight="bold"))
title.grid(row=0, column=0, columnspan=2, padx=10, pady=(12, 4), sticky="n")

# ---------- LEFT FRAME (Inputs) ----------
left_frame = ctk.CTkFrame(app, corner_radius=8)
left_frame.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(20, 10), pady=10)
left_frame.grid_rowconfigure(10, weight=1)
left_frame.grid_columnconfigure(0, weight=1)

input_label = ctk.CTkLabel(left_frame, text="Enter 2-25 IATA Codes (e.g. LHR, JFK, DXB):",
                           font=ctk.CTkFont(size=14))
input_label.pack(padx=10, pady=(20, 5))

location_box = ctk.CTkTextbox(left_frame, width=220, height=110)
location_box.pack(padx=10, pady=(0, 10))
location_box.insert("1.0", "LHR\nJFK\nDXB")  # Example default

hub_label = ctk.CTkLabel(left_frame, text="Meeting hub (IATA):", font=ctk.CTkFont(size=14))
hub_label.pack(padx=10, pady=(10, 5))

hub_entry = ctk.CTkEntry(left_frame, placeholder_text="e.g. AMS")
hub_entry.pack(padx=10, pady=(0, 10))
hub_entry.insert(0, "AMS")

# Hide hub input (removed per request)
hub_label.pack_forget()
hub_entry.pack_forget()

# -------- IATA database (from assets/airports.dat) --------
IATA_DB = None
IATA_MARKERS = []         # starting location markers
IATA_MEETING_MARKER = None
IATA_PATHS = []           # path lines from starts -> meeting
IATA_LAYOVER_MARKERS = [] # layover markers for connecting itineraries
CURRENT_RESULT_META = {}  # cached metadata from backend.compute_top10

ROUTE_COLORS = {
    "direct": "#4caf50",
    "one_stop": "#ffb300",
    "two_stop": "#ab47bc",
    "fallback": "#ef5350",
    "same": "#64b5f6",
}
DEFAULT_ROUTE_COLOR = "#9e9e9e"

submit_button = None
ai_summary_box = None
progress_bar = None


def _set_ai_summary_text(text):
    if ai_summary_box is None:
        return
    ai_summary_box.configure(state="normal")
    ai_summary_box.delete("1.0", "end")
    ai_summary_box.insert("1.0", text)
    ai_summary_box.configure(state="disabled")


def _empty_meta():
    return {"by_candidate": {}, "requested_origins": [], "ordered_candidates": []}


def _route_color(availability):
    return ROUTE_COLORS.get(availability, DEFAULT_ROUTE_COLOR)


def _route_coords(detail, db):
    if not detail:
        return None
    coords = []
    for node in detail.get("path", []):
        node_info = db.get(node)
        if not node_info:
            return None
        coords.append((node_info[0], node_info[1]))
    if len(coords) < 2:
        return None
    return coords

def load_iata_db():
    global IATA_DB
    if IATA_DB is not None:
        return IATA_DB
    IATA_DB = {}
    try:
        root = os.path.dirname(os.path.dirname(__file__))
    except Exception:
        root = os.getcwd()
    path = os.path.join(root, "assets", "airports.dat")
    try:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                try:
                    # OpenFlights format: id, name, city, country, IATA, ICAO, lat, lon, ...
                    iata = (row[4] or "").strip().upper()
                    if not iata or iata == "\\N":
                        continue
                    lat = float(row[6])
                    lon = float(row[7])
                    name = row[1]
                    IATA_DB[iata] = (lat, lon, name)
                except Exception:
                    continue
    except Exception:
        IATA_DB = {}
    return IATA_DB


def _resolve_code_or_name(token, db):
    """Resolve an input token as IATA code first; otherwise try by airport name.
    Returns (code, lat, lon, name) or None.
    """
    if not token:
        return None
    t = token.strip()
    # If looks like code
    if len(t) == 3 and t.upper() in db:
        lat, lon, name = db[t.upper()]
        return (t.upper(), lat, lon, name)
    # Try by airport name contains
    tl = t.lower()
    for code, (lat, lon, name) in db.items():
        nm = (name or "").lower()
        if nm == tl or nm.startswith(tl) or tl in nm:
            return (code, lat, lon, name)
    return None

def on_submit():
    text = location_box.get("1.0", "end").strip().upper()
    codes = [c.strip() for c in text.replace(",", " ").split() if c.strip()]
    if len(codes) < 2 or len(codes) > 25:
        messagebox.showerror("Error", "Please enter between 2 and 25 IATA codes.")
        return

    hub_code = hub_entry.get().strip().upper()
    if not hub_code:
        messagebox.showerror("Error", "Please enter a hub IATA code.")
        return

    messagebox.showinfo("Submitted", f"Processing for: {', '.join(codes)} → Hub: {hub_code}")

def on_submit_no_hub():
    text = location_box.get("1.0", "end").strip().upper()
    codes = [c.strip() for c in text.replace(",", " ").split() if c.strip()]
    if len(codes) < 2 or len(codes) > 25:
        messagebox.showerror("Error", "Please enter between 2 and 25 IATA codes.")
        return

    if submit_button is not None:
        submit_button.configure(state="disabled")

    if progress_bar is not None:
        try:
            progress_bar.stop()
        except Exception:
            pass
        try:
            progress_bar.pack(padx=10, pady=(0, 10), fill="x")
        except Exception:
            pass
        try:
            progress_bar.start()
        except Exception:
            pass

    progress_lines = [
        f"Received attendees: {', '.join(codes)}",
        "Computing meeting recommendations...",
    ]
    _set_ai_summary_text("\n".join(progress_lines))

    def _background():
        error = None
        try:
            rows, meta = backend.compute_top10(codes)
            if not isinstance(meta, dict):
                meta = _empty_meta()
        except Exception as exc:
            rows, meta = [], _empty_meta()
            error = exc
        app.after(0, lambda: _apply_submission_results(codes, rows, meta, error))

    threading.Thread(target=_background, daemon=True).start()


def _apply_submission_results(codes, rows, meta, error=None):
    if submit_button is not None:
        submit_button.configure(state="normal")

    if progress_bar is not None:
        try:
            progress_bar.stop()
        except Exception:
            pass
        try:
            progress_bar.pack_forget()
        except Exception:
            pass

    if not isinstance(meta, dict):
        meta = _empty_meta()

    global CURRENT_RESULT_META
    CURRENT_RESULT_META = meta

    if error:
        print(f"[submit] compute_top10 failed: {error}")
        try:
            messagebox.showerror(
                "Error",
                "Failed to compute meeting recommendations. Showing any partial results if available.",
            )
        except Exception:
            pass

    sanitized_rows = rows or []

    # Always clear table then insert latest results (if any)
    for item in table.get_children():
        table.delete(item)
    for r in sanitized_rows:
        # r is [iata, airport_name, score, mean_time, total_co2, total_distance, connectivity_summary]
        try:
            values = (
                str(r[0]),
                str(r[1]),
                f"{float(r[2]):.4f}",
                f"{float(r[3]):.2f}",
                f"{float(r[4]):.2f}",
                f"{float(r[5]):.2f}",
                str(r[6]),
            )
        except Exception:
            values = tuple(str(x) for x in r)
        table.insert("", "end", values=values)

    # 2) Plot starting codes on the map using IATA database
    db = load_iata_db()
    # clear previous markers
    for m in list(IATA_MARKERS):
        try:
            m.delete()
        except Exception:
            pass
        finally:
            try:
                IATA_MARKERS.remove(m)
            except Exception:
                pass
    # clear previous meeting marker and paths
    global IATA_MEETING_MARKER
    if IATA_MEETING_MARKER is not None:
        try:
            IATA_MEETING_MARKER.delete()
        except Exception:
            pass
        IATA_MEETING_MARKER = None
    for marker in list(IATA_LAYOVER_MARKERS):
        try:
            marker.delete()
        except Exception:
            pass
        finally:
            try:
                IATA_LAYOVER_MARKERS.remove(marker)
            except Exception:
                pass
    for p in list(IATA_PATHS):
        try:
            p.delete()
        except Exception:
            pass
        finally:
            try:
                IATA_PATHS.remove(p)
            except Exception:
                pass

    plotted = []
    for code in codes:
        info = db.get(code)
        if not info:
            continue
        lat, lon, name = info
        try:
            marker = map_widget.set_marker(lat, lon, text=f"{code} - {name}")
            IATA_MARKERS.append(marker)
            plotted.append((lat, lon))
        except Exception:
            continue

    # 3) Determine meeting location from top of the (now updated) table
    meeting_coord = None
    meeting_code = None
    candidate_detail = {}
    top_routes = {}
    try:
        table_items = table.get_children()
        if table_items:
            first_values = table.item(table_items[0], "values")
            if first_values:
                token = str(first_values[0]).strip().upper()
                resolved = _resolve_code_or_name(token, db)
                if resolved:
                    meeting_code, mlat, mlon, mname = resolved
                    IATA_MEETING_MARKER = map_widget.set_marker(mlat, mlon, text=f"MEETING: {meeting_code}")
                    meeting_coord = (mlat, mlon)
                    candidate_detail = (CURRENT_RESULT_META.get("by_candidate") or {}).get(meeting_code, {}) or {}
                    top_routes = candidate_detail.get("routes", {}) or {}
    except Exception:
        meeting_coord = None
        candidate_detail = {}
        top_routes = {}

    def _draw_path(coords_sequence, availability):
        if not coords_sequence or len(coords_sequence) < 2:
            return
        color = _route_color(availability)
        width = 3 if availability != "fallback" else 2
        try:
            path_obj = map_widget.set_path(coords_sequence, width=width, color=color)
            IATA_PATHS.append(path_obj)
        except Exception:
            pass

    plotted_stop_keys = set()

    def _plot_stop_markers(detail):
        if not detail:
            return
        path_nodes = detail.get("path") or []
        if len(path_nodes) <= 2:
            return
        color = _route_color(detail.get("availability"))
        for stop_code in path_nodes[1:-1]:
            key = (stop_code, color)
            if key in plotted_stop_keys:
                continue
            info = db.get(stop_code)
            if not info:
                continue
            lat, lon, name = info
            try:
                marker = map_widget.set_marker(
                    lat,
                    lon,
                    text=f"Stop: {stop_code}",
                    marker_color_outside=color,
                    marker_color_circle=color,
                )
            except TypeError:
                marker = map_widget.set_marker(lat, lon, text=f"Stop: {stop_code}")
            except Exception:
                continue
            IATA_LAYOVER_MARKERS.append(marker)
            plotted_stop_keys.add(key)

    if plotted:
        for code in codes:
            detail = top_routes.get(code)
            if detail and detail.get("availability") == "same":
                continue
            coords_sequence = _route_coords(detail, db) if detail else None
            if coords_sequence:
                _draw_path(coords_sequence, detail.get("availability"))
                _plot_stop_markers(detail)
            elif meeting_coord:
                origin_info = db.get(code)
                if origin_info:
                    _draw_path([(origin_info[0], origin_info[1]), meeting_coord], "fallback")

    # 5) Center/zoom map to include all points (starts + meeting + connections if any)
    all_pts = list(plotted)
    seen_pts = {(lat, lon) for (lat, lon) in all_pts}
    if meeting_coord:
        key = (meeting_coord[0], meeting_coord[1])
        if key not in seen_pts:
            all_pts.append(meeting_coord)
            seen_pts.add(key)
    for detail in top_routes.values():
        coords_sequence = _route_coords(detail, db)
        if coords_sequence:
            for lat, lon in coords_sequence:
                key = (lat, lon)
                if key not in seen_pts:
                    all_pts.append((lat, lon))
                    seen_pts.add(key)

    if all_pts:
        avg_lat = sum(p[0] for p in all_pts) / len(all_pts)
        avg_lon = sum(p[1] for p in all_pts) / len(all_pts)
        map_widget.set_position(avg_lat, avg_lon)
        lats = [p[0] for p in all_pts]
        lons = [p[1] for p in all_pts]
        lat_span = max(lats) - min(lats)
        lon_span = max(lons) - min(lons)
        span = max(lat_span, lon_span)
        if span < 5:
            map_widget.set_zoom(8)
        elif span < 15:
            map_widget.set_zoom(6)
        elif span < 30:
            map_widget.set_zoom(5)
        elif span < 60:
            map_widget.set_zoom(4)
        else:
            map_widget.set_zoom(3)

    # Pull the top row directly from the rendered table so the summary reflects the visible data
    table_items = table.get_children()
    top_row = table.item(table_items[0], "values") if table_items else None

    if not top_row or len(top_row) < 7:
        _set_ai_summary_text(f"Received attendees: {', '.join(codes)}\nNo results computed.")
        return

    safe = list(top_row)
    while len(safe) < 7:
        safe.append("")
    try:
        score_s = f"{float(safe[2]):.4f}"
        time_s = f"{float(safe[3]):.2f}"
        co2_s = f"{float(safe[4]):.2f}"
        dist_s = f"{float(safe[5]):.2f}"
    except Exception:
        score_s, time_s, co2_s, dist_s = str(safe[2]), str(safe[3]), str(safe[4]), str(safe[5])

    conn_s = str(safe[6])

    stats = candidate_detail.get("stats") if candidate_detail else {}
    stats_summary_line = ""
    if isinstance(stats, dict) and stats:
        stats_summary_line = (
            f"Routes: direct {stats.get('direct', 0)}, "
            f"1-stop {stats.get('one_stop', 0)}, "
            f"2-stop {stats.get('two_stop', 0)}, "
            f"fallback {stats.get('fallback', 0)}, "
            f"local {stats.get('same', 0)}"
        )

    intro_lines = [f"Received attendees: {', '.join(codes)}", "Generating AI summary..."]
    if stats_summary_line:
        intro_lines.append(stats_summary_line)
    _set_ai_summary_text("\n".join(intro_lines))

    fallback_lines = [
        "AI summary unavailable.",
        f"Top candidate: {safe[0]} - {safe[1]} (score {score_s}, time {time_s} min, CO2 {co2_s} kg, distance {dist_s} km).",
        f"Connectivity: {conn_s}",
    ]
    if stats_summary_line:
        fallback_lines.append(stats_summary_line)
    fallback = "\n".join(fallback_lines)

    stats_payload = dict(stats) if isinstance(stats, dict) and stats else None

    def _worker():
        try:
            from modules.AI import reason

            co2_val = float(top_row[4])
            time_val = float(top_row[3])
            dist_val = float(top_row[5])
            text = reason(
                CO2=co2_val,
                time=time_val,
                distance=dist_val,
                numPeople=len(codes),
                locations=codes,
                hub=top_row[0],
                connectivity=conn_s,
                stats=stats_payload,
            )
            final_text = str(text).strip() if text else ""
            app.after(0, lambda: _set_ai_summary_text(final_text if final_text else fallback))
        except Exception:
            app.after(0, lambda: _set_ai_summary_text(fallback))

    threading.Thread(target=_worker, daemon=True).start()

submit_button = ctk.CTkButton(left_frame, text="Submit", command=on_submit_no_hub, width=160, height=36)
submit_button.pack(pady=(5, 15))

progress_bar = ctk.CTkProgressBar(left_frame, mode="indeterminate")
progress_bar.pack(padx=10, pady=(0, 10), fill="x")
progress_bar.stop()
progress_bar.pack_forget()

# Textbox for AI summary under Submit
ai_summary_box = ctk.CTkTextbox(left_frame, width=220, height=140)
ai_summary_box.pack(padx=10, pady=(0, 10), fill="x")
ai_summary_box.insert("1.0", "AI summary will appear here.")
ai_summary_box.configure(state="disabled")

# ---------- RIGHT TOP (Table) ----------
table_frame = ctk.CTkFrame(app, corner_radius=8)
table_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(10, 5))
table_frame.grid_rowconfigure(0, weight=1)
table_frame.grid_columnconfigure(0, weight=1)

# Table styling
style = ttk.Style()
style.theme_use("default")
style.configure("Treeview",
                background="#2b2b2b",
                foreground="white",
                rowheight=28,
                fieldbackground="#2b2b2b",
                font=("Arial", 12))
style.configure("Treeview.Heading",
                font=("Arial", 13, "bold"),
                background="#1e1e1e",
                foreground="white")
style.map("Treeview", background=[("selected", "#1f538d")])

columns = ("IATA", "Airport", "Score", "Mean Time (min)", "Total CO2 (kg)", "Total Distance (km)", "Connectivity")
column_widths = (80, 220, 90, 150, 150, 170, 220)
column_anchors = ("center", "w", "center", "center", "center", "center", "w")
table = ttk.Treeview(table_frame, columns=columns, show="headings")
for col, width, anchor in zip(columns, column_widths, column_anchors):
    table.heading(col, text=col)
    table.column(col, anchor=anchor, width=width, stretch=(anchor == "w"))

scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
table.configure(yscroll=scroll_y.set, xscroll=scroll_x.set)
scroll_y.pack(side="right", fill="y")
scroll_x.pack(side="bottom", fill="x")
table.pack(fill="both", expand=True, padx=10, pady=10)

# Example data
sample_data = [
]
for row in sample_data:
    table.insert("", "end", values=row)

# ---------- RIGHT BOTTOM (Map) ----------
map_frame = ctk.CTkFrame(app, corner_radius=8)
map_frame.grid(row=2, column=1, sticky="nsew", padx=(10, 20), pady=(5, 20))
map_frame.grid_rowconfigure(0, weight=1)
map_frame.grid_columnconfigure(0, weight=1)

map_label = ctk.CTkLabel(map_frame, text="Locations", font=ctk.CTkFont(size=16, weight="bold"))
map_label.pack(anchor="w", padx=12, pady=(10, 0))

map_widget = tkm.TkinterMapView(map_frame)
map_widget.pack(fill="both", expand=True, padx=12, pady=10)
map_widget.set_zoom(3)
map_widget.set_position(30.0, 10.0)

# ---------- MAIN LOOP ----------
app.mainloop()
