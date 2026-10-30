## ADDED Requirements

### Requirement: Pre-run optional chat binding
The exported kit SHALL provide platform-llm-configure, platform-llm-status, platform-llm-test and platform-llm-disable Make commands that work before the serving container runs. Configuration SHALL reuse private server settings without requiring a host Python, chat provider contact or embedding startup. Provider keys SHALL travel through environment/stdin rather than printed command arguments.

#### Scenario: Configure before startup
Given no serving container is running
When an operator runs platform-llm-configure with endpoint, model and explicit context consent
Then a no-dependency one-shot container saves validated chat settings and prints only redacted configuration.

### Requirement: Optional startup chat flag
platform-start SHALL preserve saved configuration by default. LLM=1 SHALL configure/enable chat before starting services; LLM=0 SHALL disable it before starting services. Failed preconfiguration SHALL prevent startup.

#### Scenario: Explicit binding during startup
Given explicit LLM=1 and valid operator settings
When platform-start is invoked
Then configuration completes before Compose up; secrets do not appear in Make output.
