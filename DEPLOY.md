# Sharing FinSight with testers (Streamlit Community Cloud)

This puts FinSight on a free web address so friends can test it in their browser. Nothing changes when you run it on your own computer.

## What testers get, and the trade-offs

- A web link and a password. No installation.
- **One shared API quota.** Every tester uses your Gemini key. With `gemini-3.5-flash-lite` that is roughly 40 reports a day for the whole group.
- **Shared, temporary saved runs.** Every tester sees every saved run, and all of them are deleted whenever the app restarts or goes to sleep. Testers should download their report before leaving.
- **Public reports only.** Page text is sent to Google's Gemini API, whose free tier may use it to improve models.
- The app sleeps after a period without visitors; the first visit afterwards takes about a minute to wake it.

## Step 1: put the code on GitHub (private)

Your code must be in a GitHub repository. A **private** repository is fine.

If Claude has not already done this for you, run these in the project folder (replace the name if you like):

```bash
gh repo create finsight-fyp --private --source=. --push
```

Your API key is **not** uploaded: `.env` and `.streamlit/secrets.toml` are listed in `.gitignore`.

## Step 2: create the app

1. Go to **share.streamlit.io** and sign in with your GitHub account.
2. Click **Create app** → **Deploy a public app from GitHub** (the *app* is reachable by link; your *code* stays private).
3. Choose:
   - **Repository:** `finsight-fyp`
   - **Branch:** `master`
   - **Main file path:** `app.py`
   - **App URL:** pick something short, e.g. `finsight-fyp`
4. Open **Advanced settings**:
   - **Python version:** 3.12
   - **Secrets:** paste the block below, replacing the two placeholders.

```toml
AI_PROVIDER = "gemini"
GEMINI_API_KEY = "paste-your-gemini-key-here"
GEMINI_MODEL = "gemini-3.5-flash-lite"
AI_RESPONSE_FORMAT = "json_schema"
APP_PASSWORD = "choose-a-password-for-testers"
FINSIGHT_SHARED_DEPLOYMENT = "true"
```

5. Click **Deploy**. The first build takes a few minutes.

## Step 3: share it

Send testers the link and the password separately. Tell them: public annual reports only, and download the report before closing the tab.

## Managing the app

- **Update it:** commit and push changes (`git push`); the app redeploys automatically.
- **Change the password or key:** app menu (⋮) → **Settings** → **Secrets**, then save.
- **See errors:** app menu → **Manage app** shows the logs.
- **Stop sharing:** app menu → **Settings** → **Delete app**. The GitHub repository is unaffected.

## Using testers for your thesis data

Testers can produce the evidence the FYP still needs: the conventional-analyst baseline and genuine human verification.

1. Give each tester one report from the evaluation set (`data/` on your computer) and its expected values (`PROGRESS.md` results or the saved run).
2. **Manual round:** with a stopwatch running, the tester fills the 27 fields from the PDF into a spreadsheet and calculates current ratio, debt to equity, ROE and revenue growth. Record the time and compare each value with the answer key.
3. **FinSight round:** on a *different* report, the tester uses FinSight end to end, checking every row in Human verification against the PDF. The Evaluation screen records the times and corrections.
4. Swap the order for half of the testers, so learning effects cancel out.
5. Ask each tester three questions afterwards: how confident they were in the numbers, which step was hardest, and whether the source links helped them check values.
