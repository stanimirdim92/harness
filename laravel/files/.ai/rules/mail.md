---
paths:
    - 'Modules/*/app/Mail/*.php'
---

# Mail

## Choose the mail base class by who supplies the message

Extend `BaseEmail` when the caller supplies the subject and email data and the class selects the template. Extend Laravel’s `Mailable` directly when the class owns its typed payload, builds its envelope, or generates attachments.
