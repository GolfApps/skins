# Lake Jovita Happy Hour Skins game scoring app
# July 5, 2026

import streamlit as st
import pandas as pd
import numpy as np
import math
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Hide the Streamlit menu and footer
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# Define the path to the key file in the same directory
CREDS_DICT = st.secrets["gcp_service_account"]
SHEET_KEY = "1rdOkZWObTiT_ubGCFy8lG56L-ET7cUtukq2GR-StkjA"

st.set_page_config(page_title="Golf Skins Tracker", layout="wide")

# --- Configuration Constants ---
MAX_GROUPS = 4
DB_FILE = "skins_database.csv"
ROSTER_FILE = "master_roster.csv"

# Ensure the local master roster file exists
if not os.path.exists(ROSTER_FILE):
    # Initialize with default headers if it doesn't exist yet
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
        CREDS_DICT = st.secrets["gcp_service_account"]
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
            
            # 1. Extract the name string from the correct column index
            full_name = str(row[nm_idx]).strip()
            
            # 2. Safety check against blank rows using the extracted name
            if not full_name:
                continue
            
            group_val = "Unassigned"
            for col_name, idx in group_indices.items():
                if idx < len(row) and row[idx].strip():
                    group_val = row[idx].strip()
                    break
            
            # 3. Save to roster using full_name as the key
            # NOTE: We keep the internal key as "Handicap" so the main application loop reads it smoothly
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
        CREDS_DICT = st.secrets["gcp_service_account"]
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
        CREDS_DICT = st.secrets["gcp_service_account"]
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
    selected_course = st.sidebar.selectbox(
        "Select Course", 
        options=available_courses, 
        key="sidebar_course_select"
    )
    course_data = load_course_details(SHEET_KEY, selected_course)
    max_holes = len(course_data) if course_data else 0  #added here
    if max_holes > 0:
        default_hole_idx = min(9, max_holes - 1)
        chosen_num_holes = st.sidebar.selectbox(
            "Number of Holes",
            options=list(range(1, max_holes + 1)),
            index=default_hole_idx,
            key="sidebar_holes_select"
        )
        active_holes = course_data[:chosen_num_holes]
    else:
        st.sidebar.error(f"Connected to 'Course' tab, but found 0 holes listed for '{selected_course}'.")
else:
    st.sidebar.warning("No courses returned. Please check your Google Sheets connection.")

# Sync dynamic course parameters directly into running session state variables
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
# st.sidebar.header("⚙️ Game Settings")
num_players = st.sidebar.number_input("Total Number of Players", min_value=1, max_value=24, value=8, step=1)
carry_over = st.sidebar.checkbox("Carry over tied skins?", value=True)

st.sidebar.markdown("---")
st.sidebar.header("💰 Purse Settings")
buy_in_per_player = st.sidebar.number_input("Buy-in Amount per Player ($)", min_value=0, value=10, step=5)

total_purse = num_players * buy_in_per_player
skin_value_per_hole = total_purse / num_holes

st.sidebar.metric("Total Purse", f"${total_purse}")
st.sidebar.metric("Skin payout / Hole", f"${skin_value_per_hole:,.2f}")

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
        for h in range(18): # Pre-allocate all 18 standard tracking columns
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

if 'active_scorecard_group' not in st.session_state:
    st.session_state.active_scorecard_group = 1

# ---------------------------------------------------------
# --- INTERACTIVE MODULES & RENDERING ---
# ---------------------------------------------------------

# --- Course & Course Variables Setup ---
st.header("🏌️‍♂️Course & Tee Settings")
col_c1, col_c2 = st.columns([3, 1])

# available_tees = ["Gold", "Blue", "White", "White/Green", "Green", "Green/Red", "Red"]

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

# 1. Pull the fresh roster dictionary directly from your Google Sheet function
pulled_roster = load_master_roster(SHEET_KEY)

# 2. Extract options for the player names dropdown
dropdown_options = sorted(list(pulled_roster.keys()))

# 3. DYNAMIC TEE HARVESTER: Look through the sheet data to find ALL tee options (including "White/Green", etc.)
sheet_tees = set()
for player_name, info in pulled_roster.items():
    if info.get("Tee"):
        sheet_tees.add(info["Tee"].strip())

# Combine sheet tees with baseline defaults to ensure the dropdown is completely covered
baseline_tees = ["Blue", "White", "Green", "Gold", "Red"]
dynamic_tee_options = sorted(list(sheet_tees.union(baseline_tees)))

# 4. Configure the table layout with the newly expanded dynamic tee choices
roster_config = {
    "Player": st.column_config.SelectboxColumn("Player Name", options=dropdown_options, required=True),
    "Group": st.column_config.SelectboxColumn("Assigned Group", options=[f"Group {g+1}" for g in range(4)], required=True),
    "Tee": st.column_config.SelectboxColumn("Tee Box", options=dynamic_tee_options, required=True), # <-- Now tracks combo tees perfectly!
    "Handicap": st.column_config.NumberColumn("Handicap Index / PH", min_value=0, max_value=54, step=1, required=True)
}

roster_view_cols = ["Player", "Group", "Tee", "Handicap"]
roster_slice = active_players_df[roster_view_cols]

# 5. Display the interactive selection matrix
edited_roster_matrix = st.data_editor(
    roster_slice,
    use_container_width=True,
    hide_index=True,
    column_config=roster_config,
    key="global_roster_editor" 
)

# 6. Smart Update Engine
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

# --- Group Scorecard Navigation ---
st.sidebar.markdown("---")
st.sidebar.header("📱 Active Scorecard Form Menu")
for g in range(MAX_GROUPS):
    if st.sidebar.button(f"📋 Group {g+1} Scorecard", use_container_width=True):
        st.session_state.active_scorecard_group = g + 1
 
# ---------------------------------------------------------
# --- 3. DYNAMIC SCORE ENTRY FORM (CRASH-PROOFED) ---
# ---------------------------------------------------------

active_g = st.session_state.get("active_scorecard_group", 1)
st.header(f"📝 Group {active_g} Scorecard")

# Data Safeguard: Ensure 'Group' exists, string-cast it, and strip accidental whitespace
if "Group" in active_players_df.columns:
    active_players_df["Group"] = active_players_df["Group"].astype(str).str.strip()
    group_mask = active_players_df["Group"] == f"Group {active_g}"
    active_group_df = active_players_df[group_mask]
else:
    active_group_df = pd.DataFrame()

# Safe arrays extraction with global defaults to prevent row structural mismatches
try:
    par_values = st.session_state.course_df.loc["Par"].astype(int).tolist()
    hole_hdcp_values = st.session_state.course_df.loc["Hole Handicap"].astype(int).tolist()
except Exception:
    par_values = [4] * 18
    hole_hdcp_values = [10] * 18

if active_group_df.empty:
    st.warning(f"No players are currently assigned to Group {active_g}. Change player assignments to 'Group {active_g}' in Section 2 above to log scores.")
else:
    st.subheader("Select Hole & Input Scores")
    hole_options = [f"Hole {i+1}" for i in range(len(st.session_state.course_df.columns))]
    
    if hole_options:
        selected_hole = st.selectbox("Choose Hole to Update:", hole_options)
        hole_idx = hole_options.index(selected_hole)
        
        # Boundary proofing indexes
        current_par = par_values[hole_idx] if hole_idx < len(par_values) else 4
        current_hdcp = hole_hdcp_values[hole_idx] if hole_idx < len(hole_hdcp_values) else 10
        
        st.caption(f"ℹ️ **{selected_hole} Details** — Par: {current_par} | Handicap Rating: {current_hdcp}")
        st.markdown("---")
        
        with st.form(key=f"score_form_group_{active_g}", clear_on_submit=False):
            input_scores = {}
            for idx, row in active_group_df.iterrows():
                p_name = row["Player"]
                p_hdcp = row.get("Handicap", 10)
                p_tee = row.get("Tee", "Green")
                
                # CRASH GUARD: Seamlessly catch blank, NaN, or string values from data feeds
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
                if str(row["Group"]).strip() == f"Group {active_g}" and row["Player"] in input_scores:
                    master_db.at[idx, selected_hole] = input_scores[row["Player"]]
            master_db.to_csv(DB_FILE, index=False)
            st.success(f"Scores saved successfully for {selected_hole}!")
            st.rerun()
    else:
        st.error("No active holes found in your course configurations matrix.")

with st.expander(f"👀 View Group {active_g} Live Running Scorecard Summary"):
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

# Action 1: Export Data to Google Drive Engine
import datetime
# Generates string format like: 05Jul2026
date_str = datetime.datetime.now().strftime("%d%b%Y")
formatted_filename = f"golf_skins_backup_{date_str}.csv"

if st.sidebar.button("📤 Export & Backup to Google Drive", use_container_width=True, key="admin_drive_upload_btn"):
    with st.spinner("Uploading backup to Google Drive..."):
        # Import standard google client handlers inside the button trigger
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        import httplib2
        
        try:
            # 1. Establish auth context using existing scope parameters
            CREDS_DICT = st.secrets["gcp_service_account"]
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_DICT, scope)
            http_auth = creds.authorize(httplib2.Http())
            
            # 2. Build out the Drive API client
            service = build('drive', 'v3', http=http_auth)
            
            # 3. Transform master dataframe into memory stream bytes
            csv_bytes = master_db.to_csv(index=False).encode('utf-8')
            
            # 4. Finalize payload metadata details
            file_metadata = {
                'name': formatted_filename,
                'mimeType': 'text/csv'
            }
            media = MediaInMemoryUpload(csv_bytes, mimetype='text/csv', resumable=True)
            
            # 5. Commit upload execution to the service account drive directory
            drive_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            
            if drive_file.get('id'):
                st.sidebar.success(f"✅ Successfully backed up to Drive!\n\n📂 **File Name:** `{formatted_filename}`")
        except Exception as e:
            st.sidebar.error(f"❌ Drive upload failed: {e}")

# Action 2: Heavy Reset Data Engine
if st.sidebar.button("🚨 Reset Database File", use_container_width=True, type="primary", key="admin_factory_reset_btn"):
    initialize_flat_file()
    st.sidebar.success("Database cleanly wiped back to default blanks!")
    st.rerun()
