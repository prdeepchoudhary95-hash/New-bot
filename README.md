# @sxearningbot – Earning & Referral Bot

Python 3.12 • aiogram 3.13.1 • PostgreSQL (asyncpg) • aiohttp health server • Render Web Service

## ⚠️ Pehle ye padho (honest notes)
- Ye code **maine sandbox mein likha aur syntax-check kiya**. Wahan internet/PostgreSQL nahi tha, isliye
  **bot ko Telegram par aur database ke saath end-to-end run NAHI kiya gaya**. Sirf non-DB tests (paisa, time, validation)
  chalaye gaye. DB tests (`tests/test_db_logic.py`) likhe hain par yahan run nahi hue.
  Deploy ke baad neeche wali checklist se sab features khud test karo. Koi bug mile to error log bhejna, fix kar denge.
- Bot sirf **record rakhta hai**. Paisa aapko khud UPI se bhejna hai. Bot kabhi nahi kehta "payment ho gayi" jab tak admin "Paid" na dabaye.
- Render ke plans/pricing/limits badalte rehte hain (free plan par service inactivity par so sakti hai, free database ki limit/expiry ho sakti hai).
  Render ka current pricing page khud check karo.
- Bot ko sirf **ek instance** par chalao (do jagah chalega to Telegram "Conflict" error dega).
- FSM state memory mein hai: bot restart hone par adhoora flow (jaise withdrawal amount likhna) dobara shuru karna padega. Paisa/data database mein safe rehta hai.

## Folder structure
```
sxearningbot/
├── bot.py                  # entry point (polling + health server)
├── config.py               # environment variables
├── requirements.txt
├── .python-version
├── .gitignore
├── .env.example
├── pytest.ini
├── README.md
├── db/
│   ├── __init__.py
│   ├── pool.py             # connection pool + migrations runner
│   └── schema.py           # tables, constraints, indexes
├── services/               # saari business logic (SQL yahin hai)
│   ├── __init__.py
│   ├── ledger.py           # balance ka eklauta raasta
│   ├── settings.py  users.py  referrals.py  bonus.py
│   ├── withdrawals.py  tasks.py  promos.py  leaderboard.py  admin.py
├── handlers/
│   ├── __init__.py
│   ├── filters.py          # IsAdmin (ADMIN_IDS)
│   ├── common.py  user.py  withdraw.py  tasks.py  fallback.py
│   ├── admin_core.py  admin_withdrawals.py  admin_content.py
├── utils/
│   ├── __init__.py
│   ├── middleware.py       # register, ban, force-join, referral reward
│   ├── money.py  timeutil.py  validators.py  notify.py  ui.py
└── tests/
    ├── __init__.py  conftest.py  test_pure.py  test_db_logic.py
```
**Ye saari files GitHub par upload karni hain** (`.env` file kabhi upload mat karna).

## Defaults (admin panel se badal sakte ho)
Referral reward ₹2 • Daily bonus ₹1 • Min withdrawal ₹50 • Daily reset 12:00 AM IST • Leaderboard week = Monday–Sunday IST.

## Referral kaise kaam karta hai
Naya user link se aata hai → channel join verify karta hai (force-join ON ho to) → **tab** referrer ko reward milta hai (sirf ek baar).
Self-referral, purane user ko re-refer, aur double reward database constraints se block hain.

## Step 1: Zaroori cheezein
1. **BotFather** se bot token (alag se safe rakho, kisi ko mat bhejo). Agar kabhi leak ho jaye to BotFather mein `/revoke`.
2. **Admin IDs**: Telegram par `@userinfobot` ko /start karo, apni numeric ID milegi. Har admin ki ID chahiye.
3. **Channel**: bot ko `@snnetworkop8` channel mein **Administrator** banao (warna join-check kaam nahi karega).
4. GitHub account.

## Step 2: GitHub par code upload (Android)
**Tareeka A (aasaan, files kam hon to):** GitHub website → New repository (Private rakho) → "creating a new file" → naam mein
`handlers/user.py` jaisa path likho (slash se folder ban jata hai) → code paste → Commit. Har file ke liye repeat.
**Tareeka B (behtar):** Termux install karo → `pkg install git` → ZIP extract karke `git init`, `git add .`, `git commit`, `git remote add origin ...`, `git push`.
(GitHub login ke liye Personal Access Token chahiye hota hai.)

## Step 3: Render par PostgreSQL
1. render.com → **New +** → **PostgreSQL** → name do, region chuno → Create.
2. Database ban jaye to uske page par **Internal Database URL** copy karo (ye bot ke `DATABASE_URL` mein jayega).
   (Web service aur database ka **region same** rakho, tabhi Internal URL chalega.)

## Step 4: Render par Web Service
1. **New +** → **Web Service** → apna GitHub repo connect karo.
2. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Health Check Path (Advanced):** `/health`
3. **Environment** tab mein Add Environment Variable:

| Key | Value |
|---|---|
| `BOT_TOKEN` | BotFather wala token |
| `ADMIN_IDS` | `111111111,222222222` (comma se alag) |
| `DATABASE_URL` | Internal Database URL |
| `PYTHON_VERSION` | `3.12.7` |
| `FORCE_JOIN_CHANNEL` | `@snnetworkop8` (optional, default yahi hai) |
| `FORCE_JOIN_LINK` | `https://t.me/+E2b5VIy1AAtmOGI1` (optional) |

`PORT` Render khud deta hai, daalne ki zaroorat nahi.
4. **Create Web Service** dabao. Logs mein "Bot start ho raha hai" aur "Health server ..." dikhna chahiye.
   Tables pehli baar apne aap ban jate hain.

> Free plan par service kuch der traffic na milne par so sakti hai aur bot jawab dena band kar dega. Iske liye paid plan ya
> kisi uptime-ping service se `https://<aapka-service>.onrender.com/health` ko regular ping karna padta hai (plan ke rules khud check karo).

## Tests chalana (optional, computer par)
```
pip install -r requirements.txt
pytest tests/test_pure.py                 # bina database
TEST_DATABASE_URL=postgresql://... pytest # DB tests (ye database ke tables SAAF kar deta hai, alag test DB use karo!)
```

## Security
- Token/DB URL sirf environment variables mein; logs mein print nahi hote.
- Saare SQL parameterized hain. Paisa integer paise mein.
- Admin actions sirf `ADMIN_IDS` wale numeric IDs ke liye (router filter). Sensitive actions par confirmation aata hai.
- UPI IDs database mein plain text mein hain aur sirf admins ko dikhte hain. CSV export mein formula-injection guard hai.
- Admin ke actions `admin_log` table mein likhe jate hain.

## Deploy ke baad checklist
- [ ] /start par menu aaya; channel join na karne par join prompt aaya
- [ ] Join karke "✅ Join Kar Liya" dabane par menu khula
- [ ] Doosre account se referral link kholo → join verify ke baad referrer ko ₹ aur notification mila (sirf ek baar)
- [ ] Apne hi link se khud ko refer nahi kar paaye
- [ ] Daily bonus ek baar mila, dobara "kal aana" aaya
- [ ] Balance / profile / transaction / bonus / withdraw history sahi dikh rahi hai
- [ ] Withdraw: min se kam amount reject, galat UPI reject, sahi request par balance hold hua, admin ko alert aaya
- [ ] Ek active request hote hue doosri request nahi bani
- [ ] Admin: Approve → user ko message (payment baaki likha hai); Paid mark karne par hi "Paid" gaya
- [ ] Admin: Reject → balance wapas, dobara reject nahi hua
- [ ] Task banaya → user ko dikha → photo/text proof bheja → admin approve → reward ek baar mila
- [ ] Promo: code bana, user ne lagaya, dobara nahi laga, limit/expiry kaam kari, disable/delete kaam kiya
- [ ] Leaderboard weekly/all-time dikha, naam masked hai; admin ne OFF kiya to band hua
- [ ] Admin: stats, user search, balance add/deduct (reason ke saath), ban/unban, settings badalna, toggles
- [ ] Admin: broadcast gaya, CSV export (users/transactions/withdrawals) aaya
- [ ] Kisi non-admin account se `/admin` kuch nahi khola
- [ ] Bot block karne wale user ke saath broadcast crash nahi hua
