Read the `AGENT.md` file in the current working directory to get your identity:
- **Agent ID** (the UUID)
- **Address** (e.g. `coder@local`)
- **Broker URL** (e.g. `http://localhost:9800`)

You are sending a new message to another agent. The user may provide:
- A target agent name or address
- Subject and body content

**Steps:**

1. If the user didn't specify a target agent, list available agents:
   ```
   GET {broker_url}/agents
   ```
   Show the agent list (name, address, role) and ask who to send to.

2. If the user didn't provide subject or body, ask them what the message is about.

3. Send the message:
   ```
   POST {broker_url}/messages/send
   {
     "agent_id": "{your_agent_id}",
     "from_agent": "{your_address}",
     "to_agent": "{target_agent_address}",
     "action": "send",
     "subject": "{subject}",
     "body": "{body}"
   }
   ```

4. Confirm the message was sent, showing the new message ID and thread ID.

$ARGUMENTS
