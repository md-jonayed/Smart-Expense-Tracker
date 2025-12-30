import streamlit as st
import sqlite3
import os
from datetime import datetime, date, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(
    page_title="Smart Student Expense Tracker",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- LOAD OPENAI API CLIENT ----------
try:
    api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=api_key)
except (KeyError, FileNotFoundError):
    st.error("⚠️ OpenAI API key not found. Add it to .streamlit/secrets.toml")
    st.stop()

# ---------- DATABASE UTILS ----------
DB_PATH = "data/expenses.db"
os.makedirs("data", exist_ok=True)

def run_query(query, params=(), fetch=False):
    """Execute database query with error handling"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            conn.commit()
            return True
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
        return [] if fetch else False

def init_db():
    """Initialize database tables"""
    run_query("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, description TEXT, amount REAL, category TEXT)")
    run_query("CREATE TABLE IF NOT EXISTS category_cache (description TEXT PRIMARY KEY, category TEXT)")

# ---------- PAY CYCLE LOGIC (25th to 25th) ----------
def get_cycle_dates():
    """Calculate current pay cycle dates (25th to 24th)"""
    today = date.today()
    if today.day >= 25:
        start_date = today.replace(day=25)
    else:
        last_month = today.replace(day=1) - timedelta(days=1)
        start_date = last_month.replace(day=25)
    
    if start_date.month == 12:
        end_date = start_date.replace(year=start_date.year + 1, month=1, day=24)
    else:
        end_date = start_date.replace(month=start_date.month + 1, day=24)
    return start_date, end_date

# ---------- AI CATEGORIZATION ----------
def smart_category(description):
    """Categorize expense using cache, rules, and AI fallback"""
    desc_clean = description.strip()
    if not desc_clean:
        return "Other"

    # 1. Check Cache
    cached = run_query("SELECT category FROM category_cache WHERE description=?", (desc_clean,), fetch=True)
    if cached:
        return cached[0][0]
    
    # 2. Enhanced Rule-based with better keyword matching
    text = desc_clean.lower()
    mapping = {
        "Transportation": ["uber", "taxi", "bolt", "lyft", "train", "bus", "metro", "subway", "gas", "fuel", "petrol", "parking", "bike", "scooter", "car", "transport", "ride", "trip"],
        "Food": [
            # Restaurants & Fast Food
            "pizza", "burger", "mcdonalds", "kfc", "dominos", "subway", "sushi", "thai", "chinese", "indian", "restaurant",
            # Beverages
            "coffee", "starbucks", "cafe", "tea", "drink", "beverage", "juice", "soda", "coke", "pepsi", "sprite", "fanta", "red bull", "redbull", "energy drink", "water", "milk",
            # Meals
            "lunch", "dinner", "breakfast", "brunch", "food", "meal", "eat", "snack",
            # Grocery
            "grocery", "supermarket", "bakery", "deli", "market", "produce", "bread", "cheese", "meat", "vegetable", "fruit"
        ],
        "Entertainment": ["netflix", "spotify", "cinema", "movie", "game", "pub", "bar", "club", "concert", "theater", "theatre", "youtube", "twitch", "steam", "playstation", "xbox", "nintendo", "party", "event", "ticket", "show"],
        "Utilities": ["electricity", "water", "gas bill", "internet", "wifi", "phone bill", "mobile", "rent", "heating", "utility", "bill"],
        "Shopping": ["amazon", "ebay", "clothes", "clothing", "shoes", "shirt", "pants", "dress", "mall", "store", "shop", "zara", "h&m", "nike", "adidas", "online", "purchase"],
        "Education": ["book", "textbook", "course", "tuition", "school", "university", "college", "stationery", "notebook", "pen", "pencil", "study", "library", "class", "lecture"],
        "Health": ["pharmacy", "medicine", "doctor", "hospital", "clinic", "gym", "fitness", "health", "medical", "prescription", "dentist", "vitamin", "supplement"]
    }
    
    category = None
    # Check for keyword matches (partial word matching)
    for cat, keywords in mapping.items():
        if any(keyword in text for keyword in keywords):
            category = cat
            break
    
    # 3. AI Backup
    if not category:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """You are an expense categorization assistant for a student. Categorize the expense into ONE of these categories:
- Food: Groceries, restaurants, cafes, takeout, snacks
- Transportation: Uber, taxi, bus, train, gas, parking, bike rentals
- Entertainment: Movies, streaming services, games, concerts, bars, clubs
- Utilities: Rent, electricity, water, internet, phone bills
- Shopping: Clothes, electronics, general purchases, online shopping
- Education: Books, courses, tuition, school supplies
- Health: Pharmacy, gym, medical expenses, fitness
- Other: Anything that doesn't fit above categories

Return ONLY the category name, nothing else."""},
                    {"role": "user", "content": f"Categorize this expense: {desc_clean}"}
                ],
                max_tokens=15,
                temperature=0
            )
            category = response.choices[0].message.content.strip().replace(".", "")
        except Exception as e:
            st.warning(f"AI categorization failed: {e}")
            category = "Other"

    run_query("INSERT OR REPLACE INTO category_cache (description, category) VALUES (?, ?)", (desc_clean, category))
    return category

# ---------- INITIALIZATION ----------
init_db()

# ---------- SIDEBAR ----------
if "monthly_income" not in st.session_state:
    st.session_state.monthly_income = 992.0

st.sidebar.header("💰 Settings")
st.session_state.monthly_income = st.sidebar.number_input(
    "Set monthly income (€)", min_value=0.0, value=float(st.session_state.monthly_income), step=10.0
)

st.sidebar.divider()
st.sidebar.subheader("🔧 Tools")

col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🗑️ Clear Cache", help="Clear cached categorizations", use_container_width=True):
        run_query("DELETE FROM category_cache")
        st.sidebar.success("✓ Cache cleared!")
        st.rerun()

with col2:
    if st.button("⚠️ Reset All", help="Delete all expenses", use_container_width=True):
        if st.session_state.get('confirm_reset', False):
            run_query("DELETE FROM expenses")
            run_query("DELETE FROM category_cache")
            st.sidebar.success("✓ All data cleared!")
            st.session_state.confirm_reset = False
            st.rerun()
        else:
            st.session_state.confirm_reset = True
            st.sidebar.warning("Click again to confirm!")

# ---------- HEADER METRICS ----------
st.markdown("<h1 style='text-align: center; color: #008080;'>💸 Smart Student Expense Tracker</h1>", unsafe_allow_html=True)

start_cycle, end_cycle = get_cycle_dates()
cycle_data = run_query("SELECT * FROM expenses WHERE date BETWEEN ? AND ?", 
                        (start_cycle.strftime("%Y-%m-%d"), end_cycle.strftime("%Y-%m-%d")), fetch=True)

spent_this_month = sum(row[3] for row in cycle_data)
remaining_balance = st.session_state.monthly_income - spent_this_month

c1, c2, c3 = st.columns(3)
c1.metric("Cycle Income", f"€{st.session_state.monthly_income:.2f}")
c2.metric("Spent (Since 25th)", f"€{spent_this_month:.2f}")
c3.metric("Balance", f"€{remaining_balance:.2f}", delta_color="normal")

st.caption(f"📅 Current Pay Cycle: {start_cycle.strftime('%d %b')} - {end_cycle.strftime('%d %b')}")

# ---------- TABS ----------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["➕ Add", "✏️ Manage", "📊 Stats", "🔍 Search", "📂 Export"])

with tab1:
    st.subheader("New Entry")
    with st.form("add_form", clear_on_submit=True):
        desc = st.text_input("What did you buy?", placeholder="e.g., Coffee at Starbucks")
        amt = st.number_input("Amount (€)", min_value=0.0, format="%.2f")
        if st.form_submit_button("Log Expense", type="primary", use_container_width=True):
            if desc and amt > 0:
                cat = smart_category(desc)
                run_query("INSERT INTO expenses (date, description, amount, category) VALUES (?, ?, ?, ?)",
                          (date.today().strftime("%Y-%m-%d"), desc, amt, cat))
                st.success(f"✓ Added: {desc} → {cat} (€{amt:.2f})")
                st.rerun()
            else:
                st.error("Please enter both description and amount!")

with tab2:
    st.subheader("Manage Records")
    all_data = run_query("SELECT * FROM expenses ORDER BY date DESC, id DESC", fetch=True)
    if all_data:
        df_edit = pd.DataFrame(all_data, columns=["ID", "Date", "Description", "Amount", "Category"])
        
        # Display recent expenses with delete buttons
        st.markdown("#### Recent Expenses")
        for idx, row in df_edit.head(10).iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([1, 2, 4, 2, 2, 1])
            col1.write(f"**#{row['ID']}**")
            col2.write(row['Date'])
            col3.write(row['Description'])
            col4.write(f"€{row['Amount']:.2f}")
            col5.write(f"`{row['Category']}`")
            if col6.button("🗑️", key=f"del_{row['ID']}", help="Delete this expense"):
                run_query("DELETE FROM expenses WHERE id=?", (row['ID'],))
                st.success(f"Deleted expense #{row['ID']}")
                st.rerun()
        
        st.divider()
        
        # Edit functionality
        st.markdown("#### Edit Expense")
        sel_id = st.selectbox("Select ID to Edit", df_edit["ID"])
        row = df_edit[df_edit["ID"] == sel_id].iloc[0]
        
        with st.form("edit_form"):
            new_desc = st.text_input("Description", value=row["Description"])
            new_amt = st.number_input("Amount", value=float(row["Amount"]), format="%.2f")
            new_cat = st.text_input("Category", value=row["Category"])
            
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("💾 Save Changes", use_container_width=True):
                    final_cat = smart_category(new_desc) if new_desc != row["Description"] else new_cat
                    run_query("UPDATE expenses SET description=?, amount=?, category=? WHERE id=?", 
                              (new_desc, new_amt, final_cat, sel_id))
                    st.success("✓ Updated!")
                    st.rerun()
            with col2:
                if st.form_submit_button("🗑️ Delete", use_container_width=True):
                    run_query("DELETE FROM expenses WHERE id=?", (sel_id,))
                    st.success("✓ Deleted!")
                    st.rerun()
    else:
        st.info("No records found.")

with tab3:
    if cycle_data:
        df = pd.DataFrame(cycle_data, columns=["ID", "Date", "Description", "Amount", "Category"])
        
        # Top 5 Expenses
        st.subheader("💰 Top 5 Expenses This Cycle")
        top_5 = df.nlargest(5, 'Amount')[['Date', 'Description', 'Amount', 'Category']]
        for idx, row in top_5.iterrows():
            st.markdown(f"**€{row['Amount']:.2f}** - {row['Description']} *({row['Category']})* - {row['Date']}")
        
        st.divider()
        
        st.dataframe(df[['Date', 'Description', 'Amount', 'Category']], width='stretch', hide_index=True)
        
        st.subheader("📊 Cycle Analysis")
        summary = df.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        
        # Modern color palette
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2']
        
        col_pie, col_bar = st.columns(2)
        
        with col_pie:
            st.markdown("**💰 Expense Distribution**")
            # Modern donut chart with plotly
            fig_pie = go.Figure(data=[go.Pie(
                labels=summary.index,
                values=summary.values,
                hole=0.4,
                marker=dict(colors=colors, line=dict(color='#FFFFFF', width=2)),
                textinfo='label+percent',
                textfont=dict(size=14, color='white'),
                hovertemplate='<b>%{label}</b><br>€%{value:.2f}<br>%{percent}<extra></extra>'
            )])
            fig_pie.update_layout(
                showlegend=True,
                height=400,
                margin=dict(t=20, b=20, l=20, r=20),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Arial, sans-serif", size=12)
            )
            st.plotly_chart(fig_pie, width='stretch')
            
        with col_bar:
            st.markdown("**📈 Amount by Category**")
            # Modern gradient bar chart
            fig_bar = go.Figure(data=[go.Bar(
                x=summary.index,
                y=summary.values,
                marker=dict(
                    color=summary.values,
                    colorscale='Viridis',
                    line=dict(color='rgba(255,255,255,0.3)', width=1.5)
                ),
                text=[f'€{val:.2f}' for val in summary.values],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>€%{y:.2f}<extra></extra>'
            )])
            fig_bar.update_layout(
                showlegend=False,
                height=400,
                margin=dict(t=40, b=20, l=20, r=20),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, title=''),
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', title='Amount (€)'),
                font=dict(family="Arial, sans-serif", size=12)
            )
            st.plotly_chart(fig_bar, width='stretch')
        
        st.divider()
        
        # Daily spending trend
        st.markdown("**📅 Daily Spending Trend**")
        daily_spending = df.groupby('Date')['Amount'].sum().reset_index()
        daily_spending['Date'] = pd.to_datetime(daily_spending['Date'])
        
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=daily_spending['Date'],
            y=daily_spending['Amount'],
            mode='lines+markers',
            name='Daily Spending',
            line=dict(color='#FF6B6B', width=3),
            marker=dict(size=8, color='#FF6B6B', line=dict(color='white', width=2)),
            fill='tozeroy',
            fillcolor='rgba(255, 107, 107, 0.2)',
            hovertemplate='<b>%{x|%b %d}</b><br>€%{y:.2f}<extra></extra>'
        ))
        fig_trend.update_layout(
            height=300,
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', title=''),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', title='Amount (€)'),
            font=dict(family="Arial, sans-serif", size=12),
            hovermode='x unified'
        )
        st.plotly_chart(fig_trend, width='stretch')
        
        st.divider()
        
        # Weekly comparison
        st.markdown("**📊 Weekly Spending Comparison**")
        df['Date'] = pd.to_datetime(df['Date'])
        df['Week'] = df['Date'].dt.isocalendar().week
        weekly_spending = df.groupby('Week')['Amount'].sum().reset_index()
        
        fig_weekly = go.Figure(data=[go.Bar(
            x=[f'Week {w}' for w in weekly_spending['Week']],
            y=weekly_spending['Amount'],
            marker=dict(color='#4ECDC4', line=dict(color='white', width=1)),
            text=[f'€{val:.2f}' for val in weekly_spending['Amount']],
            textposition='outside'
        )])
        fig_weekly.update_layout(
            height=300,
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, title=''),
            yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)', title='Amount (€)'),
            font=dict(family="Arial, sans-serif", size=12)
        )
        st.plotly_chart(fig_weekly, width='stretch')
        
        st.divider()
        days_left = (end_cycle - date.today()).days + 1
        daily = remaining_balance / max(days_left, 1)
        st.info(f"💡 Budget: **€{max(0, daily):.2f}/day** for the remaining {days_left} days of this cycle.")
    else:
        st.info("No data for current cycle.")

with tab4:
    st.subheader("🔍 Search & Filter")
    
    # Search by description
    search_term = st.text_input("Search by description", placeholder="e.g., coffee, uber")
    
    # Filter by category
    all_categories = run_query("SELECT DISTINCT category FROM expenses ORDER BY category", fetch=True)
    categories = ["All"] + [cat[0] for cat in all_categories]
    selected_category = st.selectbox("Filter by category", categories)
    
    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From date", value=start_cycle)
    with col2:
        end_date = st.date_input("To date", value=date.today())
    
    # Build query
    query = "SELECT * FROM expenses WHERE date BETWEEN ? AND ?"
    params = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]
    
    if search_term:
        query += " AND description LIKE ?"
        params.append(f"%{search_term}%")
    
    if selected_category != "All":
        query += " AND category = ?"
        params.append(selected_category)
    
    query += " ORDER BY date DESC, id DESC"
    
    # Execute search
    search_results = run_query(query, tuple(params), fetch=True)
    
    if search_results:
        df_search = pd.DataFrame(search_results, columns=["ID", "Date", "Description", "Amount", "Category"])
        total_amount = df_search['Amount'].sum()
        
        st.success(f"Found {len(df_search)} expenses totaling €{total_amount:.2f}")
        st.dataframe(df_search, width='stretch', hide_index=True)
    else:
        st.info("No expenses found matching your criteria.")

with tab5:
    st.subheader("📂 Export Data")
    full_data = run_query("SELECT * FROM expenses ORDER BY date DESC", fetch=True)
    if full_data:
        df_csv = pd.DataFrame(full_data, columns=["ID", "Date", "Description", "Amount", "Category"])
        
        col1, col2 = st.columns(2)
        with col1:
            csv = df_csv.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download Full History (CSV)", 
                data=csv, 
                file_name=f"expenses_{date.today().strftime('%Y%m%d')}.csv", 
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Export current cycle only
            cycle_df = pd.DataFrame(cycle_data, columns=["ID", "Date", "Description", "Amount", "Category"]) if cycle_data else pd.DataFrame()
            if not cycle_df.empty:
                cycle_csv = cycle_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download Current Cycle (CSV)", 
                    data=cycle_csv, 
                    file_name=f"expenses_cycle_{start_cycle.strftime('%Y%m%d')}.csv", 
                    mime="text/csv",
                    use_container_width=True
                )
        
        st.divider()
        st.markdown("#### Export Summary")
        st.write(f"Total expenses recorded: **{len(df_csv)}**")
        st.write(f"Total amount: **€{df_csv['Amount'].sum():.2f}**")
        st.write(f"Date range: **{df_csv['Date'].min()} to {df_csv['Date'].max()}**")
    else:
        st.info("No data to export.")