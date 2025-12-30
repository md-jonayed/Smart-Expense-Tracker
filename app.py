import streamlit as st
import sqlite3
import os
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import pandas as pd
import openai

# ---------- CONFIG ----------
st.set_page_config(
    page_title="Smart Student Expense Tracker",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- LOAD OPENAI API KEY ----------
try:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("⚠️ OpenAI API key not found. Add it to .streamlit/secrets.toml or Streamlit Cloud secrets.")
    st.stop()

# ---------- DATABASE UTILS ----------
DB_PATH = "data/expenses.db"
os.makedirs("data", exist_ok=True)

def run_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            return cur.fetchall()
        conn.commit()

def init_db():
    run_query("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            category TEXT
        )
    """)
    run_query("""
        CREATE TABLE IF NOT EXISTS category_cache (
            description TEXT PRIMARY KEY,
            category TEXT
        )
    """)

# ---------- EXPENSES LOGIC ----------
def add_expense(date_str, description, amount, category):
    run_query(
        "INSERT INTO expenses (date, description, amount, category) VALUES (?, ?, ?, ?)",
        (date_str, description, round(amount, 2), category)
    )

def update_expense(expense_id, new_description, new_amount, new_category):
    run_query("""
        UPDATE expenses
        SET description = ?, amount = ?, category = ?
        WHERE id = ?
    """, (new_description, round(new_amount, 2), new_category, expense_id))

def get_expenses():
    return run_query("SELECT * FROM expenses ORDER BY date DESC", fetch=True)

# ---------- FILTERING ----------
def filter_expenses_by_period(period):
    today = date.today()
    if period == "This Month":
        start_month = today.replace(day=1).strftime("%Y-%m-%d")
        return run_query("SELECT * FROM expenses WHERE date >= ?", (start_month,), fetch=True)
    elif period == "Last Month":
        last_month_end = today.replace(day=1) - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1).strftime("%Y-%m-%d")
        return run_query("SELECT * FROM expenses WHERE date BETWEEN ? AND ?", 
                         (last_month_start, last_month_end.strftime("%Y-%m-%d")), fetch=True)
    elif period == "This Week":
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        return run_query("SELECT * FROM expenses WHERE date >= ?", (week_start,), fetch=True)
    return get_expenses()

# ---------- AI CATEGORIZATION ----------
def smart_category(description):
    cached = run_query("SELECT category FROM category_cache WHERE description=?", (description,), fetch=True)
    if cached: return cached[0][0]

    text = description.lower()
    mapping = {"Transportation": ["uber", "taxi", "bolt", "train"], "Food": ["pizza", "coffee", "restaurant", "burger"], "Entertainment": ["netflix", "spotify", "cinema"]}
    
    category = "Other"
    for cat, keywords in mapping.items():
        if any(k in text for k in keywords):
            category = cat
            break
    else:
        try:
            client = openai.OpenAI(api_key=openai.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"Categorize: '{description}'. Return only the category name: Food, Transportation, Entertainment, Utilities, Shopping, Other."}]
            )
            category = response.choices[0].message.content.strip()
        except:
            category = "Other"

    run_query("INSERT OR REPLACE INTO category_cache (description, category) VALUES (?, ?)", (description, category))
    return category

# ---------- INITIALIZATION ----------
init_db()

# Standardize existing mixed date formats in DB
run_query("UPDATE expenses SET date = SUBSTR(date, 1, 10) WHERE LENGTH(date) > 10")

# ---------- SIDEBAR ----------
if "monthly_income" not in st.session_state:
    st.session_state.monthly_income = 992.0

st.sidebar.header("💰 Settings")
st.session_state.monthly_income = st.sidebar.number_input(
    "Set your monthly income", min_value=0.0, value=float(st.session_state.monthly_income), step=10.0, format="%.2f"
)

# ---------- HEADER METRICS ----------
st.markdown("<h1 style='text-align: center; color: #008080;'>💸 Smart Student Expense Tracker</h1>", unsafe_allow_html=True)

spent_this_month = sum(row[3] for row in filter_expenses_by_period("This Month"))
remaining_balance = st.session_state.monthly_income - spent_this_month

cols = st.columns(3)
metrics = [("Income", st.session_state.monthly_income, "#20C997"), 
           ("Spent", spent_this_month, "#20C997"), 
           ("Remaining", remaining_balance, "#20C997" if remaining_balance >= 200 else "#FF6B6B")]

for col, (label, val, color) in zip(cols, metrics):
    col.markdown(f"<div style='background-color:{color};padding:15px;border-radius:15px;text-align:center;color:white;'><h4>{label}</h4><h3>€{val:.2f}</h3></div>", unsafe_allow_html=True)

# ---------- TABS ----------
tab1, tab2, tab3, tab4 = st.tabs(["➕ Add", "✏️ Update", "📊 Stats", "📂 Export"])

with tab1:
    desc = st.text_input("Description", placeholder="e.g., Starbucks Coffee")
    amt = st.number_input("Amount", min_value=0.0, format="%.2f")
    if st.button("Add Expense", type="primary"):
        if desc:
            cat = smart_category(desc)
            add_expense(date.today().strftime("%Y-%m-%d"), desc, amt, cat)
            st.success(f"Logged €{amt} for {desc}")
            st.rerun()

with tab2:
    data = get_expenses()
    if data:
        df_manage = pd.DataFrame(data, columns=["ID", "Date", "Description", "Amount (€)", "Category"])
        selected_id = st.selectbox("Select ID to Update", df_manage["ID"])
        row = df_manage[df_manage["ID"] == selected_id].iloc[0]
        
        c1, c2, c3 = st.columns(3)
        u_desc = c1.text_input("New Description", value=row["Description"])
        u_amt = c2.number_input("New Amount", value=float(row["Amount (€)"]))
        u_cat = c3.text_input("New Category", value=row["Category"])
        
        if st.button("Apply Changes"):
            update_expense(selected_id, u_desc, u_amt, u_cat)
            st.success("Updated!")
            st.rerun()
    else:
        st.info("No data available.")

with tab3:
    period = st.selectbox("Select period", ["This Month", "Last Month", "This Week", "All"])
    f_data = filter_expenses_by_period(period)
    if f_data:
        df = pd.DataFrame(f_data, columns=["ID", "Date", "Description", "Amount", "Category"])
        df['Date'] = pd.to_datetime(df['Date'], format='mixed')
        st.dataframe(df, width="stretch", height=300)

        summary = df.groupby("Category")["Amount"].sum()
        col1, col2 = st.columns(2)
        with col1:
            fig1, ax1 = plt.subplots()
            summary.plot(kind="pie", autopct='%1.1f%%', ax=ax1, colors=plt.cm.Pastel1.colors)
            ax1.set_ylabel("")
            st.pyplot(fig1)
        with col2:
            st.bar_chart(summary)

        st.divider()
        st.subheader("Budget Projection")
        
        # --- FIXED MONTH ERROR LOGIC ---
        today = date.today()
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        
        days_left = (next_month - today).days
        daily = remaining_balance / max(days_left, 1)
        st.info(f"💡 Days left in month: {days_left}. You can spend roughly **€{max(0, daily):.2f}** per day.")
    else:
        st.info("No data for this period.")

with tab4:
    st.subheader("Data Management")
    full_df = pd.DataFrame(get_expenses(), columns=["ID", "Date", "Description", "Amount", "Category"])
    csv = full_df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Expenses as CSV", data=csv, file_name="student_expenses.csv", mime="text/csv")