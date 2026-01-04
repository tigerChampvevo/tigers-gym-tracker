import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import datetime

# --- SECURITY: LOAD SECRETS ---
# We use st.secrets so we never accidentally publish passwords
# This structure matches what we will put in Streamlit Cloud later
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
SHEET_URL = st.secrets["SHEET_URL"]
GCP_CREDENTIALS = st.secrets["gcp_service_account"]

# --- SETUP AI & SHEETS ---
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Connect to Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(GCP_CREDENTIALS), scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).worksheet("Workouts")

# --- DEFAULT ROUTINE (Your specific plan) ---
DEFAULT_ROUTINE = {
    "Push": [
        {"exercise": "Machine Chest Press", "sets": 3, "reps": "8-10", "default_weight": 45},
        {"exercise": "Pec Deck (Fly)", "sets": 3, "reps": "8-10", "default_weight": 120},
        {"exercise": "Machine Shoulder Press", "sets": 3, "reps": "10-12", "default_weight": 40},
        {"exercise": "Cable Tricep Pushdowns", "sets": 4, "reps": "12-15", "default_weight": 50},
        {"exercise": "Machine Incline Press", "sets": 3, "reps": "10", "default_weight": 45},
        {"exercise": "Machine Lateral Raise", "sets": 4, "reps": "15", "default_weight": 15}
    ],
    "Pull": [
        {"exercise": "Lat Pulldown (Wide)", "sets": 3, "reps": "10-12", "default_weight": 70},
        {"exercise": "Seated Cable Row", "sets": 3, "reps": "10-12", "default_weight": 70},
        {"exercise": "Face Pulls", "sets": 4, "reps": "15", "default_weight": 30},
        {"exercise": "Machine Bicep Curl", "sets": 3, "reps": "10-12", "default_weight": 30},
        {"exercise": "Cable Hammer Curls", "sets": 4, "reps": "12", "default_weight": 30},
        {"exercise": "Tricep Overhead Ext", "sets": 3, "reps": "12", "default_weight": 30}
    ],
    "Legs": [
        {"exercise": "Leg Press", "sets": 3, "reps": "10-12", "default_weight": 180},
        {"exercise": "Seated Leg Curl", "sets": 3, "reps": "12-15", "default_weight": 90},
        {"exercise": "Calf Raise Machine", "sets": 4, "reps": "15", "default_weight": 90},
        {"exercise": "Leg Extensions", "sets": 3, "reps": "8", "default_weight": 90},
        {"exercise": "Bulgarian Split Squats", "sets": 3, "reps": "10", "default_weight": 0}
    ],
    "Cardio": [
        {"exercise": "Incline Walk", "sets": 1, "reps": "40 mins", "default_weight": 0}
    ]
}

def get_last_weight(exercise_name):
    """
    Scans the Google Sheet to find the last weight used for this exercise.
    If not found, returns the default.
    """
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # Filter for this exercise
        ex_history = df[df['Exercise'] == exercise_name]
        if not ex_history.empty:
            # Return the last logged "Next Weight"
            return int(ex_history.iloc[-1]['Next_Weight'])
    except:
        pass # If sheet is empty or error, fallback
    
    # Fallback to default
    for day in DEFAULT_ROUTINE:
        for ex in DEFAULT_ROUTINE[day]:
            if ex['exercise'] == exercise_name:
                return ex['default_weight']
    return 0

def ask_gemini_coach(exercise, current_weight, difficulty):
    prompt = f"""
    I am a 25 year old male, 280lbs. 
    Exercise: {exercise}. Weight: {current_weight} lbs. Difficulty: {difficulty}.
    What should my weight be next time? 
    Return JSON: {{"new_weight": 50, "message": "Reasoning..."}}
    """
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except:
        return {"new_weight": current_weight, "message": "AI connection issue. Keeping weight same."}

# --- APP INTERFACE ---
st.title("🏋️‍♂️ Private Gym Tracker")

day = st.selectbox("Select Routine", ["Push", "Pull", "Legs", "Cardio"])
todays_exercises = DEFAULT_ROUTINE[day]

st.divider()

for ex in todays_exercises:
    # 1. Fetch data from Google Sheet (Slow but accurate)
    suggested_weight = get_last_weight(ex['exercise'])
    
    with st.expander(f"{ex['exercise']} (Target: {suggested_weight} lbs)"):
        st.write(f"Sets: {ex['sets']} | Reps: {ex['reps']}")
        
        col1, col2 = st.columns(2)
        with col1:
            actual_weight = st.number_input("Weight Used", value=suggested_weight, key=f"w_{ex['exercise']}")
        with col2:
            difficulty = st.selectbox("Difficulty", ["Perfect", "Too Easy", "Too Hard/Fail"], key=f"d_{ex['exercise']}")
            
        if st.button("Log Workout", key=f"btn_{ex['exercise']}"):
            with st.spinner("Saving to secure cloud..."):
                # Ask AI
                ai_result = ask_gemini_coach(ex['exercise'], actual_weight, difficulty)
                
                # Save to Google Sheet
                row_data = [
                    str(datetime.date.today()),
                    ex['exercise'],
                    actual_weight,
                    ex['sets'],
                    ex['reps'],
                    difficulty,
                    ai_result['new_weight'], # "Next Weight"
                    ai_result['message']
                ]
                sheet.append_row(row_data)
                
                st.success(f"Saved! Coach says: {ai_result['message']}")
                st.info(f"Next time: {ai_result['new_weight']} lbs")
