# inbox/

Where submissions arrive, one folder each: a `generate.py`, a
`submission.json` manifest, and optionally a `memory/` folder of
free-text notes. See PLAYBOOK.md Step 6.

This directory has to exist before `toolkit.inbox.process_inbox()` runs
— it reads what is here rather than creating it, since a path it made
itself would silently process nothing when you typo'd the name. That is
why the directory ships with this file in it.

Nothing is deleted or moved from here automatically, including rejected
submissions; what to do with those is a maintainer's call.

Nothing here yet. Delete this file once real submissions replace it.
