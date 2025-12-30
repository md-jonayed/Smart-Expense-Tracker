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
# Works for both local .streamlit/secrets.toml and Streamlit Cloud
try:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
except KeyError:
    st.error("⚠️ OpenAI API key not found. Add it to .streamlit/secrets.toml or Streamlit Cloud secrets.")
    st.stop()

# ---------- DATABASE ----------
DB_PATH = "data/expenses.db"
os.makedirs("data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

def init_cache():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS category_cache (
            description TEXT PRIMARY KEY,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

# ---------- EXPENSES ----------
def add_expense(date_str, description, amount, category):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO expenses (date, description, amount, category) VALUES (?, ?, ?, ?)",
        (date_str, description, round(amount, 2), category)
    )
    conn.commit()
    conn.close()

def update_expense(expense_id, new_description, new_amount, new_category):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE expenses
        SET description = ?, amount = ?, category = ?
        WHERE id = ?
    """, (new_description, round(new_amount, 2), new_category, expense_id))
    conn.commit()
    conn.close()

def get_expenses():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM expenses ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------- FILTERING ----------
def filter_expenses_by_period(period):
    today = date.today()
    if period == "This Month":
        return get_monthly_expenses(today.year, today.month)
    elif period == "Last Month":
        last_month = today.replace(day=1) - timedelta(days=1)
        return get_monthly_expenses(last_month.year, last_month.month)
    elif period == "This Week":
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        return get_expenses_between_dates(week_start, week_end)
    else:
        return get_expenses()

def get_monthly_expenses(year, month):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM expenses WHERE strftime('%Y', date)=? AND strftime('%m', date)=?",
        (str(year), f"{month:02d}")
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_expenses_between_dates(start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM expenses WHERE date BETWEEN ? AND ?",
        (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    )
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------- AI CATEGORIZATION ----------
def ai_category(description):
    try:
        prompt = f"""
        You are a financial assistant. Categorize this expense into one of:
        Food, Transportation, Entertainment, Utilities, Shopping, Other.

        Expense: "{description}"
        Just return the category name.
        """
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None

def get_cached_category(description):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT category FROM category_cache WHERE description=?", (description,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_cached_category(description, category):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO category_cache (description, category) VALUES (?, ?)",
        (description, category)
    )
    conn.commit()
    conn.close()

def smart_category(description):
    cached = get_cached_category(description)
    if cached:
        return cached

    text = description.lower()
    if "uber" in text or "taxi" in text:
        category = "Transportation"
    elif "pizza" in text or "shawarma" in text or "coffee" in text:
        category = "Food"
    elif "netflix" in text or "spotify" in text:
        category = "Entertainment"
    else:
        ai_result = ai_category(description)
        category = ai_result if ai_result else "Other"

    set_cached_category(description, category)
    return category

# ---------- INITIALIZATION ----------
init_db()
init_cache()

# ---------- DYNAMIC MONTHLY INCOME ----------
if "monthly_income" not in st.session_state:
    st.session_state.monthly_income = 992  # default value

st.sidebar.header("💰 Monthly Income Settings")
st.session_state.monthly_income = st.sidebar.number_input(
    "Set your monthly income",
    min_value=0.0,
    value=float(st.session_state.monthly_income),
    step=10.0,
    format="%.2f"
)

# ---------- HEADER METRICS ----------
st.markdown(f"""
    <h1 style='text-align: center; color: #008080; font-family:Arial;'>💸 Smart Student Expense Tracker</h1>
""", unsafe_allow_html=True)

today = date.today()
current_month_expenses = filter_expenses_by_period("This Month")
df_current_month = pd.DataFrame(current_month_expenses, columns=["ID","Date","Description","Amount (€)","Category"])
if not df_current_month.empty:
    df_current_month["Amount (€)"] = df_current_month["Amount (€)"].map(lambda x: round(x,2))

spent_this_month = round(df_current_month["Amount (€)"].sum() if not df_current_month.empty else 0, 2)
remaining_balance = round(st.session_state.monthly_income - spent_this_month, 2)

# ---------- METRIC CARDS ----------
cols = st.columns([1,1,1])
colors = ["#20C997", "#20C997", "#20C997" if remaining_balance >=200 else "#FF6B6B"]
labels = ["💰 Monthly Income", "📝 Spent This Month", "💳 Remaining Balance"]
values = [st.session_state.monthly_income, spent_this_month, remaining_balance]

for col, label, val, color in zip(cols, labels, values, colors):
    col.markdown(f"""
    <div style='background-color:{color};padding:15px;border-radius:15px;text-align:center;color:white;'>
    <h4>{label}</h4>
    <h3>€{val:.2f}</h3>
    </div>
    """, unsafe_allow_html=True)

# ---------- TABS ----------
tab1, tab2, tab3 = st.tabs(["➕ Add Expense", "✏️ Update Expense", "📊 Visualizations"])

# --- TAB 1: Add Expense ---
with tab1:
    st.text_input("Description", key="desc")
    st.number_input("Amount", min_value=0.0, key="amount", format="%.2f")
    if st.button("Add Expense"):
        category = smart_category(st.session_state.desc)
        add_expense(datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.desc, st.session_state.amount, category)
        st.success(f"Added: {st.session_state.desc} ({category})")
        st.experimental_rerun()

# --- TAB 2: Update Expense ---
with tab2:
    df = pd.DataFrame(get_expenses(), columns=["ID","Date","Description","Amount (€)","Category"])
    if not df.empty:
        df["Amount (€)"] = df["Amount (€)"].map(lambda x: round(x,2))
        selected_id = st.selectbox("Select Expense ID to Update", df["ID"])
        selected_row = df[df["ID"] == selected_id].iloc[0]
        new_desc = st.text_input("Description", value=selected_row["Description"])
        new_amount = st.number_input("Amount", value=selected_row["Amount (€)"], format="%.2f")
        new_category = st.text_input("Category", value=selected_row["Category"])
        if st.button("Update Expense"):
            update_expense(selected_id, new_desc, new_amount, new_category)
            st.success(f"Expense ID {selected_id} updated successfully!")
            st.experimental_rerun()
    else:
        st.info("No expenses to update.")

# --- TAB 3: Visualizations ---
with tab3:
    period = st.selectbox("Select period", ["This Month", "Last Month", "This Week", "All"])
    filtered_expenses = filter_expenses_by_period(period)
    if filtered_expenses:
        df = pd.DataFrame(filtered_expenses, columns=["ID","Date","Description","Amount (€)","Category"])
        df["Amount (€)"] = df["Amount (€)"].map(lambda x: round(x,2))
        st.dataframe(df, width="stretch", height=300)

        expense_summary = df.groupby("Category")["Amount (€)"].sum().map(lambda x: round(x,2))
        max_category = expense_summary.idxmax()

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Pie Chart")
            fig1, ax1 = plt.subplots(figsize=(6,6))
            colors = ['#20C997' if cat != max_category else '#FF6B6B' for cat in expense_summary.index]
            ax1.pie(expense_summary, labels=expense_summary.index,
                    autopct=lambda p: f'{p:.1f}% (€{(p/100*expense_summary.sum()):.2f})',
                    startangle=90, colors=colors, wedgeprops={"edgecolor":"white","linewidth":1})
            ax1.set_ylabel("")
            st.pyplot(fig1)

        with col2:
            st.subheader("Bar Chart")
            fig2, ax2 = plt.subplots(figsize=(6,6))
            expense_summary.plot(kind="bar", color=colors, edgecolor="black", ax=ax2)
            ax2.set_ylabel("Amount (€)")
            ax2.set_xlabel("Category")
            ax2.set_title("Expenses by Category")
            st.pyplot(fig2)

        next_month_start = date(today.year, today.month + 1, 1) if today.month < 12 else date(today.year, 12, 31)
        days_left = (next_month_start - today).days + 1
        daily_budget = round(remaining_balance / days_left, 2) if days_left > 0 else remaining_balance
        projection_df = pd.DataFrame({"Date": [today + timedelta(days=i) for i in range(days_left)],
                                      "Daily Budget (€)": [daily_budget]*days_left})
        st.subheader("Remaining Balance Projection")
        st.line_chart(projection_df.set_index("Date"))
        st.write(f"Approximate budget for the rest of the month: **€{daily_budget:.2f}**")
    else:
        st.info("No expenses for the selected period.")
