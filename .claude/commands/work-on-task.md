Read the `AGENT.md` file in the current working directory to get your identity:
- **Agent ID** (the UUID)
- **Address** (e.g. `coder@local`)
- **Broker URL** (e.g. `http://localhost:9800`)
- **System Prompt** (your role and behavior instructions)

This is the main work loop. You will check your inbox, pick up a task, execute it, and respond.

**Steps:**

1. **Check inbox** for unread messages:
   ```
   GET {broker_url}/messages/inbox/{address}?agent_id={agent_id}
   ```

2. If there are no unread messages, inform the user and stop.

3. If there are unread messages, display them and **ask the user which message to work on** (or work on the first one if there's only one).

4. **Read the full thread** for context:
   ```
   GET {broker_url}/messages/thread/{thread_id}
   ```

5. **Mark the message as read**:
   ```
   PATCH {broker_url}/messages/{message_id}/read
   ```

6. **Execute the task** described in the message according to your System Prompt in AGENT.md. Do the actual work (write code, review code, create plans, etc.) as your role requires.

7. After completing the task, **ask the user how to respond**:
   - **Reply** to the sender with results
   - **Forward** to the next agent in the workflow (e.g. coder -> reviewer)
   - **Skip** responding for now

8. If replying or forwarding, use the appropriate API call:
   ```
   POST {broker_url}/messages/send
   {
     "agent_id": "{your_agent_id}",
     "from_agent": "{your_address}",
     "to_agent": "{target_address}",
     "action": "reply" or "forward",
     "subject": "Re: {subject}" or "Fwd: {subject}",
     "body": "{your_response_with_work_results}",
     "parent_id": "{message_id}"
   }
   ```

9. After responding, check if there are more unread messages and ask if the user wants to continue.

$ARGUMENTS
