# Lake Jovita Happy Hour Skins game scoring app
# August 2026

import os
import datetime
import pandas as pd
import numpy as np
import math
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# Standardized page configuration (Must be the first Streamlit command)
st.set_page_config(page_title="Golf Skins Tracker", layout="wide")

# Hide ONLY the hamburger menu and the footer
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# Define credentials and Google Sheet keys
CREDS_DICT = st.secrets["gcp_service_account"]
SHEET_KEY = "1rdOkZWObTiT_ubGCFy8lG56L-ET7cUtukq2GR-StkjA"
DRIVE_FOLDER_ID = "1wUDJ4WqSBX4onE7sRkCqW4U5GpPVClm0"

# --- Configuration Constants ---
MAX_GROUPS = 4
DB_FILE = "skins_database.csv"
ROSTER_FILE = "master_roster.csv"

# ---------------------------------------------------------
# --- GOOGLE SHEETS SETTINGS & SCORECARD PERSISTENCE ------
# ---------------------------------------------------------

@st.cache_data(ttl=600)
def load_game_settings(SHEET_KEY):
    """Loads saved game setup parameters from the 'Settings' tab in Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)
        
        try:
            settings_ws = sheet.worksheet('Settings')
            raw = settings_ws.get_all_records()
            return {str(row['Setting']): row['Value'] for row in raw if 'Setting' in row and 'Value' in row}
        except Exception:
            return {}
    except Exception:
        return {}

def save_game_settings(SHEET_KEY, settings_dict):
    """Saves game setup parameters into the 'Settings' tab in Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        try:
            settings_ws = sheet.worksheet('Settings')
            settings_ws.clear()
        except gspread.exceptions.WorksheetNotFound:
            settings_ws = sheet.add_worksheet(title='Settings', rows="20", cols="2")

        rows = [["Setting", "Value"]]
        for k, v in settings_dict.items():
            rows.append([str(k), str(v)])
            
        settings_ws.update(rows)
        return True, "Settings saved to Google Sheets successfully!"
    except Exception as e:
        return False, f"Failed to save settings: {e}"

def create_scorecard_tab(SHEET_KEY, active_players_df):
    """Creates a 'Scorecard-ddmmmyyyy' tab with player list and assigned groups."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        date_str = datetime.datetime.now().strftime("%d%b%Y")
        tab_name = f"Scorecard-{date_str}"

        try:
            ws = sheet.worksheet(tab_name)
            ws.clear()
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title=tab_name, rows="50", cols="10")

        cols_to_export = ["Player", "Group", "Tee", "Handicap"]
        df_export = active_players_df[cols_to_export].fillna("")
        ws.update([df_export.columns.values.tolist()] + df_export.values.tolist())
        return True, tab_name
    except Exception as e:
        return False, str(e)

def save_group_scores_to_sheet(SHEET_KEY, active_players_df):
    """Saves running scorecard summary per group to tab 'score-group(i)' in Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        groups = active_players_df["Group"].unique()
        for g_val in groups:
            g_clean = str(g_val).strip()
            if not g_clean or g_clean == "Unassigned":
                continue
            
            g_num = g_clean.lower().replace(" ", "")
            tab_name = f"score-{g_num}"

            group_df = active_players_df[active_players_df["Group"] == g_val].fillna(0)

            try:
                ws = sheet.worksheet(tab_name)
                ws.clear()
            except gspread.exceptions.WorksheetNotFound:
                ws = sheet.add_worksheet(title=tab_name, rows="30", cols="30")

            ws.update([group_df.columns.values.tolist()] + group_df.values.tolist())
        return True, "Group scores updated on Google Sheets!"
    except Exception as e:
        return False, str(e)

def load_all_group_scores_from_sheets(SHEET_KEY, max_groups=4):
    """Reads all 'score-group(i)' tabs from Google Sheets into a single DataFrame."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        merged_rows = []
        for g in range(1, max_groups + 1):
            tab_name = f"score-group{g}"
            try:
                ws = sheet.worksheet(tab_name)
                raw = ws.get_all_values()
                if raw and len(raw) > 1:
                    headers = [h.strip() for h in raw[0]]
                    for row in raw[1:]:
                        if any(row):
                            row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
                            merged_rows.append(row_dict)
            except gspread.exceptions.WorksheetNotFound:
                continue
                
        if merged_rows:
            return pd.DataFrame(merged_rows)
        return None
    except Exception:
        return None

def delete_all_scorecard_and_group_tabs(SHEET_KEY):
    """Deletes all tabs starting with 'Scorecard-' or 'score-group' from Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        worksheets = sheet.worksheets()
        deleted_tabs = []
        for ws in worksheets:
            t_lower = ws.title.lower().strip()
            if t_lower.startswith("scorecard-") or t_lower.startswith("score-group"):
                sheet.del_worksheet(ws)
                deleted_tabs.append(ws.title)
        return True, deleted_tabs
    except Exception as e:
        return False, str(e)

# Load settings into session state on app init
if "settings_loaded" not in st.session_state:
    saved_settings = load_game_settings(SHEET_KEY)
    if saved_settings:
        if "num_players" in saved_settings:
            st.session_state.num_players = int(saved_settings["num_players"])
        if "buy_in_per_player" in saved_settings:
            st.session_state.buy_in_per_player = int(saved_settings["buy_in_per_player"])
        if "carry_over" in saved_settings:
            st.session_state.carry_over = str(saved_settings["carry_over"]).lower() == 'true'
        if "saved_course" in saved_settings:
            st.session_state.saved_course = str(saved_settings["saved_course"])
        if "saved_num_holes" in saved_settings:
            st.session_state.saved_num_holes = int(saved_settings["saved_num_holes"])
    st.session_state.settings_loaded = True

# Defaults if not present in session state
if "num_players" not in st.session_state:
    st.session_state.num_players = 8

if "buy_in_per_player" not in st.session_state:
    st.session_state.buy_in_per_player = 10

if "carry_over" not in st.session_state:
    st.session_state.carry_over = True

# Ensure the local master roster file exists
if not os.path.exists(ROSTER_FILE):
    df_init = pd.DataFrame(columns=["Name", "Tee", "PH"])
    df_init.to_csv(ROSTER_FILE, index=False)

st.title("⛳ LJ Happy Hour Skins Game Tracker")
st.write("Calculate skins, handle payouts, manage group assignments and digital scorecard.")

# ---------------------------------------------------------
# --- 1. GLOBAL DATABASE SYSTEM (Multi-Device Sync) ---
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def load_master_roster(SHEET_KEY):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        players_tab = sheet.worksheet('Players')
        raw_data = players_tab.get_all_values()
        if not raw_data:
            return {}
            
        headers = [h.strip() for h in raw_data[0]]
        try:
            nm_idx = headers.index('Name')
            tee_idx = headers.index('Tee')
            hc_idx = headers.index('PH')
        except ValueError as e:
            st.error(f"Missing a required column header in the Google Sheet: {e}")
            return {}

        group_indices = {}
        for i in range(1, 7):
            col_name = f'Pulldown Group{i}'
            if col_name in headers:
                group_indices[col_name] = headers.index(col_name)

        roster = {}
        for row in raw_data[1:]:
            if len(row) <= max(nm_idx, tee_idx, hc_idx):
                continue
            
            full_name = str(row[nm_idx]).strip()
            if not full_name:
                continue
            
            group_val = "Unassigned"
            for col_name, idx in group_indices.items():
                if idx < len(row) and row[idx].strip():
                    group_val = row[idx].strip()
                    break
            
            roster[full_name] = {
                "Tee": row[tee_idx].strip() if row[tee_idx].strip() else "Green",
                "Handicap": row[hc_idx].strip() if row[hc_idx].strip() else "10",
                "Group": group_val
            }
        return roster
    except Exception as e:
        st.error(f"Failed to pull roster from Google Sheets: {e}")
        return {}

@st.cache_data(ttl=600)
def get_available_courses(SHEET_KEY):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        course_tab = sheet.worksheet('Course')
        raw_data = course_tab.get_all_values()
        if not raw_data:
            return []
            
        headers = [h.strip() for h in raw_data[0]]
        if 'Course' not in headers:
            st.error("Could not find 'Course' column in Course tab.")
            return []
            
        course_idx = headers.index('Course')
        courses = set()
        for row in raw_data[1:]:
            if len(row) > course_idx and row[course_idx].strip():
                courses.add(row[course_idx].strip())
                
        return sorted(list(courses))
    except Exception as e:
        st.error(f"Error fetching course list: {e}")
        return []

@st.cache_data(ttl=600)
def load_course_details(SHEET_KEY, selected_course):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)

        course_tab = sheet.worksheet('Course')
        raw_data = course_tab.get_all_values()
        if not raw_data:
            return []
            
        headers = [h.strip() for h in raw_data[0]]
        c_idx = headers.index('Course')
        h_idx = headers.index('Hole')
        p_idx = headers.index('Par')
        hd_idx = headers.index('Handicap')
        
        course_holes = []
        for row in raw_data[1:]:
            if len(row) <= max(c_idx, h_idx, p_idx, hd_idx):
                continue
            if row[c_idx].strip() == selected_course:
                course_holes.append({
                    "Hole": int(row[h_idx].strip()),
                    "Par": int(row[p_idx].strip()),
                    "Handicap": int(row[hd_idx].strip())
                })
                
        return sorted(course_holes, key=lambda x: x["Hole"])
    except Exception as e:
        st.error(f"Error fetching course details: {e}")
        return []

# ---------------------------------------------------------
# --- 2. DYNAMIC SCORECARD SETUP & SIDEBAR ---
# ---------------------------------------------------------

st.sidebar.header("⚙️ Game setup")

available_courses = get_available_courses(SHEET_KEY) 
active_holes = []

if available_courses:
    course_default_idx = 0
    if "saved_course" in st.session_state and st.session_state.saved_course in available_courses:
        course_default_idx = available_courses.index(st.session_state.saved_course)

    selected_course = st.sidebar.selectbox(
        "Select Course", 
        options=available_courses,
        index=course_default_idx,
        key="sidebar_course_select"
    )
    course_data = load_course_details(SHEET_KEY, selected_course)
    max_holes = len(course_data) if course_data else 0
    if max_holes > 0:
        holes_options = list(range(1, max_holes + 1))
        
        default_hole_idx = min(9, max_holes - 1)
        if "saved_num_holes" in st.session_state and st.session_state.saved_num_holes in holes_options:
            default_hole_idx = holes_options.index(st.session_state.saved_num_holes)

        chosen_num_holes = st.sidebar.selectbox(
            "Number of Holes",
            options=holes_options,
            index=default_hole_idx,
            key="sidebar_holes_select"
        )
        active_holes = course_data[:chosen_num_holes]
    else:
        st.sidebar.error(f"Connected to 'Course' tab, but found 0 holes listed for '{selected_course}'.")
else:
    st.sidebar.warning("No courses returned. Please check your Google Sheets connection.")
    chosen_num_holes = 9

# Sync dynamic course parameters directly into running session state variables
if len(active_holes) > 0 and (
    st.session_state.get("last_course") != selected_course or 
    st.session_state.get("last_num_holes") != chosen_num_holes
):
    st.session_state.last_course = selected_course
    st.session_state.last_num_holes = chosen_num_holes
    dynamic_course_map = {
        "Hole": [f"Hole {item['Hole']}" for item in active_holes],
        "Par": [item['Par'] for item in active_holes],
        "Hole Handicap": [item['Handicap'] for item in active_holes]
    }
    st.session_state.course_df = pd.DataFrame(dynamic_course_map).set_index("Hole").T

# Fallback block to safely initialize default metrics if offline
if 'course_df' not in st.session_state:
    st.session_state.course_df = pd.DataFrame({
        "Hole": [f"Hole {i+1}" for i in range(10)],
        "Par": [5, 3, 4, 3, 4, 5, 4, 4, 4, 5],
        "Hole Handicap": [17, 9, 1, 13, 11, 15, 7, 5, 3, 10] 
    }).set_index("Hole").T
    
num_holes = len(st.session_state.course_df.columns)

st.sidebar.markdown("---")
num_players = st.sidebar.number_input(
    "Total Number of Players", 
    min_value=1, 
    max_value=24, 
    step=1, 
    key="num_players"
)
carry_over = st.sidebar.checkbox(
    "Carry over tied skins?", 
    key="carry_over"
)

st.sidebar.markdown("---")
st.sidebar.header("💰 Purse Settings")
buy_in_per_player = st.sidebar.number_input(
    "Buy-in Amount per Player ($)", 
    min_value=0, 
    step=5, 
    key="buy_in_per_player"
)

total_purse = num_players * buy_in_per_player
skin_value_per_hole = (total_purse / num_holes) if num_holes > 0 else 0

st.sidebar.metric("Total Purse", f"${total_purse}")
st.sidebar.metric("Skin payout / Hole", f"${skin_value_per_hole:,.2f}")

# --- SAVE & UPDATE SETTINGS BUTTONS ---
st.sidebar.markdown("---")
st.sidebar.header("💾 Current Game Settings")
col_s1, col_s2 = st.sidebar.columns(2)

with col_s1:
    if st.button("💾 Save Settings", use_container_width=True, key="save_settings_btn"):
        settings_payload = {
            "num_players": st.session_state.num_players,
            "saved_course": selected_course if 'selected_course' in locals() else "",
            "saved_num_holes": chosen_num_holes if 'chosen_num_holes' in locals() else 18,
            "buy_in_per_player": st.session_state.buy_in_per_player,
            "carry_over": st.session_state.carry_over
        }
        success, msg = save_game_settings(SHEET_KEY, settings_payload)
        if success:
            st.sidebar.success("Saved!")
        else:
            st.sidebar.error(msg)

with col_s2:
    if st.button("🔄 Update Settings", use_container_width=True, key="update_settings_btn"):
        st.cache_data.clear()
        if "settings_loaded" in st.session_state:
            del st.session_state["settings_loaded"]
        st.sidebar.success("Updated!")
        st.rerun()

# ---------------------------------------------------------
# --- 3. FLAT FILE DATABASE INITIALIZATION ---
# ---------------------------------------------------------

def initialize_flat_file():
    df_rows = []
    for i in range(24):
        group_num = (i // 4) + 1
        row = {
            "Player": f"Player {i+1}",
            "Group": f"Group {min(group_num, MAX_GROUPS)}",
            "Tee": "Green",
            "Handicap": 10
        }
        for h in range(18):
            row[f"Hole {h+1}"] = 0
        df_rows.append(row)
    pd.DataFrame(df_rows).to_csv(DB_FILE, index=False)

if not os.path.exists(DB_FILE) or os.path.getsize(DB_FILE) == 0:
    initialize_flat_file()

master_db = pd.read_csv(DB_FILE)

# Column Structure Safeguard
for h in range(18):
    h_col = f"Hole {h+1}"
    if h_col not in master_db.columns:
        master_db[h_col] = 0

active_players_df = master_db.iloc[:num_players].copy()

# ---------------------------------------------------------
# --- INTERACTIVE MODULES & RENDERING ---
# ---------------------------------------------------------

# --- Course & Course Variables Setup ---
st.header("🏌️‍♂️Course & Tee Settings")
col_c1, col_c2 = st.columns([3, 1])

with col_c1:
    st.write("**Configure Hole Properties**")
    edited_course = st.data_editor(st.session_state.course_df, use_container_width=True, key="course_editor")
    st.session_state.course_df = edited_course
    par_values = edited_course.loc["Par"].tolist()
    hole_hdcp_values = edited_course.loc["Hole Handicap"].tolist()

# ---------------------------------------------------------
# --- 2. PLAYER ROSTER & HANDICAP SETTINGS ------------
# ---------------------------------------------------------
st.header("👤 Player Roster & Group Assignments")
st.write("Select players and assign groups for today's game.")

pulled_roster = load_master_roster(SHEET_KEY)
dropdown_options = sorted(list(pulled_roster.keys()))

sheet_tees = set()
for player_name, info in pulled_roster.items():
    if info.get("Tee"):
        sheet_tees.add(info["Tee"].strip())

baseline_tees = ["Blue", "White", "Green", "Gold", "Red"]
dynamic_tee_options = sorted(list(sheet_tees.union(baseline_tees)))

roster_config = {
    "Player": st.column_config.SelectboxColumn("Player Name", options=dropdown_options, required=True),
    "Group": st.column_config.SelectboxColumn("Assigned Group", options=[f"Group {g+1}" for g in range(4)], required=True),
    "Tee": st.column_config.SelectboxColumn("Tee Box", options=dynamic_tee_options, required=True),
    "Handicap": st.column_config.NumberColumn("Handicap Index / PH", min_value=0, max_value=54, step=1, required=True)
}

roster_view_cols = ["Player", "Group", "Tee", "Handicap"]
roster_slice = active_players_df[roster_view_cols]

edited_roster_matrix = st.data_editor(
    roster_slice,
    use_container_width=True,
    hide_index=True,
    column_config=roster_config,
    key="global_roster_editor" 
)

if not edited_roster_matrix.equals(roster_slice):
    for i, row in edited_roster_matrix.iterrows():
        old_player = master_db.at[i, "Player"]
        new_player = row["Player"]
        
        if old_player != new_player and new_player in pulled_roster:
            master_db.at[i, "Player"] = new_player
            master_db.at[i, "Tee"] = pulled_roster[new_player]["Tee"]
            master_db.at[i, "Handicap"] = int(float(pulled_roster[new_player]["Handicap"]))
            master_db.at[i, "Group"] = row["Group"]
        else:
            master_db.at[i, "Player"] = row["Player"]
            master_db.at[i, "Group"] = row["Group"]
            master_db.at[i, "Tee"] = row["Tee"]
            master_db.at[i, "Handicap"] = row["Handicap"]
            
    master_db.to_csv(DB_FILE, index=False)
    st.rerun()

# --- CREATE SCORECARD BUTTON ---
if st.button("📋 Create Scorecard", key="btn_create_scorecard"):
    with st.spinner("Creating Scorecard tab in Google Sheets..."):
        ok, result_info = create_scorecard_tab(SHEET_KEY, active_players_df)
        if ok:
            st.success(f"✅ Successfully created tab `{result_info}` in Google Sheets!")
        else:
            st.error(f"❌ Failed to create Scorecard tab: {result_info}")

# ---------------------------------------------------------
# --- 3. DYNAMIC SCORE ENTRY FORM ---
# ---------------------------------------------------------

st.header("📝 Player Score Entry")

# Group Selector placed directly ABOVE the Hole Selector
group_options = ["All Players"] + [f"Group {g+1}" for g in range(MAX_GROUPS)]
selected_group = st.selectbox(
    "Select Group Filter:",
    options=group_options,
    index=0,
    key="scorecard_group_select"
)

# Filter active players dataframe according to selection
if selected_group == "All Players":
    active_group_df = active_players_df.copy()
else:
    if "Group" in active_players_df.columns:
        active_players_df["Group"] = active_players_df["Group"].astype(str).str.strip()
        group_mask = active_players_df["Group"] == selected_group
        active_group_df = active_players_df[group_mask]
    else:
        active_group_df = pd.DataFrame()

try:
    par_values = st.session_state.course_df.loc["Par"].astype(int).tolist()
    hole_hdcp_values = st.session_state.course_df.loc["Hole Handicap"].astype(int).tolist()
except Exception:
    par_values = [4] * 18
    hole_hdcp_values = [10] * 18

if active_group_df.empty:
    st.warning(f"No players are currently assigned to {selected_group}. Change player assignments in Section 2 above.")
else:
    hole_options = [f"Hole {i+1}" for i in range(len(st.session_state.course_df.columns))]
    
    if hole_options:
        selected_hole = st.selectbox("Choose Hole to Update:", hole_options)
        hole_idx = hole_options.index(selected_hole)
        
        current_par = par_values[hole_idx] if hole_idx < len(par_values) else 4
        current_hdcp = hole_hdcp_values[hole_idx] if hole_idx < len(hole_hdcp_values) else 10
        
        st.caption(f"ℹ️ **{selected_hole} Details** — Par: {current_par} | Handicap Rating: {current_hdcp}")
        st.markdown("---")
        
        with st.form(key=f"score_form_{selected_group.replace(' ', '_')}", clear_on_submit=False):
            input_scores = {}
            for idx, row in active_group_df.iterrows():
                p_name = row["Player"]
                p_hdcp = row.get("Handicap", 10)
                p_tee = row.get("Tee", "Green")
                
                raw_score = row.get(selected_hole, 0)
                try:
                    if pd.isna(raw_score) or str(raw_score).strip() in ["", "0"]:
                        current_score_value = current_par
                    else:
                        current_score_value = int(float(raw_score))
                except Exception:
                    current_score_value = current_par
                
                score_input = st.number_input(
                    label=f"{p_name} (Tee: {p_tee} | HDCP: {p_hdcp})",
                    min_value=0,
                    max_value=15,
                    value=int(current_score_value), 
                    step=1,
                    key=f"input_{p_name}_{selected_hole}"
                )
                input_scores[p_name] = score_input
                
            submit_button = st.form_submit_button(label="💾 Save Score")

        if submit_button:
            for idx, row in master_db.iterrows():
                p_name = row["Player"]
                if p_name in input_scores:
                    master_db.at[idx, selected_hole] = input_scores[p_name]
            master_db.to_csv(DB_FILE, index=False)

            # Update active dataframe & write group score tabs in Google Sheets
            updated_active = master_db.iloc[:num_players].copy()
            sheet_ok, sheet_msg = save_group_scores_to_sheet(SHEET_KEY, updated_active)

            if sheet_ok:
                st.success(f"Scores saved locally & synced to Google Sheets for {selected_hole}!")
            else:
                st.warning(f"Saved locally, but Google Sheets update encountered an issue: {sheet_msg}")
            st.rerun()
    else:
        st.error("No active holes found in your course configurations matrix.")

with st.expander(f"👀 View {selected_group} Live Running Scorecard Summary"):
    if not active_group_df.empty:
        st.dataframe(active_group_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# --- 4. TRUE FIELD-WIDE GLOBAL GOLF SKINS CASH POOL ENGINE ---
# ---------------------------------------------------------

def get_strokes_received(player_hdcp, hole_hdcp):
    """Calculates absolute traditional golf handicap strokes received for a specific hole difficulty."""
    base_strokes = int(player_hdcp) // 18
    extra_stroke = 1 if int(hole_hdcp) <= (int(player_hdcp) % 18) else 0
    return base_strokes + extra_stroke

col_header, col_btn = st.columns([3, 1], vertical_alignment="center")

with col_header:
    st.header("📊 4. Global Net Results & Cash Leaderboard")

with col_btn:
    if st.button("🔄 Refresh Results", use_container_width=True):
        st.cache_data.clear()
        
        # 1. Reload settings from 'Settings' tab
        saved_settings = load_game_settings(SHEET_KEY)
        if saved_settings:
            if "num_players" in saved_settings:
                st.session_state.num_players = int(saved_settings["num_players"])
            if "buy_in_per_player" in saved_settings:
                st.session_state.buy_in_per_player = int(saved_settings["buy_in_per_player"])
            if "carry_over" in saved_settings:
                st.session_state.carry_over = str(saved_settings["carry_over"]).lower() == 'true'
            if "saved_course" in saved_settings:
                st.session_state.saved_course = str(saved_settings["saved_course"])
            if "saved_num_holes" in saved_settings:
                st.session_state.saved_num_holes = int(saved_settings["saved_num_holes"])

        # 2. Reload players & group scores from 'score-group1..4' tabs
        sheets_scores_df = load_all_group_scores_from_sheets(SHEET_KEY, MAX_GROUPS)
        if sheets_scores_df is not None and not sheets_scores_df.empty:
            for _, row in sheets_scores_df.iterrows():
                p_name = row.get("Player", "")
                if not p_name:
                    continue
                
                # Find matching player in master_db or insert
                match_idx = master_db[master_db["Player"] == p_name].index
                if len(match_idx) > 0:
                    idx = match_idx[0]
                else:
                    idx = len(master_db)
                    master_db.loc[idx] = 0
                    master_db.at[idx, "Player"] = p_name

                for col in sheets_scores_df.columns:
                    if col in master_db.columns:
                        master_db.at[idx, col] = row[col]
            
            master_db.to_csv(DB_FILE, index=False)

        st.success("Re-synced game settings, roster, and group scores from Google Sheets!")
        st.rerun()

tab_titles = ["🏆 Master Cash Leaderboard", "🎯 Field Skin Breakdown", "🔢 Player Net Scores Matrix"]
tabs = st.tabs(tab_titles)

player_cash_won = {row["Player"]: 0.0 for _, row in active_players_df.iterrows()}
player_groups = {row["Player"]: str(row["Group"]).strip() for _, row in active_players_df.iterrows()}
hole_results = []
current_pot_multiplier = 1
net_matrix_rows = []

for h in range(num_holes):
    hole_col = f"Hole {h+1}"
    hole_hdcp = hole_hdcp_values[h] if h < len(hole_hdcp_values) else 10
    current_hole_value = skin_value_per_hole * current_pot_multiplier
    
    net_scores_map = {}
    for idx, row in active_players_df.iterrows():
        player_name = row["Player"]
        gross = row.get(hole_col, 0)
        hdcp = row.get("Handicap", 10)
        
        strokes_allowed = get_strokes_received(hdcp, hole_hdcp)
        try:
            gross_val = int(float(gross)) if not pd.isna(gross) else 0
        except Exception:
            gross_val = 0
            
        if gross_val > 0:
            net_scores_map[player_name] = max(1, gross_val - strokes_allowed)
        else:
            net_scores_map[player_name] = 0

    played_net_scores = {p: score for p, score in net_scores_map.items() if score > 0}
    
    if not played_net_scores:
        hole_results.append({
            "Hole": hole_col, "Par/HDCP": f"P:{par_values[h] if h < len(par_values) else 4} | H:{hole_hdcp}", "Net Winner": "-", "Group": "-", "Winning Net": "-", 
            "Status": "Unplayed", "Hole Value": f"${current_hole_value:,.2f}"
        })
        if not carry_over: current_pot_multiplier = 1
        continue
        
    min_net = min(played_net_scores.values())
    players_with_min = [p for p, score in played_net_scores.items() if score == min_net]
    
    if len(players_with_min) == 1:
        winner = players_with_min[0]
        player_cash_won[winner] += current_hole_value
        hole_results.append({
            "Hole": hole_col, "Par/HDCP": f"P:{par_values[h] if h < len(par_values) else 4} | H:{hole_hdcp}", "Net Winner": winner, "Group": player_groups.get(winner, "-"), "Winning Net": int(min_net), 
            "Status": "🔥 Skin Won!", "Hole Value": f"${current_hole_value:,.2f}"
        })
        current_pot_multiplier = 1
    else:
        tie_names = ", ".join([p.split()[0] for p in players_with_min])
        if carry_over:
            hole_results.append({
                "Hole": hole_col, "Par/HDCP": f"P:{par_values[h] if h < len(par_values) else 4} | H:{hole_hdcp}", "Net Winner": "-", "Group": "-", "Winning Net": int(min_net), 
                "Status": f"Tied ({tie_names}) - Carried", "Hole Value": f"${current_hole_value:,.2f}"
            })
            current_pot_multiplier += 1
        else:
            hole_results.append({
                "Hole": hole_col, "Par/HDCP": f"P:{par_values[h] if h < len(par_values) else 4} | H:{hole_hdcp}", "Net Winner": "-", "Group": "-", "Winning Net": int(min_net), 
                "Status": f"Tied ({tie_names}) - Expired", "Hole Value": f"${current_hole_value:,.2f}"
            })
            current_pot_multiplier = 1

    net_row = {"Hole": hole_col}
    net_row.update(net_scores_map)
    net_matrix_rows.append(net_row)

summary_df = pd.DataFrame(hole_results)
master_board_data = [{"Player": p, "Group": player_groups.get(p, "-"), "Cash Won": cash} for p, cash in player_cash_won.items()]
master_board = pd.DataFrame(master_board_data).sort_values(by="Cash Won", ascending=False).reset_index(drop=True)

with tabs[0]:
    st.subheader("🏆 Overall Field Leaderboard")
    st.write(f"Active Field Size: **{len(active_players_df)} Players** | Total Payout Pool: **${total_purse:.2f}**")
    st.dataframe(
        master_board,
        use_container_width=True,
        hide_index=True,
        column_config={"Cash Won": st.column_config.NumberColumn(format="$%.2f")}
    )

with tabs[1]:
    st.subheader("🎯 Field-Wide Skin Outcomes")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("🔢 Computed Net Scores Matrix")
    if net_matrix_rows:
        st.dataframe(pd.DataFrame(net_matrix_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No scores recorded yet to generate the net matrix.")

# ---------------------------------------------------------
# --- 5. ADMINISTRATIVE MAINTENANCE TOOLS (SIDEBAR APPEND) ---
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header("🛠️ Admin & Data Tools")

# Action 1: Export & Backup to Google Sheet Tab
if st.sidebar.button("📤 Export & Backup to Google Sheet", use_container_width=True, key="admin_drive_upload_btn"):
    with st.spinner("Saving backup to Google Sheet..."):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDS_DICT, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_key(SHEET_KEY)

            date_tab_name = f"Backup_{datetime.datetime.now().strftime('%d%b%Y')}"
            
            try:
                backup_ws = sheet.worksheet(date_tab_name)
                backup_ws.clear()
            except gspread.exceptions.WorksheetNotFound:
                backup_ws = sheet.add_worksheet(title=date_tab_name, rows="100", cols="30")

            df_export = master_db.fillna("")
            backup_ws.update([df_export.columns.values.tolist()] + df_export.values.tolist())

            st.sidebar.success(f"✅ Successfully backed up to Sheet tab:\n\n📂 **Tab Name:** `{date_tab_name}`")
        except Exception as e:
            st.sidebar.error(f"❌ Sheet backup failed: {e}")

# Action 2: Reset Local DB and Purge Scorecard/Group Tabs in Google Sheets
if st.sidebar.button("🚨 Reset Database File", use_container_width=True, type="primary", key="admin_factory_reset_btn"):
    with st.spinner("Wiping local database and deleting Google Sheet scorecard tabs..."):
        initialize_flat_file()
        ok, deleted_tabs = delete_all_scorecard_and_group_tabs(SHEET_KEY)
        
        st.cache_data.clear()
        
        if ok:
            if deleted_tabs:
                st.sidebar.success(f"Database cleanly wiped! Deleted tabs: {', '.join(deleted_tabs)}")
            else:
                st.sidebar.success("Database cleanly wiped! No scorecard tabs needed deletion.")
        else:
            st.sidebar.warning(f"Local database reset, but Google Sheets tab deletion failed: {deleted_tabs}")
        st.rerun()
