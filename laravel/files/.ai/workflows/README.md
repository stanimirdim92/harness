# AI Workflows

## Intake and Execution Chain

The standard workflow for Leadbuster development is: **jira-ticket** (intake only) → **/spec** → **/plan** → **/build**. The `jira-ticket` skill/command takes a Jira ticket and extracts context; it does not plan, implement, or test. The `/spec` command writes a structured specification from the ticket. The `/plan` command breaks the spec into small, verifiable tasks with acceptance criteria and dependency ordering. The `/build` command dispatches execution for the planned tasks (fresh executor subagent per task), runs review after each task, and produces a go/no-go verdict before merge. This chain is strictly sequential and hands off at each step—never implement directly from the jira-ticket step.
    
