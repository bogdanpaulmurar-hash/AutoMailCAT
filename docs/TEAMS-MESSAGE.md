# The daily message in Teams

After **Confirm the day** or **Regenerate**, AutoMailCAT can post the message "Distribuirea mailurilor pentru ziua dd.mm.yyyy" (or "Mail distribution for …" when the team language is English). Choose how under **Team → Daily message in Teams → How it is sent**.

| Option | You need | In Teams |
|---|---|---|
| Teams Workflow (recommended) | a Workflow created once in Teams | a card with a title and sections |
| E-mail to the channel | the channel's e-mail address | a post with the mail subject |
| I copy it myself | nothing | press "Copy the message" and paste it |

## Option 1: Teams Workflow

No premium licence is needed. Someone in the team (usually the team leader) creates it once.

1. In Teams open **Workflows** (left bar or "⋯ More apps"), or from the channel's "⋯" menu → *Workflows*.
2. Search the template **Send webhook alerts to a channel** (for a group chat: **Send webhook alerts to a chat**).
3. Name it, e.g. "AutoMailCAT – Team X", and confirm the account it connects with.
4. Choose the **team** and **channel** (or the chat), then **Save** / **Add workflow**.
5. Teams shows a long address starting with `https://`. Press **Copy**.
6. In AutoMailCAT: **Team → How it is sent → Teams Workflow (webhook)**, paste it into **Workflow address**, **Save**.

Test: on **Today**, after confirming, press **Send the message**.

Good to know:
- The message is posted on behalf of the person who created the Workflow. If that person leaves, someone else recreates it and the new address goes into AutoMailCAT.
- Anyone who has the Workflow address can post to the channel. Keep it in the AutoMailCAT settings only.
- If a private channel is not listed, use a standard channel or a group chat.
- If Workflows is missing in Teams, IT blocked it: use option 2 or 3.

## Option 2: e-mail to the channel address

1. In Teams, on the channel: **⋯ → Get email address → Copy**.
2. Under **Advanced settings** you choose who may send; "Only members of this team" is enough when the PC running the engine uses a team member's account.
3. In AutoMailCAT: **Team → How it is sent → E-mail to the channel address**, paste, **Save**.

The mail is sent from the Outlook of the PC running the engine, so the engine must be running when the day is confirmed. If "Get email address" is missing, IT turned it off: use option 1 or 3.

## Option 3: manual copy

The default. After confirming, press **Copy the message** on **Today** and paste it into the team's channel or chat.
