# Google Slides access

Voice Demo Lab reads Google Slides through the Slides API (slide text and speaker notes) and the Drive
API (a PDF export for the slide images). It needs a **Desktop app** OAuth client in a Google Cloud project
you control. It only asks for read-only scopes:

- `https://www.googleapis.com/auth/presentations.readonly`
- `https://www.googleapis.com/auth/drive.readonly`

## One-time setup

1. Pick or create a project at <https://console.cloud.google.com>.
2. Enable the two APIs:

   ```
   gcloud services enable slides.googleapis.com drive.googleapis.com --project <PROJECT_ID>
   ```

3. **Google Auth Platform → Branding**: set an app name and support email. Under **Audience**, choose
   *Internal* if the project is in a Workspace org and you only use org accounts; otherwise choose *External*
   and add yourself as a test user.
4. **Data Access → Add scopes**: add the two scopes above.
5. **Clients → Create client → Desktop app**. Download the JSON and save it outside the repo, e.g.
   `~/.demolab/client_secret.json`.
6. In Voice Demo Lab **Settings → Google Slides**, enter that path and click **Connect Google**. A browser
   tab opens for consent; the refresh token is stored in the OS keychain.

Then add a deck in a project's **Sources → Google Slides** with its URL.

## Notes

- To revoke access, click **Disconnect** in Settings, and remove the app at
  <https://myaccount.google.com/permissions> if you want it gone entirely.
- External apps in *Testing* status issue refresh tokens that expire after 7 days, so you'll need to
  reconnect weekly. Internal apps don't have this limit.
