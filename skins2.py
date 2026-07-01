import streamlit as st
import pandas as pd
import numpy as np
import math
import os

st.set_page_config(page_title="Net Golf Skins Tracker", layout="wide")

# --- Configuration Constants ---
HOLES = 10
MAX_GROUPS = 4
DB_FILE = "skins_database.csv"

st.title("⛳ LJ Happy Hour Golf Skins Tracker")
st.write("Calculate net skins, handle payouts, and manage group-specific digital scorecards dynamically.")

# ---------------------------------------------------------
# --- 1. GLOBAL DATABASE SYSTEM (Multi-Device Sync) ---
# ---------------------------------------------------------

# Global Game Setup Parameters
st.sidebar.header("⚙️ Game Settings")
num_players = st.sidebar.number_input("Total Number of Players", min_value=1, max_value=100, value=8, step=1)
carry_over = st.sidebar.checkbox("Carry over tied skins?", value=True)

# Purse Metrics Setup
st.sidebar.markdown("---")
st.sidebar.header("💰 Purse Settings")
buy_in_per_player = st.sidebar.number_input("Buy-in Amount per Player ($)", min_value=0, value=10, step=5)

total_purse = num_players * buy_in_per_player
skin_value_per_hole = total_purse / HOLES

st.sidebar.metric("Total Game Purse", f"${total_purse}")
st.sidebar.metric("Base Payout / Hole", f"${skin_value_per_hole:,.2f}")

# Helper function to initialize database from scratch if missing
def initialize_flat_file():
    df_rows = []
    for i in range(100):  # Pre-allocate 100 possible player rows
        group_num = (i // 4) + 1
        row = {
            "Player": f"Player {i+1}",
            "Group": f"Group {min(group_num, MAX_GROUPS)}",
            "Tee": "Blue",
            "Handicap": 10
        }
        for h in range(HOLES):
            row[f"Hole {h+1}"] = 0
        df_rows.append(row)
    pd.DataFrame(df_rows).to_csv(DB_FILE, index=False)

# Check if flat-file database exists; if not, create it
if not os.path.exists(DB_FILE):
    initialize_flat_file()

# ALWAYS read fresh data from the file on script execution to catch changes from other devices
master_db = pd.read_csv(DB_FILE)

# Filter database rows to match current number of active players
active_players_df = master_db.iloc[:num_players].copy()

# Sync Tee configuration string locally or via session state fallback
if 'tee_colors_input' not in st.session_state:
    st.session_state.tee_colors_input = "Gold, Blue, White, Green, Red, White/Green, Green/Red"

if 'course_df' not in st.session_state:
    st.session_state.course_df = pd.DataFrame({
        "Hole": [f"Hole {i+1}" for i in range(HOLES)],
        "Par": [5, 3, 4, 3, 4, 5, 4, 4, 4, 5],
        "Hole Handicap": [17, 9, 1, 13, 11, 15, 7, 5, 3, 10] 
    }).set_index("Hole").T

if 'active_scorecard_group' not in st.session_state:
    st.session_state.active_scorecard_group = 1


# ---------------------------------------------------------
# --- 2. INTERACTIVE COMPONENT RENDERING ---
# ---------------------------------------------------------

# --- Course Setup Configuration ---
st.header("🏌️‍♂️ 1. Course & Tee Settings")
col_c1, col_c2 = st.columns([3, 1])

with col_c2:
    st.write("**Manage Tee Options**")
    tee_input = st.text_input("Enter available tees (comma-separated):", value=st.session_state.tee_colors_input)
    st.session_state.tee_colors_input = tee_input
    available_tees = [tee.strip() for tee in tee_input.split(",") if tee.strip()]
    if not available_tees:
        available_tees = ["Standard"]

with col_c1:
    st.write("**Configure Hole Properties**")
    edited_course = st.data_editor(st.session_state.course_df, use_container_width=True, key="course_editor")
    st.session_state.course_df = edited_course
    par_values = edited_course.loc["Par"].tolist()
    hole_hdcp_values = edited_course.loc["Hole Handicap"].tolist()


# --- Player Roster Setup (Stabilized via File-Sync) ---
st.header("👤 2. Player Roster & Handicap Settings")
st.write("Assign players to their designated Groups and choose their starting Tee Boxes. Edits will lock globally.")

roster_config = {
    "Player": st.column_config.TextColumn("Player Name", required=True),
    "Group": st.column_config.SelectboxColumn("Assigned Group", options=[f"Group {g+1}" for g in range(MAX_GROUPS)], required=True),
    "Tee": st.column_config.SelectboxColumn("Tee Box", options=available_tees, required=True),
    "Handicap": st.column_config.NumberColumn("Handicap Index", min_value=0, max_value=54, step=1, required=True)
}

# Pull columns relevant to Roster setup view
roster_view_cols = ["Player", "Group", "Tee", "Handicap"]
roster_slice = active_players_df[roster_view_cols]

edited_roster_matrix = st.data_editor(
    roster_slice,
    use_container_width=True,
    hide_index=True,
    column_config=roster_config,
    key="global_roster_editor" 
)

# Save changes back to the shared CSV file if updates occur
if not edited_roster_matrix.equals(roster_slice):
    for i, row in edited_roster_matrix.iterrows():
        master_db.at[i, "Player"] = row["Player"]
        master_db.at[i, "Group"] = row["Group"]
        master_db.at[i, "Tee"] = row["Tee"]
        master_db.at[i, "Handicap"] = row["Handicap"]
    master_db.to_csv(DB_FILE, index=False)
    st.rerun()


# --- Group Scorecard Active Controllers ---
st.sidebar.markdown("---")
st.sidebar.header("📱 Active Scorecard Form Menu")
st.sidebar.write("Select your group to access the dedicated input form:")

for g in range(MAX_GROUPS):
    if st.sidebar.button(f"📋 Group {g+1} Scorecard", use_container_width=True):
        st.session_state.active_scorecard_group = g + 1

# --- Render Isolated Scoring Form ---
active_g = st.session_state.active_scorecard_group
st.header(f"📝 3. Score Entry Form: Group {active_g}")

# Filter currently synchronized memory matching active group constraint
group_mask = active_players_df["Group"] == f"Group {active_g}"
active_group_df = active_players_df[group_mask]

if active_group_df.empty:
    st.warning(f"No players are currently assigned to Group {active_g}. Assign players in the Roster table above to log scores.")
else:
    with st.form(key=f"score_form_group_{active_g}", clear_on_submit=False):
        st.subheader("Select Hole & Input Scores")
        
        hole_options = [f"Hole {i+1}" for i in range(HOLES)]
        selected_hole = st.selectbox("Choose Hole to Update:", hole_options)
        
        hole_idx = hole_options.index(selected_hole)
        st.caption(f"ℹ️ **{selected_hole} Details** — Par: {par_values[hole_idx]} | Handicap Rating: {hole_hdcp_values[hole_idx]}")
        st.markdown("---")
        
        input_scores = {}
        for idx, row in active_group_df.iterrows():
            p_name = row["Player"]
            p_hdcp = row["Handicap"]
            p_tee = row["Tee"]
            current_score_value = int(row[selected_hole])
            
            score_input = st.number_input(
                label=f"{p_name} (Tee: {p_tee} | HDCP: {p_hdcp})",
                min_value=0,
                max_value=15,
                value=current_score_value if current_score_value > 0 else par_values[hole_idx], 
                step=1,
                key=f"input_{p_name}_{selected_hole}"
            )
            input_scores[p_name] = score_input
            
        submit_button = st.form_submit_button(label="💾 Save Hole Scores Globally")

    if submit_button:
        # Write directly to master database matrix tracking
        for idx, row in master_db.iterrows():
            if row["Group"] == f"Group {active_g}" and row["Player"] in input_scores:
                master_db.at[idx, selected_hole] = input_scores[row["Player"]]
        # Save to disk file instantly so other device sessions see updates
        master_db.to_csv(DB_FILE, index=False)
        st.success(f"Scores saved successfully for {selected_hole}!")
        st.rerun()


# --- Display Current Active Scores Matrix for Verification ---
with st.expander(f"👀 View Group {active_g} Live Running Scorecard Summary"):
    st.dataframe(
        active_players_df[active_players_df["Group"] == f"Group {active_g}"],
        use_container_width=True,
        hide_index=True
    )


# ---------------------------------------------------------
# --- 3. NET CALCULATIONS & CASH ENGINE ---
# ---------------------------------------------------------

def get_strokes_received(player_hdcp, hole_hdcp, hole_hdcp_list):
    strokes = player_hdcp // 18
    remainder = player_hdcp % 18
    active_handicaps_sorted = sorted(hole_hdcp_list)
    
    if remainder > 0:
        cutoff_index = min(remainder - 1, len(active_handicaps_sorted) - 1)
        cutoff_hdcp_val = active_handicaps_sorted[cutoff_index]
        
        if hole_hdcp <= cutoff_hdcp_val:
            lower_count = sum(1 for x in hole_hdcp_list if x < hole_hdcp)
            match_count = sum(1 for x in hole_hdcp_list[:hole_hdcp_list.index(hole_hdcp)+1] if x == hole_hdcp)
            if (lower_count + match_count) <= remainder:
                strokes += 1
    return strokes

st.header("📊 4. Net Results, Cash Pools, & Leaderboards")
tab_titles = [f"Group {g+1}" for g in range(MAX_GROUPS)] + ["🏆 Master Cash Leaderboard"]
tabs = st.tabs(tab_titles)

all_group_summaries = []

for g in range(MAX_GROUPS):
    group_label = f"Group {g+1}"
    group_data = active_players_df[active_players_df["Group"] == group_label].copy()
    
    net_scores_matrix = group_data.copy()
    player_cash_won = {row["Player"]: 0.0 for _, row in group_data.iterrows()}
    hole_results = []
    
    current_pot_multiplier = 1
    
    for h in range(HOLES):
        hole_col = f"Hole {h+1}"
        hole_hdcp = hole_hdcp_values[h]
        current_hole_value = skin_value_per_hole * current_pot_multiplier
        
        net_scores_map = {}
        for idx, row in group_data.iterrows():
            player_name = row["Player"]
            gross = row[hole_col]
            hdcp = row["Handicap"]
            
            strokes_allowed = get_strokes_received(hdcp, hole_hdcp, hole_hdcp_values)
            if gross > 0:
                net_scores_map[player_name] = max(1, gross - strokes_allowed)
                net_scores_matrix.at[idx, hole_col] = max(1, gross - strokes_allowed)
            else:
                net_scores_matrix.at[idx, hole_col] = 0
                
        valid_net_scores = pd.Series(net_scores_map)
        
        if valid_net_scores.empty:
            hole_results.append({
                "Hole": hole_col, "Net Winner": "-", "Winning Net": "-", 
                "Status": "Unplayed", "Hole Value": f"${current_hole_value:,.2f}"
            })
            if not carry_over: current_pot_multiplier = 1
            continue
            
        min_net = valid_net_scores.min()
        players_with_min = valid_net_scores[valid_net_scores == min_net].index.tolist()
        
        if len(players_with_min) == 1:
            winner = players_with_min[0]
            player_cash_won[winner] += current_hole_value
            hole_results.append({
                "Hole": hole_col, "Net Winner": winner, "Winning Net": int(min_net), 
                "Status": "Skin Won!", "Hole Value": f"${current_hole_value:,.2f}"
            })
            current_pot_multiplier = 1
        else:
            if carry_over:
                hole_results.append({
                    "Hole": hole_col, "Net Winner": "-", "Winning Net": int(min_net), 
                    "Status": f"Tied (x{len(players_with_min)}) - Carried", "Hole Value": f"${current_hole_value:,.2f}"
                })
                current_pot_multiplier += 1
            else:
                hole_results.append({
                    "Hole": hole_col, "Net Winner": "-", "Winning Net": int(min_net), 
                    "Status": "Tied - Expired", "Hole Value": f"${current_hole_value:,.2f}"
                })
                current_pot_multiplier = 1

    summary_df = pd.DataFrame(hole_results)
    leaderboard_df = pd.DataFrame(list(player_cash_won.items()), columns=["Player", "Cash Won"]).sort_values(by="Cash Won", ascending=False)
    leaderboard_df["Group"] = group_label
    all_group_summaries.append(leaderboard_df)
    
    with tabs[g]:
        st.subheader(f"Group {g+1} Statistics")
        if group_data.empty:
            st.info("No players assigned to this group yet.")
        else:
            col1, col2 = st.columns([3, 2])
            with col1:
                st.caption("Hole Breakdown")
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
            with col2:
                st.caption("Financial Standings")
                st.dataframe(
                    leaderboard_df[["Player", "Cash Won"]], 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={"Cash Won": st.column_config.NumberColumn(format="$%.2f")}
                )

# Master Leaderboard Panel
with tabs[-1]:
    st.subheader("🏆 Overall Cash Board (All Instances)")
    if all_group_summaries:
        master_board = pd.concat(all_group_summaries).sort_values(by="Cash Won", ascending=False).reset_index(drop=True)
        st.dataframe(
            master_board[["Group", "Player", "Cash Won"]],
            use_container_width=True,
            column_config={"Cash Won": st.column_config.NumberColumn(format="$%.2f")}
        )
