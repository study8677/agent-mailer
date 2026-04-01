Read the `AGENT.md` file in the current working directory to get your identity:
- **Agent ID** (the UUID)
- **Address** (e.g. `coder@local`)
- **Broker URL** (e.g. `http://localhost:9800`)

Then call the inbox API to fetch your unread messages:

```
GET {broker_url}/messages/inbox/{address}?agent_id={agent_id}
```

Display the results in a clear summary:
1. Show total unread count
2. For each message, show: sender address, subject, action type (send/reply/forward), timestamp, and a brief preview of the body (first 100 chars)
3. Show the message ID and thread ID for each message so they can be referenced later

If there are no unread messages, say so clearly.

**Do NOT mark any message as read** — this is just a check. The user will decide what to act on next.
