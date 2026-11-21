import streamlit as st
import sqlite3, hashlib, secrets, os
from datetime import datetime, date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = str(BASE_DIR / "campusly.db")

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
NAVY, YELLOW, CREAM, LAVENDER = '#192653', '#FFC66B', '#FFF9F1', '#E7E5F7'
CATS = ['Books & Notes', 'University Supplies', 'Food & Drinks', 'Handmade', 'Printing', 'Services', 'Other']

st.set_page_config(page_title='Campusly', page_icon='🎓', layout='wide')

st.markdown(f'''<style>
.stApp{{background:{CREAM};color:{NAVY}}}
[data-testid="stSidebar"]{{background:{NAVY}}}
[data-testid="stSidebar"] *{{color:white!important}}
h1,h2,h3,h4{{color:{NAVY}!important}}
.stButton>button,[data-testid="stFormSubmitButton"] button{{background:{YELLOW};color:{NAVY};border:0;border-radius:14px;font-weight:700;min-height:42px}}
.stButton>button:hover,[data-testid="stFormSubmitButton"] button:hover{{background:{NAVY};color:white}}
[data-testid="stSidebar"] .stButton>button,[data-testid="stSidebar"] .stButton>button *{{color:{NAVY}!important}}
[data-testid="stSidebar"] .stButton>button:hover,[data-testid="stSidebar"] .stButton>button:hover *{{color:white!important}}
[data-testid="stVerticalBlockBorderWrapper"]{{background:white;border:1px solid #e7d9cb;border-radius:18px;padding:10px}}
[data-testid="stForm"]{{background:white;border:1px solid #e7d9cb;border-radius:16px;padding:18px}}
</style>''', unsafe_allow_html=True)

# ---------------- DB ----------------
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def cols(con, table):
    return {r[1] for r in con.execute(f'PRAGMA table_info({table})').fetchall()}

def now():
    return datetime.now().isoformat(timespec='seconds')

def init_db():
    with db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT,
            university_id TEXT DEFAULT '', created_at TEXT)''')
        uc = cols(con, 'users')
        for col, typ in [('password_hash', 'TEXT'), ('password', 'TEXT'),
                         ('university_id', "TEXT DEFAULT ''"),
                         ('user_type', "TEXT DEFAULT 'Student'"),
                         ('national_id', "TEXT DEFAULT ''"), ('created_at', 'TEXT')]:
            if col not in uc:
                con.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')

        con.execute('''CREATE TABLE IF NOT EXISTS businesses(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            name TEXT NOT NULL, category TEXT, contact TEXT, description TEXT,
            id_number TEXT, created_at TEXT)''')

        con.execute('''CREATE TABLE IF NOT EXISTS listings(
            id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL,
            title TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL,
            description TEXT, image_path TEXT, created_at TEXT)''')
        lc = cols(con, 'listings')
        for col, typ in [('business_id', 'INTEGER DEFAULT NULL'),
                         ('listing_type', "TEXT DEFAULT 'Sale'"),
                         ('deposit', 'REAL DEFAULT 0'),
                         ('min_days', 'INTEGER DEFAULT 1'),
                         ('max_days', 'INTEGER DEFAULT 30'),
                         ('terms', "TEXT DEFAULT ''")]:
            if col not in lc:
                con.execute(f'ALTER TABLE listings ADD COLUMN {col} {typ}')

        con.execute('''CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL, created_at TEXT)''')

        con.execute('''CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL, seller_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1, total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Placed', created_at TEXT)''')

        con.execute('''CREATE TABLE IF NOT EXISTS rentals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL,
            renter_id INTEGER NOT NULL, owner_id INTEGER NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            days INTEGER NOT NULL, daily_rate REAL NOT NULL,
            rent_total REAL NOT NULL, deposit REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Requested',
            withheld REAL DEFAULT 0, note TEXT DEFAULT '', created_at TEXT)''')

        con.execute('''CREATE TABLE IF NOT EXISTS offers(
            id INTEGER PRIMARY KEY AUTOINCREMENT, business_id INTEGER NOT NULL,
            title TEXT NOT NULL, description TEXT, discount TEXT, created_at TEXT)''')

        con.execute('''CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            actor_id INTEGER, title TEXT NOT NULL, body TEXT,
            kind TEXT DEFAULT 'general', listing_id INTEGER DEFAULT NULL,
            business_id INTEGER DEFAULT NULL, is_read INTEGER DEFAULT 0,
            created_at TEXT)''')

init_db()

# ---------------- helpers ----------------
def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    d = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100000).hex()
    return f'{salt}:{d}'

def verify_password(pw, stored):
    try:
        if stored and ':' in stored:
            salt, digest = stored.split(':', 1)
            return hash_password(pw, salt).split(':', 1)[1] == digest
        return stored and hashlib.sha256(pw.encode()).hexdigest() == stored
    except Exception:
        return False

def user_by_email(email):
    with db() as con:
        return con.execute('''SELECT id,name,email,password_hash,university_id,
            user_type,national_id FROM users WHERE email=?''',
                           (email.lower().strip(),)).fetchone()

def get_user(uid):
    with db() as con:
        return con.execute('''SELECT id,name,email,university_id,user_type,
            national_id FROM users WHERE id=?''', (uid,)).fetchone()

def notify(user_id, actor_id, title, body='', kind='general', listing_id=None, business_id=None):
    if not user_id or user_id == actor_id:
        return
    with db() as con:
        con.execute('''INSERT INTO notifications(user_id,actor_id,title,body,kind,
            listing_id,business_id,is_read,created_at) VALUES(?,?,?,?,?,?,?,0,?)''',
                    (user_id, actor_id, title, body, kind, listing_id, business_id, now()))

def notify_all_except(actor, title, body='', kind='general', listing_id=None, business_id=None):
    with db() as con:
        ids = [r[0] for r in con.execute('SELECT id FROM users WHERE id!=?', (actor,)).fetchall()]
    for x in ids:
        notify(x, actor, title, body, kind, listing_id, business_id)

def unread_count(uid):
    with db() as con:
        return con.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0',
                           (uid,)).fetchone()[0]

def get_notifications(uid):
    with db() as con:
        return con.execute('''SELECT id,actor_id,title,body,kind,listing_id,business_id,
            is_read,created_at FROM notifications WHERE user_id=?
            ORDER BY id DESC LIMIT 100''', (uid,)).fetchall()

def mark_notification_read(nid, uid):
    with db() as con:
        con.execute('UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?', (nid, uid))

def businesses_for_user(uid):
    with db() as con:
        return con.execute('''SELECT id,name,category,contact,description,id_number
            FROM businesses WHERE user_id=? ORDER BY id DESC''', (uid,)).fetchall()

def get_business(bid):
    with db() as con:
        return con.execute('''SELECT b.id,b.user_id,b.name,b.category,b.contact,
            b.description,u.name FROM businesses b JOIN users u ON u.id=b.user_id
            WHERE b.id=?''', (bid,)).fetchone()

def all_businesses():
    with db() as con:
        return con.execute('''SELECT b.id,b.name,b.category,b.description,b.contact,u.name
            FROM businesses b JOIN users u ON u.id=b.user_id ORDER BY b.id DESC''').fetchall()

# listing tuple:
# 0 id,1 seller_id,2 title,3 category,4 price,5 description,6 image,7 seller name,
# 8 business_id,9 business name,10 type,11 deposit,12 min_days,13 max_days,14 terms
def listings(search='', category='All', business_id=None, ltype='All'):
    with db() as con:
        q = '''SELECT l.id,l.seller_id,l.title,l.category,l.price,l.description,
            l.image_path,u.name,l.business_id,b.name,
            COALESCE(l.listing_type,'Sale'),COALESCE(l.deposit,0),
            COALESCE(l.min_days,1),COALESCE(l.max_days,30),COALESCE(l.terms,'')
            FROM listings l JOIN users u ON u.id=l.seller_id
            LEFT JOIN businesses b ON b.id=l.business_id'''
        cond, p = [], []
        if search:
            cond.append('(l.title LIKE ? OR l.description LIKE ?)')
            p += [f'%{search}%', f'%{search}%']
        if category != 'All':
            cond.append('l.category=?')
            p.append(category)
        if business_id is not None:
            cond.append('l.business_id=?')
            p.append(business_id)
        if ltype != 'All':
            cond.append("COALESCE(l.listing_type,'Sale')=?")
            p.append(ltype)
        if cond:
            q += ' WHERE ' + ' AND '.join(cond)
        q += ' ORDER BY l.id DESC'
        return con.execute(q, p).fetchall()

def get_listing(lid):
    return next((z for z in listings() if z[0] == lid), None)

def save_image(file):
    if not file:
        return ''
    path = str(UPLOAD_DIR / (secrets.token_hex(8) + '_' + os.path.basename(file.name).replace(' ', '_')))
    with open(path, 'wb') as f:
        f.write(file.getbuffer())
    return path

def save_listing(uid, title, category, price, desc, img, bid=None,
                 ltype='Sale', deposit=0.0, mind=1, maxd=30, terms=''):
    with db() as con:
        cur = con.execute('''INSERT INTO listings(seller_id,title,category,price,description,
            image_path,created_at,business_id,listing_type,deposit,min_days,max_days,terms)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                          (uid, title, category, price, desc, img, now(), bid,
                           ltype, deposit, mind, maxd, terms))
        lid = cur.lastrowid
    notify_all_except(uid, '🔑 New rental listing' if ltype == 'Rent' else '🛍️ New listing posted',
                      title, 'listing', listing_id=lid, business_id=bid)

def delete_listing(lid, uid):
    with db() as con:
        busy = con.execute('''SELECT COUNT(*) FROM rentals WHERE listing_id=?
            AND status IN ('Requested','Approved','Active')''', (lid,)).fetchone()[0]
        if busy:
            return False
        con.execute('DELETE FROM listings WHERE id=? AND seller_id=?', (lid, uid))
    return True

def place_order(lid, buyer, seller, qty, price):
    with db() as con:
        con.execute('''INSERT INTO orders(listing_id,buyer_id,seller_id,quantity,total,
            status,created_at) VALUES(?,?,?,?,?,'Placed',?)''',
                    (lid, buyer, seller, qty, qty * price, now()))
    notify(seller, buyer, '🛒 New order received',
           f'{get_user(buyer)[1]} ordered {qty} × item.', 'order', lid)

def send_msg(lid, sender, receiver, msg):
    with db() as con:
        con.execute('''INSERT INTO messages(listing_id,sender_id,receiver_id,message,
            created_at) VALUES(?,?,?,?,?)''', (lid, sender, receiver, msg, now()))
    notify(receiver, sender, '💬 New message', f'{get_user(sender)[1]}: {msg[:120]}', 'message', lid)

def conversation_messages(lid, uid, other):
    with db() as con:
        return con.execute('''SELECT id,sender_id,receiver_id,message,created_at
            FROM messages WHERE listing_id=? AND
            ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?))
            ORDER BY id''', (lid, uid, other, other, uid)).fetchall()

def conversations(uid):
    with db() as con:
        rows = con.execute('''SELECT listing_id,sender_id,receiver_id FROM messages
            WHERE sender_id=? OR receiver_id=? ORDER BY id DESC''', (uid, uid)).fetchall()
        titles = {r[0]: r[1] for r in con.execute('SELECT id,title FROM listings').fetchall()}
        seen, result = set(), []
        for lid, s, r in rows:
            other = r if s == uid else s
            if (lid, other) in seen:
                continue
            seen.add((lid, other))
            u = con.execute('SELECT name FROM users WHERE id=?', (other,)).fetchone()
            result.append((lid, other, titles.get(lid, 'Deleted listing'), u[0] if u else 'Unknown user'))
        return result

def mark_thread_notifications_read(uid, lid, other):
    with db() as con:
        con.execute('''UPDATE notifications SET is_read=1 WHERE user_id=? AND kind=?
            AND listing_id=? AND actor_id=?''', (uid, 'message', lid, other))

def buyer_orders(uid):
    with db() as con:
        return con.execute('''SELECT o.id,l.title,o.quantity,o.total,o.status,o.created_at,u.name
            FROM orders o JOIN listings l ON l.id=o.listing_id JOIN users u ON u.id=o.seller_id
            WHERE o.buyer_id=? ORDER BY o.id DESC''', (uid,)).fetchall()

def seller_orders(uid):
    with db() as con:
        return con.execute('''SELECT o.id,l.title,o.quantity,o.total,o.status,o.created_at,
            u.name,o.buyer_id FROM orders o JOIN listings l ON l.id=o.listing_id
            JOIN users u ON u.id=o.buyer_id
            WHERE o.seller_id=? ORDER BY o.id DESC''', (uid,)).fetchall()

# ---------------- rentals ----------------
def rental_conflict(lid, s, e, exclude=None):
    with db() as con:
        return con.execute('''SELECT COUNT(*) FROM rentals WHERE listing_id=?
            AND status IN ('Approved','Active') AND start_date<? AND end_date>? AND id!=?''',
                           (lid, e, s, exclude or 0)).fetchone()[0] > 0

def create_rental(x, renter, start, days):
    lid, owner, title, rate, dep = x[0], x[1], x[2], x[4], x[11]
    end = start + timedelta(days=days)
    with db() as con:
        con.execute('''INSERT INTO rentals(listing_id,renter_id,owner_id,start_date,end_date,
            days,daily_rate,rent_total,deposit,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,'Requested',?)''',
                    (lid, renter, owner, start.isoformat(), end.isoformat(), days,
                     rate, rate * days, dep, now()))
    notify(owner, renter, '🔑 New rental request',
           f'{get_user(renter)[1]} wants to rent "{title}" for {days} day(s) from {start}.',
           'rental_owner', lid)

def rentals_for(uid, role):
    me, other = ('owner_id', 'renter_id') if role == 'owner' else ('renter_id', 'owner_id')
    with db() as con:
        return con.execute(f'''SELECT r.id,r.listing_id,COALESCE(l.title,'Deleted listing'),
            u.name,r.start_date,r.end_date,r.days,r.daily_rate,r.rent_total,r.deposit,
            r.status,COALESCE(r.withheld,0),COALESCE(r.note,''),r.renter_id,r.owner_id
            FROM rentals r LEFT JOIN listings l ON l.id=r.listing_id
            JOIN users u ON u.id=r.{other}
            WHERE r.{me}=? ORDER BY r.id DESC''', (uid,)).fetchall()

def set_rental(rid, status, withheld=None, note=None):
    with db() as con:
        if withheld is None:
            con.execute('UPDATE rentals SET status=? WHERE id=?', (status, rid))
        else:
            con.execute('UPDATE rentals SET status=?,withheld=?,note=? WHERE id=?',
                        (status, withheld, note or '', rid))

def rental_card(r, role, uid):
    (rid, lid, title, other, s, e, days, rate, total, dep, status,
     withheld, note, renter, owner) = r
    icons = {'Requested': '🟡', 'Approved': '🟢', 'Active': '🔵',
             'Completed': '✅', 'Rejected': '❌', 'Cancelled': '⚪'}
    with st.container(border=True):
        st.subheader(title)
        st.caption(f'{"Renter" if role == "owner" else "Owner"}: {other} • {s} → {e} ({days} day(s))')
        st.write(f'Rent: EGP {total:,.2f} • Deposit: EGP {dep:,.2f} • '
                 f'Total at handover: EGP {total + dep:,.2f}')
        st.markdown(f'**Status:** {icons.get(status, "")} {status}')

        if status == 'Completed':
            st.write(f'Deposit withheld: EGP {withheld:,.2f} • Refunded: EGP {dep - withheld:,.2f}')
            if note:
                st.caption('Owner note: ' + note)

        if role == 'owner':
            if status == 'Requested':
                a, b = st.columns(2)
                if a.button('✅ Approve', key=f'ap_{rid}'):
                    if rental_conflict(lid, s, e, rid):
                        st.warning('These dates overlap with another approved rental.')
                    else:
                        set_rental(rid, 'Approved')
                        notify(renter, uid, '✅ Rental approved',
                               f'Your request for "{title}" was approved. Meet the owner to pick it up.',
                               'rental_renter', lid)
                        st.rerun()
                if b.button('❌ Reject', key=f'rj_{rid}'):
                    set_rental(rid, 'Rejected')
                    notify(renter, uid, '❌ Rental rejected',
                           f'Your request for "{title}" was rejected.', 'rental_renter', lid)
                    st.rerun()
            elif status == 'Approved':
                a, b = st.columns(2)
                if a.button('📦 Handed over (rent + deposit received)', key=f'ho_{rid}'):
                    set_rental(rid, 'Active')
                    notify(renter, uid, '🔵 Rental started',
                           f'"{title}" handed over. Return it by {e}.', 'rental_renter', lid)
                    st.rerun()
                if b.button('Cancel rental', key=f'oc_{rid}'):
                    set_rental(rid, 'Cancelled')
                    notify(renter, uid, '⚪ Rental cancelled',
                           f'The owner cancelled your rental of "{title}".', 'rental_renter', lid)
                    st.rerun()
            elif status == 'Active':
                late = max(0, (date.today() - date.fromisoformat(e)).days)
                suggested = min(float(dep), late * rate)
                if late:
                    st.warning(f'Late by {late} day(s). Suggested late fee: EGP {suggested:,.2f}')
                st.markdown('**Confirm return & settle deposit**')
                wh = st.number_input('Amount to withhold from deposit (damage / late fee)',
                                     0.0, float(dep), float(suggested), step=10.0, key=f'wh_{rid}')
                nt = st.text_input('Note to renter (optional)', key=f'nt_{rid}')
                if st.button('Complete rental', key=f'cp_{rid}'):
                    set_rental(rid, 'Completed', wh, nt)
                    notify(renter, uid, '✅ Rental completed',
                           f'Deposit refund for "{title}": EGP {dep - wh:,.2f}'
                           + (f' (withheld EGP {wh:,.2f})' if wh else ''),
                           'rental_renter', lid)
                    st.rerun()
        else:
            if status in ('Requested', 'Approved'):
                if st.button('Cancel my request', key=f'rc_{rid}'):
                    set_rental(rid, 'Cancelled')
                    notify(owner, uid, '⚪ Rental cancelled',
                           f'The renter cancelled the rental of "{title}".', 'rental_owner', lid)
                    st.rerun()

def rent_fields(k, typ):
    if typ != 'Rent out':
        return 0.0, 1, 30, ''
    dep = st.number_input('Security deposit (EGP)', 0.0, step=50.0, key=k + '_dep')
    c1, c2 = st.columns(2)
    mind = c1.number_input('Minimum rental days', 1, 365, 1, key=k + '_min')
    maxd = c2.number_input('Maximum rental days', 1, 365, 7, key=k + '_max')
    terms = st.text_area('Rental terms & conditions (e.g. handle with care, no sub-renting, bring ID)',
                         key=k + '_terms')
    return float(dep), int(mind), int(maxd), terms

def go(p):
    st.session_state.page = p
    st.rerun()

def listing_card(x, uid, pfx):
    lid, seller, title, cat, price, desc, img, sname, bid, bname, ltype, dep, mind, maxd, terms = x
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            if img and os.path.exists(img):
                st.image(img, use_container_width=True)
            else:
                st.write('📦')
        with c2:
            st.subheader(title)
            badge = '🔑 For Rent' if ltype == 'Rent' else '🏷️ For Sale'
            st.caption(f'{badge} • {cat} • Seller: {sname}' + (f' • {bname}' if bname else ''))
            st.write(desc or '')
            if ltype == 'Rent':
                st.markdown(f'### EGP {price:,.2f} / day')
                st.caption(f'Deposit: EGP {dep:,.2f} • Rental period: {mind}–{maxd} days')
                if terms:
                    st.info('📜 Terms: ' + terms)
            else:
                st.markdown(f'### EGP {price:,.2f}')
            if seller != uid:
                a, b = st.columns(2)
                if ltype == 'Rent':
                    if a.button('🔑 Rent now', key=f'{pfx}rent_{lid}'):
                        st.session_state.rent_listing = lid
                        go('Rent Checkout')
                else:
                    if a.button('🛒 Buy now', key=f'{pfx}buy_{lid}'):
                        st.session_state.buy_listing = lid
                        go('Checkout')
                if b.button('💬 Chat with seller', key=f'{pfx}chat_{lid}'):
                    st.session_state.chat_listing = lid
                    st.session_state.chat_other = seller
                    go('Messages')

# ---------------- auth ----------------
def auth_screen():
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(f'''
        <div style="background:{NAVY};padding:32px;border-radius:28px;min-height:440px">
        <h1 style="color:{YELLOW}!important;font-size:48px">🎓 Campusly</h1>
        <h2 style="color:white!important">Everything around your campus</h2>
        <p style="color:white;font-size:18px">Buy, sell, rent and discover student essentials,
        shops and services — all in one place.</p>
        <p style="color:{YELLOW};font-size:18px">Books • Notes • Food • Rentals • Services • Shops</p>
        </div>''', unsafe_allow_html=True)

    with right:
        st.markdown("<h2 style='text-align:center'>Welcome to Campusly</h2>", unsafe_allow_html=True)
        t1, t2 = st.tabs(["Login", "Sign Up"])

        with t1:
            with st.form("login"):
                email = st.text_input("Email")
                pw = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login", use_container_width=True)
            if submit:
                u = user_by_email(email)
                if u and verify_password(pw, u[3]):
                    if u[3] and ":" not in u[3]:
                        with db() as con:
                            con.execute("UPDATE users SET password_hash=? WHERE id=?",
                                        (hash_password(pw), u[0]))
                    st.session_state.uid = u[0]
                    st.session_state.page = "Explore"
                    st.rerun()
                else:
                    st.error("Email or password is incorrect.")

        with t2:
            typ = st.selectbox("Account type", ["Student", "Campus business / service provider"],
                               key="signup_type")
            with st.form("signup"):
                name = st.text_input("Full Name")
                email = st.text_input("Email", key="signup_email")
                pw = st.text_input("Password", type="password", key="signup_pw")
                uni, nid = "", ""
                if typ == "Student":
                    uni = st.text_input("University ID")
                else:
                    nid = st.text_input("National ID")
                submit = st.form_submit_button("Create account", use_container_width=True)
            if submit:
                ident = uni.strip() if typ == "Student" else nid.strip()
                if not name.strip() or not email.strip() or not pw or not ident:
                    st.warning("Please complete all required fields.")
                elif len(pw) < 6:
                    st.warning("Password must be at least 6 characters.")
                elif user_by_email(email):
                    st.error("This email is already registered.")
                else:
                    with db() as con:
                        con.execute('''INSERT INTO users(name,email,password_hash,university_id,
                            user_type,national_id,created_at) VALUES(?,?,?,?,?,?,?)''',
                                    (name.strip(), email.lower().strip(), hash_password(pw),
                                     uni.strip(), "Student" if typ == "Student" else "Business",
                                     nid.strip(), now()))
                    st.success("Account created! Please login.")
            st.caption("ID fields are demo fields only; identity is not verified.")

# ---------------- session ----------------
for key, default in [('uid', None), ('page', 'Explore'), ('chat_listing', None),
                     ('chat_other', None), ('store_business', None),
                     ('buy_listing', None), ('rent_listing', None)]:
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state.uid is None:
    auth_screen()

else:
    u = get_user(st.session_state.uid)
    if not u:
        st.session_state.uid = None
        st.rerun()
    uid = u[0]

    with st.sidebar:
        st.markdown(f'<div style="font-size:30px;font-weight:900;color:{YELLOW}">🎓 Campusly</div>'
                    '<div>Everything around your campus</div>', unsafe_allow_html=True)
        st.write(f"Welcome, **{u[1]}**")
        count = unread_count(uid)
        nav = ['Explore', 'Stores & Services', 'Sell an Item', 'My Business', 'My Listings',
               'My Purchases', 'Seller Orders', 'My Rentals', 'Rent Requests', 'Messages',
               f'Notifications ({count})', 'Profile']
        for p in nav:
            label = 'Notifications' if p.startswith('Notifications') else p
            if st.button(p, key='nav_' + p, use_container_width=True):
                st.session_state.page = label
                st.session_state.chat_listing = None
                st.rerun()
        if st.button('Logout', use_container_width=True):
            st.session_state.uid = None
            st.rerun()

    page = st.session_state.page
    st.title('🛍️ Explore Campus' if page == 'Explore' else page)

    # ---- Explore ----
    if page == 'Explore':
        search = st.text_input('🔎 Search products, shops or services')
        c1, c2 = st.columns(2)
        cat = c1.selectbox('Category', ['All'] + CATS)
        kind = c2.selectbox('Type', ['All', 'For Sale', 'For Rent'])
        data = listings(search, cat, ltype={'All': 'All', 'For Sale': 'Sale', 'For Rent': 'Rent'}[kind])
        if not data:
            st.info('No listings found yet. Be the first to post!')
        for x in data:
            listing_card(x, uid, 'ex_')

    # ---- Stores directory ----
    elif page == 'Stores & Services':
        bs = all_businesses()
        if not bs:
            st.info('No registered businesses yet.')
        for bid, name, cat, desc, contact, owner in bs:
            with st.container(border=True):
                st.subheader('🏪 ' + name)
                st.caption(f'{cat or "Business"} • {owner}')
                st.write(desc or '')
                st.write(contact or '')
            if st.button('Open store', key=f'open_{bid}'):
                st.session_state.store_business = bid
                go('Storefront')

    # ---- Storefront ----
    elif page == 'Storefront':
        b = get_business(st.session_state.store_business) if st.session_state.store_business else None
        if not b:
            st.info('Choose a store from Stores & Services.')
        else:
            bid, ownerid, name, cat, contact, desc, owner = b
            st.subheader('🏪 ' + name)
            st.caption(f'{cat or "Business"} • {owner}')
            st.write(desc or '')
            st.write(contact or '')

            st.markdown('## 🎉 Special Offers')
            with db() as con:
                store_offers = con.execute('''SELECT title,description,discount FROM offers
                    WHERE business_id=? ORDER BY id DESC''', (bid,)).fetchall()
            if not store_offers:
                st.caption('No active offers at the moment.')
            for otitle, odesc, discount in store_offers:
                with st.container(border=True):
                    st.markdown(f'### 🎉 {otitle}')
                    st.markdown(f'**{discount}**' if discount else '')
                    st.write(odesc or '')

            st.markdown('## 🛍️ Products & Rentals')
            for x in listings(business_id=bid):
                listing_card(x, uid, 'sf_')

    # ---- Buy checkout ----
    elif page == 'Checkout':
        lid = st.session_state.get('buy_listing')
        x = get_listing(lid) if lid else None
        if not x:
            st.warning('Choose an item from Explore first.')
        else:
            seller, title, price, sname = x[1], x[2], x[4], x[7]
            st.subheader('Order confirmation')
            st.write('Item:', title)
            st.write('Seller:', sname)
            st.write('Price:', f'EGP {price:,.2f}')
            qty = st.number_input('Quantity', 1, 99, 1)
            st.info('Demo checkout: records an order but does not collect payment.')
            if seller == uid:
                st.warning('You cannot buy your own listing.')
            elif st.button('Confirm order'):
                place_order(lid, uid, seller, qty, price)
                st.success('Order placed!')
                go('My Purchases')

    # ---- Rent checkout ----
    elif page == 'Rent Checkout':
        lid = st.session_state.get('rent_listing')
        x = get_listing(lid) if lid else None
        if not x or x[10] != 'Rent':
            st.warning('Choose a rental item from Explore first.')
        else:
            seller, title, price, sname = x[1], x[2], x[4], x[7]
            dep, mind, maxd, terms = x[11], x[12], x[13], x[14]
            st.subheader('Rental request')
            st.write('Item:', title)
            st.write('Owner:', sname)
            st.write(f'Rate: EGP {price:,.2f} / day • Deposit: EGP {dep:,.2f}')
            if terms:
                st.info('📜 Owner terms: ' + terms)

            start = st.date_input('Pick-up date', min_value=date.today(), value=date.today())
            days = st.number_input('Number of days', int(mind), int(maxd), int(mind))
            end = start + timedelta(days=int(days))
            rent_total = price * days
            st.markdown(f'**Return by:** {end}')
            c1, c2, c3 = st.columns(3)
            c1.metric('Rent', f'EGP {rent_total:,.2f}')
            c2.metric('Deposit (refundable)', f'EGP {dep:,.2f}')
            c3.metric('Total at handover', f'EGP {rent_total + dep:,.2f}')

            st.markdown('#### Rental conditions')
            a1 = st.checkbox('I accept the owner\'s terms above.')
            a2 = st.checkbox(f'I will return the item by {end}. Late returns cost EGP {price:,.2f} per extra day, deducted from my deposit.')
            a3 = st.checkbox('I am responsible for damage or loss. The owner may deduct repair or replacement cost from my deposit.')
            a4 = st.checkbox('The deposit is refunded after the owner confirms the item was returned in good condition.')
            st.info('Demo only: no payment is collected here. Rent and deposit are settled with the owner at handover.')

            if seller == uid:
                st.warning('You cannot rent your own listing.')
            elif st.button('Send rental request', disabled=not (a1 and a2 and a3 and a4)):
                if rental_conflict(lid, start.isoformat(), end.isoformat()):
                    st.error('These dates are already booked. Please choose different dates.')
                else:
                    create_rental(x, uid, start, int(days))
                    st.success('Request sent! The owner will review it.')
                    go('My Rentals')

    # ---- Sell / Rent out ----
    elif page == 'Sell an Item':
        bs = businesses_for_user(uid)
        opts = [(None, 'Personal listing')] + [(b[0], b[1]) for b in bs]
        labels = [z[1] for z in opts]
        typ = st.radio('What do you want to do?', ['Sell', 'Rent out'], horizontal=True, key='sell_type')

        with st.form('post'):
            title = st.text_input('Listing title')
            cat = st.selectbox('Category', CATS)
            price = st.number_input('Price (EGP)' if typ == 'Sell' else 'Rental price per day (EGP)',
                                    0.0, step=10.0)
            dep, mind, maxd, terms = rent_fields('sell', typ)
            desc = st.text_area('Description')
            img = st.file_uploader('Product photo', type=['png', 'jpg', 'jpeg'])
            under = st.selectbox('Publish under', labels)
            submit = st.form_submit_button('Publish listing')

        if submit:
            if not title.strip():
                st.error('Add a title.')
            elif typ == 'Rent out' and maxd < mind:
                st.error('Maximum days must be at least the minimum days.')
            else:
                save_listing(uid, title.strip(), cat, price, desc, save_image(img),
                             opts[labels.index(under)][0],
                             'Rent' if typ == 'Rent out' else 'Sale', dep, mind, maxd, terms)
                st.success('Listing published!')
                go('My Listings')

    # ---- My Business ----
    elif page == 'My Business':
        bs = businesses_for_user(uid)
        if not bs:
            st.info('Create your business to start managing your store.')

        with st.expander('➕ Create a new business', expanded=not bool(bs)):
            with st.form('business_form'):
                bname = st.text_input('Business / Store name')
                bcat = st.selectbox('Business category', ['Restaurant / Cafe', 'Bookstore', 'Printing',
                                                          'Photography', 'Handmade', 'Services', 'Other'])
                contact = st.text_input('Contact information')
                desc = st.text_area('About your business')
                nid = st.text_input('National ID')
                create = st.form_submit_button('Create My Store')
            if create:
                if not bname.strip() or not nid.strip():
                    st.warning('Business name and National ID are required.')
                else:
                    with db() as con:
                        con.execute('''INSERT INTO businesses(user_id,name,category,contact,
                            description,id_number,created_at) VALUES(?,?,?,?,?,?,?)''',
                                    (uid, bname.strip(), bcat, contact, desc, nid.strip(), now()))
                    st.success('Business created!')
                    st.rerun()

        for business in businesses_for_user(uid):
            bid, bname, bcat, contact, bdesc, idnum = business
            st.divider()
            st.markdown(f'## 🏪 {bname}')
            st.caption(bcat)
            st.write(bdesc or '')
            st.write(contact or '')
            products = listings(business_id=bid)

            with db() as con:
                offers = con.execute('''SELECT id,title,description,discount,created_at
                    FROM offers WHERE business_id=? ORDER BY id DESC''', (bid,)).fetchall()
                orders = con.execute('''SELECT COUNT(*) FROM orders o JOIN listings l
                    ON l.id=o.listing_id WHERE l.business_id=?''', (bid,)).fetchone()[0]
                rents = con.execute('''SELECT COUNT(*) FROM rentals r JOIN listings l
                    ON l.id=r.listing_id WHERE l.business_id=?''', (bid,)).fetchone()[0]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric('Products', len(products))
            c2.metric('Offers', len(offers))
            c3.metric('Orders', orders)
            c4.metric('Rentals', rents)

            if st.button('👀 View My Store', key=f'preview_{bid}'):
                st.session_state.store_business = bid
                go('Storefront')

            with st.expander('➕ Add a Product / Rental item'):
                ptype = st.radio('Type', ['Sell', 'Rent out'], horizontal=True, key=f'ptype_{bid}')
                with st.form(f'product_form_{bid}'):
                    pname = st.text_input('Product name', key=f'pname_{bid}')
                    pcat = st.selectbox('Category', CATS, key=f'pcat_{bid}')
                    pprice = st.number_input('Price (EGP)' if ptype == 'Sell' else 'Rental price per day (EGP)',
                                             min_value=0.0, step=10.0, key=f'price_{bid}')
                    pdep, pmin, pmax, pterms = rent_fields(f'biz{bid}', ptype)
                    pdesc = st.text_area('Product description', key=f'desc_{bid}')
                    pic = st.file_uploader('Product photo', type=['png', 'jpg', 'jpeg'], key=f'pic_{bid}')
                    post = st.form_submit_button('Publish')
                if post:
                    if not pname.strip():
                        st.warning('Enter a product name.')
                    elif ptype == 'Rent out' and pmax < pmin:
                        st.warning('Maximum days must be at least the minimum days.')
                    else:
                        save_listing(uid, pname.strip(), pcat, pprice, pdesc, save_image(pic), bid,
                                     'Rent' if ptype == 'Rent out' else 'Sale', pdep, pmin, pmax, pterms)
                        st.success('Published!')
                        st.rerun()

            with st.expander('🎉 Create an Offer'):
                with st.form(f'offer_form_{bid}'):
                    offer_title = st.text_input('Offer title', key=f'otitle_{bid}')
                    discount = st.text_input('Discount / Offer', placeholder='20% OFF or Buy 1 Get 1',
                                             key=f'discount_{bid}')
                    offer_desc = st.text_area('Offer details', key=f'odesc_{bid}')
                    post_offer = st.form_submit_button('Publish Offer')
                if post_offer:
                    if not offer_title.strip():
                        st.warning('Enter an offer title.')
                    else:
                        with db() as con:
                            con.execute('''INSERT INTO offers(business_id,title,description,discount,
                                created_at) VALUES(?,?,?,?,?)''',
                                        (bid, offer_title.strip(), offer_desc, discount, now()))
                        notify_all_except(uid, '🎉 New store offer', offer_title, 'offer', business_id=bid)
                        st.success('Offer published!')
                        st.rerun()

            st.markdown('### 📦 My Products')
            if not products:
                st.info('No products yet.')
            for p in products:
                lid, title, category, price, desc, img, ltype = p[0], p[2], p[3], p[4], p[5], p[6], p[10]
                with st.container(border=True):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        if img and os.path.exists(img):
                            st.image(img, use_container_width=True)
                    with c2:
                        st.subheader(title)
                        st.caption(('🔑 For Rent • ' if ltype == 'Rent' else '🏷️ For Sale • ') + category)
                        st.write(desc or '')
                        st.markdown(f'**EGP {price:,.2f}' + (' / day**' if ltype == 'Rent' else '**'))
                    if st.button('Delete Product', key=f'bizdelete_{lid}'):
                        if delete_listing(lid, uid):
                            st.rerun()
                        else:
                            st.warning('This item has active rental requests. Finish or cancel them first.')

            st.markdown('### 🎉 My Offers')
            if not offers:
                st.info('No offers published yet.')
            for oid, otitle, odesc, discount, created in offers:
                with st.container(border=True):
                    st.subheader(otitle)
                    st.markdown(f'### 🟡 {discount}' if discount else '')
                    st.write(odesc or '')
                if st.button('Delete Offer', key=f'offerdelete_{oid}'):
                    with db() as con:
                        con.execute('''DELETE FROM offers WHERE id=? AND business_id IN
                            (SELECT id FROM businesses WHERE user_id=?)''', (oid, uid))
                    st.rerun()

    # ---- My Listings ----
    elif page == 'My Listings':
        mine = [x for x in listings() if x[1] == uid]
        if not mine:
            st.info('No listings yet.')
        for x in mine:
            lid, title, cat, price, desc, img, ltype = x[0], x[2], x[3], x[4], x[5], x[6], x[10]
            with st.container(border=True):
                c1, c2 = st.columns([1, 2])
                with c1:
                    if img and os.path.exists(img):
                        st.image(img, use_container_width=True)
                with c2:
                    st.subheader(title)
                    st.caption(('🔑 For Rent • ' if ltype == 'Rent' else '🏷️ For Sale • ') + cat)
                    st.markdown(f'**EGP {price:,.2f}' + (' / day**' if ltype == 'Rent' else '**'))
                    if ltype == 'Rent':
                        st.caption(f'Deposit: EGP {x[11]:,.2f} • {x[12]}–{x[13]} days')
                    st.write(desc or '')
                if st.button('Delete listing', key=f'del_{lid}'):
                    if delete_listing(lid, uid):
                        st.rerun()
                    else:
                        st.warning('This item has active rental requests. Finish or cancel them first.')

    # ---- My Purchases ----
    elif page == 'My Purchases':
        data = buyer_orders(uid)
        if not data:
            st.info('You have not placed any orders yet.')
        for oid, title, qty, total, status, created, seller in data:
            with st.container(border=True):
                st.subheader(title)
                st.write(f'Seller: {seller} • Quantity: {qty} • Total: EGP {total:,.2f}')
                st.caption(f'Status: {status} • {created}')

    # ---- Seller Orders ----
    elif page == 'Seller Orders':
        data = seller_orders(uid)
        if not data:
            st.info('No orders received yet.')
        for oid, title, qty, total, status, created, buyer, buyer_id in data:
            with st.container(border=True):
                st.subheader(title)
                st.write(f'Buyer: {buyer} • Quantity: {qty} • Total: EGP {total:,.2f}')
                st.caption(f'Status: {status} • {created}')
                options = ['Placed', 'Accepted', 'Ready', 'Completed', 'Cancelled']
                sel = st.selectbox('Update status', options,
                                   index=options.index(status) if status in options else 0,
                                   key=f'status_{oid}')
            if st.button('Save status', key=f'save_{oid}'):
                with db() as con:
                    con.execute('UPDATE orders SET status=? WHERE id=? AND seller_id=?', (sel, oid, uid))
                notify(buyer_id, uid, '📦 Order update',
                       f'Your order "{title}" is now: {sel}', 'order_update')
                st.rerun()

    # ---- My Rentals (as renter) ----
    elif page == 'My Rentals':
        data = rentals_for(uid, 'renter')
        if not data:
            st.info('You have not rented anything yet. Look for 🔑 For Rent items in Explore.')
        for r in data:
            rental_card(r, 'renter', uid)

    # ---- Rent Requests (as owner) ----
    elif page == 'Rent Requests':
        data = rentals_for(uid, 'owner')
        if not data:
            st.info('No rental requests for your items yet.')
        for r in data:
            rental_card(r, 'owner', uid)

    # ---- Messages ----
    elif page == 'Messages':
        if st.session_state.chat_listing is None:
            data = conversations(uid)
            if not data:
                st.info('No messages yet. Start a chat from a listing.')
            for lid, other, title, name in data:
                if st.button(f'{title} — {name}', key=f'thread_{lid}_{other}'):
                    st.session_state.chat_listing = lid
                    st.session_state.chat_other = other
                    st.rerun()
        else:
            lid = st.session_state.chat_listing
            other = st.session_state.chat_other
            with db() as con:
                item = con.execute('SELECT title,seller_id FROM listings WHERE id=?', (lid,)).fetchone()
            if item:
                st.subheader('Chat about: ' + item[0])
                mark_thread_notifications_read(uid, lid, other)
                for mid, sender, receiver, m, created in conversation_messages(lid, uid, other):
                    st.chat_message('user' if sender == uid else 'assistant').write(m)
                    st.caption(created)
                msg = st.chat_input('Write a message')
                if msg and msg.strip():
                    send_msg(lid, uid, other, msg.strip())
                    st.rerun()
            else:
                st.warning('This listing may have been deleted. Messages are still stored.')
            if st.button('Back to messages'):
                st.session_state.chat_listing = None
                st.session_state.chat_other = None
                st.rerun()

    # ---- Notifications ----
    elif page == 'Notifications':
        data = get_notifications(uid)
        if not data:
            st.info('No notifications yet.')
        NOTIF_PAGE = {'rental_owner': 'Rent Requests', 'rental_renter': 'My Rentals',
                      'order_update': 'My Purchases', 'order': 'Seller Orders',
                      'listing': 'Explore'}
        for nid, actor, title, body, kind, lid, bid, read, created in data:
            with st.container(border=True):
                st.markdown(('🔵 ' if not read else '') + title)
                st.write(body or '')
                st.caption(created)
                if not read and st.button('Mark read', key=f'read_{nid}'):
                    mark_notification_read(nid, uid)
                    st.rerun()

                target = None
                if kind == 'message' and lid:
                    target = 'Messages'
                elif kind in NOTIF_PAGE:
                    target = NOTIF_PAGE[kind]
                elif bid:
                    target = 'Storefront'

                if target and st.button('Open', key=f'open_notif_{nid}'):
                    if target == 'Messages':
                        st.session_state.chat_listing = lid
                        st.session_state.chat_other = actor
                    if target == 'Storefront':
                        st.session_state.store_business = bid
                    mark_notification_read(nid, uid)
                    go(target)

        if st.button('Mark all notifications read'):
            with db() as con:
                con.execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (uid,))
            st.rerun()

    # ---- Profile ----
    elif page == 'Profile':
        st.write('**Name:**', u[1])
        st.write('**Email:**', u[2])
        st.write('**Account type:**', u[4])
        st.write('**University ID:**', u[3] if u[4] == 'Student' else 'Not applicable')
        st.write('**National ID:**', u[5] if u[4] != 'Student' else 'Not applicable')
        st.caption('IDs are prototype fields and not verified.')
