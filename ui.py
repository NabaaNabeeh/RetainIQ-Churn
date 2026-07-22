import streamlit as st
import requests
import sqlite3
import json
import pandas as pd
import random
from datetime import date, datetime, timedelta

st.set_page_config(page_title="RetainIQ Predictor", page_icon="🔮", layout="wide")

# ==========================================
# 1. DATABASE SETUP & MIGRATION
# ==========================================
def init_db():
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
                    customerID TEXT PRIMARY KEY, 
                    date_added TEXT,
                    added_by TEXT,
                    real_added_by TEXT DEFAULT 'unknown',
                    public_last_edited_by TEXT DEFAULT 'No edits yet',
                    real_last_edited_by TEXT DEFAULT 'No edits yet',
                    prediction_result TEXT,
                    churn_probability REAL,
                    raw_data TEXT
                )''')
    
    # Safe migrations
    try: c.execute("ALTER TABLE customers ADD COLUMN added_by TEXT DEFAULT 'unknown'")
    except sqlite3.OperationalError: pass 
    try: c.execute("ALTER TABLE customers ADD COLUMN real_added_by TEXT DEFAULT 'unknown'")
    except sqlite3.OperationalError: pass 
    try: c.execute("ALTER TABLE customers ADD COLUMN public_last_edited_by TEXT DEFAULT 'No edits yet'")
    except sqlite3.OperationalError: pass 
    try: c.execute("ALTER TABLE customers ADD COLUMN real_last_edited_by TEXT DEFAULT 'No edits yet'")
    except sqlite3.OperationalError: pass 

    # Clean up legacy data
    try: c.execute("UPDATE customers SET real_added_by = added_by WHERE real_added_by = 'unknown' OR real_added_by IS NULL")
    except sqlite3.OperationalError: pass
    try: c.execute("UPDATE customers SET public_last_edited_by = 'No edits yet' WHERE public_last_edited_by = 'unknown' OR public_last_edited_by IS NULL")
    except sqlite3.OperationalError: pass
    try: c.execute("UPDATE customers SET real_last_edited_by = 'No edits yet' WHERE real_last_edited_by = 'unknown' OR real_last_edited_by IS NULL")
    except sqlite3.OperationalError: pass
    
    c.execute("SELECT * FROM users WHERE username='admin'")
    if c.fetchone() is None:
        c.execute("INSERT INTO users (username, password) VALUES ('admin', 'admin')")
        
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. SESSION STATE
# ==========================================
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if "username" not in st.session_state: st.session_state["username"] = ""
if "unlocked_records" not in st.session_state: st.session_state["unlocked_records"] = {}

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def check_login(username, password):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()
    return user is not None

def register_user(username, password):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False 
    conn.close()
    return success

def change_password(username, new_password):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("UPDATE users SET password=? WHERE username=?", (new_password, username))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def save_customer_data(customerID, prediction, probability, payload, added_by, real_added_by, public_last_edit, real_last_edit):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT OR REPLACE INTO customers 
                 (customerID, date_added, added_by, real_added_by, public_last_edited_by, real_last_edited_by, prediction_result, churn_probability, raw_data) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
              (customerID, timestamp, added_by, real_added_by, public_last_edit, real_last_edit, prediction, probability, json.dumps(payload)))
    conn.commit()
    conn.close()

def delete_customer_data(customerID):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE customerID=?", (customerID,))
    conn.commit()
    conn.close()

def get_customer_record(customerID):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    try:
        c.execute("SELECT added_by, real_added_by, public_last_edited_by, real_last_edited_by, raw_data FROM customers WHERE customerID=?", (customerID,))
        row = c.fetchone()
        if row: return {"added_by": row[0], "real_added_by": row[1], "public_last_edited_by": row[2], "real_last_edited_by": row[3], "raw_data": json.loads(row[4])}
    except sqlite3.OperationalError:
        c.execute("SELECT added_by, raw_data FROM customers WHERE customerID=?", (customerID,))
        row = c.fetchone()
        if row: return {"added_by": row[0], "real_added_by": row[0], "public_last_edited_by": "No edits yet", "real_last_edited_by": "No edits yet", "raw_data": json.loads(row[1])}
    finally:
        conn.close()
    return None

def generate_mock_payload(cid):
    """Generates realistic random data for bulk testing"""
    int_service = random.choice(["DSL", "Fiber optic", "No"])
    phone_service = random.choice(["Yes", "No"])

    int_opts = ["No internet service"] if int_service == "No" else ["Yes", "No"]
    pho_opts = ["No phone service"] if phone_service == "No" else ["Yes", "No"]

    tenure = random.randint(0, 72)
    monthly = round(random.uniform(18.0, 120.0), 2)

    return {
        "customerID": str(cid),
        "gender": random.choice(["Male", "Female"]),
        "SeniorCitizen": random.choice([0, 1]),
        "Partner": random.choice(["Yes", "No"]),
        "Dependents": random.choice(["Yes", "No"]),
        "tenure": tenure,
        "PhoneService": phone_service,
        "MultipleLines": random.choice(pho_opts),
        "InternetService": int_service,
        "OnlineSecurity": random.choice(int_opts),
        "OnlineBackup": random.choice(int_opts),
        "DeviceProtection": random.choice(int_opts),
        "TechSupport": random.choice(int_opts),
        "StreamingTV": random.choice(int_opts),
        "StreamingMovies": random.choice(int_opts),
        "Contract": random.choice(["Month-to-month", "One year", "Two year"]),
        "PaperlessBilling": random.choice(["Yes", "No"]),
        "PaymentMethod": random.choice(["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"]),
        "MonthlyCharges": monthly,
        "TotalCharges": str(round(monthly * tenure, 2))
    }

# ==========================================
# 4. REUSABLE UI ENGINE
# ==========================================
def render_prediction_ui(defaults=None, is_admin_edit=False, key_prefix=""):
    if defaults is None: defaults = {}
    
    def get_idx(options, val):
        return options.index(val) if val in options else 0

    st.subheader("👤 Identity")
    cid_val = defaults.get("customerID", "")
    
    wp = key_prefix
    current_user = st.session_state["username"]
    assigned_user = current_user 
    
    if is_admin_edit:
        customerID = st.text_input("Customer ID", value=cid_val, disabled=True, key=f"{key_prefix}cid")
    else:
        customerID = st.text_input("Customer ID", value=cid_val, placeholder="e.g. 9451-LPGOO", key=f"{key_prefix}cid", help="Enter the customer ID (can contain letters and dashes).")
        
    if customerID:
        wp = f"{key_prefix}{customerID}_"
        record = get_customer_record(customerID)
        
        if record:
            added_by = record["added_by"]
            
            if added_by == current_user or current_user == "admin":
                st.session_state["unlocked_records"][customerID] = True
            
            if not st.session_state["unlocked_records"].get(customerID):
                st.warning(f"🔒 This ID belongs to user: **{added_by}**")
                unlock_pass = st.text_input(f"Enter password for '{added_by}' to unlock and edit:", type="password", key=f"{wp}unlock")
                
                if unlock_pass:
                    if check_login(added_by, unlock_pass):
                        st.session_state["unlocked_records"][customerID] = True
                        st.rerun() 
                    else:
                        st.error("❌ Incorrect password.")
                        
                st.info("The form is hidden. Please enter the correct password above to edit this record.")
                return  
            else:
                if current_user == "admin":
                    st.success(f"🔓 Editing record. Public Creator: **{added_by}** | True Creator: **{record['real_added_by']}** | True Edit: **{record['real_last_edited_by']}**")
                else:
                    st.success(f"🔓 Editing record. Created by: **{added_by}** | Last edited by: **{record['public_last_edited_by']}**")
                
                if not defaults: 
                    defaults = record["raw_data"] 
        else:
            if current_user == "admin":
                all_users = get_all_users()
                st.info("✨ This is a new Customer ID.")
                assigned_user = st.selectbox("Assign Record Creator To (Public view):", all_users, index=all_users.index('admin') if 'admin' in all_users else 0, key=f"{wp}assign")

    st.divider()
    st.subheader("👥 Demographics")
    col1, col2, col3, col4 = st.columns(4)
    
    g_opts = ["Select...", "Male", "Female"]
    gender = col1.selectbox("Gender", g_opts, index=get_idx(g_opts, defaults.get("gender")), key=f"{wp}gen")
    
    sen_val = "Yes" if defaults.get("SeniorCitizen") == 1 else ("No" if "SeniorCitizen" in defaults else "Select...")
    sen_opts = ["Select...", "Yes", "No"]
    senior_str = col2.selectbox("Senior Citizen?", sen_opts, index=get_idx(sen_opts, sen_val), key=f"{wp}sen")
    
    yn_opts = ["Select...", "Yes", "No"]
    Partner = col3.selectbox("Has Partner?", yn_opts, index=get_idx(yn_opts, defaults.get("Partner")), key=f"{wp}par")
    Dependents = col4.selectbox("Has Dependents?", yn_opts, index=get_idx(yn_opts, defaults.get("Dependents")), key=f"{wp}dep")

    st.divider()
    st.subheader("🌐 Active Services")
    c_int1, c_int2 = st.columns(2)
    
    int_opts = ["Select...", "DSL", "Fiber optic", "No"]
    InternetService = c_int1.selectbox("Internet Service", int_opts, index=get_idx(int_opts, defaults.get("InternetService")), key=f"{wp}int")
    PhoneService = c_int2.selectbox("Phone Service", yn_opts, index=get_idx(yn_opts, defaults.get("PhoneService")), key=f"{wp}pho")

    int_dis = (InternetService == "No")
    sub_int_opts = ["No internet service"] if int_dis else ["Select...", "Yes", "No"]

    pho_dis = (PhoneService == "No")
    sub_pho_opts = ["No phone service"] if pho_dis else ["Select...", "Yes", "No"]

    col5, col6, col7 = st.columns(3)
    MultipleLines = col5.selectbox("Multiple Lines", sub_pho_opts, index=get_idx(sub_pho_opts, defaults.get("MultipleLines")), disabled=pho_dis, key=f"{wp}mul")
    OnlineSecurity = col5.selectbox("Online Security", sub_int_opts, index=get_idx(sub_int_opts, defaults.get("OnlineSecurity")), disabled=int_dis, key=f"{wp}sec")
    
    OnlineBackup = col6.selectbox("Online Backup", sub_int_opts, index=get_idx(sub_int_opts, defaults.get("OnlineBackup")), disabled=int_dis, key=f"{wp}bak")
    DeviceProtection = col6.selectbox("Device Protection", sub_int_opts, index=get_idx(sub_int_opts, defaults.get("DeviceProtection")), disabled=int_dis, key=f"{wp}dev")
    
    TechSupport = col7.selectbox("Tech Support", sub_int_opts, index=get_idx(sub_int_opts, defaults.get("TechSupport")), disabled=int_dis, key=f"{wp}sup")
    StreamingTV = col7.selectbox("Streaming TV", sub_int_opts, index=get_idx(sub_int_opts, defaults.get("StreamingTV")), disabled=int_dis, key=f"{wp}tv")
    StreamingMovies = st.selectbox("Streaming Movies", sub_int_opts, index=get_idx(sub_int_opts, defaults.get("StreamingMovies")), disabled=int_dis, key=f"{wp}mov")

    st.divider()
    st.subheader("💳 Contract & Billing")
    
    col8, col9 = st.columns(2)
    
    today = date.today()
    tenure_saved = defaults.get("tenure", 0)
    default_date = today - timedelta(days=int(tenure_saved)*30) 
    
    start_date = col8.date_input("Customer Start Date", value=default_date, max_value=today, key=f"{wp}dat")
    tenure_months = (today.year - start_date.year) * 12 + (today.month - start_date.month)
    if tenure_months < 0: tenure_months = 0
    col8.info(f"Calculated Tenure: **{tenure_months} months**")
    
    con_opts = ["Select...", "Month-to-month", "One year", "Two year"]
    Contract = col9.selectbox("Contract Type", con_opts, index=get_idx(con_opts, defaults.get("Contract")), key=f"{wp}con")
    PaperlessBilling = col9.selectbox("Paperless Billing?", yn_opts, index=get_idx(yn_opts, defaults.get("PaperlessBilling")), key=f"{wp}pap")
    
    pay_opts = ["Select...", "Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"]
    PaymentMethod = col9.selectbox("Payment Method", pay_opts, index=get_idx(pay_opts, defaults.get("PaymentMethod")), key=f"{wp}pay")

    col10, col11 = st.columns(2)
    MonthlyCharges_str = col10.text_input("Monthly Charges ($)", value=str(defaults.get("MonthlyCharges", "")), placeholder="e.g. 50.00", key=f"{wp}mch", help="Press Enter or click outside to instantly calculate the total.")
    
    try:
        monthly_val = float(MonthlyCharges_str)
        total_calc = monthly_val * tenure_months
    except ValueError:
        monthly_val = 0.0
        total_calc = 0.0

    col11.text_input("Total Charges ($) [Auto-Calculated]", value=f"{total_calc:.2f}", disabled=True)

    st.write("")
    btn_label = "💾 Update Customer Record" if (is_admin_edit or defaults) else "🔮 Predict & Save Data"
    submitted = st.button(btn_label, use_container_width=True, type="primary", key=f"{wp}sub")

    if submitted:
        errors = []
        if not customerID.strip(): errors.append("Customer ID is missing.")
        if "Select..." in [gender, senior_str, Partner, Dependents, InternetService, PhoneService, Contract, PaperlessBilling, PaymentMethod]:
            errors.append("Please make a selection for all applicable dropdown menus.")
        if monthly_val <= 0: errors.append("Please enter a valid Monthly Charge greater than 0.")

        if errors:
            for e in errors: st.error(f"❌ {e}")
        else:
            payload = {
                "customerID": customerID.strip(),
                "gender": gender,
                "SeniorCitizen": 1 if senior_str == "Yes" else 0,
                "Partner": Partner,
                "Dependents": Dependents,
                "tenure": tenure_months,
                "PhoneService": PhoneService,
                "MultipleLines": MultipleLines,
                "InternetService": InternetService,
                "OnlineSecurity": OnlineSecurity,
                "OnlineBackup": OnlineBackup,
                "DeviceProtection": DeviceProtection,
                "TechSupport": TechSupport,
                "StreamingTV": StreamingTV,
                "StreamingMovies": StreamingMovies,
                "Contract": Contract,
                "PaperlessBilling": PaperlessBilling,
                "PaymentMethod": PaymentMethod,
                "MonthlyCharges": monthly_val,
                "TotalCharges": str(total_calc)
            }

            try:
                with st.spinner('Asking the AI...'):
                    response = requests.post("http://localhost:8000/predict", json=payload)
                    response.raise_for_status()
                    result = response.json()
                
                existing = get_customer_record(payload["customerID"])
                
                if existing:
                    final_added_by = existing["added_by"]
                    final_real_added_by = existing["real_added_by"]
                    
                    if current_user == "admin":
                        final_public_edit = existing["public_last_edited_by"] 
                        final_real_edit = "admin"
                    else:
                        final_public_edit = current_user
                        final_real_edit = current_user
                else:
                    final_added_by = assigned_user 
                    final_real_added_by = current_user # Will be admin if admin creates it
                    final_public_edit = "No edits yet"
                    final_real_edit = "No edits yet"

                save_customer_data(
                    customerID=payload["customerID"], 
                    prediction=result["prediction"], 
                    probability=result['churn_probability'], 
                    payload=payload,
                    added_by=final_added_by,
                    real_added_by=final_real_added_by,
                    public_last_edit=final_public_edit,
                    real_last_edit=final_real_edit
                )

                st.divider()
                st.subheader("📊 Prediction Result (Saved)")
                if result["prediction"] == "Yes":
                    st.error(f"⚠️ **HIGH RISK OF CHURN** ({result['churn_probability'] * 100:.1f}%)")
                else:
                    st.success(f"✅ **LOW RISK OF CHURN** ({result['churn_probability'] * 100:.1f}%)")
                    
            except requests.exceptions.ConnectionError:
                st.error("❌ Could not connect to API. Is `python api.py` running?")
            except Exception as e:
                st.error(f"❌ Error: {e}")

# ==========================================
# 5. PAGE ROUTING & LAYOUTS
# ==========================================
if not st.session_state["logged_in"]:
    st.title("🔐 RetainIQ Portal Login")
    tab1, tab2 = st.tabs(["Login", "Register New User"])
    
    with tab1:
        st.subheader("Login to your account")
        log_user = st.text_input("Username", key="log_user")
        log_pass = st.text_input("Password", type="password", key="log_pass")
        if st.button("Login"):
            if check_login(log_user, log_pass):
                st.session_state["logged_in"] = True
                st.session_state["username"] = log_user
                st.rerun()
            else:
                st.error("❌ Invalid Username or Password")
                
    with tab2:
        st.subheader("Register an account")
        reg_user = st.text_input("New Username", key="reg_user")
        reg_pass = st.text_input("New Password", type="password", key="reg_pass")
        if st.button("Register"):
            if not reg_user or not reg_pass: st.warning("Please fill in both fields.")
            elif register_user(reg_user, reg_pass): st.success("✅ Account created! You can now log in.")
            else: st.error("❌ Username already exists.")

else:
    st.sidebar.title(f"👤 User: {st.session_state['username']}")
    
    menu_options = ["Predictor"]
    if st.session_state["username"] == "admin":
        menu_options.append("Admin Dashboard")
        
    menu_choice = st.sidebar.radio("Navigation", menu_options)
    
    st.sidebar.divider()
    col_a, col_b = st.sidebar.columns(2)
    
    if col_a.button("🚪 Logout", use_container_width=True):
        st.session_state["logged_in"] = False
        st.session_state["unlocked_records"] = {} 
        st.rerun()
        
    if col_b.button("🔄 Switch", use_container_width=True, help="Instantly log into a different account"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["unlocked_records"] = {} 
        st.rerun()

    if menu_choice == "Predictor":
        st.title("🔮 Customer Churn Predictor")
        st.write("Fill out the real-time form below.")
        render_prediction_ui(key_prefix="pred_")

    elif menu_choice == "Admin Dashboard":
        st.title("🗄️ Admin Dashboard")
        
        tab_data, tab_edit, tab_activity, tab_gen, tab_batch, tab_monitor, tab_settings = st.tabs([
            "📋 View Data", "✏️ Edit Records", "🧑💻 User Activity", "🧪 Generate Data", "📂 Batch Insights", "📊 Model Monitoring", "⚙️ Settings"
        ])
        
        with tab_data:
            conn = sqlite3.connect("app_data.db")
            # Fully expanded view for Admin tracking
            df = pd.read_sql_query("SELECT customerID, added_by as 'Public Creator', real_added_by as 'True Creator', public_last_edited_by as 'Public Editor', real_last_edited_by as 'True Editor', date_added as 'Timestamp', prediction_result as 'Result', churn_probability as 'Risk' FROM customers ORDER BY date_added DESC", conn)
            conn.close()
            
            st.dataframe(df, use_container_width=True)
            
            st.divider()
            st.subheader("🗑️ Delete Data")
            if not df.empty:
                col1, col2 = st.columns([3, 1])
                del_ids = col1.multiselect("Select IDs to Delete", df["customerID"].tolist(), key="del_ids")
                st.write("")
                if col2.button("Delete Selected", type="primary"):
                    if del_ids:
                        for d_id in del_ids:
                            delete_customer_data(d_id)
                        st.success(f"Deleted {len(del_ids)} records successfully!")
                        st.rerun()
                    else:
                        st.warning("Please select at least one ID to delete.")

        with tab_edit:
            st.subheader("🛠️ View / Edit Customer Details")
            conn = sqlite3.connect("app_data.db")
            df_ids = pd.read_sql_query("SELECT customerID FROM customers", conn)
            conn.close()
            
            if not df_ids.empty:
                edit_id = st.selectbox("Select Customer to Load", ["Select..."] + df_ids["customerID"].tolist(), key="edit_id")
                if edit_id != "Select...":
                    record = get_customer_record(edit_id)
                    if record:
                        st.divider()
                        render_prediction_ui(defaults=record["raw_data"], is_admin_edit=True, key_prefix=f"admin_{edit_id}_")
            else:
                st.info("No records available to edit.")

        with tab_activity:
            st.subheader("🧑💻 User Activity Tracker")
            all_registered_users = get_all_users()
            
            if not all_registered_users:
                st.info("No users found.")
            else:
                target_user = st.selectbox("Select a User to Inspect", all_registered_users, key="inspect_user")
                conn = sqlite3.connect("app_data.db")
                
                st.write(f"### 🆕 Records Created by **{target_user}**")
                df_created = pd.read_sql_query("SELECT customerID, added_by as 'Public Creator', real_added_by as 'True Creator', date_added as 'Timestamp', prediction_result as 'Result' FROM customers WHERE real_added_by = ? ORDER BY date_added DESC", conn, params=(target_user,))
                if df_created.empty: st.info(f"**{target_user}** hasn't created any records yet.")
                else: st.dataframe(df_created, use_container_width=True)
                    
                st.divider()
                st.write(f"### 📝 Records Edited by **{target_user}**")
                df_edited = pd.read_sql_query("SELECT customerID, public_last_edited_by as 'Public Editor', real_last_edited_by as 'True Editor', date_added as 'Timestamp', prediction_result as 'Result' FROM customers WHERE real_last_edited_by = ? ORDER BY date_added DESC", conn, params=(target_user,))
                if df_edited.empty: st.info(f"**{target_user}** hasn't edited any records yet.")
                else: st.dataframe(df_edited, use_container_width=True)
                conn.close()

        with tab_gen:
            st.subheader("🧪 Bulk Data Generator")
            st.write("Automatically generate and predict multiple randomized customer records.")
            
            all_users = get_all_users()
            
            col_g1, col_g2 = st.columns(2)
            num_to_gen_str = col_g1.text_input("Number of records to generate", value="5")
            num_to_gen = int(num_to_gen_str) if num_to_gen_str.isdigit() else 5
            
            assign_to = col_g2.multiselect("Assign Public Creator to (randomly distributed)", all_users, default=all_users)
            
            st.write("**ID Generation Range**")
            c_r1, c_r2 = st.columns(2)
            id_start_str = c_r1.text_input("From ID", value="10000")
            id_start = int(id_start_str) if id_start_str.isdigit() else 10000
            
            id_end_str = c_r2.text_input("To ID", value="99999")
            id_end = int(id_end_str) if id_end_str.isdigit() else 99999
            
            if st.button("🚀 Generate & Predict Data", type="primary"):
                if not assign_to:
                    st.error("Please select at least one user to assign the data to.")
                else:
                    conn = sqlite3.connect("app_data.db")
                    existing_ids = set(pd.read_sql_query("SELECT customerID FROM customers", conn)['customerID'].tolist())
                    conn.close()
                    
                    available_ids = [str(i) for i in range(int(id_start), int(id_end) + 1) if str(i) not in existing_ids]
                    
                    if len(available_ids) < num_to_gen:
                        st.error(f"❌ Not enough available IDs in that range! (Only {len(available_ids)} available)")
                    else:
                        chosen_ids = random.sample(available_ids, int(num_to_gen))
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        success_count = 0
                        for i, cid in enumerate(chosen_ids):
                            status_text.text(f"Generating record {i+1} of {num_to_gen} (ID: {cid})...")
                            payload = generate_mock_payload(cid)
                            assigned_creator = random.choice(assign_to)
                            
                            try:
                                resp = requests.post("http://localhost:8000/predict", json=payload)
                                resp.raise_for_status()
                                res = resp.json()
                                save_customer_data(
                                    customerID=payload["customerID"], 
                                    prediction=res["prediction"], 
                                    probability=res['churn_probability'], 
                                    payload=payload,
                                    added_by=assigned_creator,
                                    real_added_by="admin",
                                    public_last_edit="No edits yet",
                                    real_last_edit="No edits yet"
                                )
                                success_count += 1
                            except requests.exceptions.ConnectionError:
                                st.error("❌ Could not connect to API. Is `python api.py` running?")
                                break
                            except Exception as e:
                                st.error(f"Failed to generate ID {cid}: {e}")
                                
                            progress_bar.progress((i + 1) / num_to_gen)
                        
                        status_text.text(f"✅ Successfully generated {success_count} records!")
                        st.rerun()

        with tab_batch:
            st.subheader("📂 Batch Upload & Insights")
            st.write("Load an existing CSV/JSON file to run predictions and view insights. You can save them to the database afterward.")
            
            # File Upload section
            file_path = st.text_input("Enter absolute path to your data file (.csv or .json):", placeholder="e.g. C:/data/customers.csv")
            
            if st.button("Load Data & Predict", type="primary", key="load_batch_btn"):
                if not file_path:
                    st.error("Please enter a valid file path.")
                else:
                    try:
                        if file_path.endswith('.csv'):
                            df_batch = pd.read_csv(file_path)
                        elif file_path.endswith('.json'):
                            df_batch = pd.read_json(file_path)
                        else:
                            st.error("❌ Unsupported file format. Please use .csv or .json")
                            df_batch = pd.DataFrame()
                        
                        if not df_batch.empty:
                            # Preprocess for the API
                            if 'customerID' in df_batch.columns:
                                df_batch['customerID'] = df_batch['customerID'].astype(str)
                            if 'TotalCharges' in df_batch.columns:
                                df_batch['TotalCharges'] = df_batch['TotalCharges'].astype(str)

                            records = df_batch.to_dict(orient="records")
                            
                            # API request for batch prediction in chunks to avoid BATCH_MAX limit
                            BATCH_SIZE = 500
                            all_predictions = []
                            
                            with st.spinner(f'Running AI Batch Predictions on {len(records)} records (chunked)...'):
                                for i in range(0, len(records), BATCH_SIZE):
                                    chunk = records[i:i + BATCH_SIZE]
                                    payload = {"customers": chunk, "top_n": len(chunk)}
                                    resp = requests.post("http://localhost:8000/batch_predict", json=payload)
                                    
                                    if resp.status_code != 200:
                                        st.error(f"API Error ({resp.status_code}) on chunk {i}: {resp.text}")
                                        resp.raise_for_status()
                                        
                                    batch_res = resp.json()
                                    all_predictions.extend(batch_res["predictions"])
                                
                            preds_df = pd.DataFrame(all_predictions)
                            st.session_state["batch_results"] = preds_df
                            st.session_state["batch_data"] = df_batch
                            st.success(f"✅ Successfully analyzed {len(preds_df)} records!")
                            
                    except FileNotFoundError:
                        st.error(f"❌ File not found at path: {file_path}")
                    except requests.exceptions.ConnectionError:
                        st.error("❌ Could not connect to API. Make sure `python api.py` is running.")
                    except Exception as e:
                        st.error(f"❌ Error loading or predicting data: {e}")
                        
            # If results exist, display them and allow saving
            if "batch_results" in st.session_state:
                preds_df = st.session_state["batch_results"]
                df_batch = st.session_state["batch_data"]
                
                st.divider()
                st.subheader("📊 Data Insights")
                
                c1, c2 = st.columns(2)
                filter_type = c1.radio("Filter predictions by:", ["Top Risk (Will Churn)", "Lowest Risk (Will Not Churn)"], horizontal=True)
                top_k_str = c2.text_input("Select Top N records to show/save:", value=str(min(100, len(preds_df))))
                top_k = int(top_k_str) if top_k_str.isdigit() else min(100, len(preds_df))
                
                # Apply filters
                if "Will Churn" in filter_type:
                    filtered_preds = preds_df.sort_values(by="churn_probability", ascending=False).head(top_k)
                else:
                    filtered_preds = preds_df.sort_values(by="churn_probability", ascending=True).head(top_k)
                    
                # Merge predictions with original customer features for full view
                merged_df = pd.merge(df_batch, filtered_preds, left_on="customerID", right_on="customer_id", how="inner")

                # Summary Metrics
                m1, m2, m3, m4 = st.columns(4)
                total_k = len(filtered_preds)
                high_risk_count = (filtered_preds["prediction"] == "Yes").sum()
                avg_prob_k = filtered_preds["churn_probability"].mean() * 100
                top_contract = merged_df["Contract"].mode()[0] if "Contract" in merged_df.columns and not merged_df["Contract"].empty else "N/A"
                
                m1.metric("Selected Cohort Size", f"{total_k}")
                m2.metric("High Churn Risk (Yes)", f"{high_risk_count}", delta=f"{(high_risk_count/total_k*100):.1f}% of cohort" if total_k > 0 else "0%")
                m3.metric("Avg Churn Probability", f"{avg_prob_k:.1f}%")
                m4.metric("Dominant Contract Type", f"{top_contract}")
                
                st.write(f"Showing **{len(filtered_preds)}** records out of {len(preds_df)}:")
                
                # Full dataframe with all feature columns passed, but column_order sets 7 preferred columns visible by default
                target_preferred = ["customerID", "prediction", "churn_probability", "Contract", "tenure", "MonthlyCharges", "TotalCharges"]
                all_cols_ordered = [c for c in target_preferred if c in merged_df.columns] + [c for c in merged_df.columns if c not in target_preferred]
                display_df = merged_df[all_cols_ordered]
                
                default_visible = [c for c in target_preferred if c in display_df.columns]
                st.dataframe(display_df, column_order=default_visible, use_container_width=True)
                
                # Rich Visualizations with Explanations
                st.write("### 📈 Visualizations & Data Explanation")
                
                # Chart 1: Side-by-Side Model Comparison (Actual Churn vs AI Predicted Churn)
                if "Churn" in merged_df.columns:
                    st.markdown("#### 1. 🎯 Model Comparison: Actual Churn vs AI Predicted Churn (Side-by-Side)")
                    
                    actual_series = merged_df["Churn"].astype(str).str.strip().str.capitalize()
                    pred_series = merged_df["prediction"].astype(str).str.strip().str.capitalize()
                    
                    actual_counts = actual_series.value_counts()
                    pred_counts = pred_series.value_counts()
                    
                    comp_df = pd.DataFrame({
                        "Actual Churn (Ground Truth)": actual_counts,
                        "AI Predicted Churn": pred_counts
                    }).fillna(0)
                    
                    st.bar_chart(comp_df, stack=False)
                    
                    correct_count = (actual_series == pred_series).sum()
                    accuracy_pct = (correct_count / len(merged_df)) * 100 if len(merged_df) > 0 else 0
                    
                    st.caption(f"💡 **Explanation & Model Match:** Compares historical **Actual Churn** (`No`/`Yes`) directly side-by-side against **AI Predicted Churn** (`No`/`Yes`). Current cohort agreement accuracy: **{accuracy_pct:.1f}%**.")
                    st.divider()

                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    if "tenure" in merged_df.columns:
                        st.markdown("#### 2. Customer Tenure Breakdown")
                        tenure_nums = pd.to_numeric(merged_df["tenure"], errors="coerce").fillna(0)
                        tenure_bins = pd.cut(tenure_nums, bins=[-1, 12, 24, 48, 72, 1000], labels=["0-1 Year", "1-2 Years", "2-4 Years", "4-6 Years", "6+ Years"])
                        tenure_counts = tenure_bins.value_counts().sort_index()
                        st.bar_chart(tenure_counts, color="#ff4b4b")
                        st.caption("💡 **Explanation:** Shows customer loyalty length (months subscribed). Newer customers (0-1 Year) carry the highest risk of churn, while long-term customers (4+ Years) show strong subscription stability.")
                    else:
                        st.markdown("#### 2. Prediction Distribution (Count)")
                        pred_counts = merged_df["prediction"].value_counts()
                        st.bar_chart(pred_counts, color="#ff4b4b")
                        st.caption("💡 **Explanation:** Shows how many customers in the current filtered subset are flagged as **High Risk (Yes)** vs **Low Risk (No)**.")
                    
                with col_chart2:
                    if "Contract" in merged_df.columns:
                        st.markdown("#### 3. Contract Types Distribution")
                        contract_counts = merged_df["Contract"].value_counts()
                        st.bar_chart(contract_counts, color="#0068c9")
                        st.caption("💡 **Explanation:** Breakdown of agreement terms. Month-to-month contracts statistically carry the highest churn risk compared to 1-year or 2-year commitments.")
                
                # Additional Risk Breakdown Charts: Payment Method & Tech Support
                if "PaymentMethod" in merged_df.columns or "TechSupport" in merged_df.columns:
                    st.write("")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        if "PaymentMethod" in merged_df.columns:
                            st.markdown("#### 4. Payment Method Breakdown")
                            pay_counts = merged_df["PaymentMethod"].value_counts()
                            st.bar_chart(pay_counts, color="#7d3ac9")
                            st.caption("💡 **Key Finding:** **Electronic Check** users churn at **45.3%**! Switching customers to automatic credit card / bank transfer cuts churn by 65%.")
                    with col_p2:
                        if "TechSupport" in merged_df.columns:
                            st.markdown("#### 5. Tech Support Add-On Status")
                            ts_counts = merged_df["TechSupport"].value_counts()
                            st.bar_chart(ts_counts, color="#29b5e8")
                            st.caption("💡 **Key Finding:** Customers without Tech Support churn at **41.6%**, while customers with Tech Support churn at only **15.2%**!")
                
                st.info(f"📌 **Executive Takeaway & Strategy:** Out of {len(preds_df)} total uploaded records, **{high_risk_count}** customers in your top selection have high churn risk. The most common contract type in this high-risk group is **{top_contract}**. We recommend prioritizing retention offers (discounts/contract upgrades) for this group to maximize campaign ROI.")
                
                st.divider()
                st.subheader("💾 Database Integration")
                st.write("Save these selected records into the database to view, edit, or manage them in other tabs.")
                
                # Fetch existing IDs in database to detect duplicates
                conn = sqlite3.connect("app_data.db")
                existing_db_ids = set(pd.read_sql_query("SELECT customerID FROM customers", conn)["customerID"].astype(str).tolist())
                conn.close()
                
                batch_ids = set(merged_df["customerID"].astype(str).tolist())
                duplicate_ids = batch_ids.intersection(existing_db_ids)
                
                if duplicate_ids:
                    st.warning(f"⚠️ **Duplicate Customer IDs Found:** **{len(duplicate_ids)}** of the selected records already exist in the database.")
                    dup_action = st.radio(
                        "How would you like to handle existing customer IDs?",
                        ["🔄 Overwrite existing records with new prediction data", "⏭️ Skip existing records (Save new IDs only)"],
                        key="batch_dup_handling"
                    )
                else:
                    dup_action = "🔄 Overwrite existing records with new prediction data"
                
                if st.button("💾 Save Selected Records to Database", use_container_width=True, type="primary"):
                    new_saved = 0
                    overwritten = 0
                    skipped = 0
                    
                    for idx, row in merged_df.iterrows():
                        cid_str = str(row["customerID"])
                        raw_payload = row[df_batch.columns].to_dict()
                        
                        is_existing = cid_str in existing_db_ids
                        
                        if is_existing and "Skip" in dup_action:
                            skipped += 1
                            continue
                            
                        save_customer_data(
                            customerID=cid_str,
                            prediction=row["prediction"],
                            probability=float(row["churn_probability"]),
                            payload=raw_payload,
                            added_by=st.session_state["username"],
                            real_added_by="admin",
                            public_last_edit="No edits yet",
                            real_last_edit="No edits yet"
                        )
                        
                        if is_existing:
                            overwritten += 1
                        else:
                            new_saved += 1
                        
                    st.toast("✅ Database Integration Complete!", icon="🎉")
                    st.success("✅ **Database Integration Complete!**")
                    st.info(f"📊 **Summary:** Saved **{new_saved}** new records | Overwrote **{overwritten}** existing records | Skipped **{skipped}** duplicate records.")

        with tab_monitor:
            st.subheader("📊 Real-time Model Drift & Health Monitoring")
            st.write("Analyze live API prediction logs (`logs/predictions.log`) directly inside the UI to monitor model output stability and detect data drift.")
            
            from pathlib import Path
            log_file = Path("logs/predictions.log")
            
            if st.button("🔍 Run Drift & Monitoring Analysis", type="primary", use_container_width=True, key="run_ui_monitor_btn"):
                if not log_file.exists():
                    st.warning("⚠️ No prediction logs found yet! Run some batch predictions or single predictions first.")
                else:
                    records = []
                    with open(log_file, "r") as f:
                        for line in f:
                            try:
                                data = json.loads(line)
                                if "churn_probability" in data and data["churn_probability"] is not None:
                                    records.append(data)
                            except json.JSONDecodeError:
                                continue
                    
                    if not records:
                        st.info("Log file is currently empty.")
                    else:
                        df_log = pd.DataFrame(records)
                        
                        if "churn_probability" not in df_log.columns or "timestamp" not in df_log.columns:
                            st.error("❌ Log file missing required columns (`churn_probability` or `timestamp`).")
                        else:
                            df_log["timestamp"] = pd.to_datetime(df_log["timestamp"])
                            df_log = df_log.sort_values(by="timestamp")
                            
                            total_log_preds = len(df_log)
                            avg_log_prob = df_log["churn_probability"].mean()
                            high_risk_log_count = (df_log["prediction"] == "Yes").sum() if "prediction" in df_log.columns else 0
                            
                            # Summary KPI Cards
                            st.write("### 📌 Overall Prediction Logs Summary")
                            mc1, mc2, mc3 = st.columns(3)
                            mc1.metric("Total Requests Logged", f"{total_log_preds}")
                            mc2.metric("High-Risk Flagged", f"{high_risk_log_count}", delta=f"{(high_risk_log_count/total_log_preds*100):.1f}%" if total_log_preds > 0 else "0%")
                            mc3.metric("Avg Predicted Churn Risk", f"{avg_log_prob * 100:.1f}%")
                            
                            st.divider()
                            st.write("### 📈 Time-Based Drift Analysis (Last 7 Days vs Historical)")
                            
                            now = pd.Timestamp.utcnow()
                            recent_threshold = now - timedelta(days=7)
                            
                            recent_df = df_log[df_log["timestamp"] >= recent_threshold]
                            older_df = df_log[df_log["timestamp"] < recent_threshold]
                            
                            if not recent_df.empty and not older_df.empty:
                                recent_avg = recent_df["churn_probability"].mean()
                                older_avg = older_df["churn_probability"].mean()
                                diff = recent_avg - older_avg
                                
                                c_d1, c_d2 = st.columns(2)
                                c_d1.metric("Historical Avg Churn Prob (Older)", f"{older_avg * 100:.2f}%")
                                c_d2.metric("Recent Avg Churn Prob (Last 7 Days)", f"{recent_avg * 100:.2f}%", delta=f"{diff * 100:+.2f}%")
                                
                                if abs(diff) > 0.05:
                                    st.warning(f"⚠️ **DRIFT DETECTED!** Average predicted churn risk shifted by **{diff * 100:+.2f}%**. This indicates customer demographic or behavior shifts. Consider retraining your model!")
                                else:
                                    st.success("✅ **Model Stable:** No significant data drift detected between historical and recent predictions.")
                            else:
                                st.info("ℹ️ **Single Time-Window Active:** All logged predictions are within the last 7 days. Time-window comparison will dynamically update as data accumulates.")
                                if avg_log_prob > 0.45:
                                    st.warning(f"⚠️ **High Churn Alert:** Overall average churn probability is unusually high ({avg_log_prob * 100:.1f}%).")
                                else:
                                    st.success("✅ **Overall Stability:** Average predicted probability is within healthy normal limits.")
                            
                            st.divider()
                            st.write("### 📉 Chronological Churn Risk Trend & Log Details")
                            
                            # Group logs by batch request to plot average churn risk per run over time
                            if "request_id" in df_log.columns:
                                chart_grouped = df_log.groupby(["request_id"]).agg({
                                    "timestamp": "first",
                                    "churn_probability": "mean"
                                }).sort_values("timestamp").tail(50)
                            else:
                                chart_grouped = df_log.tail(50)
                                
                            st.line_chart(chart_grouped.set_index("timestamp")["churn_probability"])
                            
                            st.markdown("""
                            📌 **Graph Axis Guide for Presentation:**
                            - **Y-Axis (Vertical):** **Average Churn Risk Score** (Ranges from `0.0` = 0% risk to `1.0` = 100% risk). Higher up means higher customer churn risk.
                            - **X-Axis (Horizontal):** **Prediction Run Time / Date** (Chronological order of when batch or single requests were processed).
                            """)
                            
                            col_log1, col_log2 = st.columns([3, 1])
                            with col_log1:
                                with st.expander("📄 Click to View Prediction Logs (Unique Records)"):
                                    # Show clean log preview without identical duplicates
                                    unique_log = df_log.drop_duplicates(subset=["request_id", "customerID"], keep="last").tail(500)
                                    st.dataframe(unique_log, use_container_width=True)
                                    
                            with col_log2:
                                if st.button("🧹 Clear All Prediction Logs", type="secondary", help="Reset prediction log file to start fresh"):
                                    try:
                                        with open(log_file, "w") as f:
                                            f.write("")
                                        st.success("✅ Logs cleared successfully!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Could not clear logs: {e}")

            # Section 2: Saved Database Analytics & Visualizations
            st.divider()
            st.subheader("💾 Saved Database Analytics & Visualizations")
            st.write("Analyze all customer records currently saved and stored inside `app_data.db`.")
            
            conn = sqlite3.connect("app_data.db")
            try:
                df_db = pd.read_sql_query("SELECT customerID, prediction_result, churn_probability, raw_data FROM customers", conn)
            except Exception:
                df_db = pd.DataFrame()
            finally:
                conn.close()
            
            if df_db.empty:
                st.info("ℹ️ No customer records saved in `app_data.db` database yet. Save some batch or generated records to view database analytics!")
            else:
                db_total = len(df_db)
                db_high_risk = (df_db["prediction_result"] == "Yes").sum()
                db_avg_prob = df_db["churn_probability"].mean() * 100
                
                sb1, sb2, sb3 = st.columns(3)
                sb1.metric("Total Saved DB Records", f"{db_total}")
                sb2.metric("Saved High-Risk (Yes)", f"{db_high_risk}", delta=f"{(db_high_risk/db_total*100):.1f}% of DB" if db_total > 0 else "0%")
                sb3.metric("Avg Saved Churn Risk", f"{db_avg_prob:.1f}%")
                
                # Parse raw_data JSON to extract features for DB charts
                parsed_features = []
                for _, row in df_db.iterrows():
                    try:
                        feat = json.loads(row["raw_data"])
                        feat["customerID"] = row["customerID"]
                        feat["prediction"] = row["prediction_result"]
                        feat["churn_probability"] = row["churn_probability"]
                        parsed_features.append(feat)
                    except Exception:
                        continue
                        
                if parsed_features:
                    df_parsed = pd.DataFrame(parsed_features)
                    
                    st.write("#### 📈 Saved Database Visualizations & Data Insights")
                    
                    # Chart 1: Side-by-Side Model Comparison for Saved DB
                    if "Churn" in df_parsed.columns:
                        st.markdown("#### 1. 🎯 Saved DB Model Comparison: Actual Churn vs AI Predicted Churn (Side-by-Side)")
                        act_s = df_parsed["Churn"].astype(str).str.strip().str.capitalize()
                        pred_s = df_parsed["prediction"].astype(str).str.strip().str.capitalize()
                        
                        comp_db_df = pd.DataFrame({
                            "Actual Churn (Ground Truth)": act_s.value_counts(),
                            "AI Predicted Churn": pred_s.value_counts()
                        }).fillna(0)
                        
                        st.bar_chart(comp_db_df, stack=False)
                        
                        corr_db = (act_s == pred_s).sum()
                        acc_db = (corr_db / len(df_parsed)) * 100 if len(df_parsed) > 0 else 0
                        st.caption(f"💡 **Explanation & Model Match:** Compares saved historical **Actual Churn** (`No`/`Yes`) directly side-by-side against **AI Predicted Churn** (`No`/`Yes`). Database agreement accuracy: **{acc_db:.1f}%**.")
                        st.divider()
                    
                    c_db1, c_db2 = st.columns(2)
                    with c_db1:
                        if "tenure" in df_parsed.columns:
                            st.markdown("#### 2. Saved DB: Customer Tenure Breakdown")
                            t_nums = pd.to_numeric(df_parsed["tenure"], errors="coerce").fillna(0)
                            t_bins = pd.cut(t_nums, bins=[-1, 12, 24, 48, 72, 1000], labels=["0-1 Year", "1-2 Years", "2-4 Years", "4-6 Years", "6+ Years"])
                            st.bar_chart(t_bins.value_counts().sort_index(), color="#ff4b4b")
                            st.caption("💡 **Explanation:** Shows saved customer loyalty length. Newer customers (0-1 Year) carry the highest risk of churn.")
                        else:
                            st.markdown("#### 2. Saved DB: Churn Risk Distribution")
                            st.bar_chart(df_parsed["prediction"].value_counts(), color="#ff4b4b")
                            st.caption("💡 **Explanation:** Shows total saved database records flagged as High Risk (Yes) vs Low Risk (No).")
                            
                    with c_db2:
                        if "Contract" in df_parsed.columns:
                            st.markdown("#### 3. Saved DB: Contract Breakdown")
                            st.bar_chart(df_parsed["Contract"].value_counts(), color="#0068c9")
                            st.caption("💡 **Explanation:** Month-to-month contracts carry the highest churn risk compared to 1-year or 2-year commitments.")
                            
                    if "PaymentMethod" in df_parsed.columns or "TechSupport" in df_parsed.columns:
                        st.write("")
                        c_db3, c_db4 = st.columns(2)
                        with c_db3:
                            if "PaymentMethod" in df_parsed.columns:
                                st.markdown("#### 4. Saved DB: Payment Method Breakdown")
                                st.bar_chart(df_parsed["PaymentMethod"].value_counts(), color="#7d3ac9")
                                st.caption("💡 **Key Finding:** Electronic Check users carry a ~45% churn rate. Switching to automatic payments reduces churn by 65%.")
                        with c_db4:
                            if "TechSupport" in df_parsed.columns:
                                st.markdown("#### 5. Saved DB: Tech Support Add-On Status")
                                st.bar_chart(df_parsed["TechSupport"].value_counts(), color="#29b5e8")
                                st.caption("💡 **Key Finding:** Customers without Tech Support churn at 41.6%, while offering Tech Support reduces churn to 15.2%.")

        with tab_settings:
            st.subheader("🔑 Change Password")
            new_pass = st.text_input("New Password", type="password", key="new_pass")
            confirm_pass = st.text_input("Confirm New Password", type="password", key="conf_pass")
            if st.button("Update Password"):
                if not new_pass: st.error("Password cannot be empty.")
                elif new_pass != confirm_pass: st.error("Passwords do not match!")
                else:
                    change_password(st.session_state["username"], new_pass)
                    st.success("✅ Password updated successfully!")