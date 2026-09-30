# Production Prompt Surface

Long-form generation is fixed to the A28/V43 production surface. The active
runtime prompt templates are seeded by Alembic into PostgreSQL
`prompt_templates`; the database is the only runtime source and can be edited
from the system configuration page.

The production surface keeps these boundaries:

- canonical facts come from `published`, `user`, `frozen`, and `accepted` sources;
- `candidate` and `generated` values remain leads that require verification;
- `unknown` values may be investigated but must not be completed as facts;
- Validator sends a chapter back to Writer only for hard fact, timeline, item,
  core-event, or handoff conflicts;
- each long-form chapter must produce one observable action, choice, cost, or
  risk change.

The public repository contains only this production contract. Local research
notes, historical prompt variants, and raw experiment runs are ignored by Git
and remain available in the local workspace for investigation.
