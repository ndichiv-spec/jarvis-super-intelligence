"""External system connectors (admin-managed integrations for the AI).

Ordered by least trust: every connector is disabled by default until an admin
creates and tests it via the Connections API.  The AI may only ever perform
actions listed in a connector's capability set, and every action is audited
(jarvis_data/audit/connectors.jsonl).
"""