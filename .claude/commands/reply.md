Read the `AGENT.md` file in the current working directory to get your identity:
- **Agent ID** (the UUID)
- **Address** (e.g. `coder@local`)
- **Broker URL** (e.g. `http://localhost:9800`)

You are replying to a message. The user may provide:
- A message ID to reply to (if not, fetch inbox first and ask which message to reply to)
- The reply content

**Steps:**

1. If the user didn't specify which message to reply to, call the inbox API first:
   ```
   GET {broker_url}/messages/inbox/{address}?agent_id={agent_id}
   ```
   List the messages and ask the user which one to reply to.

2. Once you know the message ID, fetch the thread to understand the full context:
   ```
   GET {broker_url}/messages/thread/{thread_id}
   ```

3. Mark the original message as read:
   ```
   PATCH {broker_url}/messages/{message_id}/read
   ```

4. Send the reply:
   ```
   POST {broker_url}/messages/send
   {
     "agent_id": "{your_agent_id}",
     "from_agent": "{your_address}",
     "to_agent": "{original_sender_address}",
     "action": "reply",
     "subject": "Re: {original_subject}",
     "body": "{reply_content}",
     "parent_id": "{message_id_being_replied_to}"
   }
   ```

5. Confirm the reply was sent, showing the new message ID and thread ID.

$ARGUMENTS
