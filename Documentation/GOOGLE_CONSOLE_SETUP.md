# Google Console Setup Guide

This guide walks you through configuring a Google Cloud project and OAuth 2.0 credentials for the Email Assistant MCP server. Follow these steps to set up Gmail API access and prevent your credentials from expiring.

## Table of Contents

1. [Create a Google Cloud Project](#1-create-a-google-cloud-project)
2. [Enable the Gmail API](#2-enable-the-gmail-api)
3. [Configure OAuth Consent Screen](#3-configure-oauth-consent-screen)
4. [Create OAuth 2.0 Credentials](#4-create-oauth-20-credentials)
5. [Add Test Users (CRITICAL)](#5-add-test-users-critical)
6. [Download and Use Credentials](#6-download-and-use-credentials)
7. [Troubleshooting](#troubleshooting)

---

## 1. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** dropdown at the top of the page
3. Click **NEW PROJECT**
4. Enter a project name (e.g., "Email Assistant MCP")
5. Leave organization blank (unless you have a specific org)
6. Click **CREATE**
7. Wait for the project to be created, then select it from the project dropdown

## 2. Enable the Gmail API

1. With your project selected, navigate to **APIs & Services > Library**
   - Or use this direct link: https://console.cloud.google.com/apis/library
2. Search for "Gmail API"
3. Click on **Gmail API** from the results
4. Click **ENABLE**
5. Wait for the API to be enabled (usually takes a few seconds)

## 3. Configure OAuth Consent Screen

The OAuth consent screen is what users see when authenticating your application.

### 3.1 Create Consent Screen

1. Navigate to **APIs & Services > OAuth consent screen**
   - Or use: https://console.cloud.google.com/apis/credentials/consent
2. Select **External** user type (unless you have a Google Workspace organization)
3. Click **CREATE**

### 3.2 Fill Out App Information

**App information:**
- **App name:** Email Assistant MCP (or your preferred name)
- **User support email:** Your email address
- **App logo:** (optional) Upload a logo if desired

**App domain (optional):**
- Leave blank for personal use

**Authorized domains:**
- Leave blank for personal use

**Developer contact information:**
- **Email addresses:** Your email address

4. Click **SAVE AND CONTINUE**

### 3.3 Configure Scopes

1. Click **ADD OR REMOVE SCOPES**
2. Filter or search for Gmail scopes and select:
   - `https://www.googleapis.com/auth/gmail.modify` - Read, compose, send, and permanently delete mail
   - `https://www.googleapis.com/auth/gmail.labels` - Manage mailbox labels

   **Note:** You can select more restrictive scopes if you only need specific functionality:
   - `gmail.readonly` - Read-only access
   - `gmail.compose` - Create drafts and send emails
   - `gmail.send` - Send email only

3. Click **UPDATE**
4. Click **SAVE AND CONTINUE**

### 3.4 Test Users (Optional for Now)

Skip this for now - we'll add test users in Step 5 after creating credentials.

5. Click **SAVE AND CONTINUE**

### 3.5 Summary

Review your settings and click **BACK TO DASHBOARD**

## 4. Create OAuth 2.0 Credentials

1. Navigate to **APIs & Services > Credentials**
   - Or use: https://console.cloud.google.com/apis/credentials
2. Click **+ CREATE CREDENTIALS** at the top
3. Select **OAuth client ID**
4. If prompted to configure the consent screen, go back to Step 3

### 4.1 Configure OAuth Client

1. **Application type:** Select **Desktop app**
   - This is critical - do NOT select "Web application"
2. **Name:** Email Assistant MCP Desktop (or your preferred name)
3. Click **CREATE**

### 4.2 Save Your Credentials

A dialog will appear with your client ID and client secret.

1. Click **DOWNLOAD JSON** to save the credentials file
2. **IMPORTANT:** Keep this file secure - it contains your client secret
3. Click **OK** to close the dialog

The downloaded file will be named something like `client_secret_XXXXX.apps.googleusercontent.com.json`

## 5. Add Test Users (CRITICAL)

**This step prevents your OAuth tokens from expiring after 7 days.**

When your OAuth app is in "Testing" mode (the default), refresh tokens expire after 7 days UNLESS the user is explicitly added as a test user. Follow these steps to add yourself (and anyone else who will use this app) as test users.

### 5.1 Navigate to OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Scroll down to the **Test users** section

### 5.2 Add Test Users

1. Click **+ ADD USERS**
2. Enter the Gmail address(es) that will use this application
   - **IMPORTANT:** This MUST be the exact email address you'll authenticate with
   - Add your primary Gmail account
   - Add any other Google accounts that will use this MCP server
3. Click **SAVE**

### 5.3 Verify Test Users

You should now see your email address listed under **Test users** on the OAuth consent screen.

**Test users have:**
- ✅ No 7-day token expiration
- ✅ Refresh tokens that work indefinitely
- ✅ Full access to the scopes you've configured

**Publishing vs. Testing Mode:**
- **Testing mode** (current): Only test users can authenticate. Tokens don't expire for test users.
- **Published mode**: Anyone can authenticate, but requires Google verification for sensitive scopes (like Gmail)
- **Recommendation for personal use:** Stay in Testing mode and add yourself as a test user

## 6. Download and Use Credentials

### 6.1 Extract Client ID and Secret

Open the downloaded JSON file. It will look like this:

```json
{
  "installed": {
    "client_id": "123456789-abcdefg.apps.googleusercontent.com",
    "project_id": "email-assistant-mcp-12345",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "GOCSPX-aBcDeFgHiJkLmNoPqRsTuVwXyZ",
    "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]
  }
}
```

You'll need the `client_id` and `client_secret` values.

### 6.2 Configure Email Assistant

Run the configuration CLI tool:

```bash
uv run email-assistant-config add-gmail personal-gmail
```

When prompted, provide:
1. **Client ID:** Paste the value from the JSON file
2. **Client Secret:** Paste the value from the JSON file
3. **Email address:** Your Gmail address (must match a test user from Step 5)

### 6.3 Complete OAuth Flow

1. The CLI will open a browser window to Google's OAuth consent screen
2. Sign in with your Google account (must be a test user from Step 5)
3. You'll see a warning "Google hasn't verified this app" - click **Continue**
4. Review the permissions and click **Allow**
5. The browser will show "The authentication flow has completed"
6. Return to your terminal - the CLI will confirm the setup is complete

Your credentials are now stored in `~/.email_assistant_mcp/configs.json`

### 6.4 Test Your Configuration

Start the MCP server:

```bash
uv run email-assistant-mcp --transport stdio
```

The server should start without errors. Your Gmail account is now accessible via the MCP tools.

## Troubleshooting

### "Refresh token expired" after 7 days

**Cause:** You authenticated with an account that isn't added as a test user.

**Solution:**
1. Go to OAuth consent screen in Google Cloud Console
2. Add your Gmail address as a test user (Step 5)
3. Re-run the configuration: `uv run email-assistant-config add-gmail personal-gmail`
4. Complete the OAuth flow again

### "Access blocked: This app's request is invalid"

**Cause:** OAuth client is configured as "Web application" instead of "Desktop app"

**Solution:**
1. Delete the existing OAuth client in Google Cloud Console
2. Create a new OAuth client with type "Desktop app" (Step 4)
3. Download the new credentials and reconfigure

### "The OAuth client was not found"

**Cause:** Wrong project selected or credentials deleted

**Solution:**
1. Verify you're in the correct Google Cloud project
2. Check that the OAuth client exists in **APIs & Services > Credentials**
3. If missing, recreate the OAuth client (Step 4)

### "Access denied: email_assistant_mcp has not completed the Google verification process"

**Cause:** You're trying to use a non-test user account with an unverified app

**Solution:**
1. Add the account as a test user (Step 5)
2. OR publish your app (requires Google verification for Gmail scopes - time consuming)

### Tokens still expiring

**Check these items:**
1. Verify the account is listed under **Test users** in OAuth consent screen
2. Confirm you're authenticating with the exact email address listed as a test user
3. Make sure the OAuth client type is "Desktop app" not "Web application"

## Security Best Practices

1. **Keep `client_secret` secure** - Don't commit the JSON file to version control
2. **Add `.email_assistant_mcp/` to `.gitignore`** - Prevents credential leaks
3. **Use separate projects for development/production** - If you later want to publish
4. **Regularly review OAuth scopes** - Only request the minimum scopes needed
5. **Monitor API usage** - Check the Google Cloud Console for unexpected activity

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Gmail API Reference](https://developers.google.com/gmail/api/reference/rest)
- [OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [OAuth Consent Screen Configuration](https://support.google.com/cloud/answer/10311615)

---

**Need help?** Open an issue on the GitHub repository with details about which step you're stuck on.
